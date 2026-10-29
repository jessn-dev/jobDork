"""
jobdork.writing.resume_doc
==========================
The tailored resume's shape: the AI-friendly template, its file name, and
the contact line.

The layout follows Indeed's free resume template, rebuilt here (nothing of its
file is copied): one column, the name, then "Phone | Email | Location" and a
website line, centred; then PROFESSIONAL SUMMARY, EXPERIENCE, SKILLS,
EDUCATION, CERTIFICATIONS and AWARDS & VOLUNTEER WORK in that order (projects
placed by career stage, below); each job as its title with the dates at the
right margin, then "Company, Location", then bullets; skills separated by
" | ". Its length follows Indeed's guidance (writing/length.py).

In the Markdown every output is made from, a heading's dates follow a tab:
"### Software Engineer<TAB>March 2022 - Present". The PDF (output/pdf.py) and
the Word file (output/docx.py) set them at the right margin.

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

SECTIONS = ("PROFESSIONAL SUMMARY", "EXPERIENCE", "SKILLS", "EDUCATION",
            "CERTIFICATIONS", "AWARDS & VOLUNTEER WORK", "PROJECTS")

# ── the projects section: where, what it is called, whether at all ────────────
#
# One rule fails either the student or the executive. A student's projects
# are their evidence and belong near the top; a senior engineer's belong in
# the jobs they were done in, and a separate list reads as padding. So the
# model judges the career stage and the industry (it reads the resume and the
# advert), and this table decides where the section goes and what it is
# called. The judging is the model's; the layout never is.
#
# Projects the person added on the Resume page ("own") are always shown, at
# every stage (their request, 2026-10-23): they added them to be seen. For
# someone experienced that is a section after the jobs holding those alone;
# the resume's other projects still belong in the jobs they were done in.

STAGES = ("student", "career_changer", "freelancer", "experienced")
INDUSTRIES = ("tech", "creative", "business", "other")

# Section order by stage: the template's (summary, experience, skills,
# education, certifications, awards), with "PROJECTS" where the projects
# section goes.
_AFTER = ("SKILLS", "EDUCATION", "CERTIFICATIONS", "AWARDS & VOLUNTEER WORK")
ORDER = {
    # Education leads, its projects right below: it is most of the record.
    "student": ("PROFESSIONAL SUMMARY", "EDUCATION", "PROJECTS", "EXPERIENCE",
                "SKILLS", "CERTIFICATIONS", "AWARDS & VOLUNTEER WORK"),
    # Above the past jobs: proof of doing the new work today.
    "career_changer": ("PROFESSIONAL SUMMARY", "PROJECTS", "EXPERIENCE", *_AFTER),
    # Beside the experience: a track record of delivery.
    "freelancer": ("PROFESSIONAL SUMMARY", "EXPERIENCE", "PROJECTS", *_AFTER),
    # After the jobs, and only for projects the person added themselves;
    # the resume's own projects live in the jobs' bullets.
    "experienced": ("PROFESSIONAL SUMMARY", "EXPERIENCE", "PROJECTS", *_AFTER),
}
MAX_PROJECTS = {"student": 3, "career_changer": 3, "freelancer": 4, "experienced": 3}
_HEADINGS = {"tech": "TECHNICAL PROJECTS", "creative": "PORTFOLIO HIGHLIGHTS",
             "business": "KEY INITIATIVES", "other": "PROJECTS"}
SECTIONS = (*SECTIONS, *_HEADINGS.values(), "SELECTED CLIENT PROJECTS",
            "CONSULTING HIGHLIGHTS")


def stage_of(value: str) -> str:
    """A stage the table knows; unsure means experienced, the one that adds nothing."""
    return value if value in STAGES else "experienced"


def projects_heading(stage: str, industry: str) -> str:
    if stage == "freelancer":
        return ("CONSULTING HIGHLIGHTS" if industry == "business"
                else "SELECTED CLIENT PROJECTS")
    return _HEADINGS.get(industry, "PROJECTS")


def projects_plan(stage: str, industry: str, own: int = 0) -> str:
    """One line saying what the projects section does, for the page and the log.
    `own`: how many projects the person added on the Resume page."""
    stage = stage_of(stage)
    if stage == "experienced":
        if not own:
            return ("no projects section: at this stage projects belong in the jobs "
                    "they were done in")
        return (f'"{projects_heading(stage, industry).title()}", after the jobs, for '
                f"the projects you added only, at most {MAX_PROJECTS[stage]}; the "
                "resume's others belong in the jobs they were done in")
    where = {"student": "right below Education", "career_changer": "above the jobs",
             "freelancer": "after the jobs"}[stage]
    return (f'"{projects_heading(stage, industry).title()}", {where}, '
            f"at most {MAX_PROJECTS[stage]}")


def star_bullets(row) -> list[str]:
    """A project from the Resume page as bullets in the person's own words:
    what it was for, what they did, what came of it."""
    lead = " ".join(x for x in (_field(row, "situation"), _field(row, "task")) if x)
    return [b[:400] for b in (lead, _field(row, "action"), _field(row, "result")) if b]


def project_detail(row) -> str:
    """The line under a project's name: your part, the tools, the link."""
    return " | ".join(x for x in (_field(row, "role"), _field(row, "tools"),
                                  _field(row, "link")) if x)


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


