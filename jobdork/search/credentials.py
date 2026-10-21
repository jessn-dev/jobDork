"""
jobdork.search.credentials
==========================
The certifications and licenses a job post asks for, so an opened advert can
put them where they are seen: a nurse's RN licence and BLS, an accountant's
CPA, a driver's CDL, a security engineer's CISSP. A post that needs a licence
you do not hold is not a fit however well the rest reads.

Read from the advert's own lines. A line counts when it talks about a
credential ("certification", "licensed", "board certified"), or names one
(from the list below) and says it is required or preferred, or sits under a
requirements heading: "RN" alone is in every line of a nurse's advert. Each is marked required, preferred, or neither, from its
own words or the heading above it, and each credential named is looked for
in the resume. A line that says one is not needed ("no license required")
is left out.

Display only: screening and the AI read the advert as it is.
"""

from __future__ import annotations

import re

# Named credentials, by what they are called in adverts. Grouped loosely by
# field; the order inside a group is the order they are reported in.
NAMED = (
    # healthcare
    "RN", "LPN", "LVN", "CNA", "NP", "APRN", "PA-C", "CRNA", "BLS", "ACLS",
    "PALS", "NRP", "TNCC", "CCRN", "CEN", "CPR", "EMT",
    "PharmD", "RPh", "CPhT", "RRT", "OTR", "DPT", "LCSW", "LPC", "LMFT",
    "RDN", "CPC", "RHIT", "RHIA", "DEA",
    # finance and accounting
    "CPA", "CMA", "CFA", "CFP", "Certified Internal Auditor", "Enrolled Agent",
    "Series 7", "Series 63",
    "Series 65", "Series 66", "Series 24", "FINRA",
    # technology and security
    "CISSP", "CISM", "CISA", "CEH", "OSCP", "Security+", "Network+", "A+",
    "CCNA", "CCNP", "CCIE", "AWS Certified", "Azure Certified", "CKA", "CKAD",
    "PMP", "CAPM", "Certified ScrumMaster", "ITIL", "Six Sigma",
    # trades, transport, safety
    "CDL", "TWIC", "OSHA 10",
    "OSHA 30", "EPA 608", "Journeyman", "Master Electrician", "FAA", "A&P",
    "ServSafe", "Food Handler", "Notary",
    # law, engineering, teaching, HR
    "Bar admission", "Juris Doctor", "PE", "EIT", "SHRM-CP", "SHRM-SCP",
    "PHR", "SPHR", "Teaching certificate", "Teaching license",
)

# Words that mark a line as being about a credential without naming one.
_TALK = re.compile(
    r"\b(certif\w*|licen[sc](?:e|ed|es|ing)|licensure|board[- ]certified|credential\w*|"
    r"accredit\w*|endorsement|registration as|"
    r"registered (?:nurse|pharmacist|dietitian)|admitted to (?:the|practice))\b",
    re.IGNORECASE)
_REQUIRED = re.compile(
    r"\b(required|requires?|must|mandatory|minimum|need(?:ed|s)?|"
    r"current(?:ly)?|valid|active|eligible|obtain within)\b", re.IGNORECASE)
_PREFERRED = re.compile(
    r"\b(preferred|a plus|nice to have|desired|desirable|bonus|ideally|"
    r"advantage)\b", re.IGNORECASE)
_NOT_NEEDED = re.compile(
    r"\b(no|not)\b[^.]{0,40}\b(required|necessary|needed)\b", re.IGNORECASE)
# The employer's own certifications, not ones asked of you.
_COMPANY = re.compile(
    r"\b(B[- ]?Corp|Great Place to Work|ISO ?\d{4,5}|SOC ?2|FedRAMP|HITRUST|PCI[- ]DSS|"
    r"we are (?:a )?certified|we(?:'re| are) proud)\b", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[\u2022\u25cf\u25aa\u25e6\u00b7*\u2013-]|\d{1,2}[.)])\s+")
# A heading that opens a list of credentials: every line under it is one,
# named here or not ("IAT I", "IAM I"), until the next heading.
_CERT_HEADING = re.compile(
    r"^(?:(?:required|preferred|desired)\s+)?(?:certifications?|certificates?|"
    r"licen[sc]es?|licensure|credentials)(?:\s*(?:and|&|/)\s*(?:certifications?|"
    r"certificates?|licen[sc]es?|licensure))?(?:\s*\(.*\))?\s*:?$", re.IGNORECASE)
