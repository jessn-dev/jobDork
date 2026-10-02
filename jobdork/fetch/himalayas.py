"""
jobdork.fetch.himalayas
=======================
Himalayas' public remote-jobs search. No key, no account.

    GET https://himalayas.app/jobs/api/search?q=...&country=PH&sort=recent&page=1

Remote jobs only, worldwide, about 93,000 of them. Verified against the live
API and its documentation (himalayas.app/api):

  - `country` takes an ISO code and returns jobs open to that country,
    including ones open worldwide (`locationRestrictions: []`). That matters
    more than anything else here: most "remote" jobs from US employers are
    remote within the US, and a list of them is a list of jobs you cannot take.
  - `timezoneRestrictions` lists the UTC offsets a job accepts. A job open to
    the Philippines may still want US hours; one whose offsets do not come
    within an hour of yours is left out. Your offset is read from the
    anchor's longitude (15 degrees an hour), which needs no time-zone
    database and is right to within the hour the check allows.
  - 20 jobs a request at most, `page` from 1, `sort=recent`. No published
    rate limit beyond "429 when exceeded"; paced at one a second.
  - `pubDate` and `expiryDate` are Unix seconds. A post past its expiry is
    not returned, and its closing date is kept for the "still open" check.
  - Pay is `minSalary` / `maxSalary` with `currency` and `salaryPeriod`; a
    figure with no currency is not compared.
  - **Job pages answer 403 to scripts** (robots.txt allows them, the server
    does not). "Still open" goes by the expiry date, then by whether the post
    was in the latest search (listing.py), as for Kalibrr and Adzuna.

Their terms ask that a job links back to Himalayas and names it as the
source: the stored link is the Himalayas page, and the source shows as
Himalayas.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from ..core.textutil import to_text
from ..db.store import Role
from ..search import geo
from . import SourceResult, register
from .boards import clean, normalise_interval

API = "https://himalayas.app/jobs/api/search"
PAGE_SIZE = 20
# Three pages is 60 of the most recent per title per country. Remote posts
# draw hundreds of applicants in days; deeper pages are mostly too old to
# be worth one.
MAX_PAGES = 3
TZ_SLACK = 1.0           # hours either side of the job's accepted offsets


def utc_offset(cfg) -> float | None:
    """Your UTC offset, from the anchor's longitude; None if it has no place."""
    if not cfg.locations.anchor.strip():
        return None
    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    lon = getattr(anchor, "lon", None)
    return round(lon / 15) if anchor.located and lon is not None else None


def _day(seconds) -> date | None:
    try:
        return datetime.fromtimestamp(int(seconds), timezone.utc).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _to_role(job: dict, today: date, offset: float | None) -> Role | None:
    url = (job.get("applicationLink") or job.get("guid") or "").strip()
    if not url:
        return None
    ends = _day(job.get("expiryDate"))
    if ends and ends < today:
        return None
    zones = [z for z in (job.get("timezoneRestrictions") or []) if isinstance(z, (int, float))]
    if offset is not None and zones and min(abs(z - offset) for z in zones) > TZ_SLACK:
        return None                         # their working hours, not yours

    allowed = [c for c in (job.get("locationRestrictions") or []) if c]
    flags = ["remote worldwide" if not allowed else
             "remote, open to " + (", ".join(allowed) if len(allowed) <= 4
                                   else f"{len(allowed)} countries")]
    if zones and len(zones) < 20:
        flags.append("hours: UTC" + ", ".join(f"{z:+g}" for z in sorted(zones)))
    if ends:
        flags.append(f"applications close {ends.isoformat()}")

    lo, hi = job.get("minSalary"), job.get("maxSalary")
    currency = job.get("currency") or ""
    stated = bool(currency and (lo or hi))
    posted = _day(job.get("pubDate"))
    return Role(
        platform="himalayas",
        company=clean(job.get("companyName") or ""),
        title=clean(job.get("title") or ""),
        url=url,
        location_raw="Remote",
        description=to_text(job.get("description") or job.get("excerpt") or ""),
        posted_at=posted.isoformat() if posted else "",
        work_mode="remote",
        salary_min=float(lo) if stated and lo else None,
        salary_max=float(hi) if stated and hi else None,
        salary_currency=currency if stated else "",
        salary_period=normalise_interval(job.get("salaryPeriod") or "") if stated else "",
        salary_stated=stated,
        flags=flags,
    )


@register("himalayas")
def fetch(fetcher, cfg, today: date | None = None, **_) -> SourceResult:
    if cfg.locations.work_modes and "remote" not in cfg.locations.work_modes:
        return SourceResult(source="himalayas",
                            skipped="remote jobs only, and locations.work_modes "
                                    "does not include remote")
    today = today or datetime.now(timezone.utc).date()
    offset = utc_offset(cfg)
    countries = list(cfg.locations.countries) or [""]
    result = SourceResult(source="himalayas")
    seen: set[str] = set()

    for title in cfg.titles_include:
        for country in countries:
            for page in range(1, MAX_PAGES + 1):
                params = {"q": title, "sort": "recent", "page": page}
                if country:
                    params["country"] = country
                resp = fetcher.get(API, params=params)
                result.requests_made += 1
                if not resp.ok:
                    result.errors.append(f"{title!r} {country}: {resp.error}")
                    break
                payload = resp.json if isinstance(resp.json, dict) else {}
                jobs = payload.get("jobs") or []
                for job in jobs:
                    role = _to_role(job, today, offset)
                    if role and role.uid not in seen:
                        seen.add(role.uid)
                        result.roles.append(role)
                if len(jobs) < PAGE_SIZE or page * PAGE_SIZE >= (payload.get("totalCount") or 0):
                    break

    if result.requests_made and not result.roles and not result.errors:
        result.suspect = True
    return result
