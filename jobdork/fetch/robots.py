"""
jobdork.fetch.robots
====================
robots.txt, read the way RFC 9309 says, for every page jobdork reads off an
employer's own site: `discover` finding a board, and the site reader
(fetch/site.py) reading postings.
"""

from __future__ import annotations

import re
import urllib.parse

from .http import Fetcher

# Robots.txt is read as this agent. Rules for "*" apply to it as well.
ROBOTS_AGENT = "jobdork"


def base(url: str) -> str:
    """scheme://host of an address."""
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def robot_rules(text: str, agent: str = ROBOTS_AGENT) -> list[tuple[bool, str]]:
    """(allow, path pattern) for `agent`, or for "*" when no group names it.

    Groups follow RFC 9309: consecutive User-agent lines share the rules
    after them, and a group naming this agent replaces the "*" group rather
    than adding to it.
    """
    groups: dict[str, list[tuple[bool, str]]] = {}
    agents: list[str] = []
    in_rules = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.lower())
            for name in agents:
                groups.setdefault(name, [])
        elif key in ("allow", "disallow") and agents:
            in_rules = True
            if value:                         # "Disallow:" alone allows all
                for name in agents:
                    groups[name].append((key == "allow", value))
    for name, rules in groups.items():
        if name != "*" and name in agent.lower():
            return rules
    return groups.get("*", [])


def robots_allows(rules: list[tuple[bool, str]], url: str) -> bool:
    """RFC 9309: the longest matching rule decides, and Allow wins a tie.

    Python's urllib.robotparser takes the first match instead, and so reads
    jobs.nvidia.com's `Disallow: /` ahead of its `Allow: /careers` and
    closes the very page the site opens to tools.
    """
    parts = urllib.parse.urlsplit(url)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    best: tuple[int, bool] = (-1, True)
    for allow, pattern in rules:
        regex = "".join(".*" if ch == "*" else "$" if ch == "$" and i == len(pattern) - 1
                        else re.escape(ch) for i, ch in enumerate(pattern))
        if re.match(regex, path):
            best = max(best, (len(pattern), allow))
    return best[1]


class Robots:
    """Each host's robots.txt, read once, asked before every page.

    A robots.txt that cannot be read (404, a server error) allows everything,
    which is what the convention says; one that refuses us (401, 403) is the
    host refusing, and is reported as blocked.
    """

    def __init__(self, fetcher: Fetcher):
        self.fetcher = fetcher
        self.rules: dict[str, list[tuple[bool, str]]] = {}
        self.sitemaps: dict[str, list[str]] = {}
        self.status: dict[str, int] = {}

    def _load(self, site: str) -> None:
        if site in self.rules:
            return
        resp = self.fetcher.get(site + "/robots.txt", expect_json=False)
        self.status[site] = resp.status
        if not resp.ok or not resp.body or "<html" in resp.body[:500].lower():
            self.rules[site] = []
            self.sitemaps[site] = []
            return
        self.rules[site] = robot_rules(resp.body)
        self.sitemaps[site] = re.findall(r"^\s*sitemap:\s*(\S+)", resp.body,
                                         re.IGNORECASE | re.MULTILINE)

    def allowed(self, url: str) -> bool:
        url_base = base(url)
        self._load(url_base)
        return robots_allows(self.rules[url_base], url)

    def sitemap_list(self, site: str) -> list[str]:
        self._load(site)
        return self.sitemaps[site] or [site + "/sitemap.xml"]
