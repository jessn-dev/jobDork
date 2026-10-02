"""
jobdork.fetch.workday
=====================
An employer's Workday careers site, read through the JSON its own pages use.

    POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
         {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "..."}
    GET  https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}

Most large employers hire through Workday (NVIDIA among them), so without it
a scan reaches startups and misses the companies people most often name.
The token is three parts, `tenant/dc/site` (`nvidia/wd5/NVIDIAExternalCareerSite`),
all read off the employer's own careers page by `discover`, never guessed.
Verified against NVIDIA's board:

  - robots.txt allows the public site path and closes research and
    talent-community paths; the `cxs` JSON is what the site's own pages read.
  - The list gives a title, a path, a location ("India, Pune", or "2
    Locations") and a relative date ("Posted 30+ Days Ago"). The detail gives
    the advert, an exact `startDate`, the country, the apply URL, and
    `posted` / `canApply`, which the "still open" check uses.
  - **A detail is one request per job**, so only jobs whose title passes your
    title rules are fetched in full: a search for "devops engineer" returned
    99, and reading all of them to keep a handful would be a heavy hand on
    someone else's server. Workday hosts are paced at one request a second.
  - The search is per title, 20 a page, at most five pages.
  - **Your countries are asked of the board itself.** Workday offers a
    country filter, under a name each employer chooses (NVIDIA's is
    `locationHierarchy1`); it is found by its values being country names.
    One empty search per board reads it. With the Philippines asked for,
    NVIDIA's board, which has no Philippine jobs, costs that one request
    instead of 145 for two titles. A board with no country filter falls back
    to skipping listings whose location names another country.
"""

from __future__ import annotations

import re

from ..core.textutil import to_text
from ..db.store import Role
from ..search import freshness, geo
from . import SourceResult, register
from .boards import clean

PAGE_SIZE = 20
MAX_PAGES = 5


def parse_token(token: str) -> tuple[str, str, str] | None:
    """`tenant/dc/site` as its three parts, or None."""
    parts = [p for p in (token or "").strip().strip("/").split("/") if p]
    if len(parts) != 3 or not parts[1].lower().startswith("wd"):
        return None
    return parts[0], parts[1], parts[2]


def base_url(tenant: str, dc: str) -> str:
    return f"https://{tenant}.{dc}.myworkdayjobs.com"


def api_url(tenant: str, dc: str, site: str) -> str:
    return f"{base_url(tenant, dc)}/wday/cxs/{tenant}/{site}"


def search(fetcher, tenant: str, dc: str, site: str, text: str, offset: int = 0,
           facets: dict | None = None):
    return fetcher.post(f"{api_url(tenant, dc, site)}/jobs", json_body={
        "appliedFacets": facets or {}, "limit": PAGE_SIZE, "offset": offset,
        "searchText": text})


def _facets(nodes):
    """Every (parameter, values) in a facet tree; Workday nests location ones."""
    for node in nodes or []:
        values = node.get("values") or []
        if node.get("facetParameter") and values and all("id" in v for v in values):
            yield node["facetParameter"], values
        yield from _facets([v for v in values if isinstance(v, dict) and "values" in v])


def country_filter(payload: dict, wanted: list[str]) -> tuple[bool, dict]:
    """(found a country facet, the filter for your countries).

    A facet is the country one when at least three of its values are country
    names. Found, with none of yours in it: the board has no jobs there.
    """
    for param, values in _facets(payload.get("facets")):
        codes = [(v["id"], geo.country_code(v.get("descriptor") or "")) for v in values]
        if sum(1 for _, c in codes if c) >= 3:
            ids = [i for i, c in codes if c in wanted]
            return True, ({param: ids} if ids else {})
    return False, {}


def countries(payload: dict) -> list[str]:
    """Every country the board lists jobs in, from its country facet."""
    for _, values in _facets(payload.get("facets")):
        codes = [(geo.country_code(v.get("descriptor") or ""), v.get("count") or 0)
                 for v in values]
        if sum(1 for c, _ in codes if c) >= 3:
            return sorted({c for c, n in codes if c and n})
    return []


def _elsewhere(listing: dict, wanted: list[str]) -> bool:
    """With no country facet: a listing that names a country you did not ask for.

    Workday's location text leads with the country ("India, Pune", "US, CA,
    Santa Clara"); "2 Locations" names none, and is fetched to find out.
    """
    first = (listing.get("locationsText") or "").split(",")[0].strip()
    named = geo.country_code(first)
    return bool(named) and named not in wanted


