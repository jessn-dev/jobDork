"""
An Adzuna post the employer's own board does not carry is flagged, when
jobdork read that board in the same scan. Nothing here touches the network.

    python tests/test_ownboard.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config
from jobdork.db.store import Role, Store
from jobdork.search import discover, ownboard
from jobdork.web import api

DAY = "2026-10-25T06:00:00"


def test_employer_names_are_compared_without_case_punctuation_or_suffixes():
    assert ownboard.employer_key("The Home Depot, Inc.") == ownboard.employer_key("the home depot")
    assert ownboard.employer_key("TJX Companies") == ownboard.employer_key("TJX Companies, LLC")
    assert ownboard.employer_key("Acme Health") != ownboard.employer_key("Acme Health Partners")


def test_flagged_only_when_the_board_was_read_and_has_no_such_title():
    board = [("Northbridge Health", "Charge Nurse - Medical Surgical", DAY),
             ("Northbridge Health", "Registered Nurse - ICU", DAY)]
    adzuna = [
        ("on", "Northbridge Health, Inc.", "Registered Nurse", DAY),     # inside a board title
        ("off", "Northbridge Health", "Nurse Manager - Cardiology", DAY),
        ("unread", "Westfield Medical", "Nurse Manager", DAY),           # board not read: say nothing
        ("later", "Northbridge Health", "Nurse Manager", "2026-10-28T06:00:00"),
    ]
    # "later": the board was last read three days before Adzuna showed it.
    assert ownboard.missing(adzuna, board) == {"off"}
    # A post with no date cannot be vouched for by the board's date.
    assert ownboard.missing([("x", "Northbridge Health", "Nurse Manager", "")], board) == set()


def test_the_own_boards_are_the_ones_discover_reads():
    """Drift guard: a new board platform in discover counts as an own board."""
    read_by_discover = {p for p, _ in discover.BOARD_PATTERNS} | {"site"}
    assert read_by_discover == ownboard.OWN_BOARDS


def test_the_list_and_the_post_carry_the_flag_and_a_dropped_copy_vouches():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["nurse"], db_path=str(Path(tmp) / "t.db"))
        with Store(cfg.db_path) as store:
            own = Role(platform="workday", company="Northbridge Health",
                       title="Charge Nurse", url="https://x.test/1", location_raw="Chicago, IL")
            ghost = Role(platform="adzuna", company="Northbridge Health Inc",
                         title="Nurse Manager", url="https://x.test/2", location_raw="Chicago, IL")
            real = Role(platform="adzuna", company="Northbridge Health",
                        title="Unit Nurse Educator", url="https://x.test/3",
                        location_raw="Chicago, IL")
            for role in (own, ghost, real):
                store.upsert(role)
            # The board's copy of the educator job was dropped (too far away):
            # it is still on the board, so the Adzuna copy is not flagged.
            far = Role(platform="workday", company="Northbridge Health",
                       title="Unit Nurse Educator", url="https://x.test/4",
                       location_raw="Joliet, IL")
            store.save_dropped([(far, "distance", "too far")])
            store.conn.commit()
            flagged = api.not_on_own_board(store, store.list_roles())
        assert flagged == {ghost.uid}
        detail = api.role_detail(cfg, ghost.uid)
        assert ownboard.flag_text("Northbridge Health Inc") in detail["flags"]
        assert not any("own board" in f for f in api.role_detail(cfg, real.uid)["flags"])


def test_each_post_says_what_the_employers_board_says_of_it():
    """A board read in full that answered nothing matching still vouches:
    that is the case a stored job alone could never show (2026-10-27)."""
    posts = [("found", "Acme", "Nurse Manager", DAY),
             ("full", "Northern Trust", "DevOps Engineer", DAY),       # read whole, nothing
             ("part", "Big Health", "Charge Nurse", DAY),              # read partly
             ("none", "Nowhere Corp", "Nurse", DAY),                   # never read
             ("old", "Acme", "Night Nurse", DAY)]
    board = [("Acme", "Nurse Manager - ICU", DAY), ("Acme", "Unit Clerk", DAY)]
    reads = [("Northern Trust Corporation", DAY, True), ("Big Health", DAY, False)]
    assert ownboard.states(posts, board, reads) == {
        "found": "found", "full": "missing", "part": "partial", "none": "unread",
        # No read recorded for Acme: a job of its board seen then still
        # vouches, as before board_reads.
        "old": "missing"}
    # A full read days before the post was seen says nothing of it.
    later = [("late", "Northern Trust", "DevOps Engineer", "2026-10-29T06:00:00")]
    assert ownboard.states(later, [], reads) == {"late": "unread"}


def test_every_aggregator_is_checked_not_only_adzuna():
    assert {"adzuna", "himalayas", "arbeitnow", "kalibrr"} == ownboard.AGGREGATORS
    assert not ownboard.AGGREGATORS & ownboard.OWN_BOARDS
    assert "usajobs" not in ownboard.AGGREGATORS and "workable" not in ownboard.AGGREGATORS
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["devops"], db_path=str(Path(tmp) / "t.db"))
        with Store(cfg.db_path) as store:
            post = Role(platform="himalayas", company="Northern Trust",
                        title="DevOps Engineer", url="https://x.test/h", location_raw="Remote")
            store.upsert(post)
            store.record_board_reads([("workday", "ntrs/wd1/northerntrust", "Northern Trust", True)])
            store.conn.commit()
            assert api.not_on_own_board(store, store.list_roles()) == {post.uid}
        assert api.role_detail(cfg, post.uid)["own_board"] == "missing"


def test_the_window_asks_the_employers_board_now():
    """The check button: searches the board for the post's own title, says
    what it found, records the read, and nothing else."""
    from jobdork import fetch
    from jobdork.fetch import SourceResult
    from jobdork.search import directory

    asked = []

    def board(fetcher, cfg, token="", company="", **_):
        asked.append((token, list(cfg.titles_include)))
        roles = [Role(platform="workday", company=company, title="Senior DevOps Engineer",
                      url="https://nt.test/job/1")] if "devops" in token else []
        return SourceResult(source="workday", roles=roles)

    boards = [directory.Board("Northern Trust", "workday", "ntrs/devops", ("US",), "banking"),
              directory.Board("Acme Bank", "workday", "acme/x", ("US",), "banking")]
    saved = fetch.get, directory.load
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["devops"], db_path=str(Path(tmp) / "t.db"))
        try:
            # lambda: our stand-in board for every platform, asking nothing real.
            fetch.get = lambda name: board
            # lambda: the two boards above in place of data/boards.csv.
            directory.load = lambda *a, **k: boards
            with Store(cfg.db_path) as store:
                found = Role(platform="adzuna", company="Northern Trust Corp",
                             title="DevOps Engineer", url="https://a.test/1")
                gone = Role(platform="adzuna", company="Acme Bank",
                            title="DevOps Engineer", url="https://a.test/2")
                unknown = Role(platform="adzuna", company="Initech",
                               title="DevOps Engineer", url="https://a.test/3")
                for r in (found, gone, unknown):
                    store.upsert(r)
                store.conn.commit()
            out = api.check_own_board(cfg, found.uid, fetcher=object())
            assert out["state"] == "found" and out["url"] == "https://nt.test/job/1"
            assert asked[0] == ("ntrs/devops", ["DevOps Engineer"])     # the post's title
            assert api.check_own_board(cfg, gone.uid, fetcher=object())["state"] == "missing"
            assert api.check_own_board(cfg, unknown.uid, fetcher=object())["state"] == "unknown"
            with Store(cfg.db_path) as store:
                assert {r["token"] for r in store.board_reads()} == {"ntrs/devops", "acme/x"}
        finally:
            fetch.get, directory.load = saved


def test_a_scan_records_each_employer_board_it_read_and_whether_in_full():
    """Read in full with nothing matching, read only partly, failed: the
    first vouches, the second does not, the third is not a read."""
    from jobdork import fetch
    from jobdork.core.config import Locations
    from jobdork.fetch import SourceResult
    from jobdork.search import scan

    answers = {
        "nt": SourceResult(source="workday"),                                # nothing, in full
        "big": SourceResult(source="workday", complete=False),              # cut at the limit
        "down": SourceResult(source="workday", errors=["HTTP 503"]),
        "gone": SourceResult(source="workday", skipped="Gone lists no jobs in US"),
    }
    jobs = [("workday", {"token": t, "company": t.title()}) for t in answers] + [("adzuna", {})]

    def adapter(_fetcher, _cfg, token="", **_):
        return answers.get(token) or SourceResult(source="adzuna")

    saved = scan._jobs_for, fetch.get
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["devops"], db_path=str(Path(tmp) / "t.db"),
                     locations=Locations(cities=[], radius="any", countries=[]))
        try:
            # lambda: these boards instead of the configured sources.
            scan._jobs_for = lambda _cfg, _part="all": jobs
            # lambda: every source name resolves to the stand-in above.
            fetch.get = lambda _name: adapter
            with Store(cfg.db_path) as store:
                scan.run(cfg, store)
                reads = {r["token"]: bool(r["complete"]) for r in store.board_reads()}
        finally:
            scan._jobs_for, fetch.get = saved
    assert reads == {"nt": True, "big": False, "down": False}, reads


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
