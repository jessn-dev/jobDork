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
