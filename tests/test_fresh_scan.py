"""
A fresh scan: back up, delete every scanned job post, scan from nothing.
It asks for the count it will delete and refuses if that count moved.
No network: the scan itself is replaced.

    python tests/test_fresh_scan.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork import cli
from jobdork.core.config import Config
from jobdork.db.store import Role, Store
from jobdork.output import render
from jobdork.web import api


def _seed(tmp: str) -> Config:
    cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "data" / "t.db"))
    cfg.output.dir = str(Path(tmp) / "out")
    with Store(cfg.db_path) as store:
        for i, origin in enumerate(["scan"] * 4 + ["manual"]):
            store.upsert(Role(platform="lever", company="Acme", title=f"Engineer {i}",
                              url=f"https://jobs.lever.co/acme/{i}", origin=origin))
        store.conn.commit()
        uids = [r["uid"] for r in store.list_roles(collapse_duplicates=False)]
        store.set_status(uids[0], "applied")
        store.delete_many([uids[1]], "deleted by you")          # stays deleted
    return cfg


def test_the_preview_counts_what_would_go_and_deletes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _seed(tmp)
        preview = api.fresh_preview(cfg)
        assert preview["count"] == 3 and preview["kept_by_hand"] == 1
        assert preview["pursuing"] == 1
        with Store(cfg.db_path) as store:
            assert store.scanned_count() == 3


def test_a_fresh_scan_backs_up_deletes_scanned_posts_then_scans():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _seed(tmp)
        lines, scanned = [], []
        saved = api.scan_job
        api.scan_job = lambda cfg: (lambda progress: scanned.append(True) or "scanned")
        try:
            summary = api.fresh_scan_job(cfg, 3)(lines.append)
        finally:
            api.scan_job = saved
        assert scanned and summary == "fresh scan: deleted 3 · scanned"
        with Store(cfg.db_path) as store:
            left = store.conn.execute("SELECT origin FROM roles").fetchall()
            states = store.conn.execute(      # state rows whose post is gone
                "SELECT COUNT(*) FROM role_state WHERE uid NOT IN "
                "(SELECT uid FROM roles)").fetchone()[0]
            tombstones = store.conn.execute("SELECT COUNT(*) FROM deleted").fetchone()[0]
        assert [r[0] for r in left] == ["manual"]        # added by hand: kept
        assert states == 0                                # statuses went with them
        assert tombstones == 1                            # nothing new remembered
        backups = list((Path(tmp) / "data" / "backups").glob("*-before-fresh-scan.db"))
        assert len(backups) == 1 and any("backed up" in x for x in lines)


def test_a_count_that_moved_since_the_preview_deletes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _seed(tmp)
        for expect in (2, "", None):
            try:
                api.fresh_scan_job(cfg, expect)
            except api.ApiError:
                continue
            raise AssertionError(f"expect={expect!r} must be refused")
        with Store(cfg.db_path) as store:
            assert store.scanned_count() == 3


def test_the_terminal_previews_unless_told_yes():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _seed(tmp)
        assert cli._fresh_start(cfg, yes=False) is False
        with Store(cfg.db_path) as store:
            assert store.scanned_count() == 3
        assert cli._fresh_start(cfg, yes=True) is True
        with Store(cfg.db_path) as store:
            assert store.scanned_count() == 0


def test_every_configured_format_is_written_by_one_function():
    """The dashboard's scan wrote html and json only; md and csv went stale."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _seed(tmp)
        cfg.output.formats = ["html", "json", "md", "csv"]
        with Store(cfg.db_path) as store:
            paths = render.write_all(store.list_roles(), cfg)
        assert sorted(p.name for p in paths) == ["index.html", "roles.csv",
                                                 "roles.json", "roles.md"]
        assert all(p.is_file() for p in paths)


def test_a_fresh_scan_counts_as_a_scan_on_the_dashboard():
    assert api._tool("fresh scan") == "scan"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
