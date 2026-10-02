"""
jobdork.fetch.eightfold
=======================
Eightfold: an employer's board through the JSON its careers site reads.
Starbucks and Lockheed Martin hire through it.

    GET https://{host}/api/pcsx/search?domain={domain}&query=…&location=…&start=…
    GET https://{host}/api/pcsx/position_details?domain={domain}&position_id={id}

The token is two parts, `host/domain` (`starbucks.eightfold.ai/starbucks.com`):
the careers host, which is `{tenant}.eightfold.ai` or the employer's own
(`jobs.nvidia.com`), and the employer domain the API is asked for. robots.txt
on these hosts closes the site and opens `/careers` and `/api/pcsx` to tools,
so this is the path it invites. A wrong domain answers 404, so `discover`
checks the one it guesses.

  - **Pages are ten results**, ranked by relevance, whatever is asked for.
    Each title is read at most five pages deep; a listing is kept only when
    your title rules keep its title, and a page with none of yours ends it.
  - **Your countries are asked of the board** by name (`location=United
    States`); a country with no jobs costs one request and is skipped.
  - **The advert is a detail request**, one per kept job; a removed posting
    answers 404.
"""

from __future__ import annotations

import datetime as dt
import urllib.parse

from ..core.textutil import to_text
from ..db.store import Role
from ..search import geo
from . import SourceResult, register
from .boards import clean

PAGE_SIZE = 10              # fixed by Eightfold
MAX_PAGES = 5
RATE = 2.0                  # per host: tenant hosts and employers' own


def parse_token(token: str) -> tuple[str, str] | None:
    """(host, domain) from `host/domain`."""
    host, _, domain = (token or "").strip().strip("/").partition("/")
    if "." in host and "." in domain and "/" not in domain:
        return host, domain
    return None


def search(fetcher, host: str, domain: str, query: str = "", start: int = 0,
           location: str = ""):
    params = {"domain": domain, "query": query, "start": str(start)}
    if location:
        params["location"] = location
    return fetcher.get(f"https://{host}/api/pcsx/search?{urllib.parse.urlencode(params)}")


def detail(fetcher, host: str, domain: str, position_id: str):
    params = urllib.parse.urlencode({"domain": domain, "position_id": position_id})
    return fetcher.get(f"https://{host}/api/pcsx/position_details?{params}")


def data(resp) -> dict:
    payload = resp.json if resp.ok and isinstance(resp.json, dict) else {}
    return payload.get("data") or {}


def page_url(host: str, position_id: str, domain: str) -> str:
    """The posting's page, carrying the domain so it can be asked again."""
    return f"https://{host}/careers/job/{position_id}?domain={domain}"


def record(fetcher, url: str) -> tuple[dict, bool]:
    """(the position's details, answered) for a posting's page address.

    A removed posting answers 404, which is ({}, True).
    """
    parts = urllib.parse.urlsplit(url or "")
    segments = [p for p in parts.path.split("/") if p]
    domain = (urllib.parse.parse_qs(parts.query).get("domain") or [""])[0]
    if len(segments) < 3 or segments[-2] != "job" or not domain:
        return {}, False
    resp = detail(fetcher, parts.netloc, domain, segments[-1])
    if resp.status == 404:
        return {}, True
    if not resp.ok:
        return {}, False
    return data(resp), True


def _posted(seconds) -> str:
    try:
        return dt.datetime.fromtimestamp(int(seconds), dt.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _to_role(position: dict, info: dict, host: str, domain: str, company: str) -> Role:
    places = position.get("standardizedLocations") or position.get("locations") or []
    mode = str(position.get("workLocationOption") or "").lower()
    return Role(
        platform="eightfold",
        company=company or host.split(".")[0],
        title=clean(position.get("name") or ""),
        url=page_url(host, str(position.get("id")), domain),
        location_raw="; ".join(places[:3]),
        description=to_text(info.get("jobDescription") or ""),
        posted_at=_posted(position.get("postedTs") or position.get("creationTs")),
        work_mode=mode if mode in ("remote", "hybrid") else "office" if mode == "onsite" else "",
    )


@register("eightfold")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    from ..search.screen import title_verdict

    parts = parse_token(token)
    if not parts:
        return SourceResult(source="eightfold", skipped=(
            f"eightfold token {token!r} must be host/domain, as in "
            "starbucks.eightfold.ai/starbucks.com; `jobdork discover` finds it"))
    host, domain = parts
    if hasattr(fetcher, "pace"):
        fetcher.pace(host, RATE)
    result = SourceResult(source="eightfold")

    # One location per country you asked for; none when you asked for none.
    places = [""]
    if cfg.locations.countries:
        places = []
        for code in cfg.locations.countries:
            name = geo.country_name(code) or code
            resp = search(fetcher, host, domain, location=name)
            result.requests_made += 1
            if data(resp).get("count"):
                places.append(name)
        if not places:
            result.skipped = (f"{company or host} lists no jobs in "
                              f"{', '.join(cfg.locations.countries)}")
            return result

    seen: set[str] = set()
    for place in places:
        for title in cfg.titles_include:
            for page in range(MAX_PAGES):
                resp = search(fetcher, host, domain, title, page * PAGE_SIZE, place)
                result.requests_made += 1
                if not resp.ok:
                    result.errors.append(f"{token} {title!r}: {resp.error or resp.status}")
                    break
                positions = data(resp).get("positions") or []
                kept = 0
                for position in positions:
                    pid = str(position.get("id") or "")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    if not title_verdict(position.get("name") or "", cfg)[0]:
                        continue
                    kept += 1
                    info = data(detail(fetcher, host, domain, pid))
                    result.requests_made += 1
                    result.roles.append(_to_role(position, info, host, domain, company))
                if not kept or len(positions) < PAGE_SIZE:
                    break
    return result
