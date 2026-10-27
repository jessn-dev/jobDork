"""
jobdork.search.ownboard
=======================
An aggregator's post that the employer's own board does not carry.

Adzuna republishes adverts it gathers from across the web, and keeps showing
some after the employer has filled or withdrawn them; some were never real
openings. A real job is nearly always on the employer's own board too.
Adzuna's pages cannot be read to ask it (enrich.py), so the employer's board
is asked instead:

  **Only when jobdork read that board.** The employer's board answered in the
  same scan as the Adzuna post was last seen (one of its jobs, kept or
  dropped by your filters, was seen within a day of it). An employer whose
  board jobdork does not read says nothing either way, and is not flagged.

  **The same title, anywhere on it.** Places are written differently by the
  two ("Chicago, IL" and "Chicago, Illinois, United States"), so the place is
  not compared; one title containing the other counts ("Registered Nurse"
  and "Registered Nurse - ICU").

  **Employer names compared loosely.** "The Home Depot, Inc." on Adzuna is
  "The Home Depot" on its board: case, punctuation, "The" and company
  suffixes are left out.

A flagged post stays listed: the flag is a reason to look before applying,
not proof. "Ghost" alone is the age tier (freshness.py); this one says what
it found.
"""

from __future__ import annotations

import re

# Sources that carry many employers' jobs, gathered from elsewhere or posted
# there: their posts are the ones checked against the employer's own board.
# Not USAJOBS (federal agencies' own listings) nor Workable's search (each
# post is from the employer's own Workable board).
AGGREGATORS = frozenset({"adzuna", "himalayas", "arbeitnow", "kalibrr"})

# An employer's own board, read through its own system (discover.BOARD_PATTERNS)
# or its careers site. Not Adzuna, USAJOBS, Workable's search, Himalayas,
# Arbeitnow, the Arbeitsagentur or Kalibrr, which carry many employers' jobs.
OWN_BOARDS = frozenset({"greenhouse", "ashby", "lever", "smartrecruiters", "breezy",
                        "workday", "oracle", "eightfold", "taleo", "site"})

_SUFFIXES = frozenset({"the", "inc", "incorporated", "llc", "llp", "lp", "ltd", "limited",
                       "corp", "corporation", "co", "company", "plc", "group",
                       "holdings", "sa", "ag", "gmbh", "nv", "bv"})


def employer_key(name: str) -> str:
    """"The Home Depot, Inc." and "the home depot" both give "home depot"."""
    words = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split()
    return " ".join(w for w in words if w not in _SUFFIXES)


def title_key(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def same_title(a: str, b: str) -> bool:
    """One title key inside the other: "registered nurse" and "registered
    nurse icu" are the same job."""
    return bool(a and b) and (a == b or a in b or b in a)


def flag_text(company: str) -> str:
    return (f"Not on {company}'s own board, which jobdork read: "
            "may be filled, or not a real opening")


def states(posts: list[tuple[str, str, str, str]],
           board: list[tuple[str, str, str]],
           reads: list[tuple[str, str, bool]] = ()) -> dict[str, str]:
    """What the employer's own board says of each aggregator post, by uid:

    "found"    the board carries the same title
    "missing"  the board was read in full, near when the post was seen, and
               does not carry it: the post is flagged
    "partial"  the board was read, but not to the end: it cannot vouch
    "unread"   jobdork has not read that employer's board near then

    `posts`: (uid, company, title, last_seen). `board`: (company, title,
    seen) for each job seen on an employer's own board, kept or dropped.
    `reads`: (company, read_at, complete) from board_reads, so a board that
    answered nothing matching still counts as read. Dates by day.
    """
    titles: dict[str, set[str]] = {}
    seen_day: dict[str, str] = {}    # employer -> latest day a board job was seen
    for company, title, seen in board:
        key = employer_key(company)
        if key:
            titles.setdefault(key, set()).add(title_key(title))
            _later(seen_day, key, seen)
    # employer -> (latest day read, read in full that day)
    read: dict[str, tuple[str, bool]] = {}
    for company, read_at, complete in reads:
        key = employer_key(company)
        day = (read_at or "")[:10]
        if key and (day, bool(complete)) > read.get(key, ("", False)):
            read[key] = (day, bool(complete))
    out = {}
    for uid, company, title, last_seen in posts:
        key = employer_key(company)
        if key and any(same_title(title_key(title), t) for t in titles.get(key, ())):
            out[uid] = "found"
            continue
        since = _day_before((last_seen or "")[:10])
        day, complete = read.get(key, ("", False))
        if key and day and day >= since:
            out[uid] = "missing" if complete else "partial"
        elif key and seen_day.get(key, "") >= since:
            # No read recorded (a scan from before board_reads): one of the
            # board's jobs seen then is the evidence it was read, as before.
            out[uid] = "missing"
        else:
            out[uid] = "unread"
    return out


def missing(posts: list[tuple[str, str, str, str]],
            board: list[tuple[str, str, str]],
            reads: list[tuple[str, str, bool]] = ()) -> set[str]:
    """The aggregator posts to flag, by uid (states(), "missing")."""
    return {uid for uid, state in states(posts, board, reads).items() if state == "missing"}


def _later(latest: dict[str, str], key: str, stamp: str) -> None:
    day = (stamp or "")[:10]
    if day > latest.get(key, ""):
        latest[key] = day



def _day_before(day: str) -> str:
    import datetime as dt

    try:
        return (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
    except ValueError:
        return "9999-12-31"                 # no date: the board cannot vouch
