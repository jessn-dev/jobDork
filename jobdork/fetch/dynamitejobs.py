"""
jobdork.fetch.dynamitejobs
==========================
Dynamite Jobs: remote jobs, many of them in operations, admin and virtual
assistance, customer support, marketing, sales, finance and e-commerce. It
has no public API; it is read the way an employer's careers site is
(fetch/site.py): its sitemap lists the jobs, and each job's page carries a
schema.org `JobPosting`.

    GET https://dynamitejobs.com/sitemap/jobs-of-company.xml
    GET https://dynamitejobs.com/company/{company}/remote-job/{title}

Checked 2026-11-13. robots.txt closes `/api/` and the account pages and
allows the job pages, and lists the sitemap; its terms (16 December 2020)
say nothing about automated reading either way. So only the sitemap and
job pages are read, robots.txt is checked for each, the pages are paced at
one a second, and each job links to its Dynamite Jobs page.

  - The sitemap lists about 500 jobs. A job's address is its title in words
    (`/remote-job/admin-ops-coordinator`), so only pages whose title words
    match one of yours are read: newest first, MAX_PAGES a scan at most.
    The site reader cannot find them itself: it looks for an id in the
    address, and these have none.
  - `applicantLocationRequirements` lists the countries that may apply;
    none listed is worldwide. A job none of your countries may apply to is
    left out.
  - `validThrough` is the closing date: a job past it is left out, and the
    page answers scripts, so "still open" reads it like any careers page.
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.parse

from . import SourceResult, register
from .robots import Robots
from .site import closed, job_posting, sitemap_urls, to_role

SITEMAP = "https://dynamitejobs.com/sitemap/jobs-of-company.xml"
MAX_PAGES = 40
PAGE_RATE = 1.0


def job_words(url: str) -> str:
    """The title in a job's address: "admin ops coordinator"."""
    path = urllib.parse.urlsplit(url).path.rstrip("/")
    if "/remote-job/" not in path:
        return ""
    return urllib.parse.unquote(path.rsplit("/", 1)[-1]).replace("-", " ").strip()


def open_to(posting: dict, countries: set[str]) -> bool:
    """Whether one of your countries may apply: none listed, or no countries
    of yours, is yes."""
    from ..search import geo

    if not countries:
        return True
    places = posting.get("applicantLocationRequirements") or []
    if isinstance(places, dict):
        places = [places]
    codes = set()
    for place in places:
        name = place.get("name") if isinstance(place, dict) else place
        code = geo.country_code(str(name or ""))
        if code:
            codes.add(code)
    return not codes or bool(codes & countries)


def who_may_apply(posting: dict) -> str:
    """The tag for the countries that may apply: "remote worldwide", up to
    four by name, or how many."""
    places = posting.get("applicantLocationRequirements") or []
    if isinstance(places, dict):
        places = [places]
    names = [str(p.get("name") if isinstance(p, dict) else p).strip() for p in places]
    names = [n for n in names if n and n != "None"]
    if not names:
        return "remote worldwide"
    return "remote, open to " + (", ".join(names) if len(names) <= 4
                                 else f"{len(names)} countries")


@register("dynamitejobs")
def fetch(fetcher, cfg, today: dt.date | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    if cfg.locations.work_modes and "remote" not in cfg.locations.work_modes:
        return SourceResult(source="dynamitejobs",
                            skipped="remote jobs only, and locations.work_modes "
                                    "does not include remote")
    today = today or dt.date.today()
    countries = {c.upper() for c in cfg.locations.countries}
    result = SourceResult(source="dynamitejobs")
    robots = Robots(fetcher)
    if not robots.allowed(SITEMAP):
        result.skipped = "its robots.txt now closes the job sitemap"
        return result
    resp = fetcher.get(SITEMAP, expect_json=False)
    result.requests_made += 1
    if not resp.ok:
        result.errors.append(f"sitemap: {resp.error}")
        return result
    _children, pages = sitemap_urls(resp.body or "")
    jobs = [(u, m) for u, m in pages if job_words(u)]
    if not jobs:
        result.suspect = True
        return result
    chosen = [(u, m) for u, m in jobs if title_verdict(job_words(u), cfg)[0]]
    # lambda: sort key, (url, lastmod) pairs by date, newest first.
    chosen.sort(key=lambda pair: pair[1], reverse=True)
    if hasattr(fetcher, "pace"):
        fetcher.pace("dynamitejobs.com", PAGE_RATE)
    for url, _ in chosen[:MAX_PAGES]:
        if not robots.allowed(url):
            continue
        page = fetcher.get(url, expect_json=False)
        result.requests_made += 1
        if not page.ok:
            continue
        posting = job_posting(page.body or "")
        if not posting or closed(posting, today) or not open_to(posting, countries):
            continue
        role = to_role(posting, url, "")
        if role is None:
            continue
        role.platform = "dynamitejobs"
        role.work_mode = "remote"
        role.location_raw = role.location_raw or "Remote"
        # Its titles end ", Remote Job", which says nothing the source does not.
        role.title = re.sub(r",?\s*remote job$", "", role.title, flags=re.IGNORECASE).strip()
        role.flags.append(who_may_apply(posting))
        result.roles.append(role)
    if len(chosen) > MAX_PAGES:
        result.complete = False
    return result
