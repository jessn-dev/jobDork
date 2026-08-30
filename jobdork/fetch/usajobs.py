"""
jobdork.fetch.usajobs
=====================
    GET https://data.usajobs.gov/api/search

US federal hiring. Registered but dormant until a key is present: the adapter
reports that it has no credential rather than quietly not running, because a
source that silently skips looks exactly like a source that found nothing.

The key is free and instant from https://developer.usajobs.gov. It goes in
`.env`, never in config.yaml:

    USAJOBS_API_KEY="..."
    USAJOBS_EMAIL="you@example.com"

The email is not decoration — USAJOBS requires the registered address as the
`User-Agent`, and refuses the request without it.

VERIFIED against the live keyed API. What the run established:

  `Radius` is real and is in MILES. "Austin, Texas" at Radius 25 returned 23
  postings; the same search at Radius 200 returned 52.

  **An unknown parameter is ignored silently, with HTTP 200.** A search
  carrying `NotARealParam` returned the same 501 results as one without it.
  So a misspelled filter here does not fail, it just does not filter, and the
  result looks like a successful wide search. Every parameter name in this
  file has been exercised against the live API for that reason.

  `RateIntervalCode` is a two-letter code — "PA" for per annum — not a word.
  See RATE_INTERVALS below for why an unrecognised one is refused rather than
  assumed to be yearly.

  `JobSummary` is truncated to around 500 characters, so the prose fields are
  concatenated before a dealbreaker is read against them.

Why it is worth keying: federal postings state pay almost always, against
roughly a third of US private postings. This is the one source where a salary
floor does most of its work.
"""

from __future__ import annotations

from .. import geo
from ..store import Role
from ..textutil import to_text
from . import SourceResult, register
from .boards import annualise, clean, normalise_interval

API = "https://data.usajobs.gov/api/search"
PAGE_SIZE = 250            # the API allows up to 500; 250 keeps responses sane
MAX_PAGES = 4


def _location_params(cfg) -> dict:
    """LocationName plus Radius in MILES — Adzuna's is kilometres, this is not."""
    anchor_text = cfg.locations.anchor.strip()
    if not anchor_text:
        return {}
    anchor = geo.resolve_anchor(anchor_text, cfg.country_prefs())
    if not anchor.state:
        return {}
    name = (f"{anchor.city}, {geo.state_name(anchor.state)}"
            if anchor.city else geo.state_name(anchor.state))
    params = {"LocationName": name}
    radius = cfg.radius_miles()
    if radius is not None:
        params["Radius"] = round(radius)
    return params


# USAJOBS states the pay period as a two-letter code, not a word. Verified
# live: a Washington software engineer came back `RateIntervalCode: "PA"`.
# Defaulting an unrecognised code to "year" is the dangerous option — it turns
# $50 an hour into $50 a year and any floor then hides the job — so anything
# not in this table is treated as unknown and the salary is not stated.
RATE_INTERVALS = {
    "PA": "year",     # per annum
    "PH": "hour",
    "PD": "day",
    "PW": "week",
    "PM": "month",
    "BW": "week",     # biweekly, halved below
    "PB": "week",
    "SY": "year",     # per school year
    "WC": "",         # without compensation
}
BIWEEKLY_CODES = ("BW", "PB")


def _salary(item: dict) -> tuple[float | None, float | None, str, str, bool]:
    for pay in item.get("PositionRemuneration") or []:
        lo, hi = _num(pay.get("MinimumRange")), _num(pay.get("MaximumRange"))
        if lo is None and hi is None:
            continue

        code = (pay.get("RateIntervalCode") or "").strip().upper()
        # "Description" is the human form — "Per Year" — and is more reliable
        # than guessing at a code this table has not seen.
        period = RATE_INTERVALS.get(code) or normalise_interval(
            (pay.get("Description") or "").replace("Per ", "")
        )
        if not period:
            continue                      # unknown period: refuse to invent one

        if code in BIWEEKLY_CODES:
            # A biweekly figure is two weeks' pay, so halve it before the
            # per-week annualiser doubles the year.
            lo = lo / 2 if lo is not None else None
            hi = hi / 2 if hi is not None else None

        currency = (pay.get("CurrencyCode") or "USD").upper()
        return annualise(lo, period), annualise(hi, period), currency, period, True
    return None, None, "", "", False


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _location(item: dict, anchor: geo.Resolved | None = None) -> tuple[str, int]:
    """Pick the location nearest your anchor, not simply the first one.

    A federal posting is routinely open in a dozen cities at once. Taking
    `PositionLocation[0]` showed an Austin-matching job as "Salt Lake City",
    which then failed the radius for a role that was never far away.

    USAJOBS carries Latitude and Longitude on every location, so the nearest
    one is measured directly and the gazetteer is not needed here at all.

    Returns (location string, how many locations the posting has).
    """
    places = item.get("PositionLocation") or []
    if not places:
        return clean(item.get("PositionLocationDisplay") or ""), 0

    if anchor is not None and anchor.located and len(places) > 1:
        best, best_distance = None, None
        for place in places:
            lat, lon = place.get("Latitude"), place.get("Longitude")
            try:
                distance = geo.haversine_mi(anchor.lat, anchor.lon,
                                            float(lat), float(lon))
            except (TypeError, ValueError):
                continue
            if best_distance is None or distance < best_distance:
                best, best_distance = place, distance
        if best is not None:
            return clean(best.get("LocationName") or ""), len(places)

    return clean(places[0].get("LocationName") or ""), len(places)


