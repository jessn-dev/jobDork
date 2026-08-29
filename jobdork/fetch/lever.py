"""
jobdork.fetch.lever
===================
    GET https://api.lever.co/v0/postings/{token}?mode=json
    GET https://api.eu.lever.co/v0/postings/{token}?mode=json

Verified live against `leverdemo` (384 roles).

Lever runs two separate deployments, US and EU, and a token that exists on one
404s on the other. A North American search reads the US host; the EU host is
tried only as a fallback, so a company that moved does not read as a dead
board.

The response is a bare top-level list, not an object with a `jobs` key. The
title lives in `text`, and the location in `categories.location`, with every
location in `categories.allLocations`.

Tokens are case-sensitive.
"""

from __future__ import annotations

from ..store import Role
from ..textutil import to_text
from . import SourceResult, register
from .boards import _result_for, annualise, clean, normalise_interval

HOSTS = (
    "https://api.lever.co/v0/postings/{token}",
    "https://api.eu.lever.co/v0/postings/{token}",
)

WORKPLACE_TO_MODE = {"remote": "remote", "hybrid": "hybrid",
                     "on-site": "office", "onsite": "office"}


def _salary(job: dict) -> tuple[float | None, float | None, str, str, bool]:
    rng = job.get("salaryRange") or {}
    lo, hi = _num(rng.get("min")), _num(rng.get("max"))
    if lo is None and hi is None:
        return None, None, "", "", False
    period = normalise_interval(rng.get("interval") or "year") or "year"
    currency = (rng.get("currency") or "USD").upper()
    return annualise(lo, period), annualise(hi, period), currency, period, True


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _description(job: dict) -> str:
    """Lever splits the advert across three fields, and drops any of them."""
    parts = [
        job.get("descriptionPlain") or job.get("description") or "",
        job.get("descriptionBodyPlain") or job.get("descriptionBody") or "",
        job.get("additionalPlain") or job.get("additional") or "",
    ]
    return to_text("\n\n".join(p for p in parts if p))


@register("lever")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    if not token:
        return SourceResult(source="lever", skipped="no board token given")

    requests_made = 0
    errors: list[str] = []
    items: list[dict] | None = None

    for template in HOSTS:
        resp = fetcher.get(template.format(token=token), params={"mode": "json"})
        requests_made += 1
        if resp.ok and isinstance(resp.json, list):
            items = resp.json
            if items:
                break                       # found the deployment that has them
        else:
            errors.append(f"{token}: {resp.error}")

    if items is None:
        return SourceResult(source="lever", requests_made=requests_made,
                            errors=errors)

    roles: list[Role] = []
    for job in items:
        url = job.get("hostedUrl") or job.get("applyUrl") or ""
        if not url:
            continue
        categories = job.get("categories") or {}
        locations = categories.get("allLocations") or []
        location = clean(categories.get("location") or
                         (locations[0] if locations else ""))

        lo, hi, currency, period, stated = _salary(job)
        roles.append(Role(
            platform="lever",
            company=clean(company or token),
            title=clean(job.get("text") or ""),
            url=url,
            location_raw=location,
            description=_description(job),
            posted_at=_epoch_to_date(job.get("createdAt")),
            work_mode=WORKPLACE_TO_MODE.get(
                (job.get("workplaceType") or "").strip().lower(), ""
            ),
            salary_min=lo, salary_max=hi, salary_currency=currency,
            salary_period=period, salary_stated=stated,
        ))

    return _result_for("lever", roles, requests_made, errors)


def _epoch_to_date(value) -> str:
    """Lever dates are milliseconds since the epoch."""
    try:
        import time
        return time.strftime("%Y-%m-%d", time.gmtime(float(value) / 1000.0))
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
