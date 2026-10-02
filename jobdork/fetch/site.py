"""
jobdork.fetch.site
==================
An employer's own careers site, read through what it publishes for search
engines: its sitemap lists the postings, and each posting page carries a
schema.org `JobPosting` with title, place, date and the full advert.

This is how jobdork reads employers whose applicant tracking system has no
reader here: Kaiser Permanente, UnitedHealth Group and Mayo Clinic run
sites that list every posting in a sitemap and mark each one up for
Google, as do Wells Fargo, State Farm, UPS and General Motors. The token is
the careers site's address (`https://jobs.mayoclinic.org`), found by
`discover`.

What it costs, and how that is kept down:

  - The sitemap is read every scan: a few requests, whatever its size.
  - A posting page is one request each, so a page is only read when its
    address carries one of your titles (`/job/rochester/ecmo-specialist-rn/…`
    for "rn"). A site whose addresses carry no words at all
    (`/jobs/46295`) is read newest first, up to MAX_UNTITLED pages.
  - At most MAX_PAGES posting pages per site per scan.
  - robots.txt is honoured for the sitemap and every page, and the pages
    are paced at SITE_RATE a second.

A posting whose `validThrough` has passed is left out: the site itself says
it has closed.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import urllib.parse

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .boards import annualise, clean, normalise_interval
from .robots import Robots

# A single posting's address: a jobs word, then a part with three digits in a
# row (an id), as in /job/irvine/nursing-attendant/641/10035, /jobs/R-1075582
# or /careers/listing/ai-engineer/8044460. Category pages carry no id.
POSTING = re.compile(
    r"/(?:job|jobs|posting|postings|listing|listings|position|positions|"
    r"requisition|requisitions|career|careers|vacancy|vacancies|opening|openings)"
    r"/(?:[^/?#]*/)*[^/?#]*\d{3,}", re.IGNORECASE)
# A locale part of an address: /en/, /en-us/, /fr_CA/. The same posting is
# listed once per language; one is enough.
_LOCALE = re.compile(r"^[a-z]{2}(?:[-_][a-z]{2})?$", re.IGNORECASE)
# Words in an address that say where it is, not what the job is.
_ROUTE_WORDS = {"job", "jobs", "posting", "postings", "listing", "listings",
                "position", "positions", "requisition", "requisitions", "career",
                "careers", "vacancy", "vacancies", "opening", "openings", "apply",
                "details", "detail", "view", "en", "us"}

MAX_SITEMAP_READS = 8       # index plus children
MAX_PAGES = 40              # posting pages read per site per scan
MAX_UNTITLED = 20           # of those, for a site whose addresses carry no words
SITE_RATE = 1.0             # posting pages a second, per site

log = logging.getLogger("jobdork.fetch.site")

_LD_BLOCK = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL)


def _postings_in(node) -> list[dict]:
    """JobPosting objects anywhere in a JSON-LD block."""
    found: list[dict] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_postings_in(item))
    elif isinstance(node, dict):
        kind = node.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            found.append(node)
        for key in ("@graph", "mainEntity", "itemListElement", "item"):
            if key in node:
                found.extend(_postings_in(node[key]))
    return found


def job_posting(html: str) -> dict:
    """The page's schema.org JobPosting, or {}."""
    for block in _LD_BLOCK.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        postings = _postings_in(data)
        if postings:
            return postings[0]
    return {}


def posting_key(url: str) -> str:
    """One key per posting, whatever language its address is in."""
    parts = [p for p in urllib.parse.urlsplit(url).path.split("/") if p]
    ids = [p for p in parts if re.search(r"\d{3,}", p)]
    if ids:
        return ids[-1].lower()
    return "/".join(p for p in parts if not _LOCALE.match(p)).lower()


