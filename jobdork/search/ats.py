"""
jobdork.search.ats
==================
How your resume matches one job post the way an applicant tracking system
searches it: a score out of 100, and the advert's keywords you have, could
add, and lack. Script only; the same resume and advert give the same score.

The parts and their weights follow Resume Matcher's ATS score
(github.com/srbhr/resume-matcher, Apache-2.0, services/ats.py), rewritten
for jobdork. Where it asks a model for the advert's keywords, jobdork uses
its own skills vocabulary (search/resume.py), the one the Fit score uses:
offline, free, and the same words in every place.

- **keywords** (40%): the advert's skills that your resume names;
- **required skills** (20%): the same, of the skills under the advert's
  requirements ("Requirements", "Qualifications", "What you bring"); the
  whole advert when it has no such part;
- **job title** (15%): the post's title in your resume's top lines (100),
  in its summary (75), or up to 50 for the title's words found there;
- **sections** (15%): an email or phone, and the summary, experience,
  education and skills headings;
- **dates** (10%): the share of dates written in the most used format.

A part that cannot be judged (an advert with no skills, a resume with one
date) is left out and the rest weighed up to 100.

The score is of the resume file you uploaded, since that is what a
tracking system would read if you sent it. Skills that are only in your
projects, education or confirmed skills (the Resume page; "I have this")
are listed as **safe to add**: a tailored resume may use them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

WEIGHTS = {"keywords": 40, "required": 20, "title": 15, "sections": 15, "dates": 10}
LABELS = {"keywords": "Keywords", "required": "Required skills", "title": "Job title",
          "sections": "Sections", "dates": "Dates in one format"}
TITLE_TOP, TITLE_SUMMARY, TITLE_WORDS = 100.0, 75.0, 50.0
HEAD_LINES = 6
_STOP = {"a", "an", "and", "the", "of", "for", "in", "to", "at", "&", "-", "with", "i",
         "ii", "iii", "iv", "senior", "junior", "sr", "jr", "lead"}
_REQUIREMENTS = re.compile(
    r"^\W*(?:requirements?|qualifications?|minimum qualifications|basic qualifications|"
    r"required(?: skills| experience)?|must[- ]haves?|what you(?:'ll| will)? (?:bring|need)|"
    r"what we(?:'re| are) looking for|you have|you bring|skills(?: and| &) experience|"
    r"who you are)\b.{0,30}$", re.IGNORECASE | re.MULTILINE)
_NEXT_PART = re.compile(
    r"^\W*(?:nice to have|preferred|bonus|benefits|perks|what we offer|about (?:us|the)|"
    r"responsibilities|what you(?:'ll| will) do|compensation|salary|pay)\b.{0,30}$",
    re.IGNORECASE | re.MULTILINE)
_YEAR = r"(?:19|20)\d{2}"
_MONTH = (r"(?i:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
          r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_DATE = re.compile(rf"(?P<iso>\b{_YEAR}[-/]\d{{1,2}}\b)|(?P<numeric>\b\d{{1,2}}[/.-]{_YEAR}\b)"
                   rf"|(?P<name_year>\b{_MONTH}\.?,?\s+{_YEAR}\b)"
                   rf"|(?P<name_short>\b{_MONTH}\.?\s+'\d{{2}}\b)|(?P<year>\b{_YEAR}\b)")
_SUMMARY_NAMES = ("summary", "professional summary", "profile", "objective", "about me",
                  "career objective", "personal profile")


@dataclass
class Match:
    score: float | None
    parts: dict[str, float | None] = field(default_factory=dict)
    have: list[str] = field(default_factory=list)         # in the resume file
    can_add: list[str] = field(default_factory=list)      # only in the rest of the record
    missing: list[str] = field(default_factory=list)      # nowhere
    required: list[str] = field(default_factory=list)     # the advert's required skills
    advice: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "weights": WEIGHTS, "labels": LABELS,
                "parts": self.parts, "have": self.have, "can_add": self.can_add,
                "missing": self.missing, "required": self.required, "advice": self.advice}


def requirements(advert: str) -> str:
    """The advert's requirements part, or "" when it has none that says so."""
    start = _REQUIREMENTS.search(advert or "")
    if not start:
        return ""
    end = _NEXT_PART.search(advert, start.end())
    return advert[start.end():end.start() if end else None]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#.]+", (text or "").lower()) if w not in _STOP}


