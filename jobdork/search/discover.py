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

import html as html_lib
import re
import urllib.parse
from collections import deque
from dataclasses import dataclass, field

from .. import fetch as fetch_pkg
from ..fetch.http import Fetcher
from ..fetch.robots import Robots as _Robots
from ..fetch.robots import base as _base

# How many pages one employer may cost, robots.txt aside. Twelve covers the
# given page, the site root, six job links off them, two sitemap reads and
# two posting pages; past that a board is not on the site in any form this
# module can read.
MAX_PAGES = 12
# Same-site links followed, at most. A careers site links its job search from
# the front page; a dozen links deep is a crawl, and that is not this.
MAX_LINKS = 6
# Postings taken from a sitemap. One posting's Apply link names the board as
# well as a hundred would.
MAX_SITEMAP_POSTINGS = 2

# Words in a link's address that say it leads to jobs, strongest first: a
# search page lists postings, a "join us" page often only talks about them.
JOB_LINK_WORDS = ("search", "jobs", "job", "openings", "positions", "vacanc",
                  "opportunit", "career", "apply", "join")

# Tried last, when neither the site's own links nor its sitemap led anywhere.
# The listing page often carries the token where the landing page does not:
# Stripe's /jobs has no board reference at all, /jobs/search has 535.
CAREERS_PATHS = ("/careers", "/jobs", "/jobs/search", "/careers/search",
                 "/careers/jobs", "/about/careers")

# Not pages: following one costs a request and can name no board.
_NOT_PAGES = re.compile(r"\.(?:css|js|json|png|jpe?g|gif|svg|webp|ico|pdf|zip|"
                        r"mp4|woff2?|ttf|xml|gz)(?:$|\?)", re.IGNORECASE)

