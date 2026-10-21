"""
Job posts a scan's filters drop are remembered with the rule and the reason,
can be kept anyway, and stop being "dropped" once kept. Also the age limit
(freshness.show_days) and the warning a failed AI call now leaves.

    python tests/test_dropped.py
"""

from __future__ import annotations

import logging
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork import fetch
from jobdork.core import config as config_mod
from jobdork.core import setup
from jobdork.core.config import Config, Locations, Salary
from jobdork.db.store import DROPPED_DAYS, Role, Store
from jobdork.search import scan
from jobdork.web import api


def _cfg(tmp: str) -> Config:
    return Config(titles_include=["software engineer"],
                  locations=Locations(anchor="", radius="any", countries=[]),
                  salary=Salary(), db_path=str(Path(tmp) / "t.db"))


def _scan(cfg: Config, roles: list[Role]):
    def adapter(_fetcher, _cfg, **_kw):
        return fetch.SourceResult(source="fake", roles=list(roles))

    original_jobs, original_get = scan._jobs_for, fetch.get
    # lambda: one fake source instead of the configured ones.
    scan._jobs_for = lambda _cfg, _part="all": [("fake", {})]
    # lambda: every source name resolves to the fake adapter.
    fetch.get = lambda _name: adapter
    try:
        with Store(cfg.db_path) as store:
            return scan.run(cfg, store)
    finally:
        scan._jobs_for, fetch.get = original_jobs, original_get


def _role(name: str, title: str = "Software Engineer", **kw) -> Role:
    return Role(platform="workable", company=name, title=title,
                url=f"https://x.test/{name}", work_mode="remote", **kw)


def test_a_scan_remembers_what_its_filters_dropped_and_why():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        _scan(cfg, [_role("kept"), _role("chef", title="Head Chef")])
        got = api.dropped_list(cfg)
        assert [p["company"] for p in got["dropped"]] == ["chef"]
        assert got["dropped"][0]["rule"] == "title"
        assert got["dropped"][0]["reason"]
        assert got["by_rule"] == {"title": 1}


def test_keeping_a_dropped_post_stores_it_as_interested_and_forgets_the_drop():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        _scan(cfg, [_role("chef", title="Head Chef")])
        uid = api.dropped_list(cfg)["dropped"][0]["uid"]
        api.dropped_keep(cfg, uid)
        with Store(cfg.db_path) as store:
            row = store.get(uid)
            assert row is not None and row["status"] == "interested"
            assert "Kept anyway" in row["note"]
        assert api.dropped_list(cfg)["dropped"] == []
        try:
            api.dropped_keep(cfg, uid)
        except api.ApiError as exc:
            assert exc.status == 404
        else:
            raise AssertionError("a post kept once is no longer a dropped one")


def test_a_post_kept_by_a_later_scan_is_no_longer_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        _scan(cfg, [_role("chef", title="Head Chef")])
        cfg.titles_include.append("head chef")
        _scan(cfg, [_role("chef", title="Head Chef")])
        with Store(cfg.db_path) as store:
            assert store.list_dropped() == []
            assert store.get_dropped(_role("chef").uid) is None


def test_old_dropped_posts_are_pruned():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store:
            store.save_dropped([(_role("old"), "title", "x")])
            store.conn.execute("UPDATE dropped SET seen_at = '2000-01-01T00:00:00'")
            store.conn.commit()
            store.save_dropped([(_role("new"), "title", "y")])
            assert [r["company"] for r in store.list_dropped()] == ["new"]
        assert DROPPED_DAYS > 0


def test_the_age_limit_is_saved_and_checked():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text("titles: {include: [x]}\nlocations: {anchor: 'Chicago, IL'}\n"
                        f"db: {Path(tmp) / 't.db'}\n")
        assert setup.write(str(path), {"show_days": 30}).freshness.show_days == 30
        assert setup.write(str(path), {"show_days": ""}).freshness.show_days == 0
        try:
            setup.write(str(path), {"show_days": -1})
        except config_mod.ConfigError:
            pass
        else:
            raise AssertionError("a negative age limit must be refused")
        assert config_mod.load(str(path)).freshness.show_days == 0


def test_a_failed_ai_call_is_logged_with_its_reason():
    from jobdork.ai import llm

    seen: list[str] = []

    class Catch(logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    handler = Catch(level=logging.WARNING)
    llm.log.addHandler(handler)
    original = llm._ollama

    def refuse(*_a, **_kw):
        raise llm.LLMError("could not reach localhost: refused")

    llm._ollama = refuse
    try:
        llm.complete_json(llm.Settings(provider="ollama", model="m"), "s", "u",
                          {"type": "object"}, purpose="judge")
    except llm.LLMError:
        pass
    finally:
        llm._ollama = original
        llm.log.removeHandler(handler)
    assert any("AI call failed" in m and "judge" in m and "refused" in m for m in seen), seen


def test_posted_dates_still_age_dropped_posts():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        posted = (date.today() - timedelta(days=10)).isoformat()
        with Store(cfg.db_path) as store:
            store.save_dropped([(_role("a", posted_at=posted), "salary", "pays too little")])
        post = api.dropped_list(cfg)["dropped"][0]
        assert post["age"]["days"] == 10 and post["age"]["tier"] == "older"


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
