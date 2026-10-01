"""
jobdork.fetch.adzuna
====================
    GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}

The only source here that watches more than one country from the same config:
the country is two letters in the URL path, so `us` becomes `ca` for a second
national index. That is what makes it the natural primary for a North American
search once it is keyed.

Registered but dormant until credentials are present. Free and self-serve at
https://developer.adzuna.com/signup. They go in `.env`, never config.yaml:

    ADZUNA_APP_ID="..."
    ADZUNA_APP_KEY="..."

Three things this adapter is careful about:

  `title_only`, not `what`. `what` searches the advert body, so "engineering
  manager" returns every engineer whose advert mentions their manager, and
  you pay a call for each page of it.

  `distance` is KILOMETRES. The radius in this tool is miles, so it is
  converted. Sending 25 where 40 was meant quietly shrinks the search to a
  third of its area.

  `salary_is_predicted` means Adzuna guessed. A guessed figure is not a stated
  one and must never disqualify a role, so it is dropped rather than stored:
  only a number the employer published can be compared to a floor.

The free tier is 25 calls a minute, 250 a day, 1,000 a week and 2,500 a month.
One scan is one call per title per page, so six titles at three pages is 18
calls, and the monthly cap works out at roughly four scans a day. A second
country doubles it. The host is paced at 1 request a second here for that
reason.

VERIFIED against the live keyed API. Three things the run corrected about the
documentation:

  `location.display_name` is city plus COUNTY — "Round Rock, Williamson
  County" — which no gazetteer can place. `location.area` is the structured
  version, ["US", "Texas", "Travis County", "Austin"], and is what `_location`
  reads. Using display_name left 187 of 238 roles unplaced and the radius
  quietly doing nothing.

  `salary_is_predicted` is the STRING "1", not an integer and not a boolean.

  A predicted salary always has `salary_min == salary_max`, which is a second
  way to spot one. Predicted figures dominate: 251 of 292 roles in one run.
"""

from __future__ import annotations

from ..core.textutil import to_text
from ..db.store import Role
from ..search import geo
from . import SourceResult, register
from .boards import clean

API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
PAGE_SIZE = 50             # the documented maximum
MAX_PAGES = 3              # the free monthly cap is the real limit, not this

# Adzuna runs a separate national index per country, and the code is two
# letters in the URL path. Probed live: these answer, `au`, `nz` and `sg`
# currently return 503, and `ph`, `id`, `my`, `jp`, `ae` and `ru` return 404 —
# no index exists for them at all.
COUNTRY_CURRENCY = {
    "us": "USD", "ca": "CAD", "gb": "GBP", "ie": "EUR",
    "au": "AUD", "nz": "NZD", "sg": "SGD", "in": "INR",
    "de": "EUR", "fr": "EUR", "nl": "EUR", "at": "EUR", "be": "EUR",
    "es": "EUR", "it": "EUR", "ch": "CHF", "pl": "PLN",
    "br": "BRL", "mx": "MXN", "za": "ZAR",
}

# ISO alpha-2 as `locations.countries` writes it, to Adzuna's path code.
ISO_TO_INDEX = {code.upper(): code for code in COUNTRY_CURRENCY}


def _location(job: dict) -> str:
    """Build "City, State" from `location.area`, not from `display_name`.

    Verified against the live API: `display_name` is city plus COUNTY —
    "Round Rock, Williamson County" — which no gazetteer can place, so the
    radius silently stops working. `area` is the structured version and
    reads country, state, county, city:

        ["US", "Texas", "Travis County", "Austin"]

    The last element is the most specific place; index 1 is the state.
    """
    loc = job.get("location") or {}
    area = [str(a).strip() for a in (loc.get("area") or []) if a]
    if len(area) >= 3:
        city, state = area[-1], area[1]
        if city != state:
            return f"{city}, {state}"
        return state
    if len(area) == 2:
        return area[1]
    return clean(loc.get("display_name") or "")


