"""
Stale and ghost job posts: age tiers, reposts, dates read from pages, and the
date block a model is given. Dates are fixed; nothing here depends on today.

    python tests/test_freshness.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import config as config_mod
from jobdork.core.config import Config, Freshness, Locations
from jobdork.db import grouping
from jobdork.db.store import Role, Store
from jobdork.search import enrich, freshness, screen

TODAY = date(2026, 9, 30)
FRESH = Freshness()
ADVERT = "We build payments software. " * 20


def _cfg() -> Config:
    return Config(titles_include=["software engineer"],
                  locations=Locations(anchor="", work_modes=[]))


def _role(posted: str, description: str = ADVERT) -> Role:
    return Role(platform="greenhouse", company="Acme", title="Software Engineer",
                url="https://boards.greenhouse.io/acme/jobs/1", location_raw="Remote",
                description=description + " Fully remote.", posted_at=posted)


def test_ages_fall_into_the_tiers():
    cases = {"2026-09-30": "new", "2026-09-28": "new", "2026-09-27": "week",
             "2026-09-23": "week", "2026-09-22": "older", "2026-09-09": "older",
             "2026-09-08": "stale", "2026-07-02": "stale", "2026-07-01": "ghost"}
    for posted, tier in cases.items():
        assert freshness.age(posted, "", FRESH, TODAY).tier == tier, posted
    assert not freshness.age("", "", FRESH, TODAY).known


def test_first_sight_is_a_floor_only_once_it_says_something():
    # Seen for the first time this week: the post may be months old; unknown.
    assert not freshness.age("", "2026-09-27T10:00:00", FRESH, TODAY).known
    seen = freshness.age("", "2026-08-20T10:00:00", FRESH, TODAY)
    assert (seen.days, seen.tier, seen.source) == (41, "stale", "first seen")


def test_a_repost_is_as_old_as_the_first_sighting():
    a = freshness.age("2026-09-29", "2026-07-15T08:00:00", FRESH, TODAY)
    assert (a.days, a.tier, a.reposted) == (77, "stale", "2026-09-29")
    assert "reposted 2026-09-29" in a.text()
    # A board date a few days after first sight is not a repost.
    assert not freshness.age("2026-09-20", "2026-09-18", FRESH, TODAY).reposted


def test_relative_dates_are_read_only_after_posted():
    assert freshness.relative_posted("Posted 9 months ago", TODAY) == date(2026, 1, 3)   # months as 30 days
    assert freshness.relative_posted("posted 30+ days ago", TODAY) == date(2026, 8, 31)
    assert freshness.relative_posted("Posted today", TODAY) == TODAY
    for text in ("5 years of experience", "a 12-month contract", "401(k) every month"):
        assert freshness.relative_posted(text, TODAY) is None, text


def test_a_ghost_is_dropped_and_a_stale_post_kept_marked_and_ranked_lower():
    ghost = screen.screen(_role("2026-05-01"), _cfg(), today=TODAY)
    assert not ghost.keep and "freshness.ghost_days" in ghost.reasons[0]

    fresh_role, stale_role = _role("2026-09-29"), _role("2026-09-01")
    new = screen.screen(fresh_role, _cfg(), today=TODAY)
    stale = screen.screen(stale_role, _cfg(), today=TODAY)
    assert new.keep and stale.keep
    assert new.score - stale.score == FRESH.new_points - FRESH.stale_points
    part = next(p for p in stale.parts if p["part"] == "freshness")
    assert (part["tier"], part["days"], part["since"]) == ("stale", 29, "2026-09-01")
    assert any("stale" in f for f in stale_role.flags)


def test_no_date_is_kept_and_said():
    role = _role("")
    verdict = screen.screen(role, _cfg(), today=TODAY)
    assert verdict.keep and "posting date not stated" in role.flags


def test_ghost_days_zero_never_drops_for_age():
    cfg = _cfg()
    cfg.freshness = Freshness(ghost_days=0)
    assert screen.screen(_role("2023-09-05"), cfg, today=TODAY).keep


def test_an_advert_that_says_it_is_over_is_dropped():
    for text in ("This position has been filled.", "This job has been archived.",
                 "We are no longer accepting applications."):
        verdict = screen.screen(_role("2026-09-29", ADVERT + text), _cfg(), today=TODAY)
        assert not verdict.keep and "the advert says the post is over" in verdict.reasons[0]
    # USAJOBS boilerplate on an open job, and "archived" as a subject, are not.
    for text in ("This posting will no longer be available once the announcement "
                 "has closed.", "Experience with archived records management."):
        assert screen.screen(_role("2026-09-29", ADVERT + text), _cfg(), today=TODAY).keep


def test_the_page_gives_a_date_when_the_board_did_not():
    ld = ('<script type="application/ld+json">{"@type": "JobPosting", '
          '"datePosted": "2026-01-07T10:00:00Z"}</script>')
    assert enrich.extract_posted(ld) == "2026-01-07"
    assert enrich.extract_posted("<p>A 12-month contract, 5 years needed.</p>") == ""


def test_the_python_group_key_matches_the_database_one():
    with tempfile.TemporaryDirectory() as tmp, Store(str(Path(tmp) / "t.db")) as store:
        stored = Role(platform="lever", company="  Ünïted Ärts ", title="Software Engineer",
                      url="https://jobs.lever.co/ua/1", location_raw="Austin, TX",
                      city="Austin", state="TX", work_mode="hybrid")
        store.upsert(stored)
        store.conn.execute("UPDATE roles SET first_seen = '2026-06-01T09:00:00'")
        again = Role(platform="greenhouse", company="Ünïted Ärts", title="Software Engineer",
                     url="https://boards.greenhouse.io/ua/jobs/9", location_raw="Austin, Texas",
                     city="Austin", state="TX", work_mode="hybrid")
        assert grouping.earliest_seen(store.conn, role=again) == "2026-06-01T09:00:00"
        assert grouping.earliest_seen(store.conn, uid=stored.uid) == "2026-06-01T09:00:00"


def test_the_model_gets_the_posting_date_apart_from_the_resume():
    block = freshness.prompt_block("2026-09-01", "", FRESH, datetime(2026, 9, 30, 12))
    assert "Today: 2026-09-30" in block
    assert "posted 29 days ago (stale, may be filled), on 2026-09-01" in block
    assert "Dates in the resume are the candidate's history" in block


def test_the_age_is_worked_out_again_each_day():
    part = {"part": "freshness", "since": "2026-09-29", "source": "posted"}
    assert freshness.now(part, "", "", FRESH, TODAY).tier == "new"
    assert freshness.now(part, "", "", FRESH, date(2026, 10, 25)).tier == "stale"


def test_freshness_settings_must_make_sense():
    for bad in ({"new_days": 7, "week_days": 7}, {"ghost_days": 10}):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write("titles: {include: [engineer]}\n"
                     f"freshness: {bad}\n".replace("'", ""))
        try:
            config_mod.load(fh.name)
        except config_mod.ConfigError as exc:
            assert "freshness" in str(exc)
        else:
            raise AssertionError(f"{bad} should be refused")
        finally:
            Path(fh.name).unlink()


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
