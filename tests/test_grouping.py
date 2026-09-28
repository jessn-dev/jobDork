"""
Copies of one job: shown once, decided once, closed only when all are gone.

    python tests/test_grouping.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config
from jobdork.db import grouping
from jobdork.db.store import Role, Store
from jobdork.search import listing


def _role(url: str, city: str = "Chicago", state: str = "IL", desc: str = "",
          platform: str = "adzuna", mode: str = "office") -> Role:
    role = Role(platform=platform, company="Acme", title="Software Engineer",
                url=url, location_raw=f"{city}, {state}", description=desc,
                work_mode=mode)
    role.city, role.state, role.score = city, state, 50.0
    return role


def _store(tmp: str) -> Store:
    return Store(Path(tmp) / "t.db")


def test_copies_are_one_post_and_the_fuller_advert_is_shown():
    with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
        store.upsert(_role("https://a.test/1", desc="short"))
        store.upsert(_role("https://b.test/1", desc="x" * 3000, platform="workable"))
        store.conn.commit()
        rows = store.list_roles()
        assert len(rows) == 1 and rows[0]["copies"] == 2
        assert rows[0]["platform"] == "workable"
        assert len(store.list_roles(collapse_duplicates=False)) == 2


def test_the_same_title_in_another_city_is_another_job():
    """Grouping on company and title alone hid real openings."""
    with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
        store.upsert(_role("https://a.test/chi"))
        store.upsert(_role("https://a.test/aus", city="Austin", state="TX"))
        store.conn.commit()
        assert [r["copies"] for r in store.list_roles()] == [1, 1]


def test_a_decision_on_one_copy_is_on_every_copy():
    with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
        a, b = _role("https://a.test/1"), _role("https://b.test/1")
        store.upsert(a)
        store.upsert(b)
        store.set_status(a.uid, "applied", "sent CV")
        for uid in (a.uid, b.uid):
            row = store.get(uid)
            assert (row["status"], row["note"]) == ("applied", "sent CV")


def test_a_shown_copy_that_changes_does_not_come_back_as_new():
    """The bug grouping fixes: applied on one copy, then the other took over."""
    with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
        a, b = _role("https://a.test/1", desc="x" * 1500), _role("https://b.test/1")
        store.upsert(a)
        store.upsert(b)
        store.set_status(a.uid, "applied")
        b.description = "y" * 5000              # b's advert grows; b is now shown
        store.upsert(b, seen=False)
        store.conn.commit()
        shown = store.list_roles(include_settled=True)
        assert shown[0]["uid"] == b.uid and shown[0]["status"] == "applied"


class _Fetcher:
    """Answers 410 for one posting and a live advert for the other."""

    def __init__(self, dead: str):
        self.dead = dead

    def get(self, url, expect_json=True, **_):
        from jobdork.fetch.http import Response
        if url == self.dead:
            return Response(url=url, status=410, error="HTTP 410", final_url=url)
        body = '<script type="application/ld+json">{"@type": "JobPosting"}</script>'
        return Response(url=url, status=200, body=body, final_url=url)


def test_one_live_copy_keeps_the_job_open():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"))
        with Store(cfg.db_path) as store:
            a = _role("https://jobs.workable.com/view/dead", platform="workable")
            b = _role("https://jobs.workable.com/view/live", platform="workable")
            store.upsert(a)
            store.upsert(b)
            store.conn.commit()

            listing.run(cfg, store, _Fetcher(a.url), force=True)
            assert store.get(a.uid)["listing_state"] == "closed"
            assert store.get(a.uid)["status"] == "new", "b is still up"

            listing.run(cfg, store, _Fetcher("https://jobs.workable.com/view/live"),
                        uid=b.uid)
            assert store.get(a.uid)["status"] == "closed", "now every copy is gone"
            assert grouping.all_closed(store.conn, [a.uid, b.uid])


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
