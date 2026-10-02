"""
An employer's own careers site, read through its sitemap and the schema.org
JobPosting on each posting page. Shapes are the live pages' (Wells Fargo,
State Farm, Mayo Clinic, checked 2026-10-01); nothing here touches the
network.

    python tests/test_site.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import site
from jobdork.fetch.http import Response
from jobdork.search import discover

SITE = "https://jobs.acme.org"
TODAY = dt.date(2026, 10, 1)


def _page(title, *, until="2027-01-01", address=None, remote=False, pay=None):
    posting = {
        "@context": "http://schema.org", "@type": "JobPosting", "title": title,
        "datePosted": "2026-09-30T18:42:00+0000", "validThrough": until,
        "description": "<p>Care for patients.</p>",
        "hiringOrganization": {"@type": "Organization", "name": "Acme Health"},
        "jobLocation": [{"@type": "Place", "address": address or {
            "addressLocality": "Rochester", "addressRegion": "Minnesota",
            "addressCountry": "United States"}}],
    }
    if remote:
        posting["jobLocationType"] = "TELECOMMUTE"
    if pay:
        posting["baseSalary"] = pay
    return f'<html><script type="application/ld+json">{json.dumps(posting)}</script></html>'


def _sitemap(*urls):
    return "<urlset>" + "".join(
        f"<url><loc>{u}</loc><lastmod>2026-09-{10 + i:02d}</lastmod></url>"
        for i, u in enumerate(urls)) + "</urlset>"


class _Site:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, **_):
        self.asked.append(url)
        body = self.pages.get(url)
        if body is None:
            return Response(url=url, status=404, error="HTTP 404")
        return Response(url=url, status=200, body=body)


def _cfg(*titles):
    return Config(titles_include=list(titles), locations=Locations(countries=["US"]))


def test_a_posting_address_is_told_from_a_category_page():
    for url in ("https://x.org/job/irvine/nursing-attendant/641/10035",
                "https://x.com/en/jobs/r-565079/private-mortgage-banking-associate/",
                "https://stripe.com/careers/listing/ai-engineer/8044460",
                "https://jobs.statefarm.com/jobs/46295?lang=en-us"):
        assert site.POSTING.search(url.split("?")[0].split("//", 1)[1]), url
    for url in ("https://x.org/employment/oregon-nursing-license",
                "https://x.org/careers/corporate-services"):
        assert not site.POSTING.search(url.split("//", 1)[1]), url


def test_the_title_in_an_address_leaves_out_ids_places_routes_and_locales():
    assert site.slug_title("https://x.com/en/jobs/r-565079/private-mortgage-banker/") == \
        "private mortgage banker"
    assert site.slug_title("https://x.org/job/irvine/nursing-attendant/641/10035") == \
        "irvine nursing attendant"
    assert site.slug_title("https://jobs.statefarm.com/jobs/46295") == ""
    assert site.posting_key("https://x.com/en/jobs/r-565079/a/") == \
        site.posting_key("https://x.com/fr/jobs/r-565079/a/")


def test_a_job_posting_becomes_a_role_with_place_pay_and_remote():
    pay = {"@type": "MonetaryAmount", "currency": "USD",
           "value": {"@type": "QuantitativeValue", "minValue": 40, "maxValue": 50,
                     "unitText": "HOUR"}}
    posting = site.job_posting(_page("Registered Nurse", pay=pay, remote=True))
    role = site.to_role(posting, SITE + "/job/1234", "")
    assert (role.title, role.company, role.posted_at, role.work_mode) == \
        ("Registered Nurse", "Acme Health", "2026-09-30", "remote")
    assert role.location_raw == "Rochester, Minnesota, United States"
    assert role.salary_stated and role.salary_currency == "USD" and role.salary_min > 80000


def test_wells_fargo_lists_addresses_and_state_farm_states_no_pay_as_zero():
    address = [{"addressLocality": "LOS ANGELES", "addressRegion": "California",
                "addressCountry": "United States of America"}]
    zero = {"currency": "USD", "value": {"minValue": 0, "maxValue": 0, "value": 0}}
    role = site.to_role(site.job_posting(_page("Banker", address=address, pay=zero)), SITE, "")
    assert role.location_raw == "LOS ANGELES, California, United States of America"
    assert not role.salary_stated


def test_reads_only_postings_whose_address_names_your_titles():
    rn = SITE + "/job/rochester/registered-nurse/33647/1001"
    other = SITE + "/job/rochester/accountant/33647/1002"
    closed = SITE + "/job/rochester/registered-nurse-ii/33647/1003"
    fetcher = _Site({
        SITE + "/sitemap.xml": _sitemap(rn, other, closed, SITE + "/careers/nursing"),
        rn: _page("Registered Nurse"),
        closed: _page("Registered Nurse II", until="2026-09-01"),
    })
    result = site.fetch(fetcher, _cfg("registered nurse"), token=SITE, today=TODAY)
    assert [r.title for r in result.roles] == ["Registered Nurse"]
    assert other not in fetcher.asked and closed in fetcher.asked


def test_a_site_whose_addresses_carry_no_words_is_read_newest_first_and_capped():
    urls = [f"https://jobs.statefarm.com/jobs/{46000 + n}" for n in range(30)]
    fetcher = _Site({"https://jobs.statefarm.com/sitemap.xml": _sitemap(*urls),
                     **{u: _page("Analyst") for u in urls}})
    result = site.fetch(fetcher, _cfg("analyst"), token="https://jobs.statefarm.com",
                        today=TODAY)
    read = [u for u in fetcher.asked if "/jobs/" in u]
    assert len(read) == site.MAX_UNTITLED and read[0] == urls[-1]
    assert len(result.roles) == site.MAX_UNTITLED


def test_a_sitemap_index_is_followed_into_its_jobs_child_and_robots_honoured():
    job = SITE + "/job/x/registered-nurse/1001"
    fetcher = _Site({
        SITE + "/robots.txt": f"User-agent: *\nDisallow: /job/x/registered-nurse/1001\n"
                              f"Sitemap: {SITE}/index.xml\n",
        SITE + "/index.xml": (f"<sitemapindex><sitemap><loc>{SITE}/blog.xml</loc></sitemap>"
                              f"<sitemap><loc>{SITE}/jobs.xml</loc></sitemap></sitemapindex>"),
        SITE + "/jobs.xml": _sitemap(job),
        job: _page("Registered Nurse"),
    })
    result = site.fetch(fetcher, _cfg("registered nurse"), token=SITE, today=TODAY)
    assert SITE + "/blog.xml" not in fetcher.asked and job not in fetcher.asked
    assert result.roles == []


def test_a_token_that_is_not_an_address_is_refused():
    result = site.fetch(_Site({}), _cfg("nurse"), token="mayoclinic")
    assert "careers site's address" in result.skipped


def test_discover_offers_the_site_when_no_board_can_be_read():
    """Mayo Clinic: Taleo, which jobdork cannot read, and postings marked up."""
    posting = SITE + "/job/rochester/registered-nurse/33647/1001"
    fetcher = _Site({
        SITE + "/": '<a href="https://acme.taleo.net/careersection/jobs">Apply</a>',
        SITE + "/sitemap.xml": _sitemap(posting, SITE + "/job/x/other/33647/1002"),
        posting: _page("Registered Nurse"),
    })
    report = discover.discover(SITE, fetcher)
    assert [(f.platform, f.token, f.status, f.jobs) for f in report.found] == [
        ("site", SITE, "verified", 2)]
    assert report.found[0].addable and report.found[0].countries == ["US"]
    assert report.found[0].note == ""                 # their own site, no check needed


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
