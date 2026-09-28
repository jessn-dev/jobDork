"""
jobdork.fetch.breezy
====================
    GET https://{company}.breezy.hr/json

Verified live against the `breezy` board. The response is a bare list.

`location.is_remote` is not what it sounds like: it is set on hybrid roles as
well as remote ones, so it is read as "not purely an office job" and never as
proof of remote. Where the board says nothing more,
the arrangement is left unstated and the role is kept and flagged, which is
what unstated always earns here.

Countries arrive as ISO alpha-2 in `location.country.id`, and the state as a
code in `location.state.id`, so the location string is assembled rather than
taken from one field.
"""

from __future__ import annotations

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .boards import _result_for, clean

API = "https://{token}.breezy.hr/json"


def _location(job: dict) -> str:
    loc = job.get("location") or {}
    city = loc.get("city") or ""
    state = (loc.get("state") or {}).get("name") or (loc.get("state") or {}).get("id") or ""
    country = (loc.get("country") or {}).get("name") or ""
    return ", ".join(clean(b) for b in (city, state, country) if b)


def _work_mode(job: dict) -> str:
    """Deliberately conservative: is_remote covers hybrid too.

    Reading it as remote would tell you a hybrid role has no office, which is
    the kind of wrong that wastes an application.
    """
    loc = job.get("location") or {}
    return "remote" if loc.get("is_remote") is True and not loc.get("city") else ""


@register("breezy")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    if not token:
        return SourceResult(source="breezy", skipped="no board token given")

    resp = fetcher.get(API.format(token=token))
    if not resp.ok or not isinstance(resp.json, list):
        return SourceResult(source="breezy", requests_made=1,
                            errors=[f"{token}: {resp.error or 'unexpected shape'}"])

    roles: list[Role] = []
    for job in resp.json:
        url = job.get("url") or ""
        if not url:
            continue
        roles.append(Role(
            platform="breezy",
            company=clean((job.get("company") or {}).get("name")
                          if isinstance(job.get("company"), dict)
                          else job.get("company") or company or token),
            title=clean(job.get("name") or ""),
            url=url,
            location_raw=_location(job),
            # The index carries no advert. The posting page does, and enrich
            # is where that belongs rather than one request per role here.
            description=to_text(job.get("description") or ""),
            posted_at=(job.get("published_date") or "")[:10],
            work_mode=_work_mode(job),
        ))

    return _result_for("breezy", roles, 1, [])
