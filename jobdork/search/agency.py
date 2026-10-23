"""
jobdork.search.agency
=====================
Who posted a job: the employer, or a recruitment firm on its behalf.

It matters once you apply. A recruiter who sends your application to an
employer you have already applied to directly makes you a duplicate
candidate: many employers then reject the application or the agency's
claim, and some drop the candidate rather than sort out who owns them. Two
agencies submitting you for one job is the same problem. So a post is
called a recruiter's when:

  - its company is a known staffing or search firm (KNOWN_FIRMS), or its
    name says what it is ("… Staffing", "… Recruiting", "… Personnel");
  - its advert speaks for a client ("our client", "on behalf of a client");
  - it came from a built-in board listed as a staffing firm;
  - the source itself says so: the Bundesagentur für Arbeit marks
    temporary staffing and private placement (fetch/arbeitsagentur.py).

and `overlaps()` finds the posts you are already pursuing (applied or
further) that may be the same job reached the other way: the recruiter's
advert names that employer as its client, or both posts have the same
title and place.
A recruiter rarely names the client, so the title-and-place match is a
"may be"; the page says so rather than claiming it knows. It needs the same
title words and the same city: remote posts match only by name.

Grouping (db/grouping.py) never joins these: it keys on the company, and
the recruiter's post carries the recruiter's name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Staffing, recruitment and executive search firms that post under their
# own name, US first. Matched on whole words at the start of the company.
KNOWN_FIRMS = (
    "robert half", "randstad", "adecco", "manpower", "manpowergroup", "experis",
    "kelly services", "aerotek", "teksystems", "actalent", "allegis",
    "insight global", "kforce", "apex systems", "akkodis", "modis", "hays recruitment", "hays specialist",
    "michael page", "page group", "pagegroup", "page personnel", "spherion",
    "express employment", "amn healthcare", "cross country healthcare",
    "aya healthcare", "medical solutions", "maxim healthcare", "trusted health",
    "collabera", "beacon hill", "vaco", "motion recruitment", "cybercoders",
    "jobot", "kavaliro", "volt workforce", "yoh services", "peopleready", "labor finders",
    "creative circle", "aquent", "korn ferry", "heidrick", "spencer stuart",
    "russell reynolds", "egon zehnder", "lucas group", "planet pharma",
    "belcan", "judge group", "harnham", "tandym",
    "addison group", "lhh", "hudson rpo", "hirequest", "atrium staffing",
    "nesco resource",
    "system one", "talentburst", "tek ninjas", "diverse lynx", "infojini",
    "mindlance", "pyramid consulting", "artech", "net2source", "rangam",
    "ascendion", "staffmark", "trillium staffing", "integrity staffing",
    "employbridge", "prolink", "fastaff", "supplemental health care",
    "jackson healthcare", "vivian health", "hireminds", "bcforward",
    "the mom project", "toptal", "hired by matrix", "matrix resources",
)
_FIRMS = re.compile(r"^(?:the\s+)?(?:" + "|".join(
    re.escape(f).replace(r"\ ", r"\s+") for f in sorted(KNOWN_FIRMS, key=len, reverse=True))
    + r")\b", re.I)

# Words in a company's name that say it places people with other employers.
_NAME_WORDS = re.compile(
    r"\b(?:staffing|recruit(?:ing|ment|ers)|personnel|headhunt\w*|"
    r"talent (?:solutions|partners|group)|search (?:group|partners|firm)|"
    r"workforce solutions|employment (?:agency|services|solutions)|"
    r"placement(?:s)?|temps?)\b", re.I)

# An advert written for a client. "our clients" alone is not one, nor "for a
# client", nor "our client base" or "our client teams": banks and
# consultancies serve clients, and send people to them.
# A bare name that is also an employer's ("Kelly", "Hays", "Atrium") is not in
# KNOWN_FIRMS: Atrium Health and HaysMed are hospitals.
_ADVERT = re.compile(
    r"\bour client(?:['\u2019]s)?\b(?!\s*-?\s*(?:base|teams?|services?|success|relation\w*|"
    r"portfolio|experience|facing|list|satisfaction|engagements?|delivery|accounts?|"
    r"support|projects?|work|partners?|management|needs)\b)|"
    r"\bmy client\b|\bon behalf of (?:our|my|a|an) client|"
    r"\bclient of ours\b|\bone of our clients\b|"
    r"\bwe are (?:a|an) (?:staffing|recruit(?:ing|ment)) (?:agency|firm|company)\b|"
    r"\b(?:staffing|recruit(?:ing|ment)) (?:agency|firm) (?:is )?(?:seeking|looking)\b",
    re.I)


@dataclass
class Poster:
    agency: bool = False
    why: str = ""                      # how it was told, for the page

    def to_dict(self) -> dict:
        return {"agency": self.agency, "why": self.why}


# Flags a source sets when it knows the poster is an agency, and what to say.
AGENCY_FLAGS = {
    "temporary staffing (Arbeitnehmerüberlassung)":
        "the Bundesagentur für Arbeit lists it as temporary staffing",
    "private placement agency":
        "the Bundesagentur für Arbeit lists it as a private placement agency",
}


def classify(company: str, description: str = "", industry: str = "",
             flags=()) -> Poster:
    """Employer or recruiter, and why it was called a recruiter."""
    name = (company or "").strip()
    for flag in flags or ():
        if flag in AGENCY_FLAGS:
            return Poster(True, AGENCY_FLAGS[flag])
    if industry == "staffing":
        return Poster(True, "listed as a staffing firm")
    if _FIRMS.search(name):
        return Poster(True, f"{name} is a staffing or search firm")
    if _NAME_WORDS.search(name):
        return Poster(True, f'"{name}" is a recruitment firm\'s name')
    m = _ADVERT.search(description or "")
    if m:
        return Poster(True, f'the advert speaks for a client ("{m.group(0).strip()}")')
    return Poster()


# ── the same job, reached two ways ─────────────────────────────────────────────

_SUFFIX = re.compile(r"[,.]?\s+(?:inc|llc|ltd|corp|corporation|co|company|plc|"
                     r"group|holdings|lp|llp|gmbh|sa|ag)\.?$", re.I)
_WORDS = re.compile(r"[a-z0-9+#]+")


def core_name(company: str) -> str:
    """"Acme Corp, Inc." -> "acme": what an advert calls the company."""
    name = (company or "").strip().casefold()
    for _ in range(2):
        name = re.sub(r"[\s,&.]+$", "", _SUFFIX.sub("", name))
    return re.sub(r"^the\s+", "", name)


# "client", or a "Company:" label, which recruiters' adverts lead with
# ("Company: Northrop Grumman Position: …", Insight Global, 2026-10-23).
_CLIENT = re.compile(r"\bclient\b|\bcompany\s*:", re.I)
CLIENT_WINDOW = 150


def names(text: str, company: str) -> bool:
    """Whether the text names the company as the client: its name, as whole
    words, within CLIENT_WINDOW characters after "client" or "Company:".

    Anywhere in the advert was too loose (2026-10-23): "Oracle", "Google
    Cloud", "Snowflake", "Okta" and "Target" are products and plain words
    as well as employers, and recruiters' adverts are full of them.
    """
    core = core_name(company)
    if len(core) < 4:
        return False                     # "GE", "HP": too many false matches
    pattern = re.compile(r"(?<![a-z0-9])" + re.escape(core) + r"(?![a-z0-9])")
    low = (text or "").casefold()
    return any(pattern.search(low, m.end(), m.end() + CLIENT_WINDOW)
               for m in _CLIENT.finditer(low))


def same_title(a: str, b: str) -> bool:
    """The same job title, give or take punctuation, word order and "Sr."."""
    def words(t: str) -> set[str]:
        w = set(_WORDS.findall((t or "").casefold()))
        return {"senior" if x in ("sr", "snr") else "junior" if x == "jr" else x for x in w}
    wa = words(a)
    return bool(wa) and wa == words(b)


def same_place(a: dict, b: dict) -> bool:
    """The same city and state, or the same location text. Remote is no
    place: two remote posts with one title are as often two jobs as one, and
    a warning on every remote "Software Engineer" would be ignored."""
    if "remote" in (a.get("work_mode"), b.get("work_mode")):
        return False
    if a.get("city") and b.get("city"):
        return (a["city"].casefold(), (a.get("state") or "").casefold()) == \
            (b["city"].casefold(), (b.get("state") or "").casefold())
    la, lb = (a.get("location") or "").casefold().strip(), (b.get("location") or "").casefold().strip()
    return bool(la) and la == lb


def overlaps(post: dict, pursued: list[dict]) -> list[dict]:
    """Posts you are pursuing that may be this job reached another way.

    Each dict: uid, company, title, description, work_mode, city, state,
    location, status, agency (from classify). Only pairs where at least one
    side is a recruiter: two employers' posts are two jobs.
    """
    found = []
    for other in pursued:
        if other["uid"] == post["uid"] or not (post["agency"] or other["agency"]):
            continue
        if core_name(other["company"]) == core_name(post["company"]):
            continue                     # the same poster: grouping's business
        why = ""
        # The recruiter's advert naming the other side's employer.
        for rec, emp in ((post, other), (other, post)):
            if rec["agency"] and not emp["agency"] and names(rec["description"], emp["company"]):
                why = f"{rec['company']}'s advert names {emp['company']}"
        if not why and same_title(post["title"], other["title"]) and same_place(post, other):
            why = "the same title and place"
        if why:
            found.append({"uid": other["uid"], "company": other["company"],
                          "title": other["title"], "status": other["status"],
                          "agency": other["agency"], "why": why, "more": 0})
    # One line per company and reason: a recruiter naming an employer you
    # applied to eight times is one thing to know, not eight.
    merged: dict[tuple[str, str], dict] = {}
    for item in found:
        key = (core_name(item["company"]), item["why"])
        if key in merged:
            merged[key]["more"] += 1
        else:
            merged[key] = item
    return list(merged.values())
