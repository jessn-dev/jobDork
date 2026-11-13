"""
jobdork.fetch.jobicy
====================
Jobicy's public Jobs API: remote jobs in sales, marketing, finance,
healthcare and operations as well as software. No key, no account.

    GET https://jobicy.com/api/jobs?count=100&geo=usa

Checked 2026-11-13 against its documentation (jobi.cy/apidocs) and terms.
Its terms let any application use the public API without an agreement,
commercial ones included, as long as Jobicy is credited and the link goes to
the Jobicy listing: the stored link is the listing, and the source shows as
Jobicy. Storing the jobs is allowed. robots.txt allows the API.

  - The API returns jobs published in the last 7 days (each 3 hours after it
    is posted), 100 a page at most, the next page by `cursor`. A scan reads
    up to MAX_PAGES pages: one pass.
  - **One pass an hour at most**, as the documentation asks. A scan within
    the hour of the last one, in the same running jobdork, skips Jobicy and
    says so. (Scans from the scheduler run hours apart already.)
  - `geo` narrows to a region by slug; "usa" is used when the US is your only
    country. Otherwise every job is read and kept by `jobGeo` ("USA",
    "Anywhere", "Canada, USA", "EMEA, LATAM, Canada, USA"), as for We Work
    Remotely.
  - Pay is `salaryMin` / `salaryMax` with `salaryCurrency` and `salaryPeriod`
    ("yearly", "hourly"), on about six jobs in ten.
  - The advert is whole, as HTML. The job pages carry their job data, so
    "still open" reads them like any careers page.
  - The API has no search by title for many titles at once: jobs are kept by
    your titles here.
"""

from __future__ import annotations

import time
from datetime import date

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .boards import clean, normalise_interval
from .weworkremotely import region_allows

API = "https://jobicy.com/api/jobs"
PAGE_SIZE = 100
MAX_PAGES = 10
PASS_SECONDS = 3600
# When this jobdork last made a pass: the documentation's "no more than once
# per hour", kept in memory so a test never writes a file next to a database.
_LAST_PASS: dict[str, float] = {}


def _listed(value) -> list[str]:
    """`jobType` and `jobIndustry` come as lists ("['Contract']")."""
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [v.strip(" '\"") for v in str(value or "").strip("[]").split(",") if v.strip(" '\"")]


def _number(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def to_role(job: dict) -> Role | None:
    url = str(job.get("url") or "").strip()
    title = clean(job.get("jobTitle") or "")
    if not url or not title:
        return None
    where = clean(job.get("jobGeo") or "")
    flags = ["remote worldwide" if not where or where.lower() in ("anywhere", "worldwide")
             else "remote, open to " + ", ".join(p.strip() for p in where.split(",") if p.strip())]
    if any(t.lower() == "contract" for t in _listed(job.get("jobType"))):
        flags.append("contract")
    lo, hi = _number(job.get("salaryMin")), _number(job.get("salaryMax"))
    currency = str(job.get("salaryCurrency") or "").strip()
    stated = bool(currency and (lo or hi))
    posted = str(job.get("pubDate") or "")[:10]
    return Role(
        platform="jobicy",
        company=clean(job.get("companyName") or ""),
        title=title,
        url=url,
        location_raw="Remote",
        description=to_text(job.get("jobDescription") or job.get("jobExcerpt") or ""),
        posted_at=posted,
        work_mode="remote",
        salary_min=lo if stated else None,
        salary_max=hi if stated else None,
        salary_currency=currency if stated else "",
        salary_period=normalise_interval(str(job.get("salaryPeriod") or "")) if stated else "",
        salary_stated=stated,
        flags=flags,
    )


@register("jobicy")
def fetch(fetcher, cfg, today: date | None = None, now: float | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    if cfg.locations.work_modes and "remote" not in cfg.locations.work_modes:
        return SourceResult(source="jobicy", skipped="remote jobs only, and locations.work_modes "
                                                     "does not include remote")
    now = time.time() if now is None else now
    last = _LAST_PASS.get("jobicy")
    if last is not None and now - last < PASS_SECONDS:
        minutes = int((now - last) // 60)
        return SourceResult(source="jobicy",
                            skipped=f"read {minutes} minute{'s' * (minutes != 1)} ago; Jobicy asks "
                                    "for one pass an hour at most")
    _LAST_PASS["jobicy"] = now
    countries = {c.upper() for c in cfg.locations.countries}
    params: dict = {"count": PAGE_SIZE}
    if countries == {"US"}:
        params["geo"] = "usa"
    result = SourceResult(source="jobicy")
    seen: set[str] = set()
    listed = 0
    cursor = ""
    for page in range(MAX_PAGES):
        resp = fetcher.get(API, params={**params, **({"cursor": cursor} if cursor else {})})
        result.requests_made += 1
        if not resp.ok:
            result.errors.append(f"page {page + 1}: {resp.error}")
            break
        payload = resp.json if isinstance(resp.json, dict) else {}
        jobs = payload.get("jobs") or []
        listed += len(jobs)
        for job in jobs:
            if not region_allows(str(job.get("jobGeo") or ""), countries):
                continue
            if not title_verdict(str(job.get("jobTitle") or ""), cfg)[0]:
                continue
            role = to_role(job)
            if role and role.uid not in seen:
                seen.add(role.uid)
                result.roles.append(role)
        cursor = str(payload.get("nextCursor") or "")
        if not jobs or not cursor:
            break
    if result.requests_made and not listed and not result.errors:
        result.suspect = True
    return result