@register("usajobs")
def fetch(fetcher, cfg, **_) -> SourceResult:
    # US federal hiring only. A reader whose countries do not include the US
    # is told that rather than having their titles searched against a market
    # they cannot work in.
    if cfg.locations.countries and "US" not in cfg.locations.countries:
        return SourceResult(
            source="usajobs",
            skipped="US federal postings only, and US is not in "
                    "locations.countries",
        )

    if not cfg.sources.usajobs_ready():
        return SourceResult(
            source="usajobs",
            skipped="no USAJOBS_API_KEY / USAJOBS_EMAIL in .env — "
                    "free key at https://developer.usajobs.gov",
        )

    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": cfg.sources.usajobs_email,
        "Authorization-Key": cfg.sources.usajobs_key,
    }
    location = _location_params(cfg)
    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    roles: list[Role] = []
    errors: list[str] = []
    requests_made = 0
    seen: set[str] = set()

    for title in cfg.titles_include:
        for page in range(1, MAX_PAGES + 1):
            params = {
                "PositionTitle": title,
                "ResultsPerPage": PAGE_SIZE,
                "Page": page,
                **location,
            }
            if cfg.salary.floor and cfg.salary.currency == "USD":
                params["RemunerationMinimumAmount"] = int(cfg.salary.floor)

            resp = fetcher.get(API, params=params, headers=headers)
            requests_made += 1
            if not resp.ok:
                errors.append(f"{title!r}: {resp.error}")
                break

            payload = resp.json if isinstance(resp.json, dict) else {}
            items = ((payload.get("SearchResult") or {})
                     .get("SearchResultItems") or [])
            if not items:
                break

            for entry in items:
                item = entry.get("MatchedObjectDescriptor") or {}
                url = item.get("PositionURI") or ""
                if not url:
                    continue
                lo, hi, currency, period, stated = _salary(item)
                details = (item.get("UserArea") or {}).get("Details") or {}
                # JobSummary is truncated — 499 characters in the sample run —
                # which is thin to read a dealbreaker against, so every prose
                # field the search returns is joined rather than picking one.
                description = to_text("\n\n".join(
                    part for part in (
                        details.get("JobSummary"),
                        item.get("QualificationSummary"),
                        details.get("KeyRequirements") if isinstance(
                            details.get("KeyRequirements"), str) else None,
                        item.get("PositionFormattedDescription")
                        if isinstance(item.get("PositionFormattedDescription"), str)
                        else None,
                    ) if part
                ))
                location_raw, place_count = _location(item, anchor)
                role = Role(
                    platform="usajobs",
                    company=clean(item.get("OrganizationName")
                                  or item.get("DepartmentName") or "US Government"),
                    title=clean(item.get("PositionTitle") or ""),
                    url=url,
                    location_raw=location_raw,
                    description=description,
                    posted_at=(item.get("PublicationStartDate") or "")[:10],
                    salary_min=lo, salary_max=hi, salary_currency=currency,
                    salary_period=period, salary_stated=stated,
                )
                if place_count > 1:
                    role.flags.append(
                        f"open in {place_count} locations; nearest shown"
                    )
                if role.uid not in seen:
                    seen.add(role.uid)
                    roles.append(role)

            if len(items) < PAGE_SIZE:
                break

    return SourceResult(source="usajobs", roles=roles,
                        requests_made=requests_made, errors=errors)
