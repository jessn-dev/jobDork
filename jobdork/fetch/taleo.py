"""
jobdork.fetch.taleo
===================
Taleo Business Edition: an employer's careers pages on *.tbe.taleo.net.
Costco hires through it.

    GET https://{host}/{path}/ats/careers/v2/searchResults?org={org}&cws={cws}&rowFrom=…
    GET https://{host}/{path}/ats/careers/v2/viewRequisition?org={org}&cws={cws}&rid={id}

There is no JSON. The search results are a page listing ten jobs at a time
(title, department, place, link), paged by `rowFrom` with no session needed;
each job's own page carries a schema.org `JobPosting`, read as fetch/site.py
reads any employer's. robots.txt on these hosts answers 404, which allows
everything; the pages are paced all the same.

The token is four parts, `host/path/org/cws`
(`phf.tbe.taleo.net/phf02/COSTCO/41`), read off the employer's careers page by
`discover`. Only titles your title rules keep are opened, one page each.

Taleo Enterprise (`*.taleo.net/careersection/…`) is a different product, and
has no reader here.
"""

from __future__ import annotations

import datetime as dt
import html
import re
import urllib.parse

from . import SourceResult, register, site
from .boards import clean

PAGE_SIZE = 10              # fixed by Taleo
MAX_PAGES = 30              # 300 jobs: a board bigger than that is cut, and says so
RATE = 1.0

_CARD = re.compile(
    r'<a href="[^"]*viewRequisition\?[^"]*rid=(\d+)"[^>]*class="viewJobLink"[^>]*>([^<]+)</a>'
    r"\s*</h4>(.*?)</div>\s*</div>", re.DOTALL)
_FIELD = re.compile(r"<div[^>]*>([^<]+)</div>")


def parse_token(token: str) -> tuple[str, str, str, str] | None:
    """(host, path, org, cws) from `host/path/org/cws`."""
    parts = (token or "").strip().strip("/").split("/")
    if len(parts) == 4 and parts[0].endswith(".taleo.net") and parts[3].isdigit():
        return tuple(parts)                                     # type: ignore[return-value]
    return None


def base(host: str, path: str) -> str:
    return f"https://{host}/{path}/ats/careers/v2"


def results(fetcher, host: str, path: str, org: str, cws: str, row_from: int = 0):
    query = urllib.parse.urlencode({"org": org, "cws": cws, "rowFrom": row_from})
    return fetcher.get(f"{base(host, path)}/searchResults?{query}", expect_json=False)


def job_url(host: str, path: str, org: str, cws: str, rid: str) -> str:
    query = urllib.parse.urlencode({"org": org, "cws": cws, "rid": rid})
    return f"{base(host, path)}/viewRequisition?{query}"


def cards(page: str) -> list[dict]:
    """[{rid, title, place}] from a search-results page, each job once."""
    found: dict[str, dict] = {}
    for rid, title, rest in _CARD.findall(page or ""):
        fields = [html.unescape(f).strip() for f in _FIELD.findall(rest)]
        found.setdefault(rid, {"rid": rid, "title": clean(html.unescape(title)),
                               "place": fields[-1] if fields else ""})
    return list(found.values())


def listing(fetcher, host: str, path: str, org: str, cws: str,
            max_pages: int = MAX_PAGES) -> tuple[list[dict], int, bool]:
    """(every job card, requests, cut short) for one board."""
    seen: dict[str, dict] = {}
    for page in range(max_pages):
        resp = results(fetcher, host, path, org, cws, page * PAGE_SIZE)
        found = cards(resp.body) if resp.ok else []
        fresh = [c for c in found if c["rid"] not in seen]
        for card in fresh:
            seen[card["rid"]] = card
        if not fresh or len(found) < PAGE_SIZE:
            return list(seen.values()), page + 1, False
    return list(seen.values()), max_pages, True


@register("taleo")
def fetch(fetcher, cfg, token: str = "", company: str = "",
          today: dt.date | None = None, **_) -> SourceResult:
    from ..search.screen import title_verdict

    parts = parse_token(token)
    if not parts:
        return SourceResult(source="taleo", skipped=(
            f"taleo token {token!r} must be host/path/org/cws, as in "
            "phf.tbe.taleo.net/phf02/COSTCO/41; `jobdork discover` reads it off "
            "the employer's careers page"))
    host, path, org, cws = parts
    if hasattr(fetcher, "pace"):
        fetcher.pace(host, RATE)
    today = today or dt.date.today()
    result = SourceResult(source="taleo")
    jobs, requests_made, cut = listing(fetcher, host, path, org, cws)
    result.requests_made += requests_made
    if cut:
        result.errors.append(f"{token}: read the first {len(jobs)} jobs; the board lists more")

    for card in jobs:
        if not title_verdict(card["title"], cfg)[0]:
            continue
        url = job_url(host, path, org, cws, card["rid"])
        resp = fetcher.get(url, expect_json=False)
        result.requests_made += 1
        posting = site.job_posting(resp.body) if resp.ok else {}
        if posting and site.closed(posting, today):
            continue
        role = site.to_role(posting, url, company or org) if posting else None
        if role is None:
            continue
        role.platform = "taleo"
        role.url = url
        if company:
            role.company = company
        result.roles.append(role)
    return result
