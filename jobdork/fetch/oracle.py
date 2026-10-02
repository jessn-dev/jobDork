"""
jobdork.fetch.oracle
====================
Oracle Recruiting Cloud: an employer's board through the JSON its Candidate
Experience site reads. JPMorgan Chase, Kroger, Hilton, Marriott and Mayo
Clinic hire through it.

    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true&finder=findReqs;siteNumber={site},keyword="…",…
    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails
        ?onlyData=true&expand=all&finder=ById;Id="{id}",siteNumber={site}

The token is two parts, `host/site` (`jpmc.fa.oraclecloud.com/CX_1001`), read
off the employer's careers page by `discover`. robots.txt on these hosts
answers 403, so there is nothing to read there; this is the JSON the
employer's own careers page reads, as with Workday.

  - **The keyword search is loose.** "software engineer" finds 1,659 jobs at
    JPMorgan, ranked by relevance, most of them not software engineers. Each
    title is searched a few pages deep, a listing is kept only when your
    title rules keep its title, and paging stops at the first page with
    none.
  - **Your countries are asked of the board** through its location filter,
    whose country entries are recognised by name. A board with none of
    yours costs one request.
  - **The advert is a detail request**, one per kept job.
"""

from __future__ import annotations

import re
import urllib.parse

from ..core.textutil import to_text
from ..db.store import Role
from ..search import geo
from . import SourceResult, register
from .boards import clean

PAGE_SIZE = 25
MAX_PAGES = 4


def parse_token(token: str) -> tuple[str, str] | None:
    """(host, site) from `host/site`."""
    host, _, site = (token or "").strip().strip("/").partition("/")
    if host.endswith(".oraclecloud.com") and site and "/" not in site:
        return host, site
    return None


def api(host: str) -> str:
    return f"https://{host}/hcmRestApi/resources/latest"


def page_url(host: str, site: str, req_id: str) -> str:
    return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{req_id}"


# A posting's page: https://{host}/hcmUI/CandidateExperience/{locale}/sites/{site}/job/{id}
PAGE_URL = re.compile(r"https://([A-Za-z0-9.-]+\.oraclecloud\.com)(?::443)?/hcmUI/"
                      r"CandidateExperience/[A-Za-z_-]+/sites/([A-Za-z0-9_]+)/job/(\d+)")


def record(fetcher, url: str) -> tuple[dict, bool]:
    """(the requisition's detail, answered) for a posting's page address.

    A removed posting answers with no items, which is ({}, True).
    """
    match = PAGE_URL.match(url or "")
    if not match:
        return {}, False
    resp = detail(fetcher, *match.groups())
    if not resp.ok or not isinstance(resp.json, dict):
        return {}, False
    return _first(resp), True


def search(fetcher, host: str, site: str, keyword: str = "", offset: int = 0,
           limit: int = PAGE_SIZE, locations: list[str] | None = None):
    params = {"siteNumber": site, "facetsList": "LOCATIONS", "limit": str(limit),
              "offset": str(offset)}
    if keyword:
        params["keyword"] = f'"{keyword}"'
    if locations:
        # Several values in one finder parameter are joined by ";", sent
        # encoded: a bare ";" ends the finder's name.
        params["selectedLocationsFacet"] = ";".join(locations)
    finder = ",".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in params.items())
    query = ("onlyData=true&expand=requisitionList.secondaryLocations"
             f"&finder=findReqs;{finder}")
    return fetcher.get(f"{api(host)}/recruitingCEJobRequisitions?{query}")


def detail(fetcher, host: str, site: str, req_id: str):
    finder = f"ById;Id={urllib.parse.quote(chr(34) + req_id + chr(34), safe='')},siteNumber={site}"
    return fetcher.get(f"{api(host)}/recruitingCEJobRequisitionDetails"
                       f"?onlyData=true&expand=all&finder={finder}")


def _first(resp) -> dict:
    items = (resp.json or {}).get("items") if resp.ok and isinstance(resp.json, dict) else None
    return items[0] if items else {}


def countries(payload: dict) -> dict[str, str]:
    """{ISO code: facet id} for the board's country-level location entries."""
    found: dict[str, str] = {}
    for entry in payload.get("locationsFacet") or []:
        name = str(entry.get("Name") or "")
        if "," in name or not entry.get("TotalCount"):
            continue
        code = geo.country_code(name)
        if code:
            found[code] = str(entry.get("Id"))
    return found


def advert(info: dict) -> str:
    parts = [info.get(k) or "" for k in ("ExternalDescriptionStr",
                                         "ExternalResponsibilitiesStr",
                                         "ExternalQualificationsStr")]
    return to_text("\n\n".join(p for p in parts if p))


def _to_role(listing: dict, info: dict, host: str, site: str, company: str) -> Role:
    places = [listing.get("PrimaryLocation") or info.get("PrimaryLocation") or ""]
    places += [loc.get("Name") or "" for loc in listing.get("secondaryLocations") or []]
    location = "; ".join(dict.fromkeys(p for p in places if p))
    workplace = " ".join(str(listing.get(k) or "") for k in
                         ("WorkplaceType", "WorkplaceTypeCode")).lower()
    return Role(
        platform="oracle",
        company=company or host.split(".")[0],
        title=clean(listing.get("Title") or info.get("Title") or ""),
        url=page_url(host, site, str(listing.get("Id"))),
        location_raw=location,
        description=advert(info) or to_text(listing.get("ShortDescriptionStr") or ""),
        posted_at=str(listing.get("PostedDate") or info.get("ExternalPostedStartDate") or "")[:10],
        work_mode="remote" if "remote" in workplace else
                  "hybrid" if "hybrid" in workplace else "",
    )


@register("oracle")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    from ..search.screen import title_verdict

    parts = parse_token(token)
    if not parts:
        return SourceResult(source="oracle", skipped=(
            f"oracle token {token!r} must be host/site, as in "
            "jpmc.fa.oraclecloud.com/CX_1001; `jobdork discover` reads it off "
            "the employer's careers page"))
    host, site = parts
    result = SourceResult(source="oracle")
    wanted = list(cfg.locations.countries)
    locations: list[str] = []
    has_countries = False
    if wanted:
        first = search(fetcher, host, site, limit=1)
        result.requests_made += 1
        board = countries(_first(first))
        has_countries = len(board) >= 3
        locations = [board[c] for c in wanted if c in board]
        if has_countries and not locations:
            result.skipped = f"{company or host} lists no jobs in {', '.join(wanted)}"
            return result

    seen: set[str] = set()
    for title in cfg.titles_include:
        for page in range(MAX_PAGES):
            resp = search(fetcher, host, site, title, page * PAGE_SIZE,
                          locations=locations)
            result.requests_made += 1
            if not resp.ok:
                result.errors.append(f"{token} {title!r}: {resp.error or resp.status}")
                break
            listings = _first(resp).get("requisitionList") or []
            kept = 0
            for listing in listings:
                req_id = str(listing.get("Id") or "")
                if not req_id or req_id in seen:
                    continue
                seen.add(req_id)
                if not title_verdict(listing.get("Title") or "", cfg)[0]:
                    continue
                if wanted and not has_countries and \
                        (listing.get("PrimaryLocationCountry") or "") not in wanted:
                    continue
                kept += 1
                info_resp = detail(fetcher, host, site, req_id)
                result.requests_made += 1
                result.roles.append(_to_role(listing, _first(info_resp), host, site, company))
            # Ranked by relevance: a page with no title of yours ends it.
            if not kept or len(listings) < PAGE_SIZE:
                break
    return result