# What a project can be. Any kind of work counts, not only software: a writer's
# articles, a marketer's campaign, a nurse's quality project, volunteering.
PROJECT_KINDS = ("App or software", "Writing or articles", "Design or creative work",
                 "Research or analysis", "Campaign or event", "Business or operations",
                 "Teaching or training", "Volunteer or community", "Personal", "Other")


def _field(row, key: str) -> str:
    """A project field, "" for a row from before it existed."""
    try:
        return (row[key] or "").strip()
    except (KeyError, IndexError):
        return ""


def project_notes(rows) -> str:
    """Projects from the Resume page as plain text, a source beside the resume."""
    out = []
    for r in rows:
        parts = [f"Project: {r['name']}"]
        for label, key in (("Kind", "kind"), ("Role", "role"), ("Tools", "tools"),
                           ("Link", "link"),
                           ("Situation", "situation"), ("Task", "task"),
                           ("Action", "action"), ("Result", "result")):
            if _field(r, key):
                parts.append(f"{label}: {_field(r, key)}")
        out.append("\n".join(parts))
    return "\n\n".join(out)


def same_credential(a: str, b: str) -> bool:
    """"BSN" and "BSN, Nursing", "B.S. Computer Science" and "BS in Computer
    Science": the same credential, by the words they share."""
    def words(t: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", (t or "").casefold().replace(".", ""))
                if w not in ("in", "of", "and", "the")}
    wa, wb = words(a), words(b)
    return bool(wa and wb) and (wa <= wb or wb <= wa)


def education_line(row) -> str:
    """One entry from the Resume page as the resume would print it."""
    when = date_range(_field(row, "start"), _field(row, "end"))
    return " | ".join(x for x in (_field(row, "credential"), _field(row, "school"),
                                  _field(row, "location"), when) if x)


def education_notes(rows) -> str:
    """Education from the Resume page as plain text, a source beside the resume."""
    out = []
    for r in rows:
        line = f"Education: {education_line(r)}"
        if _field(r, "details"):
            line += f"\nDetails: {_field(r, 'details')}"
        out.append(line)
    return "\n\n".join(out)


def record_notes(projects, education) -> str:
    """Everything added on the Resume page, as one source beside the resume."""
    return "\n\n".join(x for x in (project_notes(projects), education_notes(education)) if x)


