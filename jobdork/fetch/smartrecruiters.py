"""
jobdork.fetch.smartrecruiters
=============================
    GET https://api.smartrecruiters.com/v1/companies/{token}/postings

UNVERIFIED. The endpoint answers HTTP 200 and the envelope is right — it
returns `{offset, limit, totalFound, content}` — but every token tried during
development came back `totalFound: 0` with an empty `content`, so no posting
from this adapter has ever been parsed against live data.

That is exactly the failure this platform is known for: SmartRecruiters
answers 200 with nothing both for a board that is not there and for one that
is throttling you, so an empty answer proves neither. Treat your first
successful run as the test and believe the run over this docstring.

The advert is not in the index. `content[]` carries a summary, and the full
posting needs a second call per role, which is why enrich exists rather than
this adapter making one request per job.
"""

from __future__ import annotations

from ..store import Role
from ..textutil import to_text
from . import SourceResult, register
from .boards import _result_for, clean

API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
PAGE_SIZE = 100
MAX_PAGES = 10


def _location(job: dict) -> str:
    loc = job.get("location") or {}
    bits = [loc.get("city"), loc.get("region"), loc.get("country")]
    out = ", ".join(clean(b) for b in bits if b)
    return out.upper() if out and len(out) == 2 else out


def _work_mode(job: dict) -> str:
    loc = job.get("location") or {}
    if loc.get("remote") is True:
        return "remote"
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
            url = (job.get("applyUrl")
                   or job.get("ref")
                   or (f"https://jobs.smartrecruiters.com/{token}/{job_id}"
                       if job_id else ""))
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
