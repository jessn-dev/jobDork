"""
Workday: an employer's board read through the JSON its careers site uses,
found by discover, filtered to your countries by the board itself. Shapes
are the live answers' (NVIDIA's board, checked 2026-09-30); nothing here
touches the network.

    python tests/test_workday.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import http, workday
from jobdork.fetch.http import Response
from jobdork.search import discover, listing

TOKEN = "acme/wd5/AcmeCareers"
FACETS = [{"facetParameter": "locationMainGroup", "values": [
    {"facetParameter": "locationHierarchy1", "descriptor": "Locations", "values": [
        {"descriptor": "India", "id": "in-id", "count": 5},
        {"descriptor": "Philippines", "id": "ph-id", "count": 2},
        {"descriptor": "United States of America", "id": "us-id", "count": 9}]}]}]


def _listing(n, title, where="Philippines-Manila"):
    return {"title": title, "externalPath": f"/job/{where}/{title.replace(' ', '-')}_JR{n}",
            "locationsText": where.replace("-", ", "), "postedOn": "Posted 3 Days Ago"}


class _Fetcher:
    """POST is the search, GET the detail; both recorded."""

    def __init__(self, postings, facets=FACETS, posted=True):
        self.postings, self.facets, self.posted = postings, facets, posted
        self.posts, self.gets = [], []

    def post(self, url, json_body=None, **_):
        self.posts.append(json_body)
        page = self.postings if json_body["searchText"] and json_body["offset"] == 0 else []
        return Response(url=url, status=200, json={
            "total": len(self.postings) if json_body["offset"] == 0 else 0,
            "jobPostings": page, "facets": self.facets})

    def get(self, url, **_):
        self.gets.append(url)
        return Response(url=url, status=200, json={"jobPostingInfo": {
            "title": "Software Engineer", "jobDescription": "<p>Build compilers.</p>",
            "location": "Philippines, Manila", "startDate": "2026-09-27",
            "country": {"descriptor": "Philippines"}, "posted": self.posted,
            "externalUrl": "https://acme.wd5.myworkdayjobs.com/AcmeCareers" + url.split("AcmeCareers")[1]}})


def _cfg(countries=("PH",)):
    return Config(titles_include=["software engineer"], titles_exclude=["sales engineer"],
                  locations=Locations(anchor="", countries=list(countries)))


def test_the_token_is_tenant_dc_and_site():
    assert workday.parse_token("nvidia/wd5/NVIDIAExternalCareerSite") == (
        "nvidia", "wd5", "NVIDIAExternalCareerSite")
    for bad in ("nvidia", "nvidia/NVIDIAExternalCareerSite", "nvidia/x5/Site", ""):
        assert workday.parse_token(bad) is None, bad
    assert workday.fetch(None, _cfg(), token="nvidia").skipped


def test_your_countries_are_asked_of_the_board():
    assert workday.country_filter({"facets": FACETS}, ["PH"]) == (
        True, {"locationHierarchy1": ["ph-id"]})
    assert workday.country_filter({"facets": FACETS}, ["JP"]) == (True, {})
    assert workday.country_filter({"facets": []}, ["PH"]) == (False, {})


def test_a_board_with_none_of_your_countries_costs_one_request():
    fetcher = _Fetcher([_listing(1, "Software Engineer")])
    result = workday.fetch(fetcher, _cfg(["JP"]), token=TOKEN, company="Acme")
    assert result.skipped == "Acme lists no jobs in JP" and result.requests_made == 1
    assert not fetcher.gets


def test_only_titles_you_keep_get_a_detail_request():
    fetcher = _Fetcher([_listing(1, "Software Engineer"), _listing(2, "Sales Engineer"),
                        _listing(3, "Accountant")])
    result = workday.fetch(fetcher, _cfg(), token=TOKEN, company="Acme")
    assert len(fetcher.gets) == 1 and len(result.roles) == 1
    assert fetcher.posts[1]["appliedFacets"] == {"locationHierarchy1": ["ph-id"]}
    role = result.roles[0]
    assert (role.platform, role.company, role.posted_at) == ("workday", "Acme", "2026-09-27")
    assert role.url.startswith("https://acme.wd5.myworkdayjobs.com/AcmeCareers/job/")
    assert "compilers" in role.description


def test_a_taken_down_posting_is_left_out():
    result = workday.fetch(_Fetcher([_listing(1, "Software Engineer")], posted=False),
                           _cfg(), token=TOKEN, company="Acme")
    assert not result.roles


def test_without_a_country_facet_listings_elsewhere_are_skipped_by_name():
    fetcher = _Fetcher([_listing(1, "Software Engineer", "India-Pune"),
                        _listing(2, "Software Engineer", "Philippines-Manila")], facets=[])
    result = workday.fetch(fetcher, _cfg(), token=TOKEN, company="Acme")
    assert len(fetcher.gets) == 1 and len(result.roles) == 1


def test_discover_reads_the_three_part_token_and_ignores_service_hosts():
    page = ('<a href="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/login">'
            '<script src="https://app.eightfold.ai/x.js"></script>'
            '<img src="https://vs-errors.eightfold.ai/p">')
    supported, unsupported = discover._extract(page, "https://jobs.nvidia.com/careers")
    assert [(f.platform, f.token) for f in supported] == [
        ("workday", "nvidia/wd5/NVIDIAExternalCareerSite")]
    assert supported[0].board_url == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
    assert unsupported == []


def test_workday_hosts_are_paced_at_one_a_second():
    assert http.rate_for("nvidia.wd5.myworkdayjobs.com") == 1.0
    assert http.rate_for("jobs.workable.com") == http.HOST_RATES["jobs.workable.com"]
    assert http.rate_for("example.com") == http.DEFAULT_RATE


def test_still_open_asks_workday_for_the_posting():
    class _One:
        def __init__(self, status, info=None):
            self.status, self.info, self.asked = status, info, []

        def get(self, url, **_):
            self.asked.append(url)
            return Response(url=url, status=self.status,
                            json={"jobPostingInfo": self.info} if self.info else None)

    url = "https://acme.wd5.myworkdayjobs.com/AcmeCareers/job/Manila/Engineer_JR1"
    gone = _One(404)
    found = listing.Checker(gone)._workday(url)
    assert found.state == "closed" and found.hard
    assert gone.asked == ["https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/job/Manila/Engineer_JR1"]
    assert listing.Checker(_One(200, {"posted": True, "canApply": True}))._workday(url).state == "open"
    assert listing.Checker(_One(200, {"posted": False}))._workday(url).hard


def test_discover_reads_the_page_you_gave_before_guessing_paths():
    """Adobe's category page names its Workday board; its front page does not."""
    class _Site:
        def __init__(self):
            self.asked = []

        def get(self, url, **_):
            self.asked.append(url)
            body = ('<a href="https://adobe.wd5.myworkdayjobs.com/external_experienced/job/x/apply">'
                    if "engineering" in url else "<p>phenompeople</p>")
            return Response(url=url, status=200, body=body)

        def post(self, url, json_body=None, **_):
            return Response(url=url, status=200, json={"total": 540, "jobPostings": [], "facets": []})

    site = _Site()
    report = discover.discover("https://careers.adobe.com/us/en/c/engineering-and-product-jobs", site)
    assert site.asked[:2] == ["https://careers.adobe.com/robots.txt",
                              "https://careers.adobe.com/us/en/c/engineering-and-product-jobs"]
    assert [(f.token, f.status, f.jobs) for f in report.found] == [
        ("adobe/wd5/external_experienced", "verified", 540)]


def test_a_front_end_with_no_board_named_says_what_to_give_instead():
    class _Phenom:
        def get(self, url, **_):
            return Response(url=url, status=200, body="phenompeople " * 5)

    report = discover.discover("careers.example.com", _Phenom())
    assert report.front_end == "Phenom"
    assert any("Apply link" in line for line in report.lines())


def test_enrich_reads_a_workday_advert_from_its_cxs_record():
    from jobdork.search import enrich

    fetcher = _Fetcher([])
    url = "https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers/job/Manila/Engineer_JR1"
    text, read = enrich.PLATFORM_READERS["workday"](fetcher, {"url": url})
    assert read and text == "Build compilers."
    assert fetcher.gets == [
        "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/job/Manila/Engineer_JR1"]
    assert enrich.PLATFORM_READERS["workday"](fetcher, {"url": "https://acme.com/x"}) == ("", False)


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
