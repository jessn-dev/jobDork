"""
Jobicy: remote jobs from its public Jobs API, kept to your countries and
titles, read once an hour at most. The sample has the live answer's field
names (checked 2026-11-13) and invented employers; nothing goes online.

    python tests/test_jobicy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import jobicy
from jobdork.fetch.http import Response


def _job(n, title="Customer Support Specialist", geo="USA", pay=("50000", "60000"),
         period="yearly", kind="['Full-Time']"):
    return {"id": str(n), "url": f"https://jobicy.com/jobs/{n}-support", "jobSlug": f"{n}-support",
            "jobTitle": title, "companyName": f"Acme {n}", "jobIndustry": "['Customer Success']",
            "jobType": kind, "jobGeo": geo, "jobLevel": "Any",
            "jobExcerpt": "Help customers.", "jobDescription": "<p>Help customers by <b>chat</b>.</p>",
            "pubDate": "2026-11-12T10:00:00+00:00",
            "salaryMin": pay[0] if pay else None, "salaryMax": pay[1] if pay else None,
            "salaryCurrency": "USD" if pay else None, "salaryPeriod": period if pay else None}


class _Fetcher:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, params=None, **_):
        self.asked.append(dict(params or {}))
        jobs, cursor = self.pages[len(self.asked) - 1]
        return Response(url=url, status=200, json={"jobs": jobs, "nextCursor": cursor,
                                                   "hasMore": bool(cursor)})


def _cfg(countries=("US",), modes=(), titles=("customer support",)):
    return Config(titles_include=list(titles),
                  locations=Locations(cities=[], radius="any", countries=list(countries),
                                      work_modes=list(modes)))


def test_a_job_is_read_with_its_pay_region_and_link():
    role = jobicy.to_role(_job(1, kind="['Contract']"))
    assert role.platform == "jobicy" and role.company == "Acme 1"
    assert role.url == "https://jobicy.com/jobs/1-support", "the link is the Jobicy listing"
    assert (role.salary_min, role.salary_max, role.salary_currency, role.salary_period) == \
        (50000.0, 60000.0, "USD", "year")
    assert role.flags == ["remote, open to USA", "contract"] and role.posted_at == "2026-11-12"
    assert "chat" in role.description and "<b>" not in role.description
    unpaid = jobicy.to_role(_job(2, geo="Anywhere", pay=None))
    assert not unpaid.salary_stated and unpaid.flags == ["remote worldwide"]


def test_pages_follow_the_cursor_and_jobs_are_kept_to_countries_and_titles():
    jobicy._LAST_PASS.clear()
    fetcher = _Fetcher([([_job(1), _job(2, geo="EMEA, LATAM")], "next"),
                        ([_job(3, title="Senior Golang Engineer"), _job(4, geo="Canada,  USA")], "")])
    result = jobicy.fetch(fetcher, _cfg(), now=1_000.0)
    assert fetcher.asked == [{"count": 100, "geo": "usa"}, {"count": 100, "geo": "usa", "cursor": "next"}]
    assert sorted(r.company for r in result.roles) == ["Acme 1", "Acme 4"]
    jobicy._LAST_PASS.clear()
    wider = jobicy.fetch(_Fetcher([([_job(1)], "")]), _cfg(countries=("US", "CA")), now=1_000.0)
    assert len(wider.roles) == 1


def test_one_pass_an_hour_at_most():
    jobicy._LAST_PASS.clear()
    first = jobicy.fetch(_Fetcher([([_job(1)], "")]), _cfg(), now=10_000.0)
    assert first.requests_made == 1
    again = jobicy.fetch(_Fetcher([]), _cfg(), now=10_000.0 + 1200)
    assert again.skipped.startswith("read 20 minutes ago") and not again.requests_made
    later = jobicy.fetch(_Fetcher([([_job(1)], "")]), _cfg(), now=10_000.0 + 3601)
    assert later.requests_made == 1
    jobicy._LAST_PASS.clear()


def test_remote_only_and_an_empty_answer_is_suspect():
    jobicy._LAST_PASS.clear()
    assert jobicy.fetch(_Fetcher([]), _cfg(modes=("onsite",)), now=1.0).skipped
    assert jobicy.fetch(_Fetcher([([], "")]), _cfg(), now=1.0).suspect
    jobicy._LAST_PASS.clear()


if __name__ == "__main__":
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
