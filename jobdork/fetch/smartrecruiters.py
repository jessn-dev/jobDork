"""
jobdork.fetch.smartrecruiters
=============================
    GET https://api.smartrecruiters.com/v1/companies/{token}/postings

VERIFIED, eventually. Ten well-known company names in a row answered HTTP 200
with `totalFound: 0` — which on this platform is also what a throttle and a
non-existent board look like, so none of them proved anything. `Bytedance`
finally returned rows, and what they contained corrected three guesses:

  `location.fullLocation` is "Mumbai, MH, India" — assembled and readable.
  Building the string from `city, region, country` instead produced
  "Mumbai, MH, in", because `country` is a LOWERCASE two-letter code.

  `location.hybrid` exists alongside `location.remote`. Reading only `remote`
  filed every hybrid role as arrangement-not-stated.

  `ref` is the posting's own detail URL, which is where the advert lives. The
  index carries none: `jobAd` appears only on the detail response, so the
  advert needs one request per role and that belongs to `enrich`.

The public posting page carries no schema.org data, so the generic enricher
cannot read it either — `enrich` uses the detail endpoint for this platform.
"""

from __future__ import annotations

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .boards import _result_for, clean

API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
PAGE_SIZE = 100
MAX_PAGES = 10


def _location(job: dict) -> str:
    """`fullLocation` first — it is the only field already spelled out.

    The parts are city, region and a LOWERCASE country code, so assembling
    them gives "Mumbai, MH, in" where the platform already offers
    "Mumbai, MH, India".
    """
    loc = job.get("location") or {}
    full = clean(loc.get("fullLocation") or "")
    if full:
        return full
    bits = [loc.get("city"), loc.get("region"),
            (loc.get("country") or "").upper()]
    return ", ".join(clean(b) for b in bits if b)


def _work_mode(job: dict) -> str:
    """Both flags are published, and reading only one loses the hybrids."""
    loc = job.get("location") or {}
    if loc.get("remote") is True:
        return "remote"
    if loc.get("hybrid") is True:
        return "hybrid"
    return ""


@register("smartrecruiters")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    if not token:
        return SourceResult(source="smartrecruiters",
                            skipped="no company token given")

    roles: list[Role] = []
    errors: list[str] = []
    requests_made = 0
    offset = 0

    for _page in range(MAX_PAGES):
        resp = fetcher.get(
            API.format(token=token),
            params={"limit": PAGE_SIZE, "offset": offset},
        )
        requests_made += 1
        if not resp.ok:
            errors.append(f"{token}: {resp.error}")
            break

        payload = resp.json if isinstance(resp.json, dict) else {}
        items = payload.get("content") or []
        if not items:
            break

        for job in items:
            job_id = job.get("id") or ""
            # The human posting page, not `ref`. `ref` is the API's own detail
            # URL — real, but it answers JSON, so storing it hands you a page
            # of braces when you click through. `enrich` derives the detail
            # URL back from this one.
            url = (f"https://jobs.smartrecruiters.com/{token}/{job_id}"
                   if job_id else (job.get("applyUrl") or ""))
            if not url:
                continue
            roles.append(Role(
                platform="smartrecruiters",
                company=clean((job.get("company") or {}).get("name")
                              or company or token),
                title=clean(job.get("name") or ""),
                url=url,
                location_raw=_location(job),
                description=to_text(job.get("jobAd") or ""),
                posted_at=(job.get("releasedDate") or "")[:10],
                work_mode=_work_mode(job),
            ))

        offset += len(items)
        if offset >= int(payload.get("totalFound") or 0):
            break

    return _result_for("smartrecruiters", roles, requests_made, errors)
