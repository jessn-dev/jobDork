"""
jobdork.writing.resume_doc
==========================
The tailored resume's shape: the AI-friendly template, its file name, and
the contact line.

The template is https://resumeoptimizerpro.com/blog/ai-friendly-resume-template:
one column, the name then one plain contact line, standard section names in a
fixed order, skills as comma-separated text, each job as title, then
"Company | City, State | Month YYYY - Month YYYY", then bullets.

**The layout is code, not a request.** A model is asked for the content only,
as fields (summary, skills, jobs, education...), and this module lays them out.
Every provider, local or hosted, gives the same document; only the wording
changes.

**The contact line comes from the resume, never from a model.** A hosted model
is sent the resume with the email, phone number and profile links removed
(ai/llm.redact), so it could not supply them if asked; and a name or address
that a model typed is one it could have got wrong.
"""

from __future__ import annotations

import re
import unicodedata

SECTIONS = ("PROFESSIONAL SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE",
            "EDUCATION", "CERTIFICATIONS", "PROJECTS")

# ── the projects section: where, what it is called, whether at all ────────────
#
# One rule fails either the student or the executive. A student's projects
# are their evidence and belong near the top; a senior engineer's belong in
# the jobs they were done in, and a separate list reads as padding. So the
# model judges the career stage and the industry (it reads the resume and the
# advert), and this table decides where the section goes and what it is
# called. The judging is the model's; the layout never is.

STAGES = ("student", "career_changer", "freelancer", "experienced")
INDUSTRIES = ("tech", "creative", "business", "other")

# Section order by stage. "PROJECTS" is where the projects section goes.
ORDER = {
    # Right below Education, which leads: it is most of the record.
    "student": ("PROFESSIONAL SUMMARY", "SKILLS", "EDUCATION", "PROJECTS",
                "PROFESSIONAL EXPERIENCE", "CERTIFICATIONS"),
    # Above the past jobs: proof of doing the new work today.
    "career_changer": ("PROFESSIONAL SUMMARY", "SKILLS", "PROJECTS",
                       "PROFESSIONAL EXPERIENCE", "EDUCATION", "CERTIFICATIONS"),
    # Beside the experience: a track record of delivery.
    "freelancer": ("PROFESSIONAL SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE",
                   "PROJECTS", "EDUCATION", "CERTIFICATIONS"),
    # No section: projects live in the jobs' bullets.
    "experienced": ("PROFESSIONAL SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE",
                    "EDUCATION", "CERTIFICATIONS"),
}
MAX_PROJECTS = {"student": 3, "career_changer": 3, "freelancer": 4, "experienced": 0}
_HEADINGS = {"tech": "TECHNICAL PROJECTS", "creative": "PORTFOLIO HIGHLIGHTS",
             "business": "KEY INITIATIVES", "other": "PROJECTS"}
SECTIONS = ("PROFESSIONAL SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE",
            "EDUCATION", "CERTIFICATIONS", "PROJECTS", *_HEADINGS.values(),
            "SELECTED CLIENT PROJECTS", "CONSULTING HIGHLIGHTS")


def stage_of(value: str) -> str:
    """A stage the table knows; unsure means experienced, the one that adds nothing."""
    return value if value in STAGES else "experienced"


def projects_heading(stage: str, industry: str) -> str:
    if stage == "freelancer":
        return ("CONSULTING HIGHLIGHTS" if industry == "business"
                else "SELECTED CLIENT PROJECTS")
    return _HEADINGS.get(industry, "PROJECTS")


def projects_plan(stage: str, industry: str) -> str:
    """One line saying what the projects section does, for the page and the log."""
    stage = stage_of(stage)
    if stage == "experienced":
        return ("no projects section: at this stage projects belong in the jobs "
                "they were done in")
    where = {"student": "right below Education", "career_changer": "above the jobs",
             "freelancer": "after the jobs"}[stage]
    return (f'"{projects_heading(stage, industry).title()}", {where}, '
            f"at most {MAX_PROJECTS[stage]}")


# The projects every course and tutorial builds. Listed, they say "followed a
# tutorial"; the advice is to replace them with something of your own.
TUTORIAL = re.compile(
    r"\b(to-?do(?: list| app)?|todo|tic[- ]?tac[- ]?toe|weather (?:app|dashboard)|"
    r"calculator|hello world|landing page|portfolio (?:site|website)|"
    r"(?:rock[- ]paper[- ]scissors)|hangman|snake game|pomodoro|"
    r"(?:simple |basic )?(?:blog|chat) app|expense tracker|quiz app|"
    r"(?:netflix|spotify|twitter|amazon) clone|recipe app|notes? app|"
    r"(?:bmi|tip) calculator|unit converter|stopwatch|countdown timer)\b",
    re.IGNORECASE)
TUTORIAL_ADVICE = ("reads as a course exercise; replace it with something you "
                   "built for a real need, or that goes well beyond the tutorial")


