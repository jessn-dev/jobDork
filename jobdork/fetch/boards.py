"""
jobdork.fetch.boards
====================
Shared machinery for the per-employer board adapters.

These five platforms all answer the same question — "what is this one employer
advertising?" — and all need a board token that is not the company's name.
Tokens rarely match the company name — `mymoose` is Rapid7, `evergreenix` is
Garrison — so a token is read off the employer's careers page and never
guessed from the name.

The empty-200 problem lives here. Ashby and SmartRecruiters answer HTTP 200
with an empty list both for a board that does not exist and for one that is
rate-limiting you, so `_result_for` marks an empty answer suspect rather than
reporting confidently that an employer is not hiring.
"""

from __future__ import annotations

import re

from ..db.store import Role
from . import SourceResult

# Compensation intervals, however each platform spells them.
INTERVAL_MAP = {
    "1 year": "year", "year": "year", "yearly": "year", "annual": "year",
    "annually": "year", "per year": "year", "salary": "year",
    "1 month": "month", "month": "month", "monthly": "month",
    "1 week": "week", "week": "week", "weekly": "week",
    "1 day": "day", "day": "day", "daily": "day",
    "1 hour": "hour", "hour": "hour", "hourly": "hour",
}

# Hours a year used to annualise a rate. 2,080 is the US convention: 40 hours
# for 52 weeks, before any holiday. A day rate is 8 of those hours.
HOURS_PER_YEAR = 2080.0
DAYS_PER_YEAR = 260.0
WEEKS_PER_YEAR = 52.0
MONTHS_PER_YEAR = 12.0


def normalise_interval(raw: str) -> str:
    return INTERVAL_MAP.get((raw or "").strip().lower(), "")


def annualise(amount: float | None, period: str) -> float | None:
    """Bring a rate up to a yearly figure so a floor can be compared to it.

    $600 a day is $156,000 a year, not $600, and a floor that compares the
    raw number hides the job. Anything whose period cannot be read is left
    alone rather than assumed to be yearly.
    """
    if amount is None:
        return None
    factor = {
        "year": 1.0,
        "month": MONTHS_PER_YEAR,
        "week": WEEKS_PER_YEAR,
        "day": DAYS_PER_YEAR,
        "hour": HOURS_PER_YEAR,
    }.get(period)
    return amount * factor if factor else None


def _result_for(source: str, roles: list[Role], requests_made: int,
                errors: list[str]) -> SourceResult:
    result = SourceResult(source=source, roles=roles,
                          requests_made=requests_made, errors=errors)
    # An employer board that answers 200 with nothing in it has told us
    # nothing. It could be a dead token, or it could be a throttle. Neither
    # is "this company is not hiring", so it is not reported as one.
    if requests_made and not roles and not errors:
        result.suspect = True
    return result


_WS = re.compile(r"\s+")


def clean(text: str) -> str:
    return _WS.sub(" ", (text or "")).strip()
