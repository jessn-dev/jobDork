"""
Himalayas: remote jobs, kept only when they are open to your countries and
your working hours. The sample has the live answer's field names (checked
2026-09-30) and invented employers; nothing here touches the network.

    python tests/test_himalayas.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import himalayas
from jobdork.fetch.http import Response

TODAY = date(2026, 9, 30)


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def _job(n, title="Software Engineer", countries=("Philippines",), zones=(8,),
         posted="2026-09-29", expires="2026-11-29", **extra):
    return {"title": title, "companyName": f"Acme {n}", "companySlug": f"acme-{n}",
            "applicationLink": f"https://himalayas.app/companies/acme-{n}/jobs/x-{n}",
            "guid": f"https://himalayas.app/companies/acme-{n}/jobs/x-{n}",
            "description": "<p>Build the payments API.</p>", "excerpt": "Payments.",
            "locationRestrictions": list(countries), "timezoneRestrictions": list(zones),
            "pubDate": _ts(posted), "expiryDate": _ts(expires) if expires else None,
            "minSalary": None, "maxSalary": None, "currency": None,
            "salaryPeriod": "annual", **extra}


class _Fetcher:
    def __init__(self, pages, total):
        self.pages, self.total, self.asked = pages, total, []

    def get(self, url, params=None, **_):
        self.asked.append(dict(params or {}))
        n = len(self.asked) - 1
        page = self.pages[n] if n < len(self.pages) else []
        return Response(url=url, status=200, json={"totalCount": self.total, "jobs": page})


def _cfg(anchor="Baguio City", countries=("PH",), modes=()):
    return Config(titles_include=["software engineer"],
                  locations=Locations(anchor=anchor, countries=list(countries),
                                      work_modes=list(modes)))


def test_your_hours_come_from_the_anchor():
    assert himalayas.utc_offset(_cfg()) == 8
    assert himalayas.utc_offset(_cfg(anchor="")) is None


def test_jobs_outside_your_hours_or_past_expiry_are_left_out():
    us_hours = _job(1, zones=(-8, -7, -6, -5))
    expired = _job(2, expires="2026-09-01")
    near = _job(3, zones=(7,))                       # an hour off is close enough
    anywhere = _job(4, countries=(), zones=())
    result = himalayas.fetch(_Fetcher([[us_hours, expired, near, anywhere]], 4),
                             _cfg(), today=TODAY)
    assert [r.company for r in result.roles] == ["Acme 3", "Acme 4"]
    assert "remote worldwide" in result.roles[1].flags


def test_a_post_is_remote_dated_and_paid_only_when_the_currency_is_given():
    paid = _job(5, minSalary=60000, maxSalary=75000, currency="USD")
    vague = _job(6, minSalary=60000, maxSalary=75000, currency=None)
    paid_role, vague_role = himalayas.fetch(_Fetcher([[paid, vague]], 2), _cfg(),
                                            today=TODAY).roles
    assert paid_role.work_mode == "remote" and paid_role.posted_at == "2026-09-29"
    assert paid_role.url == "https://himalayas.app/companies/acme-5/jobs/x-5"
    assert (paid_role.salary_min, paid_role.salary_max, paid_role.salary_currency,
            paid_role.salary_period, paid_role.salary_stated) == (60000, 75000, "USD", "year", True)
    assert not vague_role.salary_stated
    assert "remote, open to Philippines" in paid_role.flags
    assert "applications close 2026-11-29" in paid_role.flags


def test_it_asks_per_country_pages_of_twenty_and_stops_at_the_total():
    full = [_job(100 + i) for i in range(himalayas.PAGE_SIZE)]
    fetcher = _Fetcher([full, full[:5]], himalayas.PAGE_SIZE + 5)
    himalayas.fetch(fetcher, _cfg(countries=("PH",)), today=TODAY)
    assert [(a["country"], a["page"], a["sort"]) for a in fetcher.asked] == [
        ("PH", 1, "recent"), ("PH", 2, "recent")]


def test_skipped_when_you_do_not_want_remote_work():
    result = himalayas.fetch(_Fetcher([], 0), _cfg(modes=("office",)), today=TODAY)
    assert result.skipped and not result.requests_made


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
