"""
jobdork.fetch.arbeitsagentur
============================
The German Federal Employment Agency's job search (Bundesagentur für Arbeit,
Jobbörse): Germany's largest list of jobs, public, no account.

    GET https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs
        ?was=<title>&wo=<place>&umkreis=<km>&angebotsart=1&size=50&page=1
    GET .../pc/v4/jobdetails/<base64 of the reference number>

The agency publishes no API documentation of its own; this is the interface
its own site and app use, documented by the bundesAPI project
(github.com/bundesAPI/jobsuche-api), sent the public client id it names in
`X-API-Key`. robots.txt allows everything. Checked live 2026-10-23: v4's
search answers 403 now and v6 answers; details are still on v4.

  - Searched by your titles, as the agency's own search is: in German, as
    German adverts are written ("Pflegefachkraft", not "nurse").
  - `wo` is your place when it is in Germany, with your radius in km;
    otherwise all of Germany. In German: "Munich" and "Cologne" find
    nothing, "München" and "Köln" hundreds (GERMAN_NAMES).
  - `angebotsart=1` is jobs; apprenticeships and self-employment are left out.
  - Only titles that pass your title filter get a detail request, for the
    advert, at most MAX_DETAILS a scan; the rest are kept with no advert,
    and `enrich` can fetch it.
  - Pay is a range per hour, month or year, in euros.
  - Temporary staffing (Arbeitnehmerüberlassung) and private placement are
    marked by the agency itself and kept as flags.

Runs only when Germany is in locations.countries.
"""

from __future__ import annotations

import base64
import urllib.parse
from itertools import product

from ..core.textutil import to_text
from ..db.store import Role
from ..search import geo
from . import SourceResult, register
from .boards import annualise, clean

API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
SEARCH = API + "/pc/v6/jobs"
DETAIL = API + "/pc/v4/jobdetails/"
PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
PAGE_SIZE = 50
MAX_PAGES = 3               # 150 a title, newest first
MAX_DETAILS = 60            # advert requests a scan
KM_PER_MILE = 1.609344

PERIODS = {"STUNDENLOHN": "hour", "MONATSGEHALT": "month", "JAHRESGEHALT": "year"}

# German cities whose English name the agency does not know (checked live:
# "Munich" 0 jobs, "München" 516). Names it knows either way are left out.
GERMAN_NAMES = {"munich": "München", "cologne": "Köln", "nuremberg": "Nürnberg",
                "brunswick": "Braunschweig", "hanover": "Hannover"}


def _where(cfg) -> list[tuple[str, int | None]]:
    """(place to search from, radius in km) for each of your German cities;
    [("", None)], all of Germany, when there is none or a region is chosen
    (the search takes a place and a distance, not a Land)."""
    radius = str(cfg.locations.radius or "").strip()
    try:
        km = float(radius)
    except ValueError:
        km = 0.0 if radius == "exact" else 25.0
    if (cfg.locations.units or "km") == "mi":
        km *= KM_PER_MILE
    out: list[tuple[str, int | None]] = []
    for text in cfg.locations.cities:
        anchor = geo.resolve_anchor(text, cfg.country_prefs())
        if not anchor.located or anchor.country != "DE":
            continue
        city = anchor.city or text.split(",")[0].strip()
        out.append((GERMAN_NAMES.get(city.casefold(), city), max(0, round(km))))
    if not out or cfg.locations.regions:
        return [("", None)]
    return out


def _location(job: dict) -> str:
    places = []
    for spot in (job.get("stellenlokationen") or [])[:3]:
        address = (spot or {}).get("adresse") or {}
        city = address.get("ort") or ""
        if city:
            places.append(f"{city}, Germany")
    return "; ".join(dict.fromkeys(places)) or "Germany"


def _pay(job: dict) -> tuple[float | None, float | None, str, bool]:
    period = PERIODS.get(str(job.get("verguetungsangabe") or ""), "")
    lo, hi = job.get("gehaltsspanneVon"), job.get("gehaltsspanneBis")
    if not period or not (lo or hi):
        return None, None, "", False
    try:
        lo = float(lo) if lo else None
        hi = float(hi) if hi else lo
    except (TypeError, ValueError):
        return None, None, "", False
    return annualise(lo, period), annualise(hi, period), period, True


