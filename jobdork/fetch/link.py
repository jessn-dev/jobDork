"""
jobdork.fetch.link
==================
One job post read from its link, for **Add a job post** and `jobdork add`.

Adding by link knew five systems, by their addresses, and refused the rest:
a UnitedHealth Group post on Taleo Enterprise
(`uhg.taleo.net/careersection/10000/jobdetail.ftl?job=2389918`) came back
"cannot tell which platform that URL is on" (2026-10-27). Now, in order:

  1. **A board read by its token** (Greenhouse, Ashby, Lever, Breezy,
     SmartRecruiters): the board is read and the post found on it, advert
     and all, as a scan would.
  2. **A system whose page is drawn by script** (Workday, Oracle Recruiting,
     Eightfold): the post's own record, through the same address a scan
     uses for the advert.
  3. **Taleo Enterprise** (`*.taleo.net/careersection/…`): its job page has
     no schema.org markup; the title, job number, place, department, type,
     date and advert are in a hidden field, `initialHistory` (taleo_posting).
  4. **Any other page**: its schema.org `JobPosting` (JSON-LD or microdata),
     as an employer's careers site is read (fetch/site.py). robots.txt is
     honoured.

When none of these reads it, LinkError says what was tried, and the page
offers to take the advert's text pasted in instead (api.add_by_text).
"""

from __future__ import annotations

import html
import re
import urllib.parse

from ..core.textutil import to_text
from ..db.store import Role, canonical_url
from .boards import clean


class LinkError(Exception):
    """Nothing could be read from the link; the message says why."""


# Boards whose token is in the address. Each is read whole and the post found.
_BOARDS = (
    (r"(?:job-)?boards\.greenhouse\.io/([^/?]+)", "greenhouse"),
    (r"jobs\.ashbyhq\.com/([^/?]+)", "ashby"),
    (r"jobs\.lever\.co/([^/?]+)", "lever"),
    (r"([a-z0-9-]+)\.breezy\.hr", "breezy"),
    (r"jobs\.smartrecruiters\.com/([^/?]+)", "smartrecruiters"),
    (r"api\.smartrecruiters\.com/v1/companies/([^/?]+)", "smartrecruiters"),
)
TALEO_ENTERPRISE = re.compile(r"https?://[a-z0-9-]+\.taleo\.net/careersection/[^?#]*"
                              r"jobdetail\.ftl", re.IGNORECASE)


def platform_for(url: str) -> tuple[str, str]:
    """The board platform and token in a posting's address, or ("", "").

    ("greenhouse", "") for a `?gh_jid=` link on an employer's own domain:
    the platform is certain but the board token is not in the address.
    """
    for pattern, platform in _BOARDS:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return platform, match.group(1)
    if re.search(r"[?&]gh_jid=", url, re.IGNORECASE):
        return "greenhouse", ""
    return "", ""


def read(fetcher, cfg, url: str, token: str = "", company: str = "") -> Role:
    """The job post at `url`, read the best way its system allows.

    Raises LinkError when nothing could be read, saying what was tried.
    """
    url = canonical_url((url or "").strip())
    if not url.startswith(("http://", "https://")):
        raise LinkError("give the job post's address, starting https://")
    tried: list[str] = []

    platform, found = platform_for(url)
    token = token or found
    if platform and token:
        role, why = _from_board(fetcher, cfg, url, platform, token, company)
        if role:
            return role
        tried.append(why)

    role, why = _from_system(fetcher, url, company)
    if role:
        return role
    if why:
        tried.append(why)

    role, why = _from_page(fetcher, url, company)
    if role:
        return role
    tried.append(why)
    if platform == "greenhouse" and not token:
        tried.append("a Greenhouse post on the employer's own site can also be read "
                     "with its board token, typed in the second box")
    raise LinkError("no job post could be read from that link: " + "; ".join(tried))


def _from_board(fetcher, cfg, url, platform, token, company) -> tuple[Role | None, str]:
    from . import get as get_adapter

    result = get_adapter(platform)(fetcher, cfg, token=token, company=company or token)
    if result.skipped:
        return None, f"{platform}: {result.skipped}"
    wanted = next((r for r in result.roles if canonical_url(r.url) == url), None)
    if wanted is None:
        return None, (f"read {token!r} on {platform} ({len(result.roles)} job posts) "
                      "but none of them is that link; it may already be filled")
    return wanted, ""


def _from_system(fetcher, url, company) -> tuple[Role | None, str]:
    """Workday, Oracle and Eightfold, whose pages are drawn by script."""
    from . import eightfold, oracle, workday

    if workday.PAGE_URL.match(url):
        info, read = workday.advert(fetcher, url)
        if info:
            tenant = workday.PAGE_URL.match(url).group(1)
            return workday._to_role({}, info, company or tenant, url), ""
        return None, "Workday " + ("has no such job post" if read else "did not answer")
    if (match := oracle.PAGE_URL.match(url)):
        info, read = oracle.record(fetcher, url)
        if info:
            host, site, _ = match.groups()
            return oracle._to_role({}, info, host, site, company), ""
        return None, "Oracle Recruiting " + ("has no such job post" if read else "did not answer")
    if ".eightfold.ai/" in url and "/job/" in url:
        info, read = eightfold.record(fetcher, url)
        if info:
            parts = urllib.parse.urlsplit(url)
            domain = (urllib.parse.parse_qs(parts.query).get("domain") or [""])[0]
            return eightfold._to_role(info, info, parts.netloc, domain, company), ""
        return None, "Eightfold " + ("has no such job post" if read else "did not answer")
    return None, ""