# A host name label, as a capture. Bounded at 63 characters (the DNS limit)
# and only matched where a label starts: an unbounded `[A-Za-z0-9_-]+\.icims`
# retries from every letter of a long run, and one page with 40,000 letters
# of inline data in a row cost 87 seconds per pattern, a megabyte forever.
HOST = r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{1,63})"

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
    # A candidate's applications page names the board after it (Dr. Reddy's:
    # jobs.smartrecruiters.com/my-applications/DrReddysLaboratoriesLimited).
    ("smartrecruiters", r"jobs\.smartrecruiters\.com/my-applications/([A-Za-z0-9_-]+)"),
    ("smartrecruiters", r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("smartrecruiters", r"careers\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("breezy",     HOST + r"\.breezy\.hr"),
    # Three parts: tenant, data centre and site, as in
    # nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite. An optional
    # locale ("en-US/") comes before the site. All three make the token.
    # Oracle Recruiting Cloud: host and site number, from the careers link
    # (jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001)
    # or, where the page only loads its assets (Kroger), a siteNumber query.
    ("oracle",     r"(?<![A-Za-z0-9.-])((?:[A-Za-z0-9-]{1,63}\.){1,4}oraclecloud\.com)"
                   r"(?::443)?/hcmUI/CandidateExperience/[A-Za-z_-]{2,5}/sites/([A-Za-z0-9_]+)"),
    ("oracle",     r"(?<![A-Za-z0-9.-])((?:[A-Za-z0-9-]{1,63}\.){1,4}oraclecloud\.com)"
                   r"(?::443)?/hcmRestApi/[^\s\"'<>?]{0,120}\?[^\s\"'<>]{0,200}?siteNumber=([A-Za-z0-9_]+)"),
    # Eightfold: the tenant ({tenant}.eightfold.ai); the employer domain the
    # API is asked for is settled when the board is verified.
    ("eightfold",  HOST + r"\.eightfold\.ai"),
    # Taleo Business Edition: host, path, org and careers site number, in
    # either order in the query (Costco's link has cws=41 before org=COSTCO,
    # joined by \u0026 inside a script).
    ("taleo",      r"(?<![A-Za-z0-9.-])((?:[A-Za-z0-9-]{1,63}\.)?tbe\.taleo\.net)/([A-Za-z0-9]{1,20})"
                   r"/ats/careers/[^\s\"'<>]{0,160}?(?<![A-Za-z])org=([A-Za-z0-9_]{1,40})"
                   r"[^\s\"'<>]{0,80}?(?<![A-Za-z])cws=(\d{1,6})"),
    ("taleo",      r"(?<![A-Za-z0-9.-])((?:[A-Za-z0-9-]{1,63}\.)?tbe\.taleo\.net)/([A-Za-z0-9]{1,20})"
                   r"/ats/careers/[^\s\"'<>]{0,160}?(?<![A-Za-z])cws=(\d{1,6})"
                   r"[^\s\"'<>]{0,80}?(?<![A-Za-z])org=([A-Za-z0-9_]{1,40})"),
    ("workday",    HOST + r"\.(wd\d+)\.myworkdayjobs\.com/"
                   r"(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z][A-Za-z0-9_-]+)"),
)

# Platforms with no adapter here. Naming them is more useful than "nothing
# found", which is three false statements at once about a board we located.
UNSUPPORTED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("icims", HOST + r"\.icims\.com"),
    ("taleo", HOST + r"\.taleo\.net"),
    ("successfactors", HOST + r"\.jobs2web\.com"),
    ("successfactors", r"(?:career|performancemanager)\d*\.successfactors\.(?:com|eu)"
                       r"[^\s\"'<>]{0,160}?company=([A-Za-z0-9_]+)"),
    ("successfactors", HOST + r"\.sapsf\.(?:com|eu)"),
    ("turbohire", HOST + r"\.turbohire\.co"),
    ("darwinbox", HOST + r"\.darwinbox\.in"),
    ("peoplestrong", HOST + r"\.peoplestrong\.com"),
    ("jobvite", r"jobs\.jobvite\.com/([A-Za-z0-9_-]+)"),
    ("jazzhr", HOST + r"\.applytojob\.com"),
    ("bamboohr", HOST + r"\.bamboohr\.com"),
    ("paycom", r"paycomonline\.net"),
    ("adp", r"workforcenow\.adp\.com"),
    ("ukg", r"recruiting\.ultipro\.com"),
    ("paylocity", r"recruiting\.paylocity\.com"),
    ("recruitee", HOST + r"\.recruitee\.com"),
    ("teamtailor", HOST + r"\.teamtailor\.com"),
    ("oraclecloud", HOST + r"\.oraclecloud\.com"),
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

# Career-site front ends that hold no jobs of their own. Seen on the page
# when the board behind them is not named there.
FRONT_ENDS: tuple[tuple[str, str], ...] = (
    ("Phenom", r"phenompeople"),
    ("Eightfold", r"eightfold\.ai"),
)

# Paths that look like a token and are not one. For a host-named platform
# (eightfold.ai, icims.com) the same goes for the platform's own service
# hosts: jobs.nvidia.com names app.eightfold.ai and vs-errors.eightfold.ai,
# neither of which is anybody's board.
NOT_TOKENS = {
    "embed", "job_board", "jobs", "careers", "search", "api", "v1", "static",
    "assets", "www", "job", "boards", "posting-api", "job-board", "images",
    "app", "cdn", "errors", "vs-errors", "login", "wday", "auth", "sso",
    "my-applications",
}

SUPPORTED = ("greenhouse", "ashby", "lever", "smartrecruiters", "breezy", "workday",
             "oracle", "eightfold", "taleo", "site")


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
    # Countries the board lists jobs in, as far as one read shows: Workday's
    # country facet, or the places of the jobs another platform returned.
    countries: list[str] = field(default_factory=list)
    # Eightfold: employer domains the page names (`domain=starbucks.com`),
    # tried first when the board is verified.
    hints: list[str] = field(default_factory=list)

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
    # Hosts that did not answer at all (no DNS, refused, timed out). Not
    # "blocked": nobody said no, there was just nobody there.
    unreachable: list[str] = field(default_factory=list)
    # Pages left unread because the site's robots.txt asks tools not to.
    robots_skipped: list[str] = field(default_factory=list)
    # A career-site front end that shows jobs held elsewhere (Phenom,
    # Eightfold): what to give Discover instead.
    front_end: str = ""
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
        for host in self.unreachable:
            out.append(f"  {host} did not answer")
        if self.robots_skipped:
            out.append(f"  {len(self.robots_skipped)} page(s) left unread: the site's "
                       "robots.txt asks tools not to read them")
        if not self.found and not self.unsupported and not self.hinted:
            out.append("  no job board found on their site")
            if self.front_end:
                out.append(f"  their careers site runs on {self.front_end}, which shows "
                           "jobs held in another system (often Workday).\n"
                           "  Give Discover a page that lists jobs (a search or "
                           "category page), or one posting's Apply link.")
        return out


# Job sites, not employers: there is no one company's board to find on them,
# and most refuse scripts outright (ph.jobstreet.com answers 403, and its
# robots.txt closes its search API). Recognised by address before anything is
# sent, with what to do instead. A suffix matches the host and its subdomains.
_SEARCH_LINKS = ("it refuses automated access, which jobdork does not work "
                 "around. Use its search "
                 "links instead (`jobdork dork --sites {site}`, opened in your "
                 "browser), or Discover the employer's own website from a "
                 "posting you like")
JOB_SITES = {
    "kalibrr.com": ("it is read directly by jobdork: add kalibrr to sources.keyless in config.yaml, "
                    "and the next scan searches it for your titles"),
    "jobstreet.com": _SEARCH_LINKS.format(site="jobstreet"),
    "jobsdb.com": _SEARCH_LINKS.format(site="jobstreet"),
    "seek.com.au": _SEARCH_LINKS.format(site="jobstreet"),
    "linkedin.com": _SEARCH_LINKS.format(site="linkedin"),
    "indeed.com": _SEARCH_LINKS.format(site="indeed"),
    "glassdoor.com": _SEARCH_LINKS.format(site="glassdoor"),
    "onlinejobs.ph": _SEARCH_LINKS.format(site="onlinejobs"),
}


def job_site(employer: str) -> str:
    """Why `employer` is a job site rather than an employer, or ""."""
    text = (employer or "").strip().lower()
    host = urllib.parse.urlsplit(text if "://" in text else "//" + text).hostname or ""
    for suffix, why in JOB_SITES.items():
        if host == suffix or host.endswith("." + suffix) or host.startswith(
                suffix.split(".")[0] + "."):
            return f"{host} is a job site, not an employer's own site, so it has no board to find. {why[0].upper()}{why[1:]}."
    return ""


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
            # Only the first part can be a word like "careers" by mistake; a
            # Workday site may well be named Careers (razer/wd3/Careers).
            if match.group(1).lower() in NOT_TOKENS:
                continue
            if platform == "workday" and match.group(3).lower() in {
                    "wday", "job", "jobs", "login", "auth", "sso"}:
                continue                 # an API or posting path, not a site
            # A vendor's test copy of an employer's board answers with jobs
            # too: HP's page named hp-sandbox.eightfold.ai.
            if re.search(r"sandbox|staging|(?:^|[-_.])(?:test|demo|uat|dev)(?:$|[-_.])",
                         match.group(1), re.IGNORECASE):
                continue
            groups = list(match.groups())
            if platform == "taleo" and groups[2].isdigit():
                groups[2], groups[3] = groups[3], groups[2]   # cws came first
            token = "/".join(groups)        # three parts for Workday, four for Taleo
            if len(token) < 2:
                continue
            key = (platform, token.lower())
            supported.setdefault(key, Found(
                platform=platform, token=token,
                board_url=_board_url(platform, token),
                source_url=source_url,
            ))
            if platform == "eightfold":
                hints = re.findall(r"[?&;]domain=([a-z0-9-]+(?:\.[a-z0-9-]+)+)", html, re.I)
                supported[key].hints = list(dict.fromkeys(h.lower() for h in hints))

    for platform, pattern in UNSUPPORTED_PATTERNS:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            token = match.group(1) if match.groups() else platform
            if token.lower() in NOT_TOKENS:
                continue
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
        "workday": _workday_url(token),
        "oracle": f"https://{token.split('/')[0]}/hcmUI/CandidateExperience/en/sites/"
                  f"{token.split('/')[-1]}",
        "eightfold": f"https://{_eightfold_host(token)}/careers",
        "taleo": _taleo_url(token),
        "site": token,
    }.get(platform, "")


