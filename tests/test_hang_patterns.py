"""
Group 2 of the code scans of 2026-11-06: a page, a sitemap or a robots.txt
from a stranger cannot freeze jobdork, and one answer cannot fill the
memory. Each pattern is fed what used to make it backtrack, with a time
limit, and checked to still read the ordinary case. No network.

    python tests/test_hang_patterns.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import textutil
from jobdork.fetch import http, link, robots, site
from jobdork.search import agency

SECONDS = 2.0


def _quick(fn, *args):
    started = time.monotonic()
    out = fn(*args)
    took = time.monotonic() - started
    assert took < SECONDS, f"{fn.__name__} took {took:.1f}s"
    return out


def test_robots_wildcards_are_matched_without_a_regex():
    for pattern, path, want in (("/", "/jobs", True), ("/jobs", "/jobs/1", True),
                                ("/jobs$", "/jobs", True), ("/jobs$", "/jobs/1", False),
                                ("/*.pdf$", "/a/b.pdf", True), ("/*.pdf$", "/a/b.pdf?x", False),
                                ("/a*b*c", "/axxbyyc", True), ("/a*b*c", "/axxcyyb", False),
                                ("/*/careers", "/en/careers/1", True), ("*", "/x", True),
                                ("/x", "/y", False)):
        assert robots._matches(pattern, path) == want, (pattern, path)
    assert robots.robots_allows([(False, "/"), (True, "/careers")], "https://a.test/careers/1")
    hostile = "/" + "*a" * 19 + "*b"
    assert _quick(robots.robots_allows, [(False, hostile)], "https://a.test/" + "a" * 50_000) is True
    assert not robots._matches("/" + "*a" * 30, "/aaaa"), "too many wildcards: matches nothing"


def test_the_agency_pattern_does_not_stall_on_a_long_run_of_space():
    text = "Our client " + " " * 60_000 + "x"
    assert _quick(agency._ADVERT.search, text)
    assert not agency._ADVERT.search("Our client - success team")
    assert agency._ADVERT.search("Our client is a leading hospital")


def test_html_and_sitemaps_and_titles_are_read_in_one_pass():
    assert _quick(textutil.html_to_text, "<" * 200_000 + "x") .endswith("x")
    assert _quick(textutil.html_to_text, "<script>" * 20_000 + "text") == ""
    assert textutil.html_to_text("<p>One</p><script>var a='<p>';</script><p>Two</p>") == "One\n\nTwo"
    assert _quick(site.sitemap_urls, "<urlset>" + "<url><loc>x" * 50_000) == ([], [])
    assert site.sitemap_urls("<urlset><url><loc>https://a.test/1</loc></url>"
                             "<url><loc>https://a.test/2</loc><lastmod>2026</lastmod></url>") \
        == ([], [("https://a.test/1", ""), ("https://a.test/2", "2026")])
    assert _quick(link._site_name, "<title>" + " " * 200_000) == ""
    assert link._site_name("<title>Careers at Acme Health | Jobs</title>") == "Acme Health"
    assert link._site_name("<title>Acme – Open roles</title>") == "Acme"
    page = ('<script type="application/ld+json">{"a": 1}</script>'
            '<script>x</script><script type="application/ld+json">{"b": 2}</script>')
    assert textutil.ld_json_blocks(page) == ['{"a": 1}', '{"b": 2}']
    unclosed = '<script type="application/ld+json">' * 30_000
    assert _quick(textutil.ld_json_blocks, unclosed) == []


def test_one_answer_is_read_only_so_far():
    class _Resp:
        def __init__(self, chunks):
            self.chunks, self.closed = chunks, False

        def iter_content(self, size):
            yield from self.chunks

        def close(self):
            self.closed = True
    was = http.MAX_BODY_BYTES
    http.MAX_BODY_BYTES = 10
    try:
        resp = _Resp([b"12345", b"67890", b"abcde"])
        http._read_capped(resp)
    finally:
        http.MAX_BODY_BYTES = was
    assert resp._content == b"1234567890" and resp.closed
    small = _Resp([b"ok"])
    http._read_capped(small)
    assert small._content == b"ok"


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