def tutorial_projects(names) -> list[str]:
    return [n for n in names if n and TUTORIAL.search(n)]


def project_notes(rows) -> str:
    """Projects from the Resume page as plain text, a source beside the resume."""
    out = []
    for r in rows:
        parts = [f"Project: {r['name']}"]
        for label, key in (("Tools", "tools"), ("Link", "link"),
                           ("Situation", "situation"), ("Task", "task"),
                           ("Action", "action"), ("Result", "result")):
            if (r[key] or "").strip():
                parts.append(f"{label}: {r[key].strip()}")
        out.append("\n".join(parts))
    return "\n\n".join(out)


# For `claude -p`, which writes the Markdown itself (generate.py).
TEMPLATE_GUIDE = (
    "Lay `CV.md` out exactly like this, one column, nothing else:\n\n"
    "    # Full Name\n"
    "    City, State | Phone | Email | LinkedIn URL\n"
    "    ## PROFESSIONAL SUMMARY\n"
    "    Two or three plain sentences: role, years of experience, one or two\n"
    "    strengths, the kind of role targeted.\n"
    "    ## SKILLS\n"
    "    Comma-separated plain text on one line, no ratings.\n"
    "    ## PROFESSIONAL EXPERIENCE\n"
    "    ### Job Title\n"
    "    Company | City, State | Month YYYY - Month YYYY\n"
    "    - action verb + what was done + result, as the resume states it\n"
    "    ## EDUCATION\n"
    "    ### Degree\n"
    "    School | City, State | Month YYYY\n"
    "    ## CERTIFICATIONS\n"
    "    - one per line\n\n"
    "Projects depend on the person's career stage, judged from the resume and\n"
    "the advert:\n"
    "- Student or entry level: a projects section right below EDUCATION (and\n"
    "  EDUCATION before PROFESSIONAL EXPERIENCE), two or three projects.\n"
    "- Career changer: a projects section above PROFESSIONAL EXPERIENCE, with\n"
    "  the projects that use this job's skills.\n"
    "- Freelancer or contractor: \"## SELECTED CLIENT PROJECTS\" right after\n"
    "  PROFESSIONAL EXPERIENCE.\n"
    "- Mid-career or senior: no projects section. A project goes into a\n"
    "  job's bullets only where the resume says it was done in that job.\n"
    "Name a projects section for the industry: \"## TECHNICAL PROJECTS\"\n"
    "(tech), \"## PORTFOLIO HIGHLIGHTS\" (creative), \"## KEY INITIATIVES\"\n"
    "(business), otherwise \"## PROJECTS\". Each project as \"### Name\", then\n"
    "bullets: the situation, what was done and the result. `projects.md` in\n"
    "this folder, when present, describes projects in the person's own words\n"
    "and counts as part of the resume.\n\n"
    "Leave out a section the resume has nothing for. Contact details only as\n"
    "the resume gives them. Dates as \"March 2022 - Present\" when the resume\n"
    "gives the month; when it gives only the year, keep the year and do not\n"
    "invent a month. No tables, columns, icons, bold labels or skill ratings.\n\n"
)

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")
_MONTH = {m[:3].lower(): m for m in MONTHS}
_PRESENT = re.compile(r"^(present|current|now|today|ongoing)$", re.IGNORECASE)


def format_date(text: str) -> str:
    """One end of a date range as "Month YYYY", never inventing a month.

    "Mar 2022", "03/2022", "2022-03" and "March, 2022" become "March 2022";
    "current" becomes "Present"; "2021" stays "2021", because a month the
    resume does not give is a fact nobody can stand behind.
    """
    s = re.sub(r"\s+", " ", str(text or "")).strip().strip(".,")
    if not s:
        return ""
    if _PRESENT.match(s):
        return "Present"
    m = re.match(r"^([A-Za-z]{3,9})\.?,? (\d{4})$", s)
    if m and m.group(1)[:3].lower() in _MONTH:
        return f"{_MONTH[m.group(1)[:3].lower()]} {m.group(2)}"
    m = re.match(r"^(\d{1,2})[/.-](\d{4})$", s) or re.match(r"^(\d{4})[/.-](\d{1,2})$", s)
    if m:
        a, b = m.groups()
        month, year = (int(a), b) if len(b) == 4 else (int(b), a)
        if 1 <= month <= 12:
            return f"{MONTHS[month - 1]} {year}"
    return s


def date_range(start: str, end: str) -> str:
    a, b = format_date(start), format_date(end)
    return f"{a} - {b}" if a and b else a or b


# ── the contact line ──────────────────────────────────────────────────────────

_NAME_WORD = re.compile(r"^[^\W\d_][\w.'-]*$")
_SPLIT = re.compile(r"\s*[|•·●\t]\s*|\s{3,}")
_PLACE = re.compile(r"^[A-Z][A-Za-z.' -]+, (?:[A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)*)"
                    r"(?: \d{5})?$")


