"""
Kalibrr: its search answer turned into job posts, with its dates doing the
ghost-job work. The sample has the live answer's field names and nesting
(checked 2026-09-30) and invented employers; nothing here touches the network.

    python tests/test_kalibrr.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import kalibrr
from jobdork.fetch.http import Response
from jobdork.search import listing

TODAY = date(2026, 9, 30)


def _job(job_id, name, country="Philippines", city="Makati", posted="2026-09-25",
         ends="2026-11-23", recruiter="2026-09-29", wfh=False, hybrid=True, **extra):
    return {
        "id": job_id, "name": name, "slug": name.lower().replace(" ", "-"),
        "company": {"code": "acme-ph", "name": "Acme PH"}, "company_name": "Acme PH",
        "activation_date": f"{posted}T01:15:55+00:00", "created_at": "2026-09-01T00:00:00+00:00",
        "application_end_date": f"{ends}T16:00:00+00:00" if ends else None,
        "es_recruiter_last_seen": f"{recruiter}T01:29:32+00:00",
        "description": "<ul><li>Run the Kubernetes platform.</li></ul>",
        "qualifications": "<p>Three years of Terraform.</p>",
        "google_location": {"address_components": {
            "city": city, "region": "Metro Manila", "country": country}},
        "is_work_from_home": wfh, "is_hybrid": hybrid,
        "base_salary": None, "maximum_salary": None, "salary_currency": None,
        "salary_interval": None, "salary_shown": True, **extra,
    }


class _Fetcher:
    """Answers the search from a list of pages, and records what was asked."""

    def __init__(self, pages, count):
        self.pages, self.count, self.asked = pages, count, []

    def get(self, url, params=None, **_):
        self.asked.append(dict(params or {}))
        page = self.pages[len(self.asked) - 1] if len(self.asked) <= len(self.pages) else []
        return Response(url=url, status=200, json={"count": self.count, "jobs": page})


def _cfg(countries=("PH",)):
    return Config(titles_include=["devops engineer"],
                  locations=Locations(anchor="", countries=list(countries)))


def test_jobs_become_posts_with_dates_pay_and_arrangement():
    paid = _job(2, "Platform Engineer", wfh=True, hybrid=False, base_salary=80000,
                maximum_salary=120000, salary_currency="PHP", salary_interval="month")
    hidden = _job(3, "SRE", base_salary=90000, maximum_salary=99000,
                  salary_currency="PHP", salary_interval="month", salary_shown=False)
    result = kalibrr.fetch(_Fetcher([[_job(1, "DevOps Engineer"), paid, hidden]], 3),
                           _cfg(), today=TODAY)
    devops, platform, sre = result.roles
    assert devops.url == "https://www.kalibrr.com/c/acme-ph/jobs/1/devops-engineer"
    assert devops.posted_at == "2026-09-25" and devops.work_mode == "hybrid"
    assert devops.location_raw == "Makati, Metro Manila, Philippines"
    assert "Kubernetes" in devops.description and "Qualifications" in devops.description
    assert "applications close 2026-11-23" in devops.flags
    assert platform.work_mode == "remote"
    assert (platform.salary_min, platform.salary_max, platform.salary_currency,
            platform.salary_period, platform.salary_stated) == (80000, 120000, "PHP", "month", True)
    # A figure the employer chose not to show is not a stated salary.
    assert not sre.salary_stated and sre.salary_min is None


def test_closed_posts_are_not_returned_and_idle_recruiters_are_flagged():
    closed = _job(4, "DevOps Lead", ends="2026-09-01")
    idle = _job(5, "DevOps Engineer II", recruiter="2026-07-01")
    result = kalibrr.fetch(_Fetcher([[closed, idle]], 2), _cfg(), today=TODAY)
    assert [r.title for r in result.roles] == ["DevOps Engineer II"]
    assert any(f.startswith("recruiter last active 2026-07-01, 91 days ago")
               for f in result.roles[0].flags)


def test_only_the_countries_you_search_and_none_of_neither():
    mixed = [_job(6, "DevOps Engineer"), _job(7, "DevOps Engineer", country="Indonesia",
                                               city="Jakarta")]
    assert len(kalibrr.fetch(_Fetcher([mixed], 2), _cfg(["PH"]), today=TODAY).roles) == 1
    assert len(kalibrr.fetch(_Fetcher([mixed], 2), _cfg([]), today=TODAY).roles) == 2
    skipped = kalibrr.fetch(_Fetcher([], 0), _cfg(["US"]), today=TODAY)
    assert skipped.skipped and not skipped.requests_made


def test_pages_stop_at_the_total_and_at_the_cap():
    full = [_job(100 + i, f"DevOps Engineer {i}") for i in range(kalibrr.PAGE_SIZE)]
    two = kalibrr.fetch(_Fetcher([full, full[:3]], kalibrr.PAGE_SIZE + 3), _cfg(), today=TODAY)
    assert two.requests_made == 2
    pages = [[_job(1000 * p + i + 1, f"Ops {p}-{i}") for i in range(kalibrr.PAGE_SIZE)]
             for p in range(10)]
    fetcher = _Fetcher(pages, 10_000)
    capped = kalibrr.fetch(fetcher, _cfg(), today=TODAY)
    assert capped.requests_made == kalibrr.MAX_PAGES
    assert [a["offset"] for a in fetcher.asked] == [
        p * kalibrr.PAGE_SIZE for p in range(kalibrr.MAX_PAGES)]
    assert capped.roles and len(capped.roles) == kalibrr.MAX_PAGES * kalibrr.PAGE_SIZE


def test_still_open_goes_by_the_closing_date_then_by_the_last_search():
    checker = listing.Checker(None, None)
    row = {"platform": "kalibrr", "url": "https://www.kalibrr.com/c/acme-ph/jobs/1/x",
           "last_seen": "2026-09-30T08:00:00", "first_seen": "2026-09-01T08:00:00",
           "flags": json.dumps(["applications close 2020-01-01"])}
    closed = checker._evidence(row, "2026-09-30T07:00:00")
    assert closed.state == "closed" and closed.hard
    row["flags"] = json.dumps(["applications close 2099-01-01"])
    assert checker._evidence(row, "2026-09-30T07:00:00").state == "listed"
    assert checker._evidence(row, "2026-09-30T09:00:00").state == "unlisted"


def test_discover_says_a_job_site_is_not_an_employer_and_sends_nothing():
    from jobdork.search import discover

    class _NoNetwork:
        def get(self, *a, **k):
            raise AssertionError("a job site must be recognised before any request")

    report = discover.discover("https://ph.jobstreet.com/jobs", _NoNetwork())
    assert "job site" in report.error and "jobdork dork --sites jobstreet" in report.error
    assert "sources.keyless" in discover.discover("https://www.kalibrr.com/home",
                                                  _NoNetwork()).error
    assert discover.job_site("jobstreet.com.ph") and discover.job_site("www.linkedin.com/jobs")
    for employer in ("stripe.com", "https://careers.acme.ph", "seekers.example.com"):
        assert not discover.job_site(employer), employer


def test_southeast_asian_sites_are_search_links_on_request_only():
    from jobdork.dork import boards

    for site in ("jobstreet", "jobsdb", "kalibrr", "onlinejobs"):
        assert site in boards.SITE_DORKS and site not in boards.DEFAULT_SITES


def test_each_country_you_want_is_asked_for_by_name():
    """Without country=Indonesia the search answers with Philippine jobs."""
    fetcher = _Fetcher([], 0)
    kalibrr.fetch(fetcher, _cfg(("ID",)), today=TODAY)
    assert [a["country"] for a in fetcher.asked] == ["Indonesia"]
    fetcher = _Fetcher([], 0)
    kalibrr.fetch(fetcher, _cfg(()), today=TODAY)             # no countries: both
    assert sorted(a["country"] for a in fetcher.asked) == ["Indonesia", "Philippines"]


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
