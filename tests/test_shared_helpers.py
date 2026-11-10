"""
Small helpers that several modules used to keep a copy of each, now shared
(code scan, 2026-11-06). Each test pins what every old copy did, plus the
fixes that came with merging them. Nothing here touches the network.

    python tests/test_shared_helpers.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import config, notify, textutil, updates
from jobdork.fetch import adzuna, ashby, day_from_epoch, greenhouse, number, site


def test_a_number_is_a_finite_float_or_none():
    assert number("85000") == 85000.0 and number(12) == 12.0
    for bad in (None, "", "eighty", [], {}):
        assert number(bad) is None, bad
    # Code scan #16: these parse as floats, and a NaN salary broke the pay floor.
    for odd in ("nan", "NaN", "inf", "-inf", float("nan")):
        assert number(odd) is None, odd
    assert ashby._num("nan") is None and ashby._num("1.5") == 1.5
    assert greenhouse._num("12345", cents=True) == 123.45
    assert greenhouse._num("nan", cents=True) is None
    assert adzuna._num("0") is None and adzuna._num("-5") is None and adzuna._num("40000") == 40000.0


def test_a_day_from_a_unix_timestamp_is_utc_or_none():
    assert day_from_epoch(0) == dt.date(1970, 1, 1)
    assert day_from_epoch("1762646400") == dt.date(2025, 11, 9)
    for bad in (None, "soon", 10**20):
        assert day_from_epoch(bad) is None, bad


def test_folded_text_is_lower_case_with_single_spaces():
    assert textutil.folded("  Needs  FIVE\nyears\tof Python ") == "needs five years of python"
    assert textutil.folded(None) == ""


def test_xml_text_escapes_for_an_element_and_a_quoted_attribute():
    assert textutil.xml_text('a & b <c> "d"') == "a &amp; b &lt;c&gt; &quot;d&quot;"
    assert textutil.xml_text(5) == "5"


def test_every_environment_switch_reads_off_the_same_way():
    saved = {name: os.environ.get(name) for name in (notify.ENV, updates.ENV)}
    try:
        for word in ("off", "OFF", " 0 ", "no", "False"):
            os.environ[notify.ENV] = os.environ[updates.ENV] = word
            assert notify.off() and updates.off() and config.env_off(notify.ENV), word
        for word in ("on", "1", "yes", ""):
            os.environ[notify.ENV] = os.environ[updates.ENV] = word
            assert not notify.off() and not updates.off(), word
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_one_sitemap_reader_for_the_site_reader_and_discover():
    index = ("<sitemapindex><sitemap><loc> https://a.test/jobs.xml </loc></sitemap>"
             "<sitemap><loc></loc></sitemap></sitemapindex>")
    assert site.sitemap_urls(index) == (["https://a.test/jobs.xml"], [])
    pages = ("<urlset><url><loc>https://a.test/job/1</loc><lastmod>2026-11-01</lastmod></url>"
             "<url><LOC>https://a.test/job/2</LOC></url></urlset>")
    assert site.sitemap_urls(pages) == ([], [("https://a.test/job/1", "2026-11-01"),
                                             ("https://a.test/job/2", "")])


def test_a_hostile_sitemap_does_not_stall_the_reader():
    """Claude Security F12 (2026-11-06): `<loc>\\s*([^<]+?)\\s*</loc>` on a long
    run of spaces with no closing tag tried every split of the run."""
    hostile = "<urlset><url><loc>" + " " * 200_000 + "x"
    started = time.monotonic()
    assert site.sitemap_urls(hostile) == ([], [])
    assert site.sitemap_urls("<sitemapindex><loc>" + " " * 200_000) == ([], [])
    assert time.monotonic() - started < 2, "linear, not a stall"


# ── keep this block LAST ───────────────────────────────────────────────────────

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
