"""
jobdork.fetch.kalibrr
=====================
Kalibrr's own job search, which its site reads. No key, no account.

    GET https://www.kalibrr.com/kjs/job_board/search?text=...&limit=50&offset=0

A Philippine job site (Indonesia too) that also hosts many employers' own
careers pages, which makes it one of the few ways to reach Philippine
employers that run no Greenhouse or Lever board. `robots.txt` closes only
`/root` and `/candidate/profile`. Verified against the live search:

  - `text` searches titles and adverts loosely ("software engineer" put a
    marketing internship first). Screening's title match does the real work.
  - `limit` 50 and `offset` page cleanly, no overlap; `count` is the total.
  - There is no location parameter worth trusting, and results mix the
    Philippines and Indonesia, so the country is read off each job
    (`google_location`) and the radius measured locally.
  - **Dates are the best of any source here:** `activation_date` is when the
    post went live, `application_end_date` when applications close, and
    `es_recruiter_last_seen` when someone last looked at the applicants. A
    post past its closing date is not returned; one whose recruiter has not
    been seen in a month is flagged, the clearest ghost signal a board gives.
  - Pay comes as `base_salary` / `maximum_salary` with a currency and an
    interval, and only counts when `salary_shown` is true: a hidden figure is
    the employer's private range, not a stated one.
  - `is_work_from_home` and `is_hybrid` are the arrangement. Both false is
    left unstated rather than read as on-site: an unset form looks the same.
  - **Job pages answer 403 to anything but a browser.** The link works for
    you; "still open" cannot read it, and goes by the closing date and by
    whether the job was still in the last search (listing.py), as for Adzuna.
"""

from __future__ import annotations

from datetime import date, datetime

from ..core.textutil import to_text
from ..db.store import Role
from ..search import freshness
from . import SourceResult, register
from .boards import clean, normalise_interval

API = "https://www.kalibrr.com/kjs/job_board/search"
JOB_URL = "https://www.kalibrr.com/c/{company}/jobs/{id}/{slug}"
PAGE_SIZE = 50
# Four pages is 200 posts a title, sorted by Kalibrr's relevance, which is
# loose; past that it is mostly other jobs that mention the words.
MAX_PAGES = 4
COUNTRIES = {"Philippines": "PH", "Indonesia": "ID"}
# A recruiter not seen in this long is not reading applications.
RECRUITER_IDLE_DAYS = 30


def _address(job: dict) -> dict:
    return ((job.get("google_location") or {}).get("address_components") or {})


def _to_role(job: dict, today: date) -> Role | None:
    company = job.get("company") or {}
    if not (job.get("id") and company.get("code")):
        return None
    ends = freshness.parse_date(job.get("application_end_date") or "")
    if ends and ends < today:
        return None                     # applications closed: not a job any more

    where = _address(job)
    location_raw = ", ".join(x for x in (where.get("city"), where.get("region"),
                                         where.get("country")) if x)
    description = to_text(job.get("description") or "")
    qualifications = to_text(job.get("qualifications") or "")
    if qualifications:
        description = f"{description}\n\nQualifications\n{qualifications}".strip()

    lo, hi = job.get("base_salary"), job.get("maximum_salary")
    stated = bool(job.get("salary_shown") and (lo or hi))

    flags = []
    seen = (job.get("es_recruiter_last_seen") or "")[:10]
    last = freshness.parse_date(seen)
    if last and (today - last).days > RECRUITER_IDLE_DAYS:
        flags.append(f"recruiter last active {seen}, {(today - last).days} days ago: "
                     "applications may not be read")
    if ends:
        flags.append(f"applications close {ends.isoformat()}")

    mode = ("remote" if job.get("is_work_from_home")
            else "hybrid" if job.get("is_hybrid") else "")
    return Role(
        platform="kalibrr",
        company=clean(job.get("company_name") or company.get("name") or ""),
        title=clean(job.get("name") or ""),
        url=JOB_URL.format(company=company["code"], id=job["id"],
                           slug=job.get("slug") or "job"),
        location_raw=location_raw,
        description=description,
        posted_at=(job.get("activation_date") or job.get("created_at") or "")[:10],
        work_mode=mode,
        salary_min=float(lo) if stated and lo else None,
        salary_max=float(hi) if stated and hi else None,
        salary_currency=(job.get("salary_currency") or "") if stated else "",
        salary_period=normalise_interval(job.get("salary_interval") or "") if stated else "",
        salary_stated=stated,
        flags=flags,
    )


@register("kalibrr")
def fetch(fetcher, cfg, today: date | None = None, **_) -> SourceResult:
    wanted = set(cfg.locations.countries)
    if wanted and not wanted & set(COUNTRIES.values()):
        return SourceResult(
            source="kalibrr",
            skipped="Philippine and Indonesian postings only, and neither is in "
                    "locations.countries")
    today = today or datetime.now().date()
    result = SourceResult(source="kalibrr")
    seen: set[str] = set()

    # The search answers with Philippine jobs unless asked for a country by
    # name: without `country=Indonesia`, an Indonesian search found 2 jobs
    # where there were dozens. One search per country you want.
    names = [name for name, code in COUNTRIES.items() if not wanted or code in wanted]
    for title, name in ((t, n) for t in cfg.titles_include for n in names):
        for page in range(MAX_PAGES):
            resp = fetcher.get(API, params={"text": title, "limit": PAGE_SIZE,
                                            "offset": page * PAGE_SIZE, "country": name})
            result.requests_made += 1
            if not resp.ok:
                result.errors.append(f"{title!r}: {resp.error}")
                break
            payload = resp.json if isinstance(resp.json, dict) else {}
            jobs = payload.get("jobs") or []
            for job in jobs:
                country = COUNTRIES.get(_address(job).get("country") or "", "")
                if wanted and country not in wanted:
                    continue
                role = _to_role(job, today)
                if role and role.uid not in seen:
                    seen.add(role.uid)
                    result.roles.append(role)
            if len(jobs) < PAGE_SIZE or (page + 1) * PAGE_SIZE >= (payload.get("count") or 0):
                break

    if result.requests_made and not result.roles and not result.errors:
        result.suspect = True
    return result
