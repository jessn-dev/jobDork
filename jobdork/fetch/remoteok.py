"""
jobdork.fetch.remoteok
======================
Remote OK's public API: the newest remote jobs, about a hundred, in support,
operations, healthcare, marketing and finance as well as software. No key.

    GET https://remoteok.com/api

Checked 2026-11-13. The answer's first element is its terms: link back to
the job's Remote OK page and name Remote OK as the source, and do not use its
logo. The stored link is the Remote OK page, the source shows as Remote OK,
and no logo is kept. robots.txt allows every reader but named AI crawlers
(jobdork is not one), with a one-second delay; its content signal reserves AI
training, which jobdork never does.

  - One request a pass; the list is the newest jobs, so a pass an hour at
    most in one running jobdork, as for Jobicy.
  - `location` is free text and mostly empty: "Remote", "Anywhere in the
    World", "EMEA", or a city. Kept by it as for We Work Remotely; an empty
    or unknown one is kept.
  - `salary_min` / `salary_max` are US dollars a year; 0 means not given.
  - `date` is ISO 8601. The advert is whole, as HTML. The job pages answer
    scripts, so "still open" reads them like any page.
  - No search: jobs are kept by your titles here.
  - Some of its text is UTF-8 that was read as Latin-1 and encoded again
    ("Engineer \u00e2\u0080\u0094 Kubernetes" for an em dash): mended here
    when that is the only reading that makes sense (_mended).
"""

from __future__ import annotations

import re
import time
from datetime import date

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .boards import clean
from .weworkremotely import region_allows

API = "https://remoteok.com/api"
PASS_SECONDS = 3600
_LAST_PASS: dict[str, float] = {}


# A UTF-8 lead byte followed by a continuation byte, both read as Latin-1.
_DOUBLE = re.compile("[\u00c2-\u00f4][\u0080-\u00bf]")


def _mended(text) -> str:
    """Text double-encoded at the source decoded back; anything else as it
    is: "café" written properly fails the round trip and is left alone."""
    text = str(text or "")
    if not _DOUBLE.search(text):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _number(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def to_role(job: dict) -> Role | None:
    url = str(job.get("url") or "").strip()
    title = clean(_mended(job.get("position")))
    if not url or not title:
        return None
    where = clean(_mended(job.get("location")))
    flags = ["remote worldwide" if not where or where.lower() in (
        "remote", "anywhere", "anywhere in the world", "worldwide")
        else f"remote, location given as {where}"]
    lo, hi = _number(job.get("salary_min")), _number(job.get("salary_max"))
    stated = bool(lo or hi)
    return Role(
        platform="remoteok",
        company=clean(_mended(job.get("company"))),
        title=title,
        url=url,
        location_raw="Remote",
        description=to_text(_mended(job.get("description"))),
        posted_at=str(job.get("date") or "")[:10],
        work_mode="remote",
        salary_min=lo,
        salary_max=hi,
        salary_currency="USD" if stated else "",
        salary_period="year" if stated else "",
        salary_stated=stated,
        flags=flags,
    )


@register("remoteok")
def fetch(fetcher, cfg, today: date | None = None, now: float | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    if cfg.locations.work_modes and "remote" not in cfg.locations.work_modes:
        return SourceResult(source="remoteok", skipped="remote jobs only, and locations.work_modes "
                                                       "does not include remote")
    now = time.time() if now is None else now
    last = _LAST_PASS.get("remoteok")
    if last is not None and now - last < PASS_SECONDS:
        minutes = int((now - last) // 60)
        return SourceResult(source="remoteok",
                            skipped=f"read {minutes} minute{'s' * (minutes != 1)} ago; its list "
                                    "is the newest jobs, read once an hour at most")
    _LAST_PASS["remoteok"] = now
    countries = {c.upper() for c in cfg.locations.countries}
    result = SourceResult(source="remoteok")
    resp = fetcher.get(API)
    result.requests_made = 1
    if not resp.ok:
        result.errors.append(str(resp.error))
        return result
    # The first element is the terms, not a job.
    jobs = [j for j in (resp.json if isinstance(resp.json, list) else [])
            if isinstance(j, dict) and j.get("position")]
    seen: set[str] = set()
    for job in jobs:
        if not region_allows(str(job.get("location") or ""), countries):
            continue
        if not title_verdict(str(job.get("position") or ""), cfg)[0]:
            continue
        role = to_role(job)
        if role and role.uid not in seen:
            seen.add(role.uid)
            result.roles.append(role)
    if not jobs:
        result.suspect = True
    return result
