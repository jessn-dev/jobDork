"""
jobdork.fetch.remotive
======================
Remotive's public API: remote jobs, software, customer service, sales,
writing and the rest. No key.

    GET https://remotive.com/api/remote-jobs

Checked 2026-11-13. Its documentation (github.com/remotive-com/remote-jobs-api)
invites applications to use this endpoint: link back to the job's Remotive
page and name Remotive as the source, read it at most about four times a
day and never more than twice a minute, and do not pass its jobs on to other
sites. The stored link is the Remotive page and the source shows as Remotive.

**Its robots.txt says `Disallow: /api/*`.** jobdork follows robots.txt
everywhere else; here the owner of jobdork decided the API's own
documentation, which names this endpoint for third-party use, wins over a
line aimed at crawlers (2026-11-13). docs/PLATFORMS.md says so.

  - The public list is short (14 jobs on 2026-11-13) and 24 hours behind the
    site, as its documentation says.
  - One request a pass, a pass every six hours at most in one running
    jobdork: four a day.
  - `candidate_required_location` says who may apply ("Worldwide", "USA",
    "LATAM, Europe, USA, Canada, APAC"); kept by it as for We Work Remotely.
  - `salary` is free text ("$14 - $20/hour", "$25k - $35k", "OTE $25k -
    $35k"): read when it is in dollars and its period is stated or plain
    from the figures (a "k" or five-figure amount is a year's); otherwise not
    stated.
  - `publication_date` is ISO 8601. The advert is whole, as HTML.
  - No search by many titles: jobs are kept by your titles here.
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

API = "https://remotive.com/api/remote-jobs"
PASS_SECONDS = 6 * 3600
_LAST_PASS: dict[str, float] = {}

_AMOUNT = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?", re.IGNORECASE)
_PERIOD = (("hour", re.compile(r"/\s*h(?:ou)?r|hourly|per hour|an hour", re.IGNORECASE)),
           ("month", re.compile(r"/\s*mo(?:nth)?|monthly|per month", re.IGNORECASE)),
           ("year", re.compile(r"/\s*y(?:ea)?r|yearly|annual|per year|a year", re.IGNORECASE)))


def _figure(text: str) -> float:
    """"90,000" is ninety thousand; "35,3" (in "$35,3k") is 35.3: a comma
    groups thousands only when three digits follow it."""
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
        return float(text.replace(",", ""))
    return float(text.replace(",", "."))


def pay(text: str) -> tuple[float | None, float | None, str, str, bool]:
    """(min, max, currency, period, stated) from Remotive's salary text.
    Only dollars, and only with a period it states or a "k" figure (a
    year's); anything else is not stated rather than guessed."""
    figures = [(_figure(n) * (1000 if k else 1), bool(k)) for n, k in _AMOUNT.findall(text or "")]
    if not figures:
        return None, None, "", "", False
    period = next((name for name, pattern in _PERIOD if pattern.search(text)), "")
    # A "k" figure, or one of five figures, is a year's pay: no hourly or
    # monthly rate is that high.
    if not period and any(k or f >= 10_000 for f, k in figures):
        period = "year"
    if not period:
        return None, None, "", "", False
    lo, hi = min(f for f, _ in figures), max(f for f, _ in figures)
    return lo, hi if hi != lo else None, "USD", period, True


def to_role(job: dict) -> Role | None:
    url = str(job.get("url") or "").strip()
    title = clean(job.get("title") or "")
    if not url or not title:
        return None
    where = clean(job.get("candidate_required_location") or "")
    flags = ["remote worldwide" if not where or where.lower() in ("worldwide", "anywhere")
             else f"remote, open to {where}"]
    if str(job.get("job_type") or "").lower() == "contract":
        flags.append("contract")
    lo, hi, currency, period, stated = pay(str(job.get("salary") or ""))
    return Role(
        platform="remotive",
        company=clean(job.get("company_name") or ""),
        title=title,
        url=url,
        location_raw="Remote",
        description=to_text(job.get("description") or ""),
        posted_at=str(job.get("publication_date") or "")[:10],
        work_mode="remote",
        salary_min=lo, salary_max=hi, salary_currency=currency,
        salary_period=period, salary_stated=stated,
        flags=flags,
    )


@register("remotive")
def fetch(fetcher, cfg, today: date | None = None, now: float | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    if cfg.locations.work_modes and "remote" not in cfg.locations.work_modes:
        return SourceResult(source="remotive", skipped="remote jobs only, and locations.work_modes "
                                                       "does not include remote")
    now = time.time() if now is None else now
    last = _LAST_PASS.get("remotive")
    if last is not None and now - last < PASS_SECONDS:
        hours = (now - last) / 3600
        return SourceResult(source="remotive",
                            skipped=f"read {hours:.1f} hours ago; Remotive asks for about "
                                    "four reads a day")
    _LAST_PASS["remotive"] = now
    countries = {c.upper() for c in cfg.locations.countries}
    result = SourceResult(source="remotive", requests_made=1)
    resp = fetcher.get(API)
    if not resp.ok:
        result.errors.append(str(resp.error))
        return result
    payload = resp.json if isinstance(resp.json, dict) else {}
    jobs = [j for j in payload.get("jobs") or [] if isinstance(j, dict)]
    seen: set[str] = set()
    for job in jobs:
        if not region_allows(str(job.get("candidate_required_location") or ""), countries):
            continue
        if not title_verdict(str(job.get("title") or ""), cfg)[0]:
            continue
        role = to_role(job)
        if role and role.uid not in seen:
            seen.add(role.uid)
            result.roles.append(role)
    if not jobs:
        result.suspect = True
    return result