# For `claude -p`, which writes the Markdown itself (generate.py).
TEMPLATE_GUIDE = (
    "Lay `CV.md` out exactly like this, one column, nothing else (<TAB> is a\n"
    "tab character: the dates go at the right margin):\n\n"
    "    # Full Name\n"
    "    Phone | Email | City, State\n"
    "    Website or LinkedIn URL (only if the resume gives one)\n"
    "    ## PROFESSIONAL SUMMARY\n"
    "    Two or three plain sentences: role, years of experience, one or two\n"
    "    strengths, the kind of role targeted.\n"
    "    ## EXPERIENCE\n"
    "    ### Job Title<TAB>Month YYYY - Month YYYY\n"
    "    Company, City, State\n"
    "    - action verb + what was done + result, as the resume states it\n"
    "    ## SKILLS\n"
    "    Skill | Skill | Skill, on one line, no ratings.\n"
    "    ## EDUCATION\n"
    "    ### Degree, Major<TAB>Month YYYY\n"
    "    School, City, State\n"
    "    ## CERTIFICATIONS\n"
    "    - Certification, certifying organisation - year\n"
    "    ## AWARDS & VOLUNTEER WORK\n"
    "    - one per line, only if the resume has any\n\n"
    "Length, as Indeed advises: one page for up to ten years of experience,\n"
    "two after that, three only past 25 years or for academic and medical\n"
    "roles. Only the last 15 years of jobs. Three to seven bullets a job,\n"
    "more for the newest and fewer for older ones, each at most two lines,\n"
    "with a result the resume states where it gives one.\n\n"
    "Projects depend on the person's career stage, judged from the resume and\n"
    "the advert:\n"
    "- Student or entry level: EDUCATION right after the summary, a projects\n"
    "  section right below it, then EXPERIENCE; two or three projects.\n"
    "- Career changer: a projects section above EXPERIENCE, with the projects\n"
    "  that use this job's skills.\n"
    "- Freelancer or contractor: \"## SELECTED CLIENT PROJECTS\" right after\n"
    "  EXPERIENCE.\n"
    "- Mid-career or senior: a project goes into a job's bullets only where\n"
    "  the resume says it was done in that job; the projects in `projects.md`\n"
    "  get a projects section right after EXPERIENCE.\n"
    "Name a projects section for the industry: \"## TECHNICAL PROJECTS\"\n"
    "(tech), \"## PORTFOLIO HIGHLIGHTS\" (creative), \"## KEY INITIATIVES\"\n"
    "(business), otherwise \"## PROJECTS\". Each project as \"### Name\", then\n"
    "bullets: the situation, what was done and the result. `projects.md` in\n"
    "this folder, when present, describes projects in the person's own words\n"
    "and counts as part of the resume. Show every project in it, the ones\n"
    "this job cares about first (at most four), even one the resume names\n"
    "only or gives only as a link: describe it from `projects.md`. Its\n"
    "\"Education:\" lines are schooling the resume may not show yet: put each\n"
    "under EDUCATION, newest first, with any the resume has.\n\n"
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
    """The line under the name: "Phone | Email | Location", as the template."""
    return " | ".join(v for v in (info.get("phone"), info.get("email"),
                                   info.get("location")) if v)


def header_lines(info: dict) -> list[str]:
    """Under the name: the contact line, then the website, each when given."""
    return [x for x in (contact_line(info), info.get("profile") or "") if x]


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

def _dated(heading: str, entry: dict) -> str:
    """"### Title<TAB>dates": the dates at the right margin, when there are any."""
    dates = date_range(entry.get("start"), entry.get("end"))
    return f"### {heading}" + (f"\t{dates}" if dates else "")


def _place(name: str, entry: dict):
    """"Company, Location", or None when there is neither."""
    return ", ".join(x for x in (name, entry.get("location")) if x) or None


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
        blocks["SKILLS"] = [" | ".join(doc["skills"])]
    if doc.get("experience"):
        lines = []
        for job in doc["experience"]:
            lines += ["", _dated(job["title"], job), _place(job.get("company"), job)]
            lines += [f"- {b}" for b in job.get("bullets") or []]
        blocks["EXPERIENCE"] = [x for x in lines[1:] if x is not None]
    if doc.get("education"):
        lines = []
        for ed in doc["education"]:
            lines += ["", _dated(ed["credential"], ed), _place(ed.get("school"), ed)]
        blocks["EDUCATION"] = [x for x in lines[1:] if x is not None]
    if doc.get("certifications"):
        blocks["CERTIFICATIONS"] = [f"- {c}" for c in doc["certifications"]]
    if doc.get("awards"):
        blocks["AWARDS & VOLUNTEER WORK"] = [f"- {a}" for a in doc["awards"]]
    projects = [p for p in doc.get("projects") or []
                if stage != "experienced" or p.get("own")][:MAX_PROJECTS[stage]]
    if projects:
        lines = []
        for p in projects:
            lines += ["", f"### {p['name']}"] + ([p["detail"]] if p.get("detail") else []) \
                + [f"- {b}" for b in p.get("bullets") or []]
        blocks["PROJECTS"] = lines[1:]

    out = [f"# {info.get('name') or 'Resume'}", *header_lines(info)]
    for section in ORDER[stage]:
        if section in blocks:
            heading = (projects_heading(stage, doc.get("industry", ""))
                       if section == "PROJECTS" else section)
            out += ["", f"## {heading}", *blocks[section]]
    return "\n".join(out).strip() + "\n"