def _where(cfg) -> dict:
    """`where` plus `distance`, which Adzuna wants in kilometres.

    Your radius may be configured in miles or kilometres; it is normalised to
    miles internally and converted here. Sending 25 where 40 was meant shrinks
    the search to a third of its area.
    """
    anchor_text = cfg.locations.anchor.strip()
    if not anchor_text:
        return {}
    anchor = geo.resolve_anchor(anchor_text, cfg.country_prefs())
    if anchor.city and anchor.state:
        where = f"{anchor.city}, {geo.state_name(anchor.state)}"
    elif anchor.city:
        where = anchor.city
    elif anchor.state:
        where = geo.state_name(anchor.state)
    else:
        return {}
    params = {"where": where}
    radius = cfg.radius_miles()
    if radius is not None:
        params["distance"] = round(geo.miles_to_km(radius))
    return params


def _indexes(cfg) -> list[str]:
    """Which national indexes to read.

    Explicit `sources.adzuna_countries` wins. Otherwise it follows
    `locations.countries`, so a reader in Berlin does not have to know that
    Adzuna calls Germany `de`. Countries with no Adzuna index are reported
    rather than silently dropped.
    """
    configured = [c for c in cfg.sources.adzuna_countries if c in COUNTRY_CURRENCY]
    if configured:
        return configured
    return [ISO_TO_INDEX[c] for c in cfg.locations.countries if c in ISO_TO_INDEX]


@register("adzuna")
def fetch(fetcher, cfg, **_) -> SourceResult:
    if not cfg.sources.adzuna_ready():
        return SourceResult(
            source="adzuna",
            skipped="no ADZUNA_APP_ID / ADZUNA_APP_KEY in .env. "
                    "Get a free key at https://developer.adzuna.com/signup",
        )

    countries = _indexes(cfg)
    if not countries:
        wanted = ", ".join(cfg.locations.countries) or "your countries"
        return SourceResult(
            source="adzuna",
            skipped=f"Adzuna runs no national index for {wanted}. "
                    f"Available: {', '.join(sorted(COUNTRY_CURRENCY))}.",
        )
    where = _where(cfg)
    roles: list[Role] = []
    errors: list[str] = []
    requests_made = 0
    seen: set[str] = set()

    for country in countries:
        for title in cfg.titles_include:
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "app_id": cfg.sources.adzuna_app_id,
                    "app_key": cfg.sources.adzuna_app_key,
                    "results_per_page": PAGE_SIZE,
                    "title_only": title,
                    "content-type": "application/json",
                    **where,
                }
                # Ghost-age posts are not worth a request's quota: they would
                # be dropped at screening anyway (freshness.ghost_days).
                if cfg.freshness.ghost_days:
                    params["max_days_old"] = cfg.freshness.ghost_days
                resp = fetcher.get(API.format(country=country, page=page),
                                   params=params)
                requests_made += 1
                if not resp.ok:
                    errors.append(f"{country}/{title!r}: {resp.error}")
                    break

                payload = resp.json if isinstance(resp.json, dict) else {}
                items = payload.get("results") or []
                if not items:
                    break

                for job in items:
                    url = job.get("redirect_url") or ""
                    if not url:
                        continue

                    # A predicted salary is Adzuna's guess, not the employer's
                    # figure. Storing it as stated would let a guess hide a job.
                    # The flag arrives as the STRING "1", not an integer or a
                    # boolean, and a predicted figure always has min == max.
                    predicted = str(job.get("salary_is_predicted") or "0") in ("1", "true", "True")
                    lo = None if predicted else _num(job.get("salary_min"))
                    hi = None if predicted else _num(job.get("salary_max"))

                    role = Role(
                        platform="adzuna",
                        company=clean((job.get("company") or {}).get("display_name")
                                      or ""),
                        title=clean(job.get("title") or ""),
                        url=url,
                        location_raw=_location(job),
                        description=to_text(job.get("description") or ""),
                        posted_at=(job.get("created") or "")[:10],
                        salary_min=lo, salary_max=hi,
                        salary_currency=COUNTRY_CURRENCY[country] if (lo or hi) else "",
                        salary_period="year" if (lo or hi) else "",
                        salary_stated=bool(lo or hi),
                    )
                    if predicted:
                        role.flags.append("adzuna predicted salary ignored")
                    if role.uid not in seen:
                        seen.add(role.uid)
                        roles.append(role)

                if len(items) < PAGE_SIZE:
                    break

    return SourceResult(source="adzuna", roles=roles,
                        requests_made=requests_made, errors=errors)


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None
