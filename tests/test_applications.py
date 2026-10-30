"""
Tests for My applications: the dated history of statuses, which jobs count
as applications, an application's details and notes, and the API around
them. On a temporary database; nothing online.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import datetime
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.db import migrations
from jobdork.db.store import Role, Store
from jobdork.web import api


class _Cfg:
    def __init__(self, path: Path):
        self.db_path = path


def _roles(store, n=3, same=False) -> list[str]:
    uids = []
    for i in range(n):
        role = Role(platform="ashby", company="Acme", title="Nurse" if same else f"Nurse {i}",
                    url=f"https://x.test/{i}", location_raw="Chicago, IL")
        store.upsert(role)
        uids.append(role.uid)
    store.conn.commit()
    return uids


def test_each_status_change_is_dated_once():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        uid = _roles(store, 1)[0]
        store.set_status(uid, "viewed")
        store.set_status(uid, "applied")
        store.set_status(uid, "applied", "a note")
        store.set_status(uid, "interviewing")
        assert [h["status"] for h in store.history(uid)] == ["applied", "interviewing"], \
            "viewed is not a step; the same status again is not a change"


def test_applications_are_the_jobs_applied_to():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        a, b, c = _roles(store)
        store.set_status(a, "interested")
        store.set_status(b, "applied")
        store.set_status(c, "applied")
        store.set_status(c, "skipped")
        apps = store.applications()
        assert {x["row"]["uid"] for x in apps} == {b, c}, "interested is not applied; skipped after applying is"
        assert all(x["applied_at"] for x in apps)


def test_copies_of_one_job_share_one_application():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        a, b = _roles(store, 2, same=True)
        store.set_status(a, "applied")
        store.save_application(a, {"next_step": "Call", "next_date": "2026-01-02"})
        store.add_application_note(a, "Spoke to them")
        assert len(store.applications()) == 1, "one job, one row"
        assert store.application(b)["next_step"] == "Call"
        assert [n["note"] for n in store.application_notes(b)] == ["Spoke to them"]
        note = store.application_notes(b)[0]["id"]
        assert store.delete_application_note(b, note)
        assert not store.application_notes(a), "deleted on every copy"


def test_an_old_database_starts_its_history_from_the_status_it_has():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.db"
        with Store(path) as store:
            uid = _roles(store, 1)[0]
            store.set_status(uid, "applied")
            store.conn.execute("DELETE FROM status_history")
            store.conn.execute("DELETE FROM meta WHERE key = 'schema_version'")
            store.conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', '14')")
            store.conn.commit()
        with Store(path) as store:
            assert store.applied_migrations == [15]
            assert [h["status"] for h in store.history(uid)] == ["applied"]
        assert migrations.SCHEMA_VERSION == 15


def test_the_list_has_stages_and_overdue_follow_ups():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _Cfg(Path(tmp) / "x.db")
        with Store(cfg.db_path) as store:
            a, b, c = _roles(store)
            for uid in (a, b, c):
                store.set_status(uid, "applied")
            store.set_status(b, "interviewing")
            store.set_status(c, "rejected")
            past = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
            store.save_application(a, {"next_step": "Follow up", "next_date": past})
            store.save_application(c, {"next_step": "Nothing", "next_date": past})
        d = api.list_applications(cfg)
        assert d["counts"] == {"applied": 1, "interviewing": 1, "offer": 0, "closed": 1}
        assert d["overdue"] == 1, "a closed application is never overdue"
        assert next(x for x in d["applications"] if x["uid"] == a)["overdue"]


def test_saving_checks_what_it_is_given():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _Cfg(Path(tmp) / "x.db")
        with Store(cfg.db_path) as store:
            a, b = _roles(store, 2)
            store.set_status(a, "applied")
            other = store.add_artifact(b, "cover_letter", "/x.md")
            mine = store.add_artifact(a, "tailored_resume", "/y.md")
            store.conn.commit()
        bad = [{"next_date": "next week"}, {"contact_email": "not an email"},
               {"contact_link": "javascript:alert(1)"}, {"letter_id": str(other)},
               {"resume_id": "x"}, {"next_step": "x" * 121}]
        for fields in bad:
            try:
                api.save_application(cfg, {"uid": a, **fields})
            except api.ApiError:
                continue
            raise AssertionError(f"accepted {fields}")
        api.save_application(cfg, {"uid": a, "next_step": " Phone   screen ", "next_date": "2026-11-02",
                                   "contact_email": "dana@example.com", "resume_id": str(mine)})
        with Store(cfg.db_path) as store:
            detail = api.application_detail(store, a, [{"id": mine, "kind": "tailored_resume"}])
        assert detail["is_application"] and detail["details"]["next_step"] == "Phone screen"
        assert detail["details"]["resume_id"] == mine and detail["resumes"][0]["id"] == mine


def test_notes_through_the_api():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _Cfg(Path(tmp) / "x.db")
        with Store(cfg.db_path) as store:
            uid = _roles(store, 1)[0]
            store.set_status(uid, "interviewing")
        for fields in ({"note": "  "}, {"note": "x" * 2001}, {"delete": "999"}):
            try:
                api.application_note(cfg, {"uid": uid, **fields})
            except api.ApiError:
                continue
            raise AssertionError(f"accepted {fields}")
        api.application_note(cfg, {"uid": uid, "note": "Went well"})
        with Store(cfg.db_path) as store:
            (note,) = store.application_notes(uid)
        assert note["stage"] == "interviewing", "filed under the status at the time"
        api.application_note(cfg, {"uid": uid, "delete": str(note["id"])})


def test_deleting_a_job_post_deletes_its_application():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        uid = _roles(store, 1)[0]
        store.set_status(uid, "applied")
        store.save_application(uid, {"next_step": "Call"})
        store.add_application_note(uid, "hello")
        store.conn.execute("DELETE FROM roles WHERE uid = ?", (uid,))
        store.conn.commit()
        for table in ("status_history", "applications", "application_notes"):
            assert not store.conn.execute(f"SELECT 1 FROM {table}").fetchone(), table  # nosec B608


# ── keep this block LAST ───────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
