"""
Discover's reading order: the page you gave, the front page, same-site job
links, the sitemap, then the usual paths, within a page budget, honouring
robots.txt and dropping hosts that do not answer. Nothing here touches the
network.

    python tests/test_discover.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.fetch import robots
from jobdork.fetch.http import Response
from jobdork.search import discover

GREENHOUSE = '<a href="https://boards.greenhouse.io/acme/jobs/1">Apply</a>'


class _Site:
    """Pages by URL; anything else 404. Every request recorded."""

    def __init__(self, pages: dict[str, object]):
        self.pages, self.asked = pages, []

    def get(self, url, **_):
        self.asked.append(url)
        page = self.pages.get(url)
        if isinstance(page, int):
            return Response(url=url, status=page, error=f"HTTP {page}")
        if page is None:
            return Response(url=url, status=404, error="HTTP 404")
        return Response(url=url, status=200, body=page)

    def post(self, url, **_):
        return Response(url=url, status=404, error="HTTP 404")


def _pages_only(site):
    return [u for u in site.asked if not u.endswith("/robots.txt")
            and "greenhouse" not in u]


def test_job_links_stay_on_the_site_and_rank_search_first():
    html = ('<a href="/about">About</a><a href="/careers">Careers</a>'
            '<a href="https://careers.acme.com/jobs/search?q=">Search jobs</a>'
            '<a href="https://other.com/jobs">Elsewhere</a>'
            '<a href="/careers/logo.png">x</a><a href="mailto:jobs@acme.com">mail</a>')
    links = discover._job_links(html, "https://www.acme.com/")
    assert links == ["https://careers.acme.com/jobs/search?q=",
                     "https://www.acme.com/careers"]


def test_registrable_domain_reads_country_second_levels():
    assert discover._site("careers.acme.co.uk") == "acme.co.uk"
    assert discover._site("jobs.acme.com") == "acme.com"
    assert discover._site("www.acme.com.ph") == "acme.com.ph"


def test_follows_a_front_page_link_to_the_board():
    site = _Site({
        "https://acme.com/": '<a href="/work-here/open-positions">Open positions</a>',
        "https://acme.com/work-here/open-positions": GREENHOUSE,
    })
    report = discover.discover("acme.com", site)
    assert [f.token for f in report.found] == ["acme"]
    assert report.pages_read == ["https://acme.com/",
                                 "https://acme.com/work-here/open-positions"]


def test_sitemap_postings_are_read_when_links_lead_nowhere():
    site = _Site({
        "https://acme.com/robots.txt": "User-agent: *\nAllow: /\nSitemap: https://acme.com/sm.xml\n",
        "https://acme.com/": "<p>Welcome</p>",
        "https://acme.com/sm.xml": ("<sitemapindex><sitemap><loc>https://acme.com/sm-blog.xml</loc>"
                                    "</sitemap><sitemap><loc>https://acme.com/sm-jobs.xml</loc>"
                                    "</sitemap></sitemapindex>"),
        "https://acme.com/sm-jobs.xml": ("<urlset><url><loc>https://acme.com/careers</loc></url>"
                                         "<url><loc>https://acme.com/careers/jobs/nurse-123</loc></url>"
                                         "</urlset>"),
        "https://acme.com/careers/jobs/nurse-123": GREENHOUSE,
    })
    report = discover.discover("acme.com", site)
    assert [f.token for f in report.found] == ["acme"]
    assert "https://acme.com/sm-blog.xml" not in site.asked
    # The posting, the deepest address, is read before the landing page.
    assert report.pages_read[-1] == "https://acme.com/careers/jobs/nurse-123"


def test_robots_txt_closes_a_page():
    site = _Site({
        "https://acme.com/robots.txt": "User-agent: *\nDisallow: /careers\n",
        "https://acme.com/": '<a href="/careers">Careers</a>',
        "https://acme.com/careers": GREENHOUSE,
    })
    report = discover.discover("acme.com", site)
    assert "https://acme.com/careers" not in site.asked
    assert not report.found
    assert "https://acme.com/careers" in report.robots_skipped
    assert any("robots.txt" in line for line in report.lines())


def test_a_dead_host_is_not_asked_again():
    site = _Site({"https://acme.com/robots.txt": 0, "https://acme.com/": 0,
                  "https://www.acme.com/": "<p>hi</p>"})
    report = discover.discover("acme.com", site)
    assert [u for u in site.asked if u.startswith("https://acme.com")] == [
        "https://acme.com/robots.txt", "https://acme.com/"]
    assert report.unreachable == ["acme.com"]


def test_a_refusing_host_is_blocked_and_dropped():
    site = _Site({"https://acme.com/": 403})
    report = discover.discover("acme.com", site)
    assert report.blocked == ["acme.com"]
    assert [u for u in site.asked if u.startswith("https://acme.com/")
            and not u.endswith("robots.txt")] == ["https://acme.com/"]


def test_reading_stops_at_the_page_budget():
    links = "".join(f'<a href="/jobs/{n}">Job {n}</a>' for n in range(30))
    site = _Site({"https://acme.com/": links,
                  **{f"https://acme.com/jobs/{n}": links for n in range(30)},
                  **{f"https://acme.com{p}": "<p>nothing</p>" for p in discover.CAREERS_PATHS}})
    discover.discover("acme.com", site)
    # The crawl stops at its budget; the site check after it has its own.
    from jobdork.fetch import site as site_reader
    crawled = [u for u in _pages_only(site) if "sitemap" not in u]
    assert discover.MAX_PAGES - 1 <= len(crawled) <= discover.MAX_PAGES
    assert len(_pages_only(site)) <= discover.MAX_PAGES + site_reader.MAX_SITEMAP_READS + 2


def test_stops_at_the_first_board():
    site = _Site({"https://acme.com/": GREENHOUSE + '<a href="/jobs">Jobs</a>'})
    discover.discover("acme.com", site)
    assert "https://acme.com/jobs" not in site.asked


def test_robots_longest_rule_wins_as_rfc_9309_says():
    """jobs.nvidia.com: `Disallow: /` first, `Allow: /careers` after."""
    rules = robots.robot_rules("User-agent: *\nDisallow: /\nAllow: /$\nAllow: /careers\n")
    assert robots.robots_allows(rules, "https://jobs.nvidia.com/careers")
    assert robots.robots_allows(rules, "https://jobs.nvidia.com/")
    assert not robots.robots_allows(rules, "https://jobs.nvidia.com/profile")


def test_robots_group_for_this_agent_replaces_the_star_group():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: jobdork\nDisallow: /private\n"
    rules = robots.robot_rules(text)
    assert robots.robots_allows(rules, "https://acme.com/careers")
    assert not robots.robots_allows(rules, "https://acme.com/private/x")


def test_job_words_are_whole_words_and_entities_are_unescaped():
    html = ('<a href="/glucosamine-joint-supplements.html?a=1&amp;b=2">x</a>'
            '<a href="/jobs?a=1&amp;b=2">Jobs</a>')
    assert discover._job_links(html, "https://www.costco.com/") == [
        "https://www.costco.com/jobs?a=1&b=2"]


def test_a_board_met_only_deep_under_another_name_says_check_it():
    site = _Site({
        "https://careers.marriott.com/": '<a href="/brands/vacation-club/jobs">Jobs</a>',
        "https://careers.marriott.com/brands/vacation-club/jobs":
            '<a href="https://boards.greenhouse.io/mymvw/jobs/1">Apply</a>',
        "https://boards-api.greenhouse.io/v1/boards/mymvw/jobs": "{}",
    })
    report = discover.discover("careers.marriott.com", site)
    assert [f.token for f in report.found] == ["mymvw"]
    assert "sister company" in report.found[0].note


def test_a_board_named_inside_the_site_name_is_theirs():
    site = _Site({
        "https://www.lifeatspotify.com/": '<a href="/jobs/ml-manager">Job</a>',
        "https://www.lifeatspotify.com/jobs/ml-manager": '<a href="https://jobs.lever.co/spotify/1">Apply</a>',
    })
    report = discover.discover("lifeatspotify.com", site)
    assert [f.token for f in report.found] == ["spotify"] and "sister" not in report.found[0].note


def test_a_long_run_of_letters_does_not_stall_the_page_reader():
    """40,000 letters of inline data in a row took 87 seconds per pattern."""
    import time
    page = "<script>x='" + "A" * 500_000 + "'</script> https://kp.icims.com/jobs"
    started = time.monotonic()
    _, unsupported = discover._extract(page, "https://acme.com/")
    assert time.monotonic() - started < 5
    assert [f.token for f in unsupported] == ["kp"]


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