def slug_title(url: str) -> str:
    """The words in an address, as a title to match: "" when it has none."""
    parts = [p for p in urllib.parse.urlsplit(url).path.split("/") if p]
    words = []
    for part in parts:
        if _LOCALE.match(part) or part.lower() in _ROUTE_WORDS:
            continue
        split = [w for w in re.split(r"[-_+.%\s]+", urllib.parse.unquote(part)) if w]
        for i, word in enumerate(split):
            if re.search(r"\d", word):
                continue
            # An id's prefix: the R of R-565079, the JR of JR-202601927.
            if len(word) <= 3 and i + 1 < len(split) and re.search(r"\d", split[i + 1]):
                continue
            words.append(word.lower())
    return " ".join(w for w in words if w not in _ROUTE_WORDS)


def _sitemap_urls(xml: str) -> tuple[list[str], list[tuple[str, str]]]:
    """(child sitemaps, [(page, lastmod)]) in a sitemap or sitemap index."""
    if re.search(r"<sitemapindex", xml, re.IGNORECASE):
        return [u.strip() for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml, re.I)], []
    pages = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.IGNORECASE | re.DOTALL):
        loc = re.search(r"<loc>\s*([^<]+?)\s*</loc>", block, re.I)
        mod = re.search(r"<lastmod>\s*([^<]+?)\s*</lastmod>", block, re.I)
        if loc:
            pages.append((loc.group(1).strip(), mod.group(1).strip() if mod else ""))
    return [], pages


def postings(fetcher, site: str, robots: Robots | None = None,
             max_reads: int = MAX_SITEMAP_READS) -> tuple[list[tuple[str, str]], int]:
    """([(posting address, lastmod)], sitemap reads) from a site's sitemaps.

    A sitemap index is followed into its children whose address says jobs or
    careers (every child, when none does), up to `max_reads` reads in all.
    Gzipped sitemaps are skipped rather than unpacked.
    """
    robots = robots or Robots(fetcher)
    pending = [u for u in robots.sitemap_list(site) if not u.lower().endswith(".gz")]
    seen: set[str] = set()
    found: dict[str, tuple[str, str]] = {}
    reads = 0
    while pending and reads < max_reads:
        url = pending.pop(0)
        if url in seen or not robots.allowed(url):
            continue
        seen.add(url)
        resp = fetcher.get(url, expect_json=False)
        reads += 1
        if not resp.ok or not resp.body:
            continue
        children, pages = _sitemap_urls(resp.body)
        children = [c for c in children if not c.lower().endswith(".gz")]
        # The path, not the host: on jobs.mayoclinic.org every child says "jobs".
        jobby = [c for c in children if re.search(r"job|career|posting|position|vacanc",
                                                  urllib.parse.urlsplit(c).path, re.I)]
        pending = (jobby or children) + pending
        for page, lastmod in pages:
            if POSTING.search(urllib.parse.urlsplit(page).path):
                key = posting_key(page)
                if key not in found or (lastmod > found[key][1]):
                    found[key] = (page, lastmod)
    return list(found.values()), reads


def _text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("@value") or "")
    return str(value or "")


def _location(posting: dict) -> str:
    places = posting.get("jobLocation") or []
    if isinstance(places, dict):
        places = [places]
    shown = []
    for place in places[:3]:
        address = (place or {}).get("address") if isinstance(place, dict) else place
        # One address, a list of them (Wells Fargo), or plain text.
        for one in (address if isinstance(address, list) else [address])[:3]:
            if isinstance(one, str):
                shown.append(one)
                continue
            if not isinstance(one, dict):
                continue
            parts = [_text(one.get(k)) for k in
                     ("addressLocality", "addressRegion", "addressCountry")]
            text = ", ".join(p for p in parts if p)
            if text:
                shown.append(text)
    return "; ".join(dict.fromkeys(shown))


def _salary(posting: dict) -> tuple[float | None, float | None, str, str, bool]:
    pay = posting.get("baseSalary") or {}
    if not isinstance(pay, dict):
        return None, None, "", "", False
    value = pay.get("value") or {}
    if not isinstance(value, dict):
        value = {"value": value}
    period = normalise_interval(str(value.get("unitText") or pay.get("unitText") or "year"))

    def num(key):
        try:
            return float(value.get(key)) if value.get(key) not in (None, "") else None
        except (TypeError, ValueError):
            return None

    lo = num("minValue") or num("value")
    hi = num("maxValue") or lo
    currency = str(pay.get("currency") or "").upper()
    if not (currency and (lo or hi)):
        return None, None, "", "", False
    return annualise(lo, period), annualise(hi, period), currency, period, True


