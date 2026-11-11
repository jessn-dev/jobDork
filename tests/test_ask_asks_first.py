"""
Claude Security F19 and code scan #9 (2026-11-06): a coding agent, Ask
included, reads adverts strangers wrote, and one could ask it to change the
user's applications. Its changes now wait for the user's OK in My
applications. Nothing here goes online or touches live data.

    python tests/test_ask_asks_first.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config
from jobdork.db.store import Role, Store
from jobdork.web import agent, api


def _setup(tmp: str):
    cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"))
    role = Role(platform="greenhouse", company="Initech", title="Platform Engineer",
                url="https://boards.greenhouse.io/initech/jobs/1", location_raw="Remote")
    with Store(cfg.db_path) as store:
        store.upsert(role)
        store.set_status(role.uid, "applied")
    return cfg, role.uid


def test_a_change_waits_and_nothing_moves_until_approved():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        done = agent.call(cfg, "update_application", {
            "uid": uid, "status": "withdrawn", "contact_email": "x@evil.test",
            "note": "Withdrawn as asked", "_client": "claude-code"})
        assert done["waiting"] and set(done["suggested"]) == {"status", "contact_email", "note"}
        with Store(cfg.db_path) as store:
            assert store.conn.execute("SELECT status FROM role_state WHERE uid = ?", (uid,)).fetchone()[0] == "applied"
            assert not store.application_notes(uid)
            (waiting,) = store.application_suggestions()
        assert waiting["title"] == "Platform Engineer" and waiting["changes"]["status"] == "withdrawn"
        assert api.suggestions_count(cfg, applications=True) == 1
        assert api.suggestions_count(cfg) == 0, "the Resume page's count is the record's only"
        assert api.list_suggestions(cfg)["applications"][0]["id"] == waiting["id"]

        turned = api.decide_suggestion(cfg, {"kind": "application", "key": str(waiting["id"]),
                                             "approve": "0"})
        assert not turned["approved"]
        with Store(cfg.db_path) as store:
            assert store.conn.execute("SELECT status FROM role_state WHERE uid = ?", (uid,)).fetchone()[0] == "applied"
            assert not store.application_suggestions()


def test_an_approved_change_is_made_and_marked_as_the_agents():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        agent.call(cfg, "update_application", {"uid": uid, "status": "interviewing",
                                               "next_step": "Call", "next_date": "2026-12-01",
                                               "_client": "claude-code"})
        with Store(cfg.db_path) as store:
            (waiting,) = store.application_suggestions()
        done = api.decide_suggestion(cfg, {"kind": "application", "key": str(waiting["id"]),
                                           "approve": "1"})
        assert done["approved"] and "status interviewing" in done["applied"]
        with Store(cfg.db_path) as store:
            assert store.conn.execute("SELECT status FROM role_state WHERE uid = ?", (uid,)).fetchone()[0] == "interviewing"
            assert store.application(uid)["next_step"] == "Call"
            assert store.history(uid)[-1]["by"] == "Coding agent · Claude Code"
        try:
            api.decide_suggestion(cfg, {"kind": "application", "key": str(waiting["id"]),
                                        "approve": "1"})
        except api.ApiError as exc:
            assert exc.status == 404
        else:
            raise AssertionError("one approval only")


def test_a_bad_value_is_refused_and_kept_for_another_look():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        agent.call(cfg, "update_application", {"uid": uid, "next_date": "next tuesday"})
        with Store(cfg.db_path) as store:
            (waiting,) = store.application_suggestions()
        try:
            api.decide_suggestion(cfg, {"kind": "application", "key": str(waiting["id"]),
                                        "approve": "1"})
        except api.ApiError:
            pass
        else:
            raise AssertionError("a date that is not one was saved")
        with Store(cfg.db_path) as store:
            assert len(store.application_suggestions()) == 1


def test_waiting_changes_count_toward_the_limit():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        was = Store.SUGGESTED_MOST
        Store.SUGGESTED_MOST = 2
        try:
            for i in range(2):
                agent.call(cfg, "update_application", {"uid": uid, "note": f"n{i}"})
            try:
                agent.call(cfg, "update_application", {"uid": uid, "note": "n3"})
            except agent.ToolError as exc:
                assert "already waiting" in str(exc)
            else:
                raise AssertionError("no limit")
        finally:
            Store.SUGGESTED_MOST = was


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