_HEADING_PREFERRED = re.compile(r"\b(preferred|nice to have|bonus|plus)\b", re.IGNORECASE)
_HEADING_REQUIRED = re.compile(r"\b(required|requirements|minimum|basic|must)\b", re.IGNORECASE)

# One pattern per name: whole word, and for the short ones case-sensitive,
# so "RN" is not found in "learn" and "EA" not in "team" or "Each".
_PATTERNS = []
for _name in NAMED:
    _flags = 0 if len(_name) <= 4 and _name.isupper() else re.IGNORECASE
    _PATTERNS.append((_name, re.compile(
        r"(?<![\w+])" + re.escape(_name) + r"(?![\w+])", _flags)))

MAX_LINES = 12
# A line that only talks about credentials, past this length, is boilerplate
# (pay transparency, equal opportunity), not a requirement.
MAX_TALK_LINE = 300


def line_of(raw: str) -> str:
    """A line as the dashboard shows it: bullet off, spaces collapsed."""
    return _BULLET.sub("", re.sub(r"[ \t ]+", " ", raw).strip())


def named_in(text: str) -> list[str]:
    return [name for name, pattern in _PATTERNS if pattern.search(text)]


def _word(name: str) -> re.Pattern:
    """`name` as a whole word; short all-caps ones keep their case."""
    flags = 0 if len(name) <= 4 and name.isupper() else re.IGNORECASE
    return re.compile(r"(?<![\w+])" + re.escape(name) + r"(?![\w+])", flags)


def find(advert: str, resume_text: str = "", held: list[str] = ()) -> list[dict]:
    """Lines asking for a certification or licence, in advert order.

    Each: {"line": the line as displayed, "need": "required" | "preferred" |
    "", "names": credentials named, "have": those you hold}. You hold one
    the resume names or `held` lists (yours, as you wrote them); one of
    yours that the line names counts even when the list above does not
    know it ("IAT I").
    """
    held = [h.strip() for h in held if h and h.strip()]
    held_text = "\n".join(held)
    out: list[dict] = []
    heading_need, cert_section = "", False
    for raw in (advert or "").replace("\r", "").split("\n"):
        line = line_of(raw)
        if not line:
            continue
        names = named_in(line)
        # "Certifications (one or more required):" opens a list of them.
        if _CERT_HEADING.match(line):
            cert_section = True
            heading_need = ("preferred" if _HEADING_PREFERRED.search(line)
                            else "required" if _REQUIRED.search(line) else heading_need)
            continue
        # Any other heading ("Preferred Qualifications", "Experience:") says
        # how to read what follows and ends a list of credentials. A heading
        # ends in a colon, or is a few words naming no credential; "Current
        # RN license in Illinois" is short too, but it is an item.
        words = len(line.split())
        if len(line) <= 70 and (line.endswith(":") or (
                words <= 4 and not names and not _TALK.search(line)
                and not re.search(r"[.!?;,]$", line) and not cert_section)):
            heading_need = ("preferred" if _HEADING_PREFERRED.search(line)
                            else "required" if _HEADING_REQUIRED.search(line) else "")
            cert_section = False
            continue
        talks = bool(_TALK.search(line)) and len(line) <= MAX_TALK_LINE
        asked = bool(_REQUIRED.search(line) or _PREFERRED.search(line) or heading_need)
        if not (talks or cert_section) and not (names and asked):
            continue
        if _NOT_NEEDED.search(line) or (_COMPANY.search(line) and not names):
            continue
        need = ("preferred" if _PREFERRED.search(line)
                else "required" if _REQUIRED.search(line) else heading_need)
        names += [h for h in held if h not in names and _word(h).search(line)
                  and not any(_word(h).search(n) or _word(n).search(h) for n in names)]
        have = [n for n in names
                if (resume_text and _word(n).search(resume_text)) or n in held
                or (held_text and _word(n).search(held_text))]
        out.append({"line": line, "need": need, "names": names, "have": have})
        if len(out) >= MAX_LINES:
            break
    return out
