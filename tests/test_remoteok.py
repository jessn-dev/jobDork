"""
Remote OK: the newest remote jobs from its public API, kept to your
countries and titles, read once an hour at most. The sample has the live
answer's shape (checked 2026-11-13: its first element is its terms) and
invented employers; nothing goes online.

    python tests/test_remoteok.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import remoteok
from jobdork.fetch.http import Response

TERMS = {"last_updated": 1794556821, "legal": "API Terms of Service: Please link back..."}


def _job(n, position="Customer Support Specialist", location="", pay=(0, 0)):
    return {"slug": f"support-{n}", "id": str(n), "epoch": "1794384008",
            "date": "2026-11-11T08:00:08+00:00", "company": f"Acme {n}", "company_logo": "",
            "position": position, "tags": ["customer support"], "location": location,
            "description": "<p>Answer tickets.</p>", "salary_min": pay[0], "salary_max": pay[1],
            "url": f"https://remoteOK.com/remote-jobs/support-{n}",
            "apply_url": f"https://remoteOK.com/remote-jobs/support-{n}"}


class _Fetcher:
    def __init__(self, answer, status=200):
        self.answer, self.status, self.asked = answer, status, 0

    def get(self, url, **_):
        self.asked += 1
        return Response(url=url, status=self.status, json=self.answer,
                        error="" if self.status == 200 else f"HTTP {self.status}")


def _cfg(countries=("US",), titles=("customer support",)):
    return Config(titles_include=list(titles),
                  locations=Locations(cities=[], radius="any", countries=list(countries)))


def test_a_job_is_read_with_its_pay_and_mended_text():
    role = remoteok.to_role(_job(1, position="Support Lead â\u0080\u0094 Billing",
                                 pay=(60000, 80000)))
    assert role.platform == "remoteok" and role.title == "Support Lead — Billing"
    assert (role.salary_min, role.salary_max, role.salary_currency, role.salary_period) == \
        (60000.0, 80000.0, "USD", "year")
    assert role.url.endswith("/support-1") and role.posted_at == "2026-11-11"
    assert role.flags == ["remote worldwide"]
    unpaid = remoteok.to_role(_job(2, location="Warsaw"))
    assert not unpaid.salary_stated, "0 means not given"
    assert unpaid.flags == ["remote, location given as Warsaw"]
    assert remoteok._mended("café") == "café", "proper text is left alone"


def test_the_terms_are_skipped_and_jobs_kept_to_countries_and_titles():
    remoteok._LAST_PASS.clear()
    answer = [TERMS, _job(1), _job(2, location="EMEA"), _job(3, position="Golang Engineer"),
              _job(4, location="Boston")]
    result = remoteok.fetch(_Fetcher(answer), _cfg(), now=1_000.0)
    assert sorted(r.company for r in result.roles) == ["Acme 1", "Acme 4"], \
        "EMEA is not open to the US; Boston is a place it cannot judge, so kept"
    assert result.requests_made == 1 and not result.suspect
    remoteok._LAST_PASS.clear()


def test_once_an_hour_and_failures_said():
    remoteok._LAST_PASS.clear()
    remoteok.fetch(_Fetcher([TERMS, _job(1)]), _cfg(), now=5_000.0)
    again = remoteok.fetch(_Fetcher([TERMS]), _cfg(), now=5_000.0 + 60)
    assert again.skipped.startswith("read 1 minute ago") and not again.requests_made
    remoteok._LAST_PASS.clear()
    refused = remoteok.fetch(_Fetcher(None, status=403), _cfg(), now=1.0)
    assert refused.errors == ["HTTP 403"]
    remoteok._LAST_PASS.clear()
    assert remoteok.fetch(_Fetcher([TERMS]), _cfg(), now=1.0).suspect
    remoteok._LAST_PASS.clear()


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
