"""
Working Nomads (a public JSON feed) and Dynamite Jobs (its sitemap and job
pages), kept to your countries and titles; and the region check they share
with We Work Remotely reading a time zone. Samples have the live fields
(checked 2026-11-13) and invented employers; nothing goes online.

    python tests/test_workingnomads_dynamitejobs.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import dynamitejobs, workingnomads
from jobdork.fetch.http import Response
from jobdork.fetch.weworkremotely import region_allows

TODAY = date(2026, 11, 13)


def _cfg(titles=("customer service",), countries=("US",)):
    return Config(titles_include=list(titles),
                  locations=Locations(cities=[], radius="any", countries=list(countries)))


def test_a_time_zone_names_a_region_when_nothing_else_does():
    assert not region_allows("Time zone: CET (+/- 3 hours)", {"US"})
    assert region_allows("CET (+/- 3 hours)", {"DE"})
    assert region_allows("EST overlap", {"US"}) and not region_allows("EST overlap", {"PH"})
    assert region_allows("West Coast hours", {"US"}), "a word with two readings is not a zone"


def _wn(n, title="Customer Service Rep", location="Global"):
    return {"url": f"https://www.workingnomads.com/job/go/{n}/", "title": title,
            "company_name": f"Acme {n}", "category_name": "Customer Success", "tags": "support",
            "location": location, "pub_date": "2026-11-13T09:12:26-05:00",
            "description": "<p>Help customers.</p>"}


class _Feed:
    def __init__(self, answer):
        self.answer = answer

    def get(self, url, **_):
        return Response(url=url, status=200, json=self.answer)


def test_working_nomads_feed_is_kept_to_countries_and_titles():
    workingnomads._LAST_PASS.clear()
    feed = [_wn(1), _wn(2, location="Time zone: CET (+/- 3 hours)"), _wn(3, title="Golang Dev"),
            _wn(4, location="Canada, USA")]
    result = workingnomads.fetch(_Feed(feed), _cfg(), now=1.0)
    assert sorted(r.company for r in result.roles) == ["Acme 1", "Acme 4"]
    assert result.roles[0].url.startswith("https://www.workingnomads.com/")
    again = workingnomads.fetch(_Feed(feed), _cfg(), now=60.0)
    assert again.skipped and not again.requests_made
    workingnomads._LAST_PASS.clear()


SITEMAP = ('<?xml version="1.0"?><urlset>'
           "<url><loc>https://dynamitejobs.com/company/acme/remote-job/customer-service-specialist</loc>"
           "<lastmod>2026-11-13T05:00:00+00:00</lastmod></url>"
           "<url><loc>https://dynamitejobs.com/company/bolt/remote-job/customer-service-lead</loc>"
           "<lastmod>2026-11-12T05:00:00+00:00</lastmod></url>"
           "<url><loc>https://dynamitejobs.com/company/acme/remote-job/golang-engineer</loc>"
           "<lastmod>2026-11-13T06:00:00+00:00</lastmod></url>"
           "<url><loc>https://dynamitejobs.com/skill/remote-crm-jobs</loc></url></urlset>")


def _page(company, places):
    posting = {"@context": "https://schema.org", "@type": "JobPosting",
               "title": "Customer Service Specialist, Remote Job",
               "hiringOrganization": {"@type": "Organization", "name": company},
               "description": "<p>Help customers by chat.</p>",
               "datePosted": "2026-11-11T21:13:43.924Z", "validThrough": "2026-12-11T21:13:43.924Z",
               "jobLocationType": "TELECOMMUTE",
               "applicantLocationRequirements": [{"@type": "Country", "name": p} for p in places]}
    return f'<script type="application/ld+json">{json.dumps(posting)}</script>'


class _Site:
    def __init__(self):
        self.asked = []

    def get(self, url, **_):
        self.asked.append(url)
        if url.endswith("robots.txt"):
            return Response(url=url, status=200, body="User-agent: *\nDisallow: /api/\n")
        if url.endswith(".xml"):
            return Response(url=url, status=200, body=SITEMAP)
        if "acme" in url:
            return Response(url=url, status=200, body=_page("Acme", []))
        return Response(url=url, status=200, body=_page("Bolt", ["Brazil", "Mexico"]))


def test_dynamite_reads_only_pages_titled_like_yours_and_open_to_you():
    site = _Site()
    result = dynamitejobs.fetch(site, _cfg(), today=TODAY)
    pages = [u for u in site.asked if "/remote-job/" in u]
    assert sorted(pages) == ["https://dynamitejobs.com/company/acme/remote-job/customer-service-specialist",
                             "https://dynamitejobs.com/company/bolt/remote-job/customer-service-lead"]
    assert [r.company for r in result.roles] == ["Acme"], "Bolt's job is for Brazil and Mexico"
    role = result.roles[0]
    assert role.platform == "dynamitejobs" and role.title == "Customer Service Specialist"
    assert role.flags[-1] == "remote worldwide" and role.work_mode == "remote"
    assert dynamitejobs.job_words(pages[0]) == "customer service specialist"


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
