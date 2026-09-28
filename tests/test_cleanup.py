"""
Cleaning up job posts: the right ones go, pursued ones never do, a deleted
post stays deleted, and a delete only happens at the count you previewed.

    python tests/test_cleanup.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork import fetch
from jobdork.core.config import Config, Locations, Salary
from jobdork.db.store import Role, Store
from jobdork.search import scan
from jobdork.web import api


def _setup(tmp: str) -> tuple[Config, dict[str, str]]:
    cfg = Config(titles_include=["software engineer"],
                 locations=Locations(anchor="", radius="any", countries=[]),
                 salary=Salary(), db_path=str(Path(tmp) / "t.db"))
    uids = {}
    with Store(cfg.db_path) as store:
        for name, status, age in (("old_new", "new", "2026-01-01"),
                                  ("old_applied", "applied", "2026-01-01"),
                                  ("old_offer", "offer", "2026-01-01"),
                                  ("old_closed", "closed", "2026-01-01"),
                                  ("fresh_skipped", "skipped", "2099-01-01")):
            role = Role(platform="workable", company=name, title="Software Engineer",
                        url=f"https://x.test/{name}", work_mode="remote")
            store.upsert(role)
            store.conn.execute("UPDATE roles SET first_seen = ? WHERE uid = ?",
                               (f"{age}T00:00:00", role.uid))
            if status != "new":
                store.set_status(role.uid, status)
            uids[name] = role.uid
        store.conn.commit()
    return cfg, uids


def test_age_cleanup_never_touches_a_job_you_are_pursuing():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, _ = _setup(tmp)
        preview = api.cleanup_preview(cfg, days=30)
        assert preview["count"] == 2 and preview["total"] == 5
        assert preview["by_status"] == {"new": 1, "closed": 1}


def test_status_cleanup_takes_only_the_statuses_ticked():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, _ = _setup(tmp)
        assert api.cleanup_preview(cfg, statuses="skipped")["count"] == 1
        assert api.cleanup_preview(cfg, statuses="closed,skipped")["count"] == 2
        for bad in ({"statuses": "applied"}, {}, {"days": 30, "statuses": "closed"}):
            try:
                api.cleanup_preview(cfg, **bad)
            except api.ApiError:
                continue
            raise AssertionError(f"{bad} should be refused")


def test_a_delete_needs_the_previewed_count_and_backs_up_first():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uids = _setup(tmp)
        try:
            api.cleanup_run(cfg, days=30, expect=99)
        except api.ApiError as exc:
            assert exc.status == 409
        else:
            raise AssertionError("a stale count must not delete")
        done = api.cleanup_run(cfg, days=30, expect=2)
        assert done["deleted"] == 2 and Path(done["backup"]).is_file()
        with Store(cfg.db_path) as store:
            assert store.get(uids["old_applied"]) is not None
            assert store.get(uids["old_new"]) is None


def test_a_deleted_job_post_is_not_brought_back_by_a_scan():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uids = _setup(tmp)
        api.cleanup_run(cfg, statuses="closed", expect=1)

        def adapter(_fetcher, _cfg, **_kw):
            return fetch.SourceResult(source="fake", roles=[Role(
                platform="workable", company="old_closed", title="Software Engineer",
                url="https://x.test/old_closed", work_mode="remote")])

        original_jobs, original_get = scan._jobs_for, fetch.get
        scan._jobs_for = lambda _cfg: [("fake", {})]
        fetch.get = lambda _name: adapter
        try:
            with Store(cfg.db_path) as store:
                report = scan.run(cfg, store)
                assert report.previously_deleted == 1
                assert store.get(uids["old_closed"]) is None
        finally:
            scan._jobs_for, fetch.get = original_jobs, original_get


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
