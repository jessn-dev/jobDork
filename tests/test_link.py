"""
One job post added from its link (fetch/link.py): a board by its token, a
Taleo Enterprise page, any page's schema.org JobPosting, and what is said
when none of them reads it. The Taleo page's shape is uhg.taleo.net's
(2026-10-28), with made-up words; nothing here touches the network.

    python tests/test_link.py
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import link
from jobdork.fetch.http import Response

TALEO = "https://acme.taleo.net/careersection/10000/jobdetail.ftl?job=12345"


class _Pages:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, **_):
        self.asked.append(url)
        body = self.pages.get(url)
        if body is None:
            return Response(url=url, status=404, error="HTTP 404")
        return Response(url=url, status=200, body=body)


def _cfg():
    return Config(titles_include=["nurse"], locations=Locations(countries=["US"]))


def _taleo_page(title="Charge Nurse", number="12345"):
    parts = ["ftlx0", "ftlUtil_resetPage!$!requisitionDescriptionInterface", "descRequisition",
             "rdPager!$!1", "true", "1", "false",
             f"Submission for the position\\: {title} - (Job Number\\: {number})",
             "false", "1", "false", "false", title, number,
             "!*!<p>Lead a 30-bed medical unit.</p>", "!*!<p>Lead a 30-bed medical unit.</p>",
             "!*!<p>Required: an RN licence.</p>", "!*!<p>Required: an RN licence.</p>",
             "Nursing", "Nursing", "US-TX-Austin", "US-TX-Austin", "", "",
             "Acme Nursing", "Acme Nursing", "Full-time", "Full-time",
             "Oct 26, 2026, 12\\:15\\:09 PM", "1", "1", "false"]
    value = "!|!".join(urllib.parse.quote(p, safe="!*$ ") for p in parts)
    return (f'<html><head><title>Careers at Acme Health</title></head><body>'
            f'<input type="hidden" name="initialHistory" id="initialHistory" value="{value}" />'
            f'</body></html>')


def _ld_page(**extra):
    posting = {"@context": "https://schema.org", "@type": "JobPosting",
               "title": "Registered Nurse", "datePosted": "2026-10-20",
               "description": "<p>Care for patients on a busy ward.</p>",
               "hiringOrganization": {"@type": "Organization", "name": "Acme Health"},
               "jobLocation": {"@type": "Place", "address": {
                   "addressLocality": "Austin", "addressRegion": "TX",
                   "addressCountry": "US"}}, **extra}
    return f'<script type="application/ld+json">{json.dumps(posting)}</script>'


def test_a_taleo_enterprise_page_is_read_from_its_hidden_field():
    found = link.taleo_posting(_taleo_page())
    assert found["title"] == "Charge Nurse"
    assert found["location_raw"] == "Austin, TX, US"
    assert found["posted_at"] == "2026-10-26"
    assert "30-bed" in found["description"] and "RN licence" in found["description"]
    assert found["description"].count("30-bed") == 1, "each part is there twice; read once"
    assert found["flags"] == ["job number 12345, Acme Nursing"]
    assert link.taleo_posting("<html>no field</html>") == {}


def test_a_taleo_link_becomes_a_job_post_named_for_the_employer():
    role = link.read(_Pages({TALEO: _taleo_page()}), _cfg(), TALEO)
    assert (role.platform, role.title, role.company, role.url) == \
        ("taleo", "Charge Nurse", "Acme Health", TALEO)


def test_any_page_with_a_job_posting_is_read():
    url = "https://careers.acme.org/jobs/rn-42"
    role = link.read(_Pages({url: _ld_page()}), _cfg(), url)
    assert (role.title, role.company, role.location_raw) == \
        ("Registered Nurse", "Acme Health", "Austin, TX, US")
    assert role.url == url and "busy ward" in role.description


def test_a_page_with_nothing_to_read_says_what_was_tried():
    url = "https://careers.acme.org/jobs/rn-42"
    for pages, said in (({url: "<html>a page drawn by script</html>"}, "schema.org JobPosting"),
                        ({}, "did not open"),
                        ({url: _ld_page(), "https://careers.acme.org/robots.txt":
                          "User-agent: *\nDisallow: /jobs/"}, "robots.txt")):
        try:
            link.read(_Pages(pages), _cfg(), url)
        except link.LinkError as exc:
            assert said in str(exc), exc
        else:
            raise AssertionError(f"expected nothing read: {said}")


def test_a_greenhouse_link_on_the_employer_s_site_is_read_from_its_page_or_says_token():
    url = "https://www.acme.org/careers?gh_jid=123"
    assert link.read(_Pages({url: _ld_page()}), _cfg(), url).title == "Registered Nurse"
    try:
        link.read(_Pages({}), _cfg(), url)
    except link.LinkError as exc:
        assert "board token" in str(exc)
    else:
        raise AssertionError("nothing to read")


def test_board_addresses_still_name_their_platform_and_token():
    assert link.platform_for("https://job-boards.greenhouse.io/acme/jobs/1") == ("greenhouse", "acme")
    assert link.platform_for("https://jobs.lever.co/acme/abc") == ("lever", "acme")
    assert link.platform_for("https://acme.breezy.hr/p/1") == ("breezy", "acme")
    assert link.platform_for("https://uhg.taleo.net/careersection/1/jobdetail.ftl") == ("", "")
    assert link.TALEO_ENTERPRISE.match("https://uhg.taleo.net/careersection/10000/jobdetail.ftl?job=1")


def test_a_pasted_advert_is_added_and_a_thin_one_refused():
    import tempfile

    from jobdork.db.store import Store
    from jobdork.web import api
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg()
        cfg.db_path = str(Path(tmp) / "j.db")
        for bad, said in ((("", "Nurse", "x" * 300), "link"), (("https://a.test/1", "", "x" * 300), "title"),
                          (("https://a.test/1", "Nurse", "too short"), "whole advert")):
            try:
                api.add_by_text(cfg, bad[0], bad[1], "Acme", "Austin, TX", bad[2])
            except api.ApiError as exc:
                assert said in str(exc), exc
            else:
                raise AssertionError(f"{bad} must be refused")
        done = api.add_by_text(cfg, "https://a.test/1", "Registered Nurse", "Acme",
                               "Austin, TX", "Care for patients. " * 20)
        assert done["added"] and done["title"] == "Registered Nurse"
        with Store(cfg.db_path) as store:
            row = store.conn.execute("SELECT title, description FROM roles").fetchone()
        assert row[0] == "Registered Nurse" and "Care for patients" in row[1]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"\n{len(tests)}/{len(tests)} passed")
