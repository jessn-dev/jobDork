"""
jobdork.fetch.weworkremotely
============================
We Work Remotely's public RSS feeds: remote jobs in every kind of work, sales
and support as much as programming. No key, no account.

    GET https://weworkremotely.com/categories/remote-customer-support-jobs.rss

Checked 2026-11-13. robots.txt allows everything but accounts, the site links
its RSS from every page, and its terms say nothing against reading it (only
the Internet Archive's copy of them could be read: the live page is behind a
browser check). The main feed, `/remote-jobs.rss`, holds only the 10 newest
of each category, so the 10 category feeds are read instead: about 600 jobs,
one request each, at one a second. The feed asks to be read at most hourly
(`<ttl>60</ttl>`); a scan reads it once.

  - Each item's title is "Company: Job title".
  - `region` says who may apply: "Anywhere in the World", "USA Only",
    "North America Only", "Europe Only", "Asia Only" and the like. A job
    limited to a region none of your countries is in is left out; with no
    countries, every job is kept.
  - `pubDate` and `expires_at` are RFC 822 dates. A post past its expiry is
    left out, and its closing date kept for the "still open" check.
  - The advert is whole, as HTML; no pay figures.
  - `type` is "Full-Time" or "Contract".
  - **Job pages answer 403 to scripts** (a browser check). "Still open" goes
    by the expiry date, then by whether the post was in the latest feed
    (listing.py), as for Himalayas; enrich skips it.
  - The feed has no search: jobs are kept by your titles here.

The stored link is the job's We Work Remotely page, and the source shows as
We Work Remotely.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .arbeitnow import EUROPE
from .boards import clean
from .site import _field

FEED = "https://weworkremotely.com/categories/{}.rss"
CATEGORIES = (
    "remote-customer-support-jobs", "remote-sales-and-marketing-jobs",
    "remote-management-and-finance-jobs", "remote-product-jobs", "remote-design-jobs",
    "remote-full-stack-programming-jobs", "remote-back-end-programming-jobs",
    "remote-front-end-programming-jobs", "remote-devops-sysadmin-jobs",
    "all-other-remote-jobs",
)
MAX_FEED = 8_000_000            # characters; a category feed is about 1 MB

_NORTH_AMERICA = frozenset({"US", "CA", "MX"})
_LATIN_AMERICA = frozenset({
    "MX", "GT", "BZ", "HN", "SV", "NI", "CR", "PA", "CU", "DO", "HT", "JM", "PR", "TT",
    "CO", "VE", "EC", "PE", "BO", "CL", "AR", "UY", "PY", "BR", "GY", "SR",
})
_AFRICA = frozenset({
    "ZA", "NG", "KE", "GH", "EG", "MA", "TN", "DZ", "ET", "UG", "TZ", "RW", "SN", "CI",
    "CM", "ZW", "ZM", "MW", "MZ", "AO", "NA", "BW", "MU",
})
_MIDDLE_EAST = frozenset({"AE", "SA", "QA", "KW", "BH", "OM", "IL", "JO", "LB", "TR", "IQ"})
_ASIA = frozenset({
    "PH", "IN", "PK", "BD", "LK", "NP", "ID", "MY", "SG", "TH", "VN", "KH", "MM", "CN",
    "HK", "TW", "JP", "KR", "MN",
})
_OCEANIA = frozenset({"AU", "NZ"})
# Who may apply, by the words of `region`, as countries. One not named here
# is kept and its words shown: better a job you can read about than one
# lost to a region this table does not know.
REGIONS = {
    "usa": frozenset({"US"}), "us": frozenset({"US"}), "united states": frozenset({"US"}),
    "canada": frozenset({"CA"}), "uk": frozenset({"GB"}), "united kingdom": frozenset({"GB"}),
    "north america": _NORTH_AMERICA, "americas": _NORTH_AMERICA | _LATIN_AMERICA,
    "latin america": _LATIN_AMERICA, "south america": _LATIN_AMERICA, "latam": _LATIN_AMERICA,
    "europe": EUROPE, "emea": EUROPE | _MIDDLE_EAST | _AFRICA, "africa": _AFRICA,
    "middle east": _MIDDLE_EAST, "asia": _ASIA, "apac": _ASIA | _OCEANIA,
    "asia pacific": _ASIA | _OCEANIA, "oceania": _OCEANIA, "australia": frozenset({"AU"}),
}
_WORLDWIDE = ("anywhere", "worldwide", "global")
# A job limited to working hours, by its time zone's name, when nothing else
# names a region: "Time zone: CET (+/- 3 hours)" is Europe's hours. Only
# names with one reading: GMT and "West" also appear in US listings.
_ZONES = (
    (re.compile(r"\b(?:cet|cest|eet|eest)\b"), EUROPE | _AFRICA | _MIDDLE_EAST),
    (re.compile(r"\b(?:est|edt|cst|cdt|mst|mdt|pst|pdt)\b|eastern time|pacific time"),
     _NORTH_AMERICA | _LATIN_AMERICA),
    (re.compile(r"\b(?:ist|sgt|pht|aest|aedt)\b"), _ASIA | _OCEANIA),
)


def _items(xml: str) -> list[str]:
    """Each <item>…</item>, found by str.find: a pattern over a feed with an
    unclosed item would read to the end once for every one."""
    out, at = [], 0
    while True:
        start = xml.find("<item>", at)
        if start < 0:
            return out
        end = xml.find("</item>", start)
        if end < 0:
            return out
        out.append(xml[start + 6:end])
        at = end + 7


def _day(text: str) -> date | None:
    try:
        return parsedate_to_datetime(text.strip()).astimezone(timezone.utc).date()
    except (TypeError, ValueError, IndexError):
        return None


def region_allows(region: str, countries: set[str]) -> bool:
    """Whether a job open to `region` ("USA Only", "EMEA, LATAM, Canada, USA",
    "Germany, UK, USA") is open to one of `countries`. Each part is a region
    of REGIONS or a country's name. No countries, a worldwide job, or one
    whose parts none of these name: yes. Shared with Jobicy and Remote OK."""
    from ..search import geo

    words = region.lower().replace(" only", "").strip()
    if not countries or not words or any(w in words for w in _WORLDWIDE):
        return True
    known = []
    for part in (p.strip() for p in words.replace("/", ",").replace(";", ",").split(",")):
        if part in REGIONS:
            known.append(REGIONS[part])
        elif part and (code := geo.country_code(part)) and len(part) > 2:
            known.append(frozenset({code}))
    if not known:
        known = [zone for pattern, zone in _ZONES if pattern.search(words)]
    if not known:
        return True
    return any(countries & allowed for allowed in known)


def to_role(item: str, today: date) -> Role | None:
    url = _field(item, "link").strip() or _field(item, "guid").strip()
    heading = clean(_field(item, "title"))
    if not url or not heading:
        return None
    company, sep, title = heading.partition(": ")
    if not sep:
        company, title = "", heading
    ends = _day(_field(item, "expires_at"))
    if ends and ends < today:
        return None
    region = clean(_field(item, "region"))
    open_to = region.lower().replace(" only", "").strip()
    flags = ["remote worldwide" if not region or any(w in open_to for w in _WORLDWIDE)
             else f"remote, open to {region.removesuffix(' Only').removesuffix(' only')} only"]
    if _field(item, "type").strip().lower() == "contract":
        flags.append("contract")
    if ends:
        flags.append(f"applications close {ends.isoformat()}")
    posted = _day(_field(item, "pubDate"))
    return Role(
        platform="weworkremotely",
        company=clean(company),
        title=clean(title),
        url=url,
        location_raw="Remote",
        description=to_text(_field(item, "description")),
        posted_at=posted.isoformat() if posted else "",
        work_mode="remote",
        flags=flags,
    )


@register("weworkremotely")
def fetch(fetcher, cfg, today: date | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    if cfg.locations.work_modes and "remote" not in cfg.locations.work_modes:
        return SourceResult(source="weworkremotely",
                            skipped="remote jobs only, and locations.work_modes "
                                    "does not include remote")
    today = today or datetime.now(timezone.utc).date()
    countries = {c.upper() for c in cfg.locations.countries}
    result = SourceResult(source="weworkremotely")
    seen: set[str] = set()
    listed = 0
    for category in CATEGORIES:
        resp = fetcher.get(FEED.format(category), expect_json=False)
        result.requests_made += 1
        if not resp.ok:
            result.errors.append(f"{category}: {resp.error}")
            continue
        for item in _items((resp.body or "")[:MAX_FEED]):
            listed += 1
            if not region_allows(_field(item, "region"), countries):
                continue
            heading = _field(item, "title")
            if not title_verdict(heading.partition(": ")[2] or heading, cfg)[0]:
                continue
            role = to_role(item, today)
            if role and role.uid not in seen:
                seen.add(role.uid)
                result.roles.append(role)
    if result.requests_made and not listed and not result.errors:
        result.suspect = True            # 600 jobs do not all vanish at once
    return result