def _workday_url(token: str) -> str:
    from ..fetch import workday
    parts = workday.parse_token(token)
    return f"{workday.base_url(parts[0], parts[1])}/{parts[2]}" if parts else ""


def _verify(fetcher: Fetcher, item: Found) -> Found:
    """Read the board. Job count decides, never the status code.

    Ashby and SmartRecruiters answer HTTP 200 with an empty array both for a
    board that does not exist and for one that is rate-limiting you, so an
    empty answer is recorded as empty and never as verified.
    """
    if item.platform == "workday":
        return _verify_workday(fetcher, item)
    if item.platform == "oracle":
        return _verify_oracle(fetcher, item)
    if item.platform == "eightfold":
        return _verify_eightfold(fetcher, item)
    if item.platform == "taleo":
        return _verify_taleo(fetcher, item)
    if item.platform == "site":
        # Read off the sitemap and one marked-up posting by _site_board.
        item.status = "verified" if item.jobs else "empty"
        return item
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
        item.countries = _countries_of(result.roles)
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


def _countries_of(roles) -> list[str]:
    """Countries named by the jobs' own locations; a remote job names none."""
    from . import geo

    found: set[str] = set()
    for role in roles:
        where = role.country or geo.resolve(role.location_raw).country
        if where:
            found.add(where.upper())
    return sorted(found)


