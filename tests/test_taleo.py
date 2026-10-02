"""
Taleo Business Edition: an employer's careers pages, read as pages. Shapes
are the live ones (Costco, checked 2026-10-01); nothing here touches the
network.

    python tests/test_taleo.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import site, taleo
from jobdork.fetch.http import Response
from jobdork.search import discover, listing

HOST, PATH, ORG, CWS = "phf.tbe.taleo.net", "phf02", "COSTCO", "41"
TOKEN = f"{HOST}/{PATH}/{ORG}/{CWS}"
BASE = f"https://{HOST}/{PATH}/ats/careers/v2"


def _card(rid, title, place="Issaquah &#40;Seattle&#41;, WA"):
    return (f'<div class="oracletaleocwsv2-accordion-head-info"><h4 class="oracletaleocwsv2-head-title">'
            f'<a href="{BASE}/viewRequisition?org={ORG}&cws={CWS}&rid={rid}" class="viewJobLink">'
            f'{title}</a></h4> <div tabindex="0" >627 - IT</div> <div tabindex="0" >{place}</div> </div>')


def _job(title, posted="Thu Jul 02 00:00:00 GMT 2026"):
    posting = {"@type": "JobPosting", "title": title, "datePosted": posted,
               "description": "<p>Keep Costco Travel running.</p>",
               "hiringOrganization": {"name": "Costco IT"},
               "jobLocation": {"address": {"addressLocality": "Issaquah", "addressRegion": "WA",
                                           "addressCountry": "US"}}}
    return f'<script type="application/ld+json">{json.dumps(posting)}</script>'


class _Board:
    def __init__(self, titles, removed=()):
        self.titles, self.removed, self.asked = titles, set(removed), []

    def get(self, url, **_):
        self.asked.append(url)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        if "searchResults" in url:
            start = int(query.get("rowFrom", 0))
            page = self.titles[start:start + taleo.PAGE_SIZE]
            body = "".join(_card(10000 + start + i, t) for i, t in enumerate(page))
            return Response(url=url, status=200, body=body)
        rid = query["rid"]
        if rid in self.removed:
            return Response(url=url, status=200,
                            body="This job has moved or is no longer available.")
        title = self.titles[int(rid) - 10000]
        return Response(url=url, status=200, body=_job(title))


def _cfg(*titles):
    return Config(titles_include=list(titles), locations=Locations(countries=["US"]))


def test_the_token_is_host_path_org_and_careers_site():
    assert taleo.parse_token(TOKEN) == (HOST, PATH, ORG, CWS)
    assert taleo.parse_token("phf.tbe.taleo.net/phf02/COSTCO") is None


def test_results_are_paged_by_row_and_only_your_titles_are_opened():
    titles = [f"Store Clerk {i}" for i in range(14)] + ["Build Engineer - Costco Travel"]
    board = _Board(titles)
    result = taleo.fetch(board, _cfg("engineer"), token=TOKEN, company="Costco",
                         today=dt.date(2026, 10, 1))
    assert [r.title for r in result.roles] == ["Build Engineer - Costco Travel"]
    assert [u for u in board.asked if "searchResults" in u][-1].endswith("rowFrom=10")
    assert len([u for u in board.asked if "viewRequisition" in u]) == 1
    role = result.roles[0]
    assert (role.platform, role.company, role.posted_at) == ("taleo", "Costco", "2026-07-02")
    assert role.url == f"{BASE}/viewRequisition?org={ORG}&cws={CWS}&rid=10014"


def test_discover_reads_either_order_even_inside_a_script():
    """Costco's link: cws before org, joined by \\u0026 in a script."""
    page = (f'"https://{HOST}/{PATH}/ats/careers/v2/jobSearch?act=redirectCwsV2'
            f'\\u0026cws={CWS}\\u0026org={ORG}\\"')
    other = f'<a href="https://{HOST}/{PATH}/ats/careers/v2/jobSearch?org=ACME&cws=7">x</a>'
    found, _ = discover._extract(page + other, "https://www.costco.com/jobs.html")
    assert sorted(f.token for f in found) == sorted([TOKEN, f"{HOST}/{PATH}/ACME/7"])


def test_discover_counts_the_board_and_does_not_also_call_it_unread():
    page = f'<a href="https://{HOST}/{PATH}/ats/careers/v2/jobSearch?org={ORG}&cws={CWS}">Jobs</a>'

    class _Costco(_Board):
        def get(self, url, **kw):
            if "taleo.net" in url:
                return super().get(url, **kw)
            return Response(url=url, status=200, body=page)

    report = discover.discover("https://www.costco.com", _Costco(["Pharmacist", "Optician"]))
    assert [(f.platform, f.token, f.status, f.jobs) for f in report.found] == [
        ("taleo", TOKEN, "verified", 2)]
    assert report.unsupported == [] and report.found[0].note == ""


def test_a_removed_job_says_so_and_counts_as_closed():
    board = _Board(["Build Engineer"], removed={"10001"})
    checker = listing.Checker(board)
    gone = checker._taleo(f"{BASE}/viewRequisition?org={ORG}&cws={CWS}&rid=10001")
    assert gone.state == "closed" and gone.hard
    assert checker._taleo(f"{BASE}/viewRequisition?org={ORG}&cws={CWS}&rid=10000") is None


def test_site_dates_in_the_java_form_are_read():
    assert site.date_of("Thu Jul 02 00:00:00 GMT 2026") == "2026-07-02"
    assert site.date_of("2026-06-24 00:00:00.0") == "2026-06-24"
    assert site.date_of("soon") == ""


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
