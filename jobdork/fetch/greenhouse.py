"""
jobdork.fetch.greenhouse
========================
    GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs
        ?content=true&pay_transparency=true

Verified live. Two things to know:

  `content=true` is what makes the advert come back at all; without it the
  response is a list of titles and there is nothing to read a dealbreaker
  against.

  The advert arrives HTML-ESCAPED — `&lt;h2&gt;`, not `<h2>`. A tag stripper
  run against it matches nothing and returns the entities verbatim, so
  textutil unescapes first.

Greenhouse answers 403 to a GET carrying a body, which is why the HTTP layer
only ever attaches one to a POST.

`pay_input_ranges` exists but is usually empty: Stripe's board returned `[]`
on every role. Salary from here is the exception, not the rule.
"""

from __future__ import annotations

from ..core.textutil import to_text
from ..db.store import Role
from . import SourceResult, register
from .boards import _result_for, annualise, clean, normalise_interval

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _salary(job: dict) -> tuple[float | None, float | None, str, str, bool]:
    ranges = job.get("pay_input_ranges") or []
    if not ranges:
        return None, None, "", "", False
    first = ranges[0] or {}
    period = normalise_interval(first.get("pay_period") or first.get("interval") or "year")
    lo = _num(first.get("min_cents"), cents=True) or _num(first.get("min_value"))
    hi = _num(first.get("max_cents"), cents=True) or _num(first.get("max_value"))
    currency = (first.get("currency_type") or first.get("currency") or "USD").upper()
    lo, hi = annualise(lo, period or "year"), annualise(hi, period or "year")
    return lo, hi, currency, period or "year", bool(lo or hi)


def _num(value, cents: bool = False) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out / 100.0 if cents else out


@register("greenhouse")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    if not token:
        return SourceResult(source="greenhouse", skipped="no board token given")

    resp = fetcher.get(
        API.format(token=token),
        params={"content": "true", "pay_transparency": "true"},
    )
    if not resp.ok:
        return SourceResult(
            source="greenhouse", requests_made=1,
            errors=[f"{token}: {resp.error}"],
        )

    payload = resp.json if isinstance(resp.json, dict) else {}
    roles: list[Role] = []
    for job in payload.get("jobs") or []:
        url = job.get("absolute_url") or ""
        if not url:
            continue
        lo, hi, currency, period, stated = _salary(job)
        roles.append(Role(
            platform="greenhouse",
            company=clean(job.get("company_name") or company or token),
            title=clean(job.get("title") or ""),
            url=url,
            location_raw=clean((job.get("location") or {}).get("name") or ""),
            description=to_text(job.get("content") or ""),
            posted_at=(job.get("first_published") or job.get("updated_at") or "")[:10],
            salary_min=lo, salary_max=hi, salary_currency=currency,
            salary_period=period, salary_stated=stated,
        ))

    return _result_for("greenhouse", roles, 1, [])
