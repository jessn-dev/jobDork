"""
Oracle Recruiting Cloud: an employer's board through the JSON its Candidate
Experience site reads, found by discover, filtered to your countries by the
board. Shapes are the live answers' (JPMorgan Chase, Kroger, Hilton, checked
2026-10-01); nothing here touches the network.

    python tests/test_oracle.py
"""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import oracle
from jobdork.fetch.http import Response
from jobdork.search import discover, enrich, listing

HOST, SITE = "jpmc.fa.oraclecloud.com", "CX_1001"
TOKEN = f"{HOST}/{SITE}"
FACET = [{"Id": 300000000289738, "Name": "United States", "TotalCount": 5398},
         {"Id": 300000000289576, "Name": "Philippines", "TotalCount": 100},
         {"Id": 300000000289276, "Name": "United Kingdom", "TotalCount": 315},
         {"Id": 1, "Name": "NJ, United States", "TotalCount": 360}]


def _req(n, title, country="US", where="Tampa, FL, United States"):
    return {"Id": str(210748000 + n), "Title": title, "PostedDate": "2026-08-02",
            "PrimaryLocation": where, "PrimaryLocationCountry": country,
            "ShortDescriptionStr": "Design and deliver.", "WorkplaceType": "",
            "secondaryLocations": []}


class _Board:
    """Searches by keyword page, details by id; every request recorded."""

    def __init__(self, pages, facet=FACET, removed=()):
        self.pages, self.facet, self.removed, self.asked = pages, facet, set(removed), []

    def get(self, url, **_):
        self.asked.append(url)
        finder = urllib.parse.unquote(url.split("finder=", 1)[1])
        if "recruitingCEJobRequisitionDetails" in url:
            req_id = finder.split('Id="', 1)[1].split('"', 1)[0]
            items = [] if req_id in self.removed else [{
                "Id": req_id, "ExternalDescriptionStr": "<p>Build payment systems.</p>",
                "ExternalQualificationsStr": "<p>Five years.</p>",
                "PrimaryLocation": "Tampa, FL, United States"}]
            return Response(url=url, status=200, json={"items": items})
        offset = int(finder.split("offset=", 1)[1].split(",", 1)[0])
        listings = self.pages[offset // oracle.PAGE_SIZE] \
            if "keyword=" in finder and offset // oracle.PAGE_SIZE < len(self.pages) else []
        return Response(url=url, status=200, json={"items": [{
            "TotalJobsCount": 7375, "locationsFacet": self.facet,
            "requisitionList": listings}]})


def _cfg(countries=("US",), titles=("software engineer",)):
    return Config(titles_include=list(titles), titles_exclude=["sales engineer"],
                  locations=Locations(countries=list(countries)))


def _full(page):
    """A page as long as PAGE_SIZE, so paging does not stop on its length."""
    return page + [_req(900 + i, "Branch Teller") for i in range(oracle.PAGE_SIZE - len(page))]


def test_the_token_is_host_and_site():
    assert oracle.parse_token("jpmc.fa.oraclecloud.com/CX_1001") == ("jpmc.fa.oraclecloud.com", "CX_1001")
    assert oracle.parse_token("eluq.fa.us2.oraclecloud.com/CX_2001")
    assert oracle.parse_token("jpmc") is None and oracle.parse_token("x.com/CX_1") is None


def test_several_countries_are_one_finder_value_joined_by_an_encoded_semicolon():
    board = _Board([])
    oracle.search(board, HOST, SITE, "software engineer", locations=["1", "2"])
    url = board.asked[0]
    assert "finder=findReqs;siteNumber=CX_1001," in url
    assert "selectedLocationsFacet=1%3B2" in url and "keyword=%22software%20engineer%22" in url


def test_countries_are_read_off_the_location_facet():
    assert oracle.countries({"locationsFacet": FACET}) == {
        "US": "300000000289738", "PH": "300000000289576", "GB": "300000000289276"}


def test_titles_are_filtered_here_and_paging_stops_at_a_page_with_none():
    """The keyword search is loose: 1,659 'software engineer' results at JPMorgan."""
    pages = [_full([_req(1, "Software Engineer III"), _req(2, "Sales Engineer")]),
             _full([]), _full([_req(3, "Software Engineer II")])]
    board = _Board(pages)
    result = oracle.fetch(board, _cfg(), token=TOKEN, company="JPMorgan Chase")
    assert [r.title for r in result.roles] == ["Software Engineer III"]
    assert not any("offset=50" in u for u in board.asked)
    role = result.roles[0]
    assert role.url == f"https://{HOST}/hcmUI/CandidateExperience/en/sites/{SITE}/job/210748001"
    assert role.description == "Build payment systems.\n\nFive years."
    assert (role.company, role.posted_at) == ("JPMorgan Chase", "2026-08-02")


def test_your_countries_are_asked_of_the_board_and_none_costs_one_request():
    board = _Board([_full([_req(1, "Software Engineer")])])
    oracle.fetch(board, _cfg(("US", "PH")), token=TOKEN)
    assert "selectedLocationsFacet=300000000289738%3B300000000289576" in board.asked[1]
    board = _Board([_full([_req(1, "Software Engineer")])])
    result = oracle.fetch(board, _cfg(("DE",)), token=TOKEN, company="JPMorgan Chase")
    assert len(board.asked) == 1 and result.skipped == "JPMorgan Chase lists no jobs in DE"


def test_discover_reads_the_careers_link_and_krogers_site_number():
    jpm = ('<a href="https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/'
           'CX_1001/requisitions?keyword=Technology">Tech</a>')
    kroger = ('<link href="https://eluq.fa.us2.oraclecloud.com:443/hcmRestApi/CandidateExperience/'
              'siteFavicon/favicon-16x16.png?siteNumber=CX_2001&size=16x16">')
    found, _ = discover._extract(jpm + kroger, "https://careers.jpmorgan.com/")
    assert sorted(f.token for f in found if f.platform == "oracle") == [
        "eluq.fa.us2.oraclecloud.com/CX_2001", "jpmc.fa.oraclecloud.com/CX_1001"]


def test_discover_verifies_and_keeps_one_of_two_site_numbers_with_one_count():
    """Hilton: CX_1 and CX_1009 on one host, 4,225 jobs each."""
    page = "".join(f'<a href="https://efet.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/'
                   f'en/sites/{s}/jobs">x</a>' for s in ("CX_1", "CX_1009"))

    class _Hilton(_Board):
        def get(self, url, **kw):
            if "oraclecloud" in url:
                return super().get(url, **kw)
            return Response(url=url, status=200, body=page)

    report = discover.discover("https://jobs.hilton.com", _Hilton([]))
    assert [(f.platform, f.token, f.status, f.jobs) for f in report.found] == [
        ("oracle", "efet.fa.us2.oraclecloud.com/CX_1", "verified", 7375)]
    assert report.found[0].countries == ["GB", "PH", "US"]
    assert report.unsupported == []


def test_still_open_and_enrich_read_the_requisition_record():
    url = f"https://{HOST}/hcmUI/CandidateExperience/en/sites/{SITE}/job/210748001"
    board = _Board([], removed={"210748002"})
    checker = listing.Checker(board)
    assert checker._oracle(url).state == "open"
    gone = checker._oracle(url.replace("210748001", "210748002"))
    assert gone.state == "closed" and gone.hard
    text, read = enrich.PLATFORM_READERS["oracle"](board, {"url": url})
    assert read and text.startswith("Build payment systems.")


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
