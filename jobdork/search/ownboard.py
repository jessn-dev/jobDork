"""
jobdork.search.ownboard
=======================
An Adzuna post that the employer's own board does not carry.

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


def _same_title(a: str, b: str) -> bool:
    return bool(a and b) and (a == b or a in b or b in a)


def flag_text(company: str) -> str:
    return (f"Not on {company}'s own board, which jobdork read: "
            "may be filled, or not a real opening")


def missing(adzuna: list[tuple[str, str, str, str]],
            board: list[tuple[str, str, str]]) -> set[str]:
    """The Adzuna posts to flag, by uid.

    `adzuna`: (uid, company, title, last_seen) for each Adzuna post.
    `board`: (company, title, seen) for each job seen on an employer's own
    board, kept or dropped. Dates are compared by day.
    """
    titles: dict[str, set[str]] = {}
    latest: dict[str, str] = {}
    for company, title, seen in board:
        key = employer_key(company)
        if not key:
            continue
        titles.setdefault(key, set()).add(title_key(title))
        day = (seen or "")[:10]
        if day > latest.get(key, ""):
            latest[key] = day
    flagged = set()
    for uid, company, title, last_seen in adzuna:
        key = employer_key(company)
        read = latest.get(key)
        if not key or not read or read < _day_before((last_seen or "")[:10]):
            continue
        wanted = title_key(title)
        if not any(_same_title(wanted, t) for t in titles[key]):
            flagged.add(uid)
    return flagged


def _day_before(day: str) -> str:
    import datetime as dt

    try:
        return (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
    except ValueError:
        return "9999-12-31"                 # no date: the board cannot vouch