def title_match(title: str, resume_text: str) -> float | None:
    """How literally the post's title is in the resume: its top lines, then
    its summary, then the share of the title's words in the top lines."""
    plain = re.sub(r"\(.*?\)|\[.*?\]", " ", title or "")
    # " - Remote", " | Chicago", ", Payments": the title is what comes before.
    plain = re.split(r"\s[-\u2013|,]\s|\s/\s", plain)[0].strip().lower()
    if not plain:
        return None
    lines = [ln.strip() for ln in (resume_text or "").splitlines() if ln.strip()]
    head = "\n".join(_head(lines)).lower()
    if re.search(r"\b" + re.escape(plain) + r"\b", head):
        return TITLE_TOP
    summary = _summary(lines).lower()
    if summary and re.search(r"\b" + re.escape(plain) + r"\b", summary):
        return TITLE_SUMMARY
    wanted = _words(plain)
    if not wanted:
        return 0.0
    return round(len(wanted & _words(head)) / len(wanted) * TITLE_WORDS, 1)


def _head(lines: list[str]) -> list[str]:
    """The lines above the first section heading (the name, a headline, the
    contact line), at most HEAD_LINES: where a title is read first."""
    from .readable import find_sections

    out = []
    for line in lines[:HEAD_LINES]:
        plain = line.strip(" :•|*#-").lower()
        if plain in _SUMMARY_NAMES or find_sections(line):
            break
        out.append(line)
    return out


def _summary(lines: list[str]) -> str:
    for n, line in enumerate(lines):
        if line.strip(" :•|*#-").lower() in _SUMMARY_NAMES:
            out = []
            for nxt in lines[n + 1:n + 8]:
                if nxt.isupper() and len(nxt.split()) <= 4:
                    break
                out.append(nxt)
            return " ".join(out)
    return ""


def date_consistency(resume_text: str) -> float | None:
    styles: dict[str, int] = {}
    for m in _DATE.finditer(resume_text or ""):
        styles[m.lastgroup] = styles.get(m.lastgroup, 0) + 1
    total = sum(styles.values())
    if total < 2:
        return None
    return round(max(styles.values()) / total * 100, 1)


def sections(resume_text: str) -> float:
    from .readable import _EMAIL, find_sections, has_phone

    lines = [ln.strip() for ln in (resume_text or "").splitlines() if ln.strip()]
    found = set(find_sections(resume_text))
    summary = bool(_summary(lines))
    contact = bool(_EMAIL.search(resume_text or "") or has_phone(resume_text or ""))
    have = contact + summary + sum(k in found for k in ("experience", "education", "skills"))
    return round(have / 5 * 100, 1)


def match(resume_text: str, record_text: str, advert: str, title: str = "") -> Match:
    """`resume_text` is the file's text; `record_text` is it with the Resume
    page's projects, education and confirmed skills added."""
    from . import resume as resume_mod

    if not resume_text or not advert:
        return Match(None)
    have_file = resume_mod.resume_skills(resume_text)
    have_all = resume_mod.resume_skills(record_text or resume_text)
    wanted = resume_mod.near(have_all, resume_mod.extract_skills(f"{title}\n{advert}"))
    need = resume_mod.near(have_all, resume_mod.extract_skills(requirements(advert))) or wanted
    out = Match(None, required=sorted(need, key=str.lower))
    out.have = sorted(wanted & have_file, key=str.lower)
    out.can_add = sorted((wanted & have_all) - have_file, key=str.lower)
    out.missing = sorted(wanted - have_all, key=str.lower)
    parts: dict[str, float | None] = {
        "keywords": round(len(wanted & have_file) / len(wanted) * 100, 1) if wanted else None,
        "required": round(len(need & have_file) / len(need) * 100, 1) if need else None,
        "title": title_match(title, resume_text),
        "sections": sections(resume_text),
        "dates": date_consistency(resume_text),
    }
    out.parts = parts
    scored = {k: v for k, v in parts.items() if v is not None}
    weight = sum(WEIGHTS[k] for k in scored)
    out.score = round(sum(v * WEIGHTS[k] for k, v in scored.items()) / weight, 1) if weight else None
    out.advice = _advice(out, title)
    return out


def _advice(m: Match, title: str) -> list[str]:
    from .resume import skill_name

    tips = []
    if m.can_add:
        tips.append(f"{', '.join(map(skill_name, m.can_add[:6]))}: in your projects, education "
                    "or confirmed skills but not your resume file. A tailored resume for this "
                    "post can name them.")
    if m.missing:
        tips.append("The skills under Missing are not anywhere in your record. Tick "
                    "\"I have this\" only for one you really have: a tailored resume may then "
                    "name it, and an interviewer may ask about it.")
    if (m.parts.get("title") or 0) < TITLE_SUMMARY and title:
        tips.append(f"Recruiters search by job title. If \"{title}\" is what you do, say so at "
                    "the top of your resume or in its summary: a tailored resume does.")
    if (m.parts.get("sections") or 0) < 100:
        tips.append("A section a tracking system files resumes by is missing: see your "
                    "resume's Checks on the Resume page.")
    if m.parts.get("dates") is not None and m.parts["dates"] < 100:
        tips.append("Dates are written more than one way. Write them all alike, such as "
                    "\"March 2022 - Present\".")
    return tips