def _site_board(fetcher: Fetcher, robots, root: str) -> Found | None:
    """The careers site as a board, when its sitemap postings carry JobPosting.

    Two postings at most are read: the first one marked up is the proof.
    """
    from ..fetch import site

    listed, _ = site.postings(fetcher, root, robots)
    for url, _ in sorted(listed, key=lambda pair: pair[1], reverse=True)[:2]:
        if not robots.allowed(url):
            continue
        resp = fetcher.get(url, expect_json=False)
        posting = site.job_posting(resp.body) if resp.ok else {}
        if posting:
            item = Found(platform="site", token=root, board_url=root, source_url=url,
                         jobs=len(listed))
            role = site.to_role(posting, url, "")
            item.countries = _countries_of([role]) if role else []
            item.company_claim = role.company if role and role.company else ""
            return item
    return None


def _taleo_url(token: str) -> str:
    from ..fetch import taleo
    parts = taleo.parse_token(token)
    if not parts:
        return ""
    host, path, org, cws = parts
    return f"{taleo.base(host, path)}/searchResults?org={org}&cws={cws}"


def _eightfold_host(token: str) -> str:
    """A bare tenant is {tenant}.eightfold.ai; anything with a dot is a host."""
    head = token.split("/")[0]
    return head if "." in head else f"{head}.eightfold.ai"


def _verify_eightfold(fetcher: Fetcher, item: Found) -> Found:
    """Settle the employer domain the API answers for, and count the board.

    The API answers 404 for a domain that is not the board's, so a guess is
    checked rather than trusted: the page's own `domain=` first, then the
    site the token was read on, then the tenant's name with .com.
    """
    from ..fetch import eightfold

    host = _eightfold_host(item.token)
    tenant = host.split(".")[0]
    source = _site(urllib.parse.urlsplit(item.source_url).hostname or "")
    guesses = [*item.hints, source, f"{tenant}.com"]
    for domain in dict.fromkeys(g for g in guesses if g and "eightfold" not in g):
        resp = eightfold.search(fetcher, host, domain)
        if resp.status == 404 or resp.status == 422:
            continue
        count = eightfold.data(resp).get("count")
        item.token = f"{host}/{domain}"
        item.board_url = f"https://{host}/careers"
        if count:
            item.status, item.jobs = "verified", int(count)
            item.countries = sorted({
                code for p in eightfold.data(resp).get("positions") or []
                for code in [_countries_of_text(p.get("standardizedLocations") or [])] if code})
        elif count == 0:
            item.status, item.note = "empty", "the board answered with no open jobs"
        else:
            item.status, item.note = "unread", resp.error or f"answered {resp.status}"
        return item
    item.status = "unread"
    item.note = "no employer domain the board answers for: " + ", ".join(dict.fromkeys(guesses))
    return item