def to_role(posting: dict, url: str, company: str) -> Role | None:
    title = clean(_text(posting.get("title")))
    if not title:
        return None
    remote = str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE"
    location = _location(posting) or ("Remote" if remote else "")
    lo, hi, currency, period, stated = _salary(posting)
    return Role(
        platform="site",
        company=clean(_text(posting.get("hiringOrganization"))) or company,
        title=title,
        url=_text(posting.get("url")) or url,
        location_raw=location,
        description=to_text(posting.get("description") or ""),
        posted_at=date_of(posting.get("datePosted")),
        work_mode="remote" if remote else "",
        salary_min=lo, salary_max=hi, salary_currency=currency,
        salary_period=period, salary_stated=stated,
    )


_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def date_of(value) -> str:
    """A schema.org date as YYYY-MM-DD, or "".

    ISO first ("2026-09-30T18:42:00+0000", "2026-06-24 00:00:00.0"); then the
    Java form some sites send ("Thu Jul 02 00:00:00 GMT 2026", Taleo).
    """
    text = str(value or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    found = re.search(r"\b([A-Za-z]{3})[a-z]*\s+(\d{1,2})\b.*?\b(\d{4})\b", text)
    if found and found.group(1).lower() in _MONTHS:
        try:
            return dt.date(int(found.group(3)), _MONTHS[found.group(1).lower()],
                           int(found.group(2))).isoformat()
        except ValueError:
            return ""
    return ""


def closed(posting: dict, today: dt.date) -> bool:
    """The site's own `validThrough` has passed."""
    until = date_of(posting.get("validThrough"))
    try:
        return dt.date.fromisoformat(until) < today
    except ValueError:
        return False


@register("site")
def fetch(fetcher, cfg, token: str = "", company: str = "",
          today: dt.date | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    site = token.rstrip("/")
    if not site.startswith(("http://", "https://")):
        return SourceResult(source="site", skipped=(
            f"site token {token!r} must be the careers site's address, as in "
            "https://jobs.mayoclinic.org; `jobdork discover` finds it"))
    today = today or dt.date.today()
    result = SourceResult(source="site")
    robots = Robots(fetcher)
    listed, reads = postings(fetcher, site, robots)
    result.requests_made += reads
    if not listed:
        result.suspect = True
        result.errors.append(f"{site}: no postings in its sitemap")
        return result

    titled = [(u, m) for u, m in listed if slug_title(u)]
    if len(titled) * 2 >= len(listed):
        # Addresses carry the title: read only the ones naming yours.
        chosen = [(u, m) for u, m in titled if title_verdict(slug_title(u), cfg)[0]]
        limit = MAX_PAGES
    else:
        # Addresses are ids only: newest first, a few.
        chosen = list(listed)
        limit = MAX_UNTITLED
    chosen.sort(key=lambda pair: pair[1], reverse=True)

    if hasattr(fetcher, "pace"):
        fetcher.pace(urllib.parse.urlsplit(site).netloc, SITE_RATE)
    for url, _ in chosen[:limit]:
        if not robots.allowed(url):
            continue
        resp = fetcher.get(url, expect_json=False)
        result.requests_made += 1
        if not resp.ok:
            continue
        posting = job_posting(resp.body)
        if not posting or closed(posting, today):
            continue
        try:
            role = to_role(posting, url, company or urllib.parse.urlsplit(site).netloc)
        except (AttributeError, TypeError, ValueError) as exc:   # one odd page
            result.errors.append(f"{url}: {type(exc).__name__}: {exc}")
            continue
        if role:
            result.roles.append(role)
    if len(chosen) > limit:
        log.info("%s: read the newest %d of %d matching postings", site, limit, len(chosen))
    return result
