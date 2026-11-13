"""
jobdork.fetch.workingnomads
===========================
Working Nomads' public JSON feed: the newest remote jobs it collects, in
development, administration, design, customer success, sales, marketing and
education. No key.

    GET https://www.workingnomads.com/api/exposed_jobs/

Checked 2026-11-13. Every page of the site links this feed as "API";
robots.txt allows everything; its terms (11 March 2025) say nothing against
reading it, and forbid using the service to build a competing one, which
jobdork, a tool for one person, is not. Each job's link is its Working
Nomads address, and the source shows as Working Nomads.

  - The feed is short (36 jobs on 2026-11-13): one request a pass, a pass an
    hour at most in one running jobdork.
  - `location` is free text ("Global", "Canada", "Europe, LATAM, APAC",
    "Time zone: CET (+/- 3 hours)"); kept by it as for We Work Remotely, one
    it cannot read kept.
  - `pub_date` is ISO 8601. The advert is whole, as HTML. No pay figures.
  - No search: jobs are kept by your titles here.
"""

from __future__ import annotations

import time
from datetime import date

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .boards import clean
from .weworkremotely import region_allows

API = "https://www.workingnomads.com/api/exposed_jobs/"
PASS_SECONDS = 3600
_LAST_PASS: dict[str, float] = {}


def to_role(job: dict) -> Role | None:
    url = str(job.get("url") or "").strip()
    title = clean(job.get("title") or "")
    if not url or not title:
        return None
    where = clean(job.get("location") or "")
    flags = ["remote worldwide" if not where or where.lower() in (
        "global", "worldwide", "anywhere", "anywhere in the world")
        else f"remote, location given as {where}"]
    return Role(
        platform="workingnomads",
        company=clean(job.get("company_name") or ""),
        title=title,
        url=url,
        location_raw="Remote",
        description=to_text(job.get("description") or ""),
        posted_at=str(job.get("pub_date") or "")[:10],
        work_mode="remote",
        flags=flags,
    )


@register("workingnomads")
def fetch(fetcher, cfg, today: date | None = None, now: float | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    if cfg.locations.work_modes and "remote" not in cfg.locations.work_modes:
        return SourceResult(source="workingnomads",
                            skipped="remote jobs only, and locations.work_modes "
                                    "does not include remote")
    now = time.time() if now is None else now
    last = _LAST_PASS.get("workingnomads")
    if last is not None and now - last < PASS_SECONDS:
        minutes = int((now - last) // 60)
        return SourceResult(source="workingnomads",
                            skipped=f"read {minutes} minute{'s' * (minutes != 1)} ago; its "
                                    "feed is the newest jobs, read once an hour at most")
    _LAST_PASS["workingnomads"] = now
    countries = {c.upper() for c in cfg.locations.countries}
    result = SourceResult(source="workingnomads", requests_made=1)
    resp = fetcher.get(API)
    if not resp.ok:
        result.errors.append(str(resp.error))
        return result
    jobs = [j for j in (resp.json if isinstance(resp.json, list) else []) if isinstance(j, dict)]
    seen: set[str] = set()
    for job in jobs:
        if not region_allows(str(job.get("location") or ""), countries):
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