# A posting's page address: tenant, data centre, optional locale, site, path.
PAGE_URL = re.compile(r"https://([A-Za-z0-9_-]+)\.(wd\d+)\.myworkdayjobs\.com/"
                      r"(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)(/job/[^?#]+)")


def advert(fetcher, url: str) -> tuple[dict, bool]:
    """(jobPostingInfo, read) for a posting's page address."""
    match = PAGE_URL.match(url or "")
    if not match:
        return {}, False
    tenant, dc, site, path = match.groups()
    resp = detail(fetcher, tenant, dc, site, path)
    if not resp.ok or not isinstance(resp.json, dict):
        return {}, False
    return resp.json.get("jobPostingInfo") or {}, True


def detail(fetcher, tenant: str, dc: str, site: str, path: str):
    return fetcher.get(f"{api_url(tenant, dc, site)}{path}",
                       headers={"Accept": "application/json"})


def _to_role(listing: dict, info: dict, company: str, page_url: str) -> Role:
    posted = (info.get("startDate") or "")[:10]
    if not posted:
        when = freshness.relative_posted(info.get("postedOn") or listing.get("postedOn") or "")
        posted = when.isoformat() if when else ""
    country = ((info.get("country") or {}).get("descriptor") or "")
    location = info.get("location") or listing.get("locationsText") or ""
    if country and country not in location:
        location = f"{location}, {country}" if location else country
    remote = " ".join(str(info.get(k) or "") for k in ("remoteType", "location")).lower()
    return Role(
        platform="workday",
        company=company,
        title=clean(info.get("title") or listing.get("title") or ""),
        url=info.get("externalUrl") or page_url,
        location_raw=location,
        description=to_text(info.get("jobDescription") or ""),
        posted_at=posted,
        work_mode="remote" if "remote" in remote else "",
    )


@register("workday")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    from ..search.screen import title_verdict

    parts = parse_token(token)
    if not parts:
        return SourceResult(source="workday", skipped=(
            f"workday token {token!r} must be tenant/dc/site, as in "
            "nvidia/wd5/NVIDIAExternalCareerSite; `jobdork discover` reads it "
            "off the employer's careers page"))
    tenant, dc, site = parts
    result = SourceResult(source="workday")
    seen: set[str] = set()
    wanted = list(cfg.locations.countries)
    facets: dict = {}
    has_country_facet = False
    if wanted:
        first = search(fetcher, tenant, dc, site, "")
        result.requests_made += 1
        if first.ok and isinstance(first.json, dict):
            has_country_facet, facets = country_filter(first.json, wanted)
            if has_country_facet and not facets:
                result.skipped = (f"{company or tenant} lists no jobs in "
                                  f"{', '.join(wanted)}")
                return result

    for title in cfg.titles_include:
        total = 0
        for page in range(MAX_PAGES):
            resp = search(fetcher, tenant, dc, site, title, page * PAGE_SIZE, facets)
            result.requests_made += 1
            if not resp.ok or not isinstance(resp.json, dict):
                result.errors.append(f"{token} {title!r}: {resp.error or resp.status}")
                break
            postings = resp.json.get("jobPostings") or []
            # Workday states the total on the first page only; later pages say 0.
            total = total or resp.json.get("total") or 0
            for listing in postings:
                path = listing.get("externalPath") or ""
                if not path or path in seen:
                    continue
                seen.add(path)
                # Only a title you would keep, somewhere you would work, is
                # worth a second request.
                if not title_verdict(listing.get("title") or "", cfg)[0]:
                    continue
                if wanted and not has_country_facet and _elsewhere(listing, wanted):
                    continue
                info_resp = detail(fetcher, tenant, dc, site, path)
                result.requests_made += 1
                info = ((info_resp.json or {}).get("jobPostingInfo") or {}
                        if info_resp.ok and isinstance(info_resp.json, dict) else {})
                if info and info.get("posted") is False:
                    continue
                result.roles.append(_to_role(
                    listing, info, company or tenant,
                    f"{base_url(tenant, dc)}/{site}{path}"))
            if len(postings) < PAGE_SIZE or (page + 1) * PAGE_SIZE >= total:
                break
    return result
