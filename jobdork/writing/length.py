"""
jobdork.writing.length
======================
How long a tailored resume may be, after Indeed's guidance
(https://www.indeed.com/career-advice/resumes-cover-letters/how-long-should-a-resume-be,
read 2026-10-28):

- one page up to ten years of experience, two after that, and three only
  past 25 years or for academic and medical work;
- the last 15 years of jobs in full;
- three to seven bullets a job, more for the newest, fewer for older ones,
  each at most about two lines.

The model is told all of it (ai/writer.py), and this module holds it to it:
`fit` moves a job older than 15 years to one line under Earlier experience
(resume_doc.split_earlier: its title, employer, dates and what carries
over), caps each job's bullets by how recent it is, then renders the PDF
and, while it runs over its pages, takes the least of what is left (an
older job's last bullets first, then extra projects, awards and the end of
the skills list, then the oldest jobs into one line each) until it fits.
A job is never left out: a gap in the dates reads worse than an old job in
one line, and a person asked for theirs compressed, not dropped
(2026-11-12). What it took is said in a gate, so the person sees what is not
on the page.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

YEARS_ONE_PAGE = 10
YEARS_THREE_PAGES = 25
RECENT_YEARS = 15
# Bullets for the newest job, the next and so on; every older one keeps three.
BULLETS_BY_RECENCY = (7, 6, 5, 4)
OLDER_BULLETS = 3
MIN_BULLETS = 2              # a job keeps at least this many when trimmed for space
LINE_CHARS = 115             # about one line of an 11 point bullet, 0.7 inch margins
# Work where a longer record is the custom: a CV more than a resume.
_LONG_FORM = re.compile(
    r"\b(professor|lecturer|faculty|academic|postdoc\w*|research (?:fellow|scientist)|"
    r"physician|surgeon|resident|fellowship|psychiatrist|clinical (?:director|researcher)|"
    r"principal investigator|md\b|ph\.?d)", re.IGNORECASE)
_YEAR = re.compile(r"\b(19|20)\d\d\b")


@dataclass
class Fitted:
    pages: int = 0                 # pages it fills
    budget: int = 1                # pages it may fill
    reason: str = ""               # why that budget
    left_out: list[str] = field(default_factory=list)   # what was taken, said
    long_bullets: int = 0          # bullets over two lines, kept as written


def budget(years: float, title: str = "", advert: str = "") -> tuple[int, str]:
    """(pages, why), from the years of work and the kind of job."""
    if _LONG_FORM.search(f"{title}\n{advert[:2000]}"):
        return 3, "academic or medical work, where a longer record is usual"
    if years > YEARS_THREE_PAGES:
        return 3, f"over {YEARS_THREE_PAGES} years of experience"
    if years > YEARS_ONE_PAGE:
        return 2, f"over {YEARS_ONE_PAGE} years of experience"
    return 1, f"up to {YEARS_ONE_PAGE} years of experience"


def _ended(job: dict) -> int:
    """The year a job ended; a current one, or one with no year, is now."""
    end = (job.get("end") or "").strip()
    if not end or re.match(r"^(present|current|now|today|ongoing)$", end, re.IGNORECASE):
        return 9999
    years = [int(m.group(0)) for m in _YEAR.finditer(end)]
    return max(years) if years else 9999


def recent(jobs: list[dict], this_year: int | None = None) -> tuple[list[dict], list[dict]]:
    """(in full, in one line): jobs that ended in the last 15 years, and the
    older ones, kept with no bullets. When none is recent (someone returning
    to work), the newest stays in full."""
    year = this_year or time.localtime().tm_year
    full = [j for j in jobs if _ended(j) >= year - RECENT_YEARS]
    if not full and jobs:
        full = jobs[:1]
    return full, [j for j in jobs if j not in full]


def cap_bullets(jobs: list[dict]) -> int:
    """Each job's bullets capped by its place, newest first. Returns how many went."""
    gone = 0
    for n, job in enumerate(jobs):
        cap = BULLETS_BY_RECENCY[n] if n < len(BULLETS_BY_RECENCY) else OLDER_BULLETS
        bullets = job.get("bullets") or []
        gone += max(0, len(bullets) - cap)
        job["bullets"] = bullets[:cap]
    return gone


def _trim_once(doc: dict) -> str:
    """Take the least of what is left; say what. "" when nothing can go."""
    jobs = doc.get("experience") or []
    # An older job's last bullet first, the oldest job first.
    for job in reversed(jobs):
        if len(job.get("bullets") or []) > MIN_BULLETS:
            job["bullets"].pop()
            return f"a bullet of {job['title']}"
    projects = doc.get("projects") or []
    shown = [p for p in projects if not p.get("own")]
    if shown:
        projects.remove(shown[-1])
        return f"project: {shown[-1]['name']}"
    if doc.get("awards"):
        return f"award: {doc['awards'].pop()}"
    if len(doc.get("skills") or []) > 8:
        return f"skill: {doc['skills'].pop()}"
    # Last, the oldest job in full down to one line under Earlier
    # experience: its first bullet says what carries over; the job stays.
    for job in reversed(jobs[1:]):
        if not job.get("brief"):
            job["brief"] = True
            job["bullets"] = (job.get("bullets") or [])[:1]
            return f"{job['title']} in one line"
    return ""


def fit(doc: dict, render, years: float, title: str = "", advert: str = "",
        this_year: int | None = None) -> Fitted:
    """Hold `doc` (the tailored resume's fields) to its length, in place.

    `render(doc)` gives the PDF bytes for a doc: the pages are counted from
    the very file the person gets.
    """
    from ..output import pdf

    pages, why = budget(years, title, advert)
    out = Fitted(budget=pages, reason=why)
    _full, old = recent(doc.get("experience") or [], this_year)
    for job in old:
        if not job.get("brief") and len(job.get("bullets") or []) > 1:
            out.left_out.append(f"a job before the last {RECENT_YEARS} years, kept in "
                                f"one line: {job['title']}")
        job["brief"] = True
        job["bullets"] = (job.get("bullets") or [])[:1]
    capped = cap_bullets([j for j in doc.get("experience") or [] if not j.get("brief")])
    if capped:
        out.left_out.append(f"{capped} bullet(s) over the {BULLETS_BY_RECENCY[0]} a job "
                            "Indeed suggests, older jobs fewer")
    while True:
        out.pages = pdf.page_count(render(doc))
        if out.pages <= out.budget:
            break
        took = _trim_once(doc)
        if not took:
            break
        out.left_out.append(f"for space: {took}")
    out.long_bullets = sum(1 for j in doc["experience"] for b in j.get("bullets") or []
                           if len(b) > 2 * LINE_CHARS)
    return out