def to_role(job: dict, detail: dict | None = None) -> Role | None:
    ref = str(job.get("referenznummer") or "").strip()
    title = clean(job.get("stellenangebotsTitel") or job.get("hauptberuf") or "")
    if not ref or not title:
        return None
    detail = detail or {}
    lo, hi, period, stated = _pay(job)
    flags = []
    if detail.get("istArbeitnehmerUeberlassung") or job.get("istArbeitnehmerUeberlassung"):
        flags.append("temporary staffing (Arbeitnehmerüberlassung)")
    if detail.get("istPrivateArbeitsvermittlung") or job.get("istPrivateArbeitsvermittlung"):
        flags.append("private placement agency")
    return Role(
        platform="arbeitsagentur",
        company=clean(job.get("firma") or ""),
        title=title,
        url=PAGE + urllib.parse.quote(ref),
        location_raw=_location(job),
        description=to_text(detail.get("stellenangebotsBeschreibung") or ""),
        posted_at=str(job.get("datumErsteVeroeffentlichung") or "")[:10],
        salary_min=lo, salary_max=hi,
        salary_currency="EUR" if stated else "", salary_period=period,
        salary_stated=stated,
        flags=flags,
    )


def record(fetcher, url: str) -> tuple[dict, bool]:
    """(the job's detail record, whether the agency answered) for a stored
    posting's address. A job it no longer lists answers 404, which is
    ({}, True): the agency has said it is gone."""
    ref = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]) if url.startswith(PAGE) else ""
    if not ref:
        return {}, False
    key = base64.b64encode(ref.encode("utf-8")).decode("ascii")
    resp = fetcher.get(DETAIL + key, headers=HEADERS)
    if resp.status == 404:
        return {}, True
    if not resp.ok or not isinstance(resp.json, dict):
        return {}, False
    return resp.json, True


@register("arbeitsagentur")
def fetch(fetcher, cfg, **_) -> SourceResult:
    from ..search.screen import title_verdict

    if "DE" not in {c.upper() for c in cfg.locations.countries}:
        return SourceResult(source="arbeitsagentur",
                            skipped="German jobs only, and Germany is not in "
                                    "locations.countries")
    result = SourceResult(source="arbeitsagentur")
    found: dict[str, dict] = {}
    for (place, km), title in product(_where(cfg), cfg.titles_include):
        for page in range(1, MAX_PAGES + 1):
            params = {"was": title, "angebotsart": 1, "size": PAGE_SIZE, "page": page}
            if place:
                params.update(wo=place, umkreis=km)
            resp = fetcher.get(SEARCH, params=params, headers=HEADERS)
            result.requests_made += 1
            if not resp.ok:
                result.errors.append(f"{place or 'Germany'}/{title!r}: {resp.error}")
                break
            payload = resp.json if isinstance(resp.json, dict) else {}
            jobs = payload.get("ergebnisliste") or []
            for job in jobs:
                ref = str(job.get("referenznummer") or "")
                if ref:
                    found.setdefault(ref, job)
            total = int(payload.get("maxErgebnisse") or 0)
            if len(jobs) < PAGE_SIZE or page * PAGE_SIZE >= total:
                break

    details = 0
    for ref, job in found.items():
        detail = None
        if details < MAX_DETAILS and title_verdict(
                str(job.get("stellenangebotsTitel") or ""), cfg)[0]:
            key = base64.b64encode(ref.encode("utf-8")).decode("ascii")
            resp = fetcher.get(DETAIL + key, headers=HEADERS)
            result.requests_made += 1
            details += 1
            detail = resp.json if resp.ok and isinstance(resp.json, dict) else None
        role = to_role(job, detail)
        if role:
            result.roles.append(role)
    if result.requests_made and not found and not result.errors:
        result.suspect = True
    return result