def _countries_of_text(places: list[str]) -> str:
    """The country of the first place that names one ("Petal, MS, US")."""
    from . import geo

    for place in places:
        code = geo.country_code(place.split(",")[-1].strip())
        if code:
            return code
    return ""


def _verify_taleo(fetcher: Fetcher, item: Found) -> Found:
    """Count the board by paging its search results (ten a page, no JSON)."""
    from ..fetch import taleo

    parts = taleo.parse_token(item.token)
    if not parts:
        item.status, item.note = "unread", "not a host/path/org/cws token"
        return item
    jobs, _, cut = taleo.listing(fetcher, *parts, max_pages=10)
    if jobs:
        item.status, item.jobs = "verified", len(jobs)
        item.countries = _countries_of_text_list([c["place"] for c in jobs])
        if cut:
            item.note = f"counted the first {len(jobs)}; the board lists more"
    else:
        item.status, item.note = "empty", "its search results list no jobs"
    return item


def _countries_of_text_list(places: list[str]) -> list[str]:
    from . import geo

    found = {geo.resolve(p).country for p in places if p}
    return sorted(c for c in found if c)


def _verify_oracle(fetcher: Fetcher, item: Found) -> Found:
    """One empty search: the board's own count, and the countries it lists."""
    from ..fetch import oracle

    parts = oracle.parse_token(item.token)
    if not parts:
        item.status, item.note = "unread", "not a host/site token"
        return item
    resp = oracle.search(fetcher, *parts, limit=1)
    first = oracle._first(resp)
    total = first.get("TotalJobsCount") if first else None
    if total:
        item.status, item.jobs = "verified", int(total)
        item.countries = sorted(oracle.countries(first))
    elif total == 0:
        item.status, item.note = "empty", "the board answered with no open jobs"
    else:
        item.status, item.note = "unread", resp.error or f"answered {resp.status}"
    return item


def _verify_workday(fetcher: Fetcher, item: Found) -> Found:
    """One empty search: the board's own count of open jobs.

    The adapter searches by your titles, and discovery has none yet; one
    request with no search text says whether the board answers and how big
    it is, without reading every posting.
    """
    from ..fetch import workday

    tenant, dc, site = workday.parse_token(item.token)
    resp = workday.search(fetcher, tenant, dc, site, "")
    total = (resp.json or {}).get("total") if resp.ok and isinstance(resp.json, dict) else None
    if total:
        item.status, item.jobs = "verified", int(total)
        item.countries = workday.countries(resp.json)
    elif total == 0:
        item.status = "empty"
        item.note = "the board answered with no open jobs"
    else:
        item.status = "unread"
        item.note = resp.error or f"answered {resp.status}"
    return item


# Second-level labels under a country code: careers.jobs.co.uk belongs to
# jobs.co.uk, not to co.uk. Short and incomplete on purpose; a miss only
# means a link on a sister host is not followed.
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu", "ne", "or"}


def _site(host: str) -> str:
    """The registrable domain: careers.adobe.com and www.adobe.com are adobe.com."""
    labels = (host or "").lower().split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _job_word(url: str) -> int | None:
    """How strongly an address says "jobs": the rank of its strongest job word.

    Words are matched at the start of a word in the path, and the short ones
    whole: Costco's /glucosamine-joint-supplements.html is not a "join" page.
    """
    words = re.split(r"[^a-z]+", urllib.parse.urlsplit(url).path.lower())
    for rank, word in enumerate(JOB_LINK_WORDS):
        exact = len(word) <= 6 and word not in ("vacanc", "career")
        if any(w == word or w == word + "s" if exact else w.startswith(word)
               for w in words):
            return rank
    return None


def _job_links(html: str, page_url: str, limit: int = MAX_LINKS) -> list[str]:
    """Links on the page to job pages on the same site, strongest first.

    Same site means the same registrable domain, so careers.example.com is
    followed from example.com. Boards on other domains need no following:
    their address is already on this page, and `_extract` reads it there.
    """
    site = _site(urllib.parse.urlsplit(page_url).hostname or "")
    ranked: dict[str, int] = {}
    for href in re.findall(r"""href\s*=\s*["']([^"'#]+)""", html, re.IGNORECASE):
        url = urllib.parse.urljoin(page_url, html_lib.unescape(href.strip()))
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or _NOT_PAGES.search(parts.path):
            continue
        if _site(parts.hostname or "") != site:
            continue
        rank = _job_word(url)
        if rank is not None and url.rstrip("/") != page_url.rstrip("/"):
            ranked.setdefault(url, rank)
    return sorted(ranked, key=ranked.get)[:limit]


