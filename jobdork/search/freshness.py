"""
jobdork.search.freshness
========================
How old a job post is, and what that means for applying to it.

An application in the first two days sits at the top of the pile; after
three weeks the employer is often deep in interviews, or the post is an
"evergreen" listing reposted by a script, or abandoned. So a post's age is a
tier, and the tier moves its score:

    new      0 to `new_days` (2)         top of the pile            +5
    week     up to `week_days` (7)       when most people apply       0
    older    up to `older_days` (21)     screening may have started  -5
    stale    beyond that                 may be filled or reposted  -15
    ghost    beyond `ghost_days` (90)    dropped at screening

Nothing but a ghost is hidden: a stale post for the job you want most is
still worth a try, so it is marked and ranked lower, never removed.

**The age is measured in code, from dates, never by a model.** A model has no
clock and no reliable way to tell a posting's date from the dates in a
resume; this module is the only thing that decides freshness, and the model
is told the result (prompt_block) so its verdict can mention it.

**Where the date comes from**, best first: the board's own posting date
(`posted_at`); failing that, the day jobdork first saw the post, which is a
lower bound (a post first seen 30 days ago is at least 30 days old); failing
that, nothing, and the post is marked "posting date not stated".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# A post that says it is over. Worded tightly on purpose (listing.py uses it
# on posting pages too): USAJOBS prints "this posting will no longer be
# available once the announcement has closed" on every OPEN job, and a loose
# "no longer available" would close all of them. "Archived" only as a state
# of the post itself, never the word alone ("archived records management").
CLOSED_TEXT = re.compile(
    r"\b(?:"
    r"no longer accepting (?:applications|applicants|candidates)"
    r"|(?:this|the) (?:job|position|posting|role|vacancy|opening|requisition|listing)"
    r"(?: you(?:'re| are) looking for)? "
    r"(?:is no longer (?:available|open|active|accepting)"
    r"|has (?:been )?(?:closed|filled|expired|removed|taken down|archived)"
    r"|(?:was|is) (?:closed|filled|expired|removed|archived))"
    r"|(?:job|position|posting|vacancy) (?:has )?expired"
    r"|applications? (?:are|is|have) (?:now )?closed"
    r"|position (?:has been )?filled"
    r"|job (?:posting )?not found"
    r"|archived (?:job|posting|position|listing)"
    r")\b",
    re.IGNORECASE,
)


TIERS = ("new", "week", "older", "stale", "ghost")
LABELS = {"new": "brand new", "week": "first week", "older": "older, risky",
          "stale": "stale, may be filled", "ghost": "ghost listing"}


@dataclass
class Age:
    days: int | None = None        # None: no date at all
    source: str = ""               # "posted", "first seen" (a lower bound) or ""
    tier: str = ""                 # one of TIERS, or "" when unknown
    posted: str = ""               # the date measured from, YYYY-MM-DD
    reposted: str = ""             # the board's newer date, when it is a repost

    @property
    def known(self) -> bool:
        return self.days is not None

    def text(self) -> str:
        """ "posted 26 days ago (stale, may be filled)" """
        if not self.known:
            return "posting date not stated"
        ago = ("today" if self.days == 0 else "yesterday" if self.days == 1
               else f"{self.days} days ago")
        verb = "posted" if self.source == "posted" else "first seen"
        again = f", reposted {self.reposted}" if self.reposted else ""
        return f"{verb} {ago}{again} ({LABELS[self.tier]})"


def parse_date(text: str) -> date | None:
    """YYYY-MM-DD at the start of an ISO date or timestamp; anything else is None."""
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", str(text or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# "Posted 3 days ago", "30+ days ago", "posted 9 months ago", "Posted today".
_RELATIVE = re.compile(
    r"\bposted\s+(?:on\s+)?(?:(today|yesterday)|(?:about\s+|over\s+)?(\d{1,3})\+?\s*"
    r"(hour|day|week|month|year)s?\s+ago)\b", re.IGNORECASE)
_UNIT_DAYS = {"hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def relative_posted(text: str, today: date | None = None) -> date | None:
    """A date from "Posted 9 months ago" on a posting page, or None.

    Only after the word "posted": "5 years of experience" and "a 12-month
    contract" are not posting dates, and a filter on the words "month" or
    "year" alone would throw out real jobs for them.
    """
    m = _RELATIVE.search(text or "")
    if not m:
        return None
    today = today or date.today()
    if m.group(1):
        return today - timedelta(days=0 if m.group(1).lower() == "today" else 1)
    return today - timedelta(days=int(m.group(2)) * _UNIT_DAYS[m.group(3).lower()])


def tier_of(days: int, fresh) -> str:
    if fresh.ghost_days and days > fresh.ghost_days:
        return "ghost"
    if days <= fresh.new_days:
        return "new"
    if days <= fresh.week_days:
        return "week"
    if days <= fresh.older_days:
        return "older"
    return "stale"


def age(posted_at: str, first_seen: str, fresh, today: date | None = None) -> Age:
    """How old a post is, from its posting date or, failing that, first sight.

    A repost is dated from the first sighting: when jobdork saw the job (this
    copy or another of it, grouping.earliest_seen) more than a week before
    the date the board now gives, the board's date is a re-list, and the job
    is as old as the first sighting says.
    """
    today = today or date.today()
    posted, seen = parse_date(posted_at), parse_date(first_seen)
    if posted and seen and (posted - seen).days > fresh.week_days:
        days = max(0, (today - seen).days)
        return Age(days=days, source="first seen", tier=tier_of(days, fresh),
                   posted=seen.isoformat(), reposted=posted.isoformat())
    for text, source in ((posted_at, "posted"), (first_seen, "first seen")):
        when = parse_date(text)
        if when is None:
            continue
        days = max(0, (today - when).days)
        if source == "first seen" and days <= fresh.week_days:
            # First seen recently says nothing: the post may be months old.
            break
        return Age(days=days, source=source, tier=tier_of(days, fresh),
                   posted=when.isoformat())
    return Age()


def now(part: dict | None, posted_at: str, first_seen: str, fresh,
        today: date | None = None) -> Age:
    """The age today, for the page: a post screened as new is not new a month on.

    From the date screening measured from (the score's freshness part), which
    already accounts for reposts; for a post screened before there was one,
    from its own dates.
    """
    today = today or date.today()
    start = parse_date((part or {}).get("since", ""))
    if start is None:
        return age(posted_at, first_seen, fresh, today)
    days = max(0, (today - start).days)
    return Age(days=days, source=part.get("source") or "posted",
               tier=tier_of(days, fresh), posted=start.isoformat(),
               reposted=part.get("reposted") or "")


def points(tier: str, fresh) -> float:
    return {"new": fresh.new_points, "older": fresh.older_points,
            "stale": fresh.stale_points}.get(tier, 0.0)


def prompt_block(posted_at: str, first_seen: str, fresh,
                 now: datetime | None = None) -> str:
    """The post's dates for a model, apart from the advert and the resume.

    Kept in its own block because a model given a resume full of "2019 -
    2023" and an advert full of dates can take any of them for the posting
    date. This block is the only posting date it gets.
    """
    now = now or datetime.now()
    a = age(posted_at, first_seen, fresh, now.date())
    lines = [f"Today: {now.date().isoformat()}"]
    if a.known:
        lines.append(f"This post: {a.text()}, on {a.posted}. Measured by jobdork "
                     "from the job board's own data.")
    else:
        lines.append("This post: posting date not stated by the job board.")
    lines.append("This is the only posting date. Dates in the resume are the "
                 "candidate's history; dates in the advert are the employer's text.")
    return "\n".join(lines)
