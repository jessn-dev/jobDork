"""
jobdork.fetch.workable
======================
Workable's own cross-employer search. No token, no key, no account.

    GET https://jobs.workable.com/api/v1/jobs?query=...&location=...

This is the widest keyless source there is, and the only one that reaches
employers nobody has added to a list by hand. Verified against the live API:

  - The advert text comes back in the search response. There is no enrich
    step for Workable, which is unusual and saves one request per role.
  - `location` takes exactly ONE value. Repeating the parameter answers 400,
    so several places mean several calls.
  - `location` accepts a city ("Austin, Texas"), a state ("Texas") or a
    country ("United States"), spelled out. Two-letter codes are ignored
    silently, which is worse than an error: "TX" returns the whole world.
  - `workplace` is `remote`, `hybrid` or `on_site`, and filters server-side.
  - `pageToken` pages cleanly with no overlap, 20 to a page.
  - **There is no salary field.** Not empty — absent. Every role from here is
    an unconfirmed salary, and no floor can ever disqualify one.

Radius is not a parameter Workable has. So a radius search asks for the whole
state and measures locally; that is what the gazetteer is for.
"""

from __future__ import annotations

from .. import geo
from ..store import Role
from ..textutil import to_text
from . import SourceResult, register

BASE = "https://jobs.workable.com/api/v1/jobs"

# 20 results a page. The documented cap is 15 pages, but the real constraint
# is the host's patience: a search is run once per title per place, plus a
# remote pass, so a 16-title config at 15 pages is up to 480 requests against
# an endpoint that starts refusing well before that. Six pages is 120 roles
# per title per place, sorted by the board's own relevance, and it is already
# more than anyone reads.
MAX_PAGES = 6

WORKPLACE_TO_MODE = {"remote": "remote", "hybrid": "hybrid", "on_site": "office"}


def location_queries(cfg) -> list[str]:
    """What to put in `location=`, given the config.

    Exact radius asks for the city. Any numeric radius asks for the whole
    state and lets the haversine do the rest, because a 25-mile circle around
    Austin includes Round Rock and Workable has never heard of a circle.
    """
    anchor_text = cfg.locations.anchor.strip()
    if anchor_text:
        anchor = geo.resolve_anchor(anchor_text, cfg.country_prefs())
        if cfg.locations.radius == "exact" and anchor.city and anchor.state:
            return [f"{anchor.city}, {geo.state_name(anchor.state)}"]
        if anchor.state:
            return [geo.state_name(anchor.state)]
        # Most countries do not name a region in their postings. A city with
        # its country is the tightest query available there.
        if anchor.city and anchor.country:
            return [f"{anchor.city}, {geo.country_name(anchor.country)}"]
        if anchor.country:
            return [geo.country_name(anchor.country)]
    if cfg.locations.countries:
        return [geo.country_name(c) for c in cfg.locations.countries]
    # No anchor and no countries means no geographic constraint at all, and
    # Workable requires a location, so the query is run unrestricted.
    return [""]


def _wants_remote(cfg) -> bool:
    """Empty work_modes keeps all three, so remote is wanted by default."""
    return not cfg.locations.work_modes or "remote" in cfg.locations.work_modes


def _to_role(item: dict) -> Role | None:
    url = (item.get("url") or "").strip()
    if not url:
        return None

    # A remote posting often carries `location: null`. That is not a missing
    # field to repair, it is the employer saying the job has no address.
    loc = item.get("location") or {}
    bits = [loc.get("city"), loc.get("subregion"), loc.get("countryName")]
    location_raw = ", ".join(b for b in bits if b)
    if not location_raw:
        locations = item.get("locations") or []
        location_raw = locations[0] if locations else ""

    company = (item.get("company") or {}).get("title") or ""

    description = to_text(item.get("description") or "")
    for extra in ("requirementsSection", "benefitsSection"):
        section = to_text(item.get(extra) or "")
        if section:
            description = f"{description}\n\n{section}".strip()

    return Role(
        platform="workable",
        company=company,
        title=(item.get("title") or "").strip(),
        url=url,
        location_raw=location_raw,
        description=description,
        posted_at=(item.get("created") or "")[:10],
        # Workable states the arrangement on every posting, which almost
        # nothing else does. Take it rather than guessing from the advert.
        work_mode=WORKPLACE_TO_MODE.get(item.get("workplace") or "", ""),
    )


def _search(fetcher, result: SourceResult, params: dict, seen: set[str]) -> None:
    """One query, paged to the cap, appending to `result` in place."""
    token = ""
    for _ in range(MAX_PAGES):
        query = dict(params)
        if token:
            query["pageToken"] = token
        resp = fetcher.get(BASE, params=query)
        result.requests_made += 1

        if not resp.ok:
            result.errors.append(f"{params.get('query','')!r}: {resp.error}")
            return
        payload = resp.json if isinstance(resp.json, dict) else {}
        items = payload.get("jobs") or []
        if not items:
            return

        for item in items:
            role = _to_role(item)
            if role and role.uid not in seen:
                seen.add(role.uid)
                result.roles.append(role)

        token = payload.get("nextPageToken") or ""
        if not token:
            return


@register("workable")
def fetch(fetcher, cfg, **_) -> SourceResult:
    result = SourceResult(source="workable")
    seen: set[str] = set()
    places = location_queries(cfg)

    for title in cfg.titles_include:
        for place in places:
            params = {"query": title}
            if place:
                params["location"] = place
            _search(fetcher, result, params, seen)

        # Remote roles are not in the state you searched, and the ones with a
        # null location are not in any state. A separate pass is the only way
        # to see them, and distance never applied to them anyway.
        if _wants_remote(cfg):
            for country in cfg.locations.countries:
                _search(
                    fetcher, result,
                    {
                        "query": title,
                        "location": geo.country_name(country),
                        "workplace": "remote",
                    },
                    seen,
                )

    # Workable is a busy board. Nothing at all, across every title, means the
    # search answered rather than that the market is empty.
    if result.requests_made and not result.roles and not result.errors:
        result.suspect = True

    return result
