"""
Remotive: remote jobs from its public API, four reads a day at most, pay read
from its free text only when it is plain. The sample has the live answer's
fields (checked 2026-11-13) and invented employers; nothing goes online.

    python tests/test_remotive.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import remotive
from jobdork.fetch.http import Response


def _job(n, title="Customer Service Representative", where="USA", salary="$14 - $20/hour",
         kind="contract"):
    return {"id": n, "url": f"https://remotive.com/remote-jobs/customer-service/rep-{n}",
            "title": title, "company_name": f"Acme {n}", "category": "Customer Service",
            "job_type": kind, "publication_date": "2026-11-11T09:11:58",
            "candidate_required_location": where, "salary": salary,
            "description": "<p>Answer customers.</p>"}


class _Fetcher:
    def __init__(self, jobs, status=200):
        self.jobs, self.status, self.asked = jobs, status, 0

    def get(self, url, **_):
        self.asked += 1
        return Response(url=url, status=self.status,
                        json={"0-legal-notice": "Please link back.", "jobs": self.jobs},
                        error="" if self.status == 200 else f"HTTP {self.status}")


def _cfg(countries=("US",)):
    return Config(titles_include=["customer service"],
                  locations=Locations(cities=[], radius="any", countries=list(countries)))


def test_pay_is_read_only_when_it_is_plain():
    assert remotive.pay("$14 - $20/hour") == (14.0, 20.0, "USD", "hour", True)
    assert remotive.pay("OTE $25k - $35k")[:2] == (25000.0, 35000.0)
    assert remotive.pay("$35,3k- $52k")[:2] == (35300.0, 52000.0), "a decimal comma"
    assert remotive.pay("$90,000 - $120,000")[3] == "year"
    assert remotive.pay("$3.5k–$5k/month")[3] == "month"
    for unclear in ("70K-80K", "$1000 per task", "Competitive", "€50k", ""):
        assert remotive.pay(unclear)[4] is False, unclear


def test_jobs_are_kept_to_countries_and_titles_and_link_to_remotive():
    remotive._LAST_PASS.clear()
    jobs = [_job(1), _job(2, where="Europe"), _job(3, title="Golang Engineer"),
            _job(4, where="Worldwide", salary="")]
    result = remotive.fetch(_Fetcher(jobs), _cfg(), now=1_000.0)
    assert sorted(r.company for r in result.roles) == ["Acme 1", "Acme 4"]
    one = next(r for r in result.roles if r.company == "Acme 1")
    assert one.url.startswith("https://remotive.com/") and one.platform == "remotive"
    assert one.flags == ["remote, open to USA", "contract"] and one.salary_period == "hour"
    remotive._LAST_PASS.clear()


def test_four_reads_a_day_at_most():
    remotive._LAST_PASS.clear()
    remotive.fetch(_Fetcher([_job(1)]), _cfg(), now=0.0)
    again = remotive.fetch(_Fetcher([_job(1)]), _cfg(), now=5 * 3600)
    assert again.skipped.startswith("read 5.0 hours ago") and not again.requests_made
    assert remotive.fetch(_Fetcher([_job(1)]), _cfg(), now=6 * 3600 + 1).requests_made == 1
    remotive._LAST_PASS.clear()
    assert remotive.fetch(_Fetcher([], status=429), _cfg(), now=1.0).errors == ["HTTP 429"]
    remotive._LAST_PASS.clear()


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
