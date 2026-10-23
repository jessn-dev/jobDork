"""
jobdork.fetch.arbeitnow
=======================
Arbeitnow's free job board API: jobs in Germany and the rest of Europe
(London, Paris, Amsterdam, Zurich…), many of them in English. No key.

    GET https://www.arbeitnow.com/api/job-board-api?page=1

Checked live 2026-10-23. The API has no search: every job, newest first, 300
a page, about 600 new a day. So the newest pages are read and filtered by
your titles here, back to MAX_DAYS old and at most MAX_PAGES pages (about
five days of jobs), one every two seconds: at one a second, scans of
several cities in a row met a 429 at the fifteenth page. Its terms ask not to abuse it and to link back: the
stored link is the job's Arbeitnow page, and the source shows as Arbeitnow.
robots.txt allows the API.

  - `created_at` is Unix seconds; `remote` is true for remote jobs.
  - The place is often a bare city ("Amsterdam", "London"). Screening places
    a bare city only in your own countries, and keeps one it cannot place,
    so for someone in Stockholm every Amsterdam job was kept (84 of 143,
    2026-10-23). Each bare city is placed in Europe here and its country
    added: "Amsterdam, Netherlands".
  - The advert is HTML, and whole.
  - No pay figures.

Runs when one of your countries is in Europe, or when you have none.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from ..core.textutil import to_text
from ..db.store import Role
from ..search import geo
from . import SourceResult, register
from .boards import clean

API = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 10
MAX_DAYS = 21

# Where its jobs are: Europe. A config with none of these has nothing to
# find here.
EUROPE = frozenset((
    "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB",
    "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT", "NL", "NO",
    "PL", "PT", "RO", "SE", "SI", "SK",
))
# Where a bare city is looked for, the countries with the most of its jobs first.
PLACES = ("DE", "GB", "NL", "FR", "CH", "AT", *sorted(EUROPE - {"DE", "GB", "NL", "FR", "CH", "AT"}))


def _day(seconds) -> date | None:
    try:
        return datetime.fromtimestamp(int(seconds), timezone.utc).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _place(location: str) -> str:
    """The place with its country, when it names a European city and no
    country: "Amsterdam" is "Amsterdam, Netherlands". Several places
    ("Nantes; Paris") each get theirs."""
    parts = [p.strip() for p in location.split(";") if p.strip()]
    placed = []
    for part in parts:
        if "," not in part:
            where = geo.resolve(part, PLACES)
            if where.located and where.country in EUROPE:
                part = f"{part}, {geo.country_name(where.country)}"
        placed.append(part)
    return "; ".join(placed)


def to_role(job: dict) -> Role | None:
    url = str(job.get("url") or "").strip()
    title = clean(job.get("title") or "")
    if not url or not title:
        return None
    posted = _day(job.get("created_at"))
    remote = bool(job.get("remote"))
    return Role(
        platform="arbeitnow",
        company=clean(job.get("company_name") or ""),
        title=title,
        url=url,
        location_raw=_place(str(job.get("location") or "").strip()) or ("Remote" if remote else ""),
        description=to_text(job.get("description") or ""),
        posted_at=posted.isoformat() if posted else "",
        work_mode="remote" if remote else "",
    )


@register("arbeitnow")
def fetch(fetcher, cfg, today: date | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    wanted = {c.upper() for c in cfg.locations.countries}
    if wanted and not wanted & EUROPE:
        return SourceResult(source="arbeitnow",
                            skipped="jobs in Europe only, and no European country "
                                    "is in locations.countries")
    today = today or datetime.now(timezone.utc).date()
    result = SourceResult(source="arbeitnow")
    seen: set[str] = set()
    listed = 0
    for page in range(1, MAX_PAGES + 1):
        resp = fetcher.get(API, params={"page": page})
        result.requests_made += 1
        if not resp.ok:
            result.errors.append(f"page {page}: {resp.error}")
            break
        payload = resp.json if isinstance(resp.json, dict) else {}
        jobs = payload.get("data") or []
        listed += len(jobs)
        oldest = None
        for job in jobs:
            posted = _day(job.get("created_at"))
            oldest = posted if posted and (not oldest or posted < oldest) else oldest
            if posted and (today - posted).days > MAX_DAYS:
                continue
            if not title_verdict(str(job.get("title") or ""), cfg)[0]:
                continue
            role = to_role(job)
            if role and role.uid not in seen:
                seen.add(role.uid)
                result.roles.append(role)
        next_page = (payload.get("links") or {}).get("next")
        if not jobs or not next_page or (oldest and (today - oldest).days > MAX_DAYS):
            break
    if not listed and not result.errors:      # the board is never empty
        result.suspect = True
    return result