def _sitemap_urls(xml: str) -> tuple[list[str], list[str]]:
    """(child sitemaps, page addresses) in a sitemap or sitemap index."""
    locs = [u.strip() for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml, re.IGNORECASE)]
    if re.search(r"<sitemapindex", xml, re.IGNORECASE):
        return locs, []
    return [], locs


def discover(employer: str, fetcher: Fetcher, max_pages: int = MAX_PAGES) -> Report:
    """Find an employer's boards by reading their own careers pages.

    Pages are read in this order, and reading stops at the first page that
    names a board jobdork can read, or after `max_pages`:

      1. the page you gave, as given;
      2. the site's front page;
      3. job links on the pages read so far, same site only, strongest first;
      4. the sitemap: postings, whose Apply links name the board;
      5. a short list of the usual careers paths.

    A host that does not answer or refuses (401, 403) is not asked again, and
    a page the site's robots.txt closes to tools is left unread.

    With no board found, the site itself is tried as one (fetch/site.py):
    up to eight sitemap reads, and two posting pages to find one marked up
    as a schema.org JobPosting.
    """
    report = Report(employer=employer)
    site = job_site(employer)
    if site:
        report.error = site
        return report
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
    robots = _Robots(fetcher)
    dead: set[str] = set()
    queued: set[str] = set()
    read_final: set[str] = set()
    queue: deque[str] = deque()
    links_left = MAX_LINKS

    def push(url: str) -> None:
        key = url.rstrip("/")
        if key not in queued:
            queued.add(key)
            queue.append(url)

    def mark_dead(host: str, resp_status: int) -> None:
        dead.add(host)
        bucket = report.blocked if resp_status in (401, 403) else report.unreachable
        if host not in bucket:
            bucket.append(host)

    def get(url: str):
        """One page, or None when its host is dead or robots.txt closes it."""
        host = urllib.parse.urlsplit(url).netloc
        if host in dead:
            return None
        if not robots.allowed(url):
            if robots.status.get(_base(url)) in (401, 403):
                mark_dead(host, robots.status[_base(url)])
            elif url not in report.robots_skipped:
                report.robots_skipped.append(url)
            return None
        resp = fetcher.get(url, expect_json=False)
        if "banned" in (resp.body or "").lower()[:2000]:
            mark_dead(host, 403)              # a refusal, whatever the status
            return None
        if resp.status == 0 or resp.status in (401, 403):
            mark_dead(host, resp.status)
            return None
        return resp

    # The page you gave first, as given. A jobs list deep in a careers site
    # often names the board where the site's front page does not: Adobe's
    # /us/en/c/engineering-and-product-jobs links every Apply button to its
    # Workday board, and careers.adobe.com itself names it nowhere.
    given = (employer or "").strip()
    if "://" in given and urllib.parse.urlsplit(given).path.strip("/"):
        push(given)
    # The address given may be the board itself
    # (razer.wd3.myworkdayjobs.com/Careers): read it like a page's link.
    for item in _extract(given, given)[0]:
        seen_supported.setdefault((item.platform, item.token.lower()), item)
    for base in bases:
        push(base + "/")
    landing = set(queue)

    fallbacks = ["sitemap", "paths"]
    pages_tried = 0
    live_base = ""
    while pages_tried < max_pages and not seen_supported:
        if not queue:
            if not fallbacks:
                break
            step = fallbacks.pop(0)
            roots = [live_base] if live_base else [b for b in bases
                                                  if urllib.parse.urlsplit(b).netloc not in dead]
            if step == "sitemap":
                for root in roots[:1]:
                    postings, reads = _sitemap_postings(get, robots.sitemap_list(root))
                    pages_tried += reads      # the sitemap reads count
                    for posting in postings:
                        push(posting)
            else:
                for root in roots[:1]:
                    for path in CAREERS_PATHS:
                        push(root + path)
            continue

        url = queue.popleft()
        resp = get(url)
        if resp is None:
            continue
        pages_tried += 1
        if not resp.ok or not resp.body:
            continue
        final = (resp.final_url or url).rstrip("/")
        if final in read_final:
            continue                          # www and bare host, one site
        read_final.add(final)
        live_base = live_base or _base(resp.final_url or url)

        report.pages_read.append(url)
        pages_content.append(resp.body)
        supported, unsupported = _extract(resp.body, url)
        for item in supported:
            seen_supported.setdefault((item.platform, item.token.lower()), item)
        for item in unsupported:
            seen_unsupported.setdefault((item.platform, item.token.lower()), item)

        if links_left > 0:
            for link in _job_links(resp.body, resp.final_url or url, links_left):
                if link.rstrip("/") not in queued:
                    push(link)
                    links_left -= 1

    # An Eightfold careers site on the employer's own host (jobs.nvidia.com)
    # names no tenant; the host is the board, if its API answers.
    if not seen_supported:
        for url, page in zip(report.pages_read, pages_content, strict=True):
            if len(re.findall(r"eightfold", page, re.IGNORECASE)) >= 3:
                host = urllib.parse.urlsplit(url).hostname or ""
                seen_supported[("eightfold", host)] = Found(
                    platform="eightfold", token=host, source_url=url,
                    board_url=f"https://{host}/careers")
                break

    # No board jobdork can read: the site itself may be one. Its sitemap
    # lists postings, and a posting marked up as schema.org JobPosting is
    # read by fetch/site.py. Tried where the jobs pages were, then the
    # address given.
    if not seen_supported:
        for root in dict.fromkeys(r for r in (live_base, *bases) if r):
            if urllib.parse.urlsplit(root).netloc in dead:
                continue
            item = _site_board(fetcher, robots, root)
            if item:
                seen_supported[("site", item.token.lower())] = item
                break

    report.found = [_verify(fetcher, item) for item in seen_supported.values()]
    report.found.sort(key=lambda f: (f.status != "verified", -f.jobs))
    # One Oracle board under two site numbers (Hilton's CX_1 and CX_1009)
    # answers with the same count; reading both reads every job twice.
    same: set[tuple[str, int]] = set()
    kept_found = []
    for item in report.found:
        key = (item.token.split("/")[0], item.jobs)
        if item.platform == "oracle" and item.status == "verified" and key in same:
            continue
        same.add(key)
        kept_found.append(item)
    report.found = kept_found
    # Oracle's hosts are also matched by the "no adapter" pattern; a host
    # read as an oracle board is not reported a second time.
    # Taleo's hosts likewise: a Business Edition board read as one is not
    # also "taleo, no adapter".
    read = {i.platform for i in seen_supported.values()}
    report.unsupported = [u for u in seen_unsupported.values()
                          if not (u.platform == "oraclecloud" and "oracle" in read)
                          and not (u.platform == "taleo" and "taleo" in read)]

    # A board met only on a page Discover followed, under a name that is not
    # the site's, may be a sister company's: careers.marriott.com links
    # Marriott Vacations Worldwide's board (mymvw) from a brand page. It
    # stays addable, since it was read off their own site, but says so.
    home = _site(urllib.parse.urlsplit(bases[0]).hostname or "")
    name = home.split(".")[0]
    for item in report.found:
        if item.platform == "site":
            # The site is the board: theirs, unless their address sent us
            # somewhere else (compassgroupcareers.com to compass-usa.com).
            elsewhere = _site(urllib.parse.urlsplit(item.token).hostname or "")
            if elsewhere != home:
                item.note = (f"{home} led to {elsewhere}: check it is theirs "
                             "and not a sister company's before adding it")
            continue
        # The tenant: workday's first part, a host's first label; for
        # Eightfold the employer domain, since its host may be their own
        # (careers.lumen.com, whose first label is "careers").
        at = {"eightfold": -1, "taleo": 2}.get(item.platform, 0)    # Taleo: the org
        head = item.token.lower().split("/")[at]
        token = head.split(".")[0]
        if item.source_url not in landing and name and \
                name not in token and token not in name:     # lifeatspotify / spotify
            item.note = (f"found on {item.source_url}, not on their careers front "
                         f"page, and the board's name does not say {name}: check "
                         "it is theirs and not a sister company's before adding it")

    if not seen_supported:
        for name, pattern in FRONT_ENDS:
            if any(len(re.findall(pattern, page, re.IGNORECASE)) >= 3 for page in pages_content):
                report.front_end = name
                break
        found_platforms = {item.platform for item in seen_unsupported.values()}
        for platform, pattern in PLATFORM_HINTS:
            if platform in found_platforms:
                continue
            if any(re.search(pattern, page, re.IGNORECASE)
                   for page in pages_content):
                report.hinted.append(platform)

    return report


