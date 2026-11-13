"""
We Work Remotely: remote jobs from its category RSS feeds, kept to your
countries and titles. The sample has the live feed's fields (checked
2026-11-13) and invented employers; nothing here touches the network.

    python tests/test_weworkremotely.py
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config, Locations
from jobdork.fetch import weworkremotely as wwr
from jobdork.fetch.http import Response

TODAY = date(2026, 11, 13)


def _item(n, title="Customer Support Specialist", region="USA Only", kind="Full-Time",
          posted="Wed, 11 Nov 2026 10:00:00 +0000", expires="Fri, 11 Dec 2026 10:00:00 +0000"):
    return (f"<item><title>Acme {n}: {title}</title><region>{region}</region>"
            f"<category>Customer Support</category><type>{kind}</type>"
            "<description>&lt;p&gt;Answer customers by &lt;b&gt;email&lt;/b&gt; "
            "and chat.&lt;/p&gt;</description>"
            f"<pubDate>{posted}</pubDate><expires_at>{expires}</expires_at>"
            f"<guid>https://weworkremotely.com/remote-jobs/acme-{n}</guid>"
            f"<link>https://weworkremotely.com/remote-jobs/acme-{n}</link></item>")


def _feed(*items):
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            "<title>We Work Remotely</title><ttl>60</ttl>" + "".join(items)
            + "</channel></rss>")


class _Fetcher:
    """Every category feed answers with the same body."""

    def __init__(self, body, status=200):
        self.body, self.status, self.asked = body, status, []

    def get(self, url, **_):
        self.asked.append(url)
        return Response(url=url, status=self.status, body=self.body,
                        error="" if self.status == 200 else f"HTTP {self.status}")


def _cfg(countries=("US",), modes=(), titles=("customer support",)):
    return Config(titles_include=list(titles),
                  locations=Locations(cities=[], radius="any", countries=list(countries),
                                      work_modes=list(modes)))


def test_a_job_is_read_whole_with_its_employer_dates_and_region():
    role = wwr.to_role(_item(1, kind="Contract")[6:-7], TODAY)
    assert role.platform == "weworkremotely" and role.company == "Acme 1"
    assert role.title == "Customer Support Specialist" and role.work_mode == "remote"
    assert role.url == "https://weworkremotely.com/remote-jobs/acme-1"
    assert role.posted_at == "2026-11-11"
    assert "email" in role.description and "<p>" not in role.description
    assert role.flags == ["remote, open to USA only", "contract",
                          "applications close 2026-12-11"]
    worldwide = wwr.to_role(_item(2, region="Anywhere in the World")[6:-7], TODAY)
    assert worldwide.flags[0] == "remote worldwide"
    assert wwr.to_role(_item(3, expires="Mon, 09 Nov 2026 10:00:00 +0000")[6:-7], TODAY) is None


def test_who_may_apply_decides_what_is_kept():
    us = {"US"}
    assert wwr.region_allows("USA Only", us) and wwr.region_allows("North America Only", us)
    assert wwr.region_allows("Anywhere in the World", us)
    assert not wwr.region_allows("Asia Only", us) and not wwr.region_allows("EMEA Only", us)
    assert wwr.region_allows("Asia Only", {"PH"}) and not wwr.region_allows("USA Only", {"PH"})
    assert wwr.region_allows("Europe Only", {"DE"}) and wwr.region_allows("EMEA Only", {"NG"})
    assert wwr.region_allows("Mars Only", us), "a region the table does not know is kept"
    assert wwr.region_allows("Asia Only", set()), "with no countries, every job is kept"


def test_every_category_feed_is_read_and_kept_to_your_countries_and_titles():
    body = _feed(_item(1), _item(2, region="Asia Only"), _item(3, region="Anywhere in the World"),
                 _item(4, title="Senior Golang Engineer"))
    fetcher = _Fetcher(body)
    result = wwr.fetch(fetcher, _cfg(), today=TODAY)
    assert len(fetcher.asked) == len(wwr.CATEGORIES) == result.requests_made
    assert all(u.startswith("https://weworkremotely.com/categories/") for u in fetcher.asked)
    assert sorted(r.company for r in result.roles) == ["Acme 1", "Acme 3"], \
        "Asia only is not open to the US; the engineer is not one of your titles"
    assert not result.errors and not result.suspect


def test_it_says_why_it_did_not_run_or_found_nothing():
    skipped = wwr.fetch(_Fetcher(_feed()), _cfg(modes=("onsite",)), today=TODAY)
    assert skipped.skipped and "remote" in skipped.skipped and not skipped.requests_made
    empty = wwr.fetch(_Fetcher(_feed()), _cfg(), today=TODAY)
    assert empty.suspect, "600 jobs do not all vanish at once"
    refused = wwr.fetch(_Fetcher("", status=403), _cfg(), today=TODAY)
    assert len(refused.errors) == len(wwr.CATEGORIES) and not refused.suspect


def test_a_feed_of_unclosed_items_is_read_in_one_pass():
    """str.find, not a pattern: a pattern would read to the end once per item."""
    started = time.perf_counter()
    assert wwr._items("<item><title>x" * 200_000) == []
    assert time.perf_counter() - started < 1.0


def test_it_is_a_keyless_source_paced_and_not_read_page_by_page():
    from jobdork.core.config import KEYLESS_SOURCES
    from jobdork.fetch import REGISTRY, http
    from jobdork.search import enrich, listing

    assert "weworkremotely" in KEYLESS_SOURCES and "weworkremotely" in REGISTRY
    assert http.HOST_RATES["weworkremotely.com"] <= 1.0
    assert "weworkremotely" in listing.UNREADABLE and "weworkremotely" in enrich.UNREACHABLE


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
