"""
jobdork.search.discover
=======================
Finds an employer's job board, by reading it off their own site.

Board tokens are not company names. `mymoose` is Rapid7, `evergreenix` is
Garrison, `knowbe4` is Egress. So this never guesses a token from a name — it
fetches the employer's careers page and takes the token out of the links they
publish themselves.

That distinction is the whole point, because **a board that answers is not
proof you found the right company.** On Ashby, `primer` is a Florida
micro-schools operator. On Greenhouse, `peak` is a Texas physiotherapy chain.
Both return jobs, both look perfectly healthy, and neither is the company you
meant. A guessed token that happens to resolve is worse than no result at all,
so a token this module did not read off the employer's own domain is reported
and refused rather than written into your config.

Four outcomes, and they are kept distinct on purpose:

    verified        found on their site, and the board returns jobs
    empty           found on their site, but the board returns nothing —
                    which on several platforms is also what throttling
                    looks like, so it is not "they are not hiring"
    unread          found, but the board would not answer at all
    blocked         the site refused us; nothing here works around that
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field

from .. import fetch as fetch_pkg
from ..fetch.http import Fetcher

# Where a careers page usually lives. Tried in order, and the first that
# answers with something board-shaped wins.
CAREERS_PATHS = (
    "", "/careers", "/careers/", "/jobs", "/jobs/",
    # The listing page often carries the token where the landing page does
    # not: Stripe's /jobs has no board reference at all, /jobs/search has 535.
    "/jobs/search", "/careers/search", "/careers/jobs", "/careers/openings",
    "/company/careers", "/about/careers", "/about/careers/",
    "/careers/open-roles", "/join-us", "/work-with-us",
    "/en/careers", "/company/jobs",
)

# Board URL shapes, most specific first. Each capture group is the token.
BOARD_PATTERNS: tuple[tuple[str, str], ...] = (
    # `embed/job_board/js?for=TOKEN` is the script tag form, and it is how
    # Vectra publishes theirs. Missing the `/js` variant lost a board whose
    # token — `vectranetworks` — is nothing like the company name, which is
    # exactly the case this command exists for.
    ("greenhouse", r"boards\.greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)"),
    ("greenhouse", r"(?:job-)?boards\.greenhouse\.io/([A-Za-z0-9_-]+)"),
    ("greenhouse", r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)"),
    ("ashby",      r"jobs\.ashbyhq\.com/([A-Za-z0-9._-]+)"),
    ("ashby",      r"api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9._-]+)"),
    ("lever",      r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_-]+)"),
    ("smartrecruiters", r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("smartrecruiters", r"careers\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("breezy",     r"([A-Za-z0-9-]+)\.breezy\.hr"),
)

# Platforms with no adapter here. Naming them is more useful than "nothing
# found", which is three false statements at once about a board we located.
UNSUPPORTED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("workday", r"([A-Za-z0-9_-]+)\.(?:wd\d+\.)?myworkdayjobs\.com"),
    ("icims", r"([A-Za-z0-9_-]+)\.icims\.com"),
    ("taleo", r"([A-Za-z0-9_-]+)\.taleo\.net"),
    ("successfactors", r"([A-Za-z0-9_-]+)\.jobs2web\.com"),
    ("jobvite", r"jobs\.jobvite\.com/([A-Za-z0-9_-]+)"),
    ("jazzhr", r"([A-Za-z0-9_-]+)\.applytojob\.com"),
    ("bamboohr", r"([A-Za-z0-9_-]+)\.bamboohr\.com"),
    ("paycom", r"paycomonline\.net"),
    ("adp", r"workforcenow\.adp\.com"),
    ("ukg", r"recruiting\.ultipro\.com"),
    ("paylocity", r"recruiting\.paylocity\.com"),
    ("recruitee", r"([A-Za-z0-9_-]+)\.recruitee\.com"),
    ("teamtailor", r"([A-Za-z0-9_-]+)\.teamtailor\.com"),
    ("oraclecloud", r"([A-Za-z0-9_-]+)\.oraclecloud\.com"),
    ("eightfold", r"([A-Za-z0-9_-]+)\.eightfold\.ai"),
)

# Marks of a platform whose token is NOT in the page. Stripe's careers search
# carries 535 mentions of Greenhouse — every posting has a `greenhouseId` —
# and never once names the board. Reporting "no job board found" there is
# false; the board exists, it just cannot be read off the page, and the honest
# answer tells you to supply the token yourself.
PLATFORM_HINTS: tuple[tuple[str, str], ...] = (
    ("greenhouse", r"greenhouseId|gh_jid|greenhouse\.io"),
    ("ashby", r"ashbyhq|ashby_jid"),
    ("lever", r"lever\.co|leverJobId"),
    ("smartrecruiters", r"smartrecruiters"),
    ("breezy", r"breezy\.hr"),
)

# Paths that look like a token and are not one.
NOT_TOKENS = {
    "embed", "job_board", "jobs", "careers", "search", "api", "v1", "static",
    "assets", "www", "job", "boards", "posting-api", "job-board", "images",
}

SUPPORTED = ("greenhouse", "ashby", "lever", "smartrecruiters", "breezy")


@dataclass
class Found:
    platform: str
    token: str
    board_url: str = ""
    source_url: str = ""          # the page the token was read from
    jobs: int = 0
    status: str = "unread"        # verified | empty | unread | blocked
    company_claim: str = ""       # what the board calls itself, when it says
    note: str = ""

    @property
    def addable(self) -> bool:
        """Only a board that answered with jobs is worth writing down.

        An unread board is a guess, and banking a guess into the source list
        is worse than leaving it out.
        """
        return self.status == "verified" and self.platform in SUPPORTED


@dataclass
class Report:
    employer: str
    found: list[Found] = field(default_factory=list)
    unsupported: list[Found] = field(default_factory=list)
    # Platform visible on the page, token not. Kept apart from `found`
    # because there is nothing to verify and nothing to add.
    hinted: list[str] = field(default_factory=list)
    pages_read: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    error: str = ""

    def lines(self) -> list[str]:
        out: list[str] = []
        for item in self.found:
            mark = {"verified": "[verified]", "empty": "[empty board]",
                    "unread": "[could not read]", "blocked": "[blocked]"}[item.status]
            out.append(f"  {item.platform:16} {item.jobs:>4} jobs  {mark}  {item.board_url}")
            if item.company_claim:
                out.append(f"{'':20}board names itself {item.company_claim!r}")
            if item.note:
                out.append(f"{'':20}{item.note}")
        for item in self.unsupported:
            out.append(f"  {item.platform:16} {'':>4}       [no adapter]  {item.board_url}")
        for platform in self.hinted:
            out.append(
                f"  {platform:16} {'':>4}       [token not on page]"
            )
            out.append(
                f"{'':20}their site uses {platform} but never names the board. "
                "Find the\n"
                f"{'':20}token in a posting URL and pass it by hand:\n"
                f"{'':20}  jobdork add <posting-url> --token <token>"
            )
        for host in self.blocked:
            out.append(f"  {host} refused the request; nothing here works around that")
        if not self.found and not self.unsupported and not self.hinted:
            out.append("  no job board found on their site")
        return out


def _normalise(employer: str) -> list[str]:
    """Candidate base URLs for whatever the user typed."""
    text = (employer or "").strip().rstrip("/")
    if not text:
        return []
    if "://" in text:
        parts = urllib.parse.urlsplit(text)
        return [f"{parts.scheme}://{parts.netloc}"]
    if "." in text and " " not in text:
        return [f"https://{text}", f"https://www.{text}"]
    # A name rather than a domain. Guessing a domain from a name is the same
    # mistake as guessing a token from a name, so it is refused.
    return []


def _extract(html: str, source_url: str) -> tuple[list[Found], list[Found]]:
    supported: dict[tuple[str, str], Found] = {}
    unsupported: dict[tuple[str, str], Found] = {}

    for platform, pattern in BOARD_PATTERNS:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            token = match.group(1)
            if token.lower() in NOT_TOKENS or len(token) < 2:
                continue
            key = (platform, token.lower())
            supported.setdefault(key, Found(
                platform=platform, token=token,
                board_url=_board_url(platform, token),
                source_url=source_url,
            ))

    for platform, pattern in UNSUPPORTED_PATTERNS:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            token = match.group(1) if match.groups() else platform
            key = (platform, token.lower())
            unsupported.setdefault(key, Found(
                platform=platform, token=token,
                board_url=match.group(0), source_url=source_url,
                note="no adapter; reachable through `jobdork dork`",
            ))

    return list(supported.values()), list(unsupported.values())


def _board_url(platform: str, token: str) -> str:
    return {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{token}",
        "lever": f"https://api.lever.co/v0/postings/{token}?mode=json",
        "smartrecruiters": f"https://api.smartrecruiters.com/v1/companies/{token}/postings",
        "breezy": f"https://{token}.breezy.hr/json",
    }.get(platform, "")


def _verify(fetcher: Fetcher, item: Found) -> Found:
    """Read the board. Job count decides, never the status code.

    Ashby and SmartRecruiters answer HTTP 200 with an empty array both for a
    board that does not exist and for one that is rate-limiting you, so an
    empty answer is recorded as empty and never as verified.
    """
    adapter = fetch_pkg.get(item.platform)
    if adapter is None:
        item.status = "unread"
        item.note = "no adapter for this platform"
        return item

    class _Stub:
        """The minimum an adapter reads. Discovery has no user config yet."""
        titles_include: list[str] = []
        class locations:
            anchor = ""
            radius = "exact"
            units = "mi"
            countries: list[str] = []
        class sources:
            adzuna_countries: list[str] = []
        def country_prefs(self):
            return ()
        def radius_miles(self):
            return None

    try:
        result = adapter(fetcher, _Stub(), token=item.token, company=item.token)
    except Exception as exc:                                # one board, not the run
        item.status = "unread"
        item.note = f"board raised {type(exc).__name__}: {exc}"
        return item

    item.jobs = len(result.roles)
    if result.roles:
        item.status = "verified"
        claims = {role.company for role in result.roles if role.company}
        # Greenhouse states the employer on every posting; the others do not,
        # and an absent claim is left absent rather than filled with the token.
        real = {c for c in claims if c.lower() != item.token.lower()}
        if len(real) == 1:
            item.company_claim = real.pop()
    elif result.errors:
        item.status = "unread"
        item.note = result.errors[0]
    else:
        item.status = "empty"
        item.note = ("answered 200 with no jobs; on this platform that is "
                     "also what throttling looks like, so it is unknown "
                     "rather than 'not hiring'")
    return item


def discover(employer: str, fetcher: Fetcher, max_pages: int = 6) -> Report:
    """Find an employer's boards by reading their own careers pages."""
    report = Report(employer=employer)
    bases = _normalise(employer)
    if not bases:
        report.error = (
            f"{employer!r} is not a domain. Give the employer's website, as in "
            "`jobdork discover stripe.com`, because guessing a domain from a "
            "company name is the same mistake as guessing a board token from "
            "one."
        )
        return report

    seen_supported: dict[tuple[str, str], Found] = {}
    seen_unsupported: dict[tuple[str, str], Found] = {}
    pages_content: list[str] = []
    pages_tried = 0

    for base in bases:
        for path in CAREERS_PATHS:
            if pages_tried >= max_pages and seen_supported:
                break
            url = base + path
            resp = fetcher.get(url, expect_json=False)
            pages_tried += 1

            if resp.status in (401, 403) or "banned" in (resp.body or "").lower()[:2000]:
                host = urllib.parse.urlsplit(url).netloc
                if host not in report.blocked:
                    report.blocked.append(host)
                continue
            if not resp.ok or not resp.body:
                continue

            report.pages_read.append(url)
            pages_content.append(resp.body)
            supported, unsupported = _extract(resp.body, url)
            for item in supported:
                seen_supported.setdefault((item.platform, item.token.lower()), item)
            for item in unsupported:
                seen_unsupported.setdefault((item.platform, item.token.lower()), item)

            if seen_supported:
                break
        if seen_supported:
            break

    report.found = [_verify(fetcher, item) for item in seen_supported.values()]
    report.found.sort(key=lambda f: (f.status != "verified", -f.jobs))
    report.unsupported = list(seen_unsupported.values())

    if not seen_supported:
        found_platforms = {item.platform for item in seen_unsupported.values()}
        for platform, pattern in PLATFORM_HINTS:
            if platform in found_platforms:
                continue
            if any(re.search(pattern, page, re.IGNORECASE)
                   for page in pages_content):
                report.hinted.append(platform)

    return report


def add_to_config(config_path: str, name: str, items: list[Found]) -> list[Found]:
    """Append verified boards to `sources.companies`, preserving comments.

    Rewritten as text rather than through the YAML round-trip on purpose: a
    dump would strip every comment out of a file that is mostly comments.
    """
    from pathlib import Path

    path = Path(config_path)
    text = path.read_text(encoding="utf-8")
    addable = [item for item in items if item.addable]
    if not addable:
        return []

    entries = "".join(
        f"    - name: {name}\n"
        f"      platform: {item.platform}\n"
        f"      token: {item.token}\n"
        for item in addable
    )

    empty = re.search(r"^(\s*)companies:\s*\[\s*\]\s*$", text, re.M)
    if empty:
        text = text[: empty.start()] + "  companies:\n" + entries + text[empty.end() + 1:]
    else:
        listed = re.search(r"^(\s*)companies:\s*$", text, re.M)
        if not listed:
            raise ValueError(
                "could not find `companies:` under `sources:` in "
                f"{config_path}. Add the entries by hand."
            )
        insert = listed.end() + 1
        text = text[:insert] + entries + text[insert:]

    path.write_text(text, encoding="utf-8")
    return addable