def _sitemap_postings(get, sitemaps: list[str]) -> tuple[list[str], int]:
    """Up to MAX_SITEMAP_POSTINGS job pages out of a site's sitemaps, and
    how many reads that took.

    A sitemap index is followed into one child whose address says jobs (or
    the first, when none does); a gzipped sitemap is skipped rather than
    unpacked. Two reads at most, whatever the index holds.
    """
    reads = 0
    pending = [u for u in sitemaps if not u.lower().endswith(".gz")][:2]
    while pending and reads < 2:
        resp = get(pending.pop(0))
        reads += 1
        if resp is None or not resp.ok or not resp.body:
            continue
        children, pages = _sitemap_urls(resp.body)
        if children:
            children = [c for c in children if not c.lower().endswith(".gz")]
            jobby = [c for c in children if _job_word(c) is not None]
            pending = (jobby or children)[:1]
            continue
        ranked = [u for u in pages if _job_word(u) is not None and
                  not _NOT_PAGES.search(urllib.parse.urlsplit(u).path)]
        # The deepest addresses are postings; /careers itself is a landing page.
        ranked.sort(key=lambda u: -urllib.parse.urlsplit(u).path.count("/"))
        return ranked[:MAX_SITEMAP_POSTINGS], reads
    return [], reads


def add_to_config(config_path: str, name: str, items: list[Found]) -> list[Found]:
    """Append verified boards to `sources.companies`, preserving comments.

    Rewritten as text rather than through the YAML round-trip on purpose: a
    dump would strip every comment out of a file that is mostly comments.
    """
    from pathlib import Path

    path = Path(config_path)
    text = path.read_text(encoding="utf-8")
    # A board already listed is not added twice: looking an employer up
    # again, from the dashboard or the terminal, would otherwise duplicate it.
    import yaml
    listed = ((yaml.safe_load(text) or {}).get("sources") or {}).get("companies") or []
    have = {(str(c.get("platform", "")).lower(), str(c.get("token", "")))
            for c in listed if isinstance(c, dict)}
    addable = [item for item in items
               if item.addable and (item.platform, item.token) not in have]
    if not addable:
        return []

    def entries(dash: str) -> str:
        """The new items, at the indent of the `- ` that starts each one."""
        body = " " * (len(dash) + 2)
        return "".join(
            f"{dash}- name: {name}\n"
            f"{body}platform: {item.platform}\n"
            f"{body}token: {item.token}\n"
            for item in addable
        )

    empty = re.search(r"^(\s*)companies:\s*\[\s*\]\s*$", text, re.M)
    if empty:
        indent = empty.group(1)
        text = (text[: empty.start()] + f"{indent}companies:\n"
                + entries(indent + "  ") + text[empty.end() + 1:])
    else:
        listed = re.search(r"^(\s*)companies:\s*$", text, re.M)
        if not listed:
            raise ValueError(
                "could not find `companies:` under `sources:` in "
                f"{config_path}. Add the entries by hand."
            )
        # Match the items already there. A hand-written file indents them
        # under `companies:`; a YAML dump (the dashboard saves one) puts the
        # dash level with it. Mixing the two is a parse error that stops
        # every later scan from loading the config.
        insert = listed.end() + 1
        first = re.match(r"(?:[ \t]*(?:#.*)?\n)*([ \t]*)- ", text[insert:])
        dash = first.group(1) if first else listed.group(1) + "  "
        text = text[:insert] + entries(dash) + text[insert:]

    path.write_text(text, encoding="utf-8")
    return addable
