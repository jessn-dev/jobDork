"""
jobdork.fetch.ashby
===================
    GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true

Verified live. The two traps:

  `isRemote` is a decoy. Ramp's board returned `isRemote: true` on a role whose
  `workplaceType` was `Hybrid`. `workplaceType` is the field that means what it
  says; `isRemote` is read only when `workplaceType` is missing.

  Ashby answers HTTP 200 with an empty `jobs` array both for a board that does
  not exist and for one that is rate-limiting you. Validation is on job count,
  never on the status code, and an empty answer is reported as suspect rather
  than as "not hiring".

Compensation is structured and good when present: `compensation.compensationTiers[]
.components[]` carries `compensationType: "Salary"`, an `interval` like
`"1 YEAR"`, a `currencyCode`, and min/max values.
"""

from __future__ import annotations

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .boards import _result_for, annualise, clean, normalise_interval

API = "https://api.ashbyhq.com/posting-api/job-board/{name}"

WORKPLACE_TO_MODE = {"remote": "remote", "hybrid": "hybrid", "onsite": "office",
                     "on-site": "office", "on site": "office"}


def _work_mode(job: dict) -> str:
    workplace = (job.get("workplaceType") or "").strip().lower()
    mode = WORKPLACE_TO_MODE.get(workplace, "")
    if mode:
        return mode
    # Only reached when the board states no arrangement. isRemote is not
    # trusted above this line because it is true on hybrid roles.
    if job.get("isRemote") is True:
        return "remote"
    return ""


def _salary(job: dict) -> tuple[float | None, float | None, str, str, bool]:
    comp = job.get("compensation") or {}
    for tier in comp.get("compensationTiers") or []:
        for part in tier.get("components") or []:
            if (part.get("compensationType") or "") != "Salary":
                continue
            period = normalise_interval(part.get("interval") or "") or "year"
            lo = _num(part.get("minValue"))
            hi = _num(part.get("maxValue"))
            if lo is None and hi is None:
                continue
            currency = (part.get("currencyCode") or "USD").upper()
            return (annualise(lo, period), annualise(hi, period),
                    currency, period, True)
    return None, None, "", "", False


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@register("ashby")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    if not token:
        return SourceResult(source="ashby", skipped="no board name given")

    resp = fetcher.get(
        API.format(name=token), params={"includeCompensation": "true"}
    )
    if not resp.ok:
        return SourceResult(source="ashby", requests_made=1,
                            errors=[f"{token}: {resp.error}"])

    payload = resp.json if isinstance(resp.json, dict) else {}
    roles: list[Role] = []
    for job in payload.get("jobs") or []:
        if job.get("isListed") is False:
            continue
        url = job.get("jobUrl") or job.get("applyUrl") or ""
        if not url:
            continue

        location = clean(job.get("location") or "")
        if not location:
            postal = (job.get("address") or {}).get("postalAddress") or {}
            bits = [postal.get("addressLocality"), postal.get("addressRegion"),
                    postal.get("addressCountry")]
            location = ", ".join(b for b in bits if b)

        lo, hi, currency, period, stated = _salary(job)
        roles.append(Role(
            platform="ashby",
            company=clean(company or token),
            title=clean(job.get("title") or ""),
            url=url,
            location_raw=location,
            description=to_text(job.get("descriptionPlain")
                                or job.get("descriptionHtml") or ""),
            posted_at=(job.get("publishedAt") or "")[:10],
            work_mode=_work_mode(job),
            salary_min=lo, salary_max=hi, salary_currency=currency,
            salary_period=period, salary_stated=stated,
        ))

    return _result_for("ashby", roles, 1, [])