def contact(resume_text: str) -> dict:
    """Name, place, phone, email and profile link, as the resume gives them."""
    from ..ai.llm import _EMAIL, _PHONE_RUN, _PROFILE, _phone

    lines = [ln.strip() for ln in (resume_text or "").splitlines() if ln.strip()]
    head = lines[:8]
    name = ""
    for line in head[:4]:
        words = line.split()
        if (2 <= len(words) <= 4 and all(_NAME_WORD.match(w) for w in words)
                and line.upper() not in SECTIONS and "resume" not in line.lower()):
            name = " ".join(w if not w.isupper() or len(w) <= 2 else w.title()
                            for w in words)
            break
    place = ""
    for line in head:
        for part in _SPLIT.split(line):
            if _PLACE.match(part.strip()) and "@" not in part:
                place = part.strip()
                break
        if place:
            break
    email = _EMAIL.search(resume_text or "")
    profile = next((m.group(0) for m in _PROFILE.finditer(resume_text or "")
                    if "linkedin" in m.group(0).lower()), "")
    if not profile:
        found = _PROFILE.search(resume_text or "")
        profile = found.group(0) if found else ""
    phone = next((m.group(0).strip() for m in _PHONE_RUN.finditer(resume_text or "")
                  if _phone(m) != m.group(0)), "")
    return {"name": name, "location": place, "phone": phone,
            "email": email.group(0) if email else "",
            "profile": re.sub(r"^https?://(www\.)?", "", profile)}


def name_of(markdown: str) -> str:
    """The name a template document starts with ("# Name")."""
    for line in (markdown or "").splitlines():
        if line.startswith("# "):
            return line[2:].strip().replace("**", "")
        if line.strip():
            break
    return ""


def contact_line(info: dict) -> str:
    return " | ".join(v for v in (info.get("location"), info.get("phone"),
                                   info.get("email"), info.get("profile")) if v)


# ── the file name ─────────────────────────────────────────────────────────────

def _words(text: str) -> list[str]:
    """ASCII words: "María" is "Maria", so a file name survives any system."""
    plain = unicodedata.normalize("NFKD", text or "").replace("\u0141", "L").replace("\u0142", "l")
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return [w for w in re.split(r"[^A-Za-z0-9]+", plain) if w]


def filename(name: str, job_title: str, suffix: str = ".pdf") -> str:
    """FirstName_LastName_JobTitle_Resume.pdf, in letters a file system keeps.

    A middle name is left out; a title keeps its words, joined by underscores,
    and is cut at six words ("Senior Software Engineer II, Payments Platform
    (Remote)" is not a file name anyone wants to type).
    """
    names = _words(name)
    person = [names[0], names[-1]] if len(names) >= 2 else names
    title = _words(re.sub(r"\(.*?\)", " ", job_title or ""))[:6]
    return "_".join([*person, *title, "Resume"]) + suffix


# ── the document ──────────────────────────────────────────────────────────────

def to_markdown(info: dict, doc: dict) -> str:
    """The template, filled: `info` from contact(), `doc` from the model.

    `doc["stage"]` and `doc["industry"]` place and name the projects section
    (ORDER, projects_heading); without them it is an experienced resume.
    """
    stage = stage_of(doc.get("stage", ""))
    blocks: dict[str, list[str]] = {}
    if doc.get("summary"):
        blocks["PROFESSIONAL SUMMARY"] = [doc["summary"]]
    if doc.get("skills"):
        blocks["SKILLS"] = [", ".join(doc["skills"])]
    if doc.get("experience"):
        lines = []
        for job in doc["experience"]:
            lines += ["", f"### {job['title']}",
                      " | ".join(x for x in (job.get("company"), job.get("location"),
                                             date_range(job.get("start"), job.get("end")))
                                 if x)]
            lines += [f"- {b}" for b in job.get("bullets") or []]
        blocks["PROFESSIONAL EXPERIENCE"] = lines[1:]
    if doc.get("education"):
        lines = []
        for ed in doc["education"]:
            lines += ["", f"### {ed['credential']}",
                      " | ".join(x for x in (ed.get("school"), ed.get("location"),
                                             date_range(ed.get("start"), ed.get("end")))
                                 if x)]
        blocks["EDUCATION"] = lines[1:]
    if doc.get("certifications"):
        blocks["CERTIFICATIONS"] = [f"- {c}" for c in doc["certifications"]]
    projects = (doc.get("projects") or [])[:MAX_PROJECTS[stage]]
    if projects:
        lines = []
        for p in projects:
            lines += ["", f"### {p['name']}"] + [f"- {b}" for b in p.get("bullets") or []]
        blocks["PROJECTS"] = lines[1:]

    out = [f"# {info.get('name') or 'Resume'}"]
    line = contact_line(info)
    if line:
        out.append(line)
    for section in ORDER[stage]:
        if section in blocks:
            heading = (projects_heading(stage, doc.get("industry", ""))
                       if section == "PROJECTS" else section)
            out += ["", f"## {heading}", *blocks[section]]
    return "\n".join(out).strip() + "\n"
