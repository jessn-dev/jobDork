"""
Eightfold: an employer's board through the JSON its careers site reads,
found by discover with the employer domain it answers for. Shapes are the
live answers' (Starbucks, Lockheed Martin, checked 2026-10-01); nothing here
touches the network.

    python tests/test_eightfold.py
"""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import eightfold
from jobdork.fetch.http import Response
from jobdork.search import discover, enrich, listing

HOST, DOMAIN = "starbucks.eightfold.ai", "starbucks.com"
TOKEN = f"{HOST}/{DOMAIN}"


def _position(n, name, where="Orlando, FL, US", mode="onsite"):
    return {"id": 481080416000 + n, "name": name, "standardizedLocations": [where],
            "locations": [where], "postedTs": 1787371200, "workLocationOption": mode,
            "positionUrl": f"/careers/job/{481080416000 + n}"}


class _Board:
    """Search by query and location; details by id; wrong domains 404."""

    def __init__(self, pages, counts=None, domain=DOMAIN, removed=()):
        self.pages, self.domain, self.removed, self.asked = pages, domain, set(removed), []
        self.counts = counts or {"United States": 9727}

    def get(self, url, **_):
        self.asked.append(url)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        if query.get("domain") != self.domain:
            return Response(url=url, status=404, error="HTTP 404")
        if "position_details" in url:
            if query["position_id"] in self.removed:
                return Response(url=url, status=404, error="HTTP 404")
            return Response(url=url, status=200, json={"status": 200, "data": {
                "id": int(query["position_id"]), "jobDescription": "<p>Lead the store.</p>"}})
        if not query.get("query"):
            count = self.counts.get(query.get("location", ""), 21842 if not query.get("location") else 0)
            return Response(url=url, status=200, json={"data": {
                "count": count, "positions": [_position(0, "barista")] if count else []}})
        page = int(query["start"]) // eightfold.PAGE_SIZE
        positions = self.pages[page] if page < len(self.pages) else []
        return Response(url=url, status=200, json={"data": {"count": 52, "positions": positions}})


def _cfg(countries=("US",), titles=("store manager",)):
    return Config(titles_include=list(titles), titles_exclude=["assistant store manager"],
                  locations=Locations(countries=list(countries)))


def _full(page):
    return page + [_position(900 + i, "barista") for i in range(eightfold.PAGE_SIZE - len(page))]


def test_the_token_is_host_and_domain():
    assert eightfold.parse_token(TOKEN) == (HOST, DOMAIN)
    assert eightfold.parse_token("jobs.nvidia.com/nvidia.com") == ("jobs.nvidia.com", "nvidia.com")
    assert eightfold.parse_token("starbucks") is None


def test_titles_are_filtered_here_and_paging_stops_at_a_page_with_none():
    pages = [_full([_position(1, "store manager - Orlando"),
                    _position(2, "assistant store manager")]),
             _full([]), _full([_position(3, "store manager - Tampa")])]
    board = _Board(pages)
    result = eightfold.fetch(board, _cfg(), token=TOKEN, company="Starbucks")
    assert [r.title for r in result.roles] == ["store manager - Orlando"]
    assert not any("start=20" in u for u in board.asked)
    role = result.roles[0]
    assert role.url == f"https://{HOST}/careers/job/481080416001?domain={DOMAIN}"
    assert (role.description, role.posted_at, role.work_mode, role.location_raw) == (
        "Lead the store.", "2026-08-22", "office", "Orlando, FL, US")


def test_your_countries_are_asked_by_name_and_a_country_with_none_is_skipped():
    board = _Board([_full([_position(1, "store manager")])])
    eightfold.fetch(board, _cfg(("US",)), token=TOKEN)
    assert "location=United+States" in board.asked[1]
    board = _Board([])
    result = eightfold.fetch(board, _cfg(("PH",)), token=TOKEN, company="Starbucks")
    assert len(board.asked) == 1 and result.skipped == "Starbucks lists no jobs in PH"


def test_discover_settles_the_domain_the_board_answers_for():
    """Lockheed's page names the tenant, not the domain; a wrong one answers 404."""
    page = '<a href="https://lockheedmartin.eightfold.ai/careers">Search jobs</a>'

    class _Site(_Board):
        def get(self, url, **kw):
            if "eightfold.ai" in url:
                return super().get(url, **kw)
            return Response(url=url, status=200, body=page)

    report = discover.discover("https://www.lockheedmartinjobs.com", _Site([], domain="lockheedmartin.com"))
    found = report.found[0]
    assert (found.platform, found.token, found.status, found.jobs) == (
        "eightfold", "lockheedmartin.eightfold.ai/lockheedmartin.com", "verified", 21842)
    assert found.note == "" and found.addable


def test_discover_tries_the_domain_the_page_names_first():
    page = ('<a href="https://starbucks.eightfold.ai/careers?domain=starbucks.com">Jobs</a>'
            '<script src="https://app.eightfold.ai/x.js"></script>')
    found, _ = discover._extract(page, "https://careers.starbucks.com/")
    assert [(f.platform, f.token, f.hints) for f in found] == [
        ("eightfold", "starbucks", ["starbucks.com"])]


def test_a_test_copy_of_a_board_is_not_a_board_and_a_custom_host_is_named_by_domain():
    page = ('<a href="https://hp-sandbox.eightfold.ai/careers">x</a>'
            '<a href="https://acme-test.eightfold.ai/careers">y</a>')
    assert discover._extract(page, "https://jobs.hp.com/")[0] == []
    assert discover._extract('<a href="https://acme.wd5.myworkdayjobs.com/en-US/Ext">x</a>',
                             "https://x/")[0]                 # not every board is a test


def test_still_open_and_enrich_read_the_position():
    url = f"https://{HOST}/careers/job/481080416001?domain={DOMAIN}"
    board = _Board([], removed={"481080416002"})
    checker = listing.Checker(board)
    assert checker._eightfold(url).state == "open"
    gone = checker._eightfold(url.replace("416001", "416002"))
    assert gone.state == "closed" and gone.hard
    text, read = enrich.PLATFORM_READERS["eightfold"](board, {"url": url})
    assert read and text == "Lead the store."


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