def _from_page(fetcher, url, company) -> tuple[Role | None, str]:
    from .robots import Robots
    from .site import job_posting, microdata_posting, to_role

    if not Robots(fetcher).allowed(url):
        return None, "the site's robots.txt does not allow reading that page"
    resp = fetcher.get(url, expect_json=False)
    if not resp.ok:
        return None, f"the page did not open ({_why_closed(resp)})"
    page = resp.body or ""
    host = urllib.parse.urlsplit(url).netloc
    owner = company or _site_name(page) or host
    if TALEO_ENTERPRISE.match(url):
        posting = taleo_posting(page)
        if posting:
            return Role(platform="taleo", company=owner, url=url, **posting), ""
        return None, "the Taleo page carried no job post (it may be closed)"
    posting = job_posting(page) or microdata_posting(page)
    if posting:
        role = to_role(posting, url, owner)
        if role:
            role.url = url
            return role, ""
    return None, "the page has no job post marked up for search engines (schema.org JobPosting)"


def _why_closed(resp) -> str:
    """A failed page in words, not the HTTP library's exception text."""
    error = resp.error or ""
    if resp.status and not error.startswith(("HTTPS", "HTTP", "Connection")):
        return f"HTTP {resp.status}" if not error else error[:120]
    if re.search(r"resolve|Name or service|nodename", error):
        return "that site's address was not found"
    if re.search(r"[Tt]imed? ?out", error):
        return "the site did not answer in time"
    return f"HTTP {resp.status}" if resp.status else "the site could not be reached"


def _site_name(page: str) -> str:
    """"Careers at UnitedHealth Group" -> "UnitedHealth Group"; "" if none."""
    match = re.search(r"<title>\s*(?:Careers? (?:at|with) )?([^<|\u2013-]{2,80}?)\s*(?:[|\u2013-][^<]*)?</title>",
                      page or "", re.IGNORECASE)
    return clean(html.unescape(match.group(1))) if match else ""


# ── Taleo Enterprise ─────────────────────────────────────────────────────────
# The job page keeps its post in one hidden field, its parts joined by "!|!"
# and URL-encoded, with ":" escaped as "\:". After a "Submission for the
# position: <title> - (Job Number: <n>)" part come the title, the number,
# the advert in parts marked "!*!" (each twice), then pairs of category,
# place, an unused one, department and job type, then the posting date.
# Read from uhg.taleo.net, 2026-10-28.
_HISTORY = re.compile(r'id="initialHistory"\s+value="([^"]*)"')
_SUBMISSION = re.compile(r"Submission for the position: (.+) - \(Job Number: ([\w-]+)\)")


def taleo_posting(page: str) -> dict:
    """Role fields from a Taleo Enterprise job page, or {} when it has none."""
    found = _HISTORY.search(page or "")
    if not found:
        return {}
    parts = [urllib.parse.unquote(html.unescape(p)).replace("\\:", ":")
             for p in found.group(1).split("!|!")]
    at = next((i for i, p in enumerate(parts) if _SUBMISSION.match(p)), None)
    if at is None:
        return {}
    title, number = _SUBMISSION.match(parts[at]).groups()
    try:
        start = parts.index(number, at + 1) + 1
    except ValueError:
        return {}
    advert, i = [], start
    while i < len(parts) and parts[i].startswith("!*!"):
        if parts[i] not in advert:
            advert.append(parts[i])
        i += 1
    rest = parts[i:i + 11]
    if len(rest) < 11:
        return {}
    place, department, kind, when = rest[2], rest[6], rest[8], rest[10]
    return {
        "title": clean(title),
        "location_raw": _taleo_place(place),
        "description": to_text("\n".join(a[3:] for a in advert)),
        "posted_at": _taleo_date(when),
        "work_mode": "remote" if "remote" in f"{place} {kind}".lower() else "",
        **({"flags": [f"job number {number}"
                      + (f", {department}" if department else "")]} if number else {}),
    }


def _taleo_place(text: str) -> str:
    """"US-IL-Naperville" -> "Naperville, IL, US"; anything else as it is."""
    bits = (text or "").split("-", 2)
    if len(bits) == 3 and len(bits[0]) == 2 and bits[0].isalpha():
        return f"{bits[2]}, {bits[1]}, {bits[0]}"
    return text or ""


def _taleo_date(text: str) -> str:
    """"Oct 26, 2026, 12:15:09 PM" -> "2026-10-26"; "" when unreadable."""
    from .site import date_of

    return date_of(text)
