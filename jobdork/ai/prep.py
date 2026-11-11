"""
jobdork.ai.prep
===============
Writing and preparing beyond the letter, by the AI-page model: for one job
post, a tailoring report, a story for an interview question, a thank-you
email, help with an offer and an outreach message; from the resume alone, a
LinkedIn headline and About section, a career-change positioning and a
30-day search plan.

Asked for on 2026-11-09 from a pack of job-search prompts; the ideas and the
shape of each answer come from there, the prompts are jobdork's own.

Each is held to the rules every AI output here is:

  **Facts from the sources only.** What it says about you comes from your
  resume or what you typed into the tool's form, nothing else; the advert is
  a claim about the job. A script checks what it can (a quote must be in the
  resume, a message must fit its limit, no stock phrases), and lists what it
  finds as "Read this".

  **Checked.** Everything but the plan (advice, not claims about you) goes
  through the hallucination check against the resume, the advert and your
  own notes, and is recorded in `ai_outputs`, so the Dashboard counts it.

  **Data, not instructions.** The advert is fenced as in llm.py, and so is
  what you type: a pasted interview note cannot talk to the model either.

Nothing is sent anywhere. A post's result is kept in its folder and listed
with its documents; the others are kept beside the resume.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..core import telemetry
from ..writing import humanize
from ..writing.gates import STOCK  # one list of stock phrases, the cover letter's too
from . import guard
from .llm import MAX_ADVERT, MAX_RESUME, LLMError, Settings, _fenced, complete_json
from .tools import _DATA, _FACTS
from .writer import OFF, _advert, _role_header

# ── the forms' fields ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    most: int = 600
    required: bool = False
    long: bool = False                 # a text area on the page, not one line
    hint: str = ""




def stock_phrases(text: str) -> list[str]:
    low = (text or "").lower()
    return [p for p in STOCK if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", low)]


def words(text: str) -> int:
    return len(re.findall(r"\b[\w'’-]+\b", text or ""))


# ── what one tool is ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Spec:
    kind: str
    label: str
    post: bool                         # for one job post, or from the resume alone
    fields: tuple[Field, ...]
    system: str
    schema: dict
    render: Callable[[dict], str]      # markdown, shown and checked
    guarded: bool = True               # advice with no claims about you is not
    copy: tuple[str, ...] = ()         # fields the page offers to copy
    blurb: str = ""


def _str(schema_props: dict) -> dict:
    return {"type": "object", "properties": schema_props,
            "required": list(schema_props), "additionalProperties": False}


S = {"type": "string"}
SL = {"type": "array", "items": S}


def _obj_list(**props) -> dict:
    return {"type": "array", "items": _str(dict.fromkeys(props, S))}


def _list(items) -> str:
    return "\n".join(f"- {x}" for x in items if str(x).strip())


# ── for one job post ──────────────────────────────────────────────────────────

def _render_tailoring(d: dict) -> str:
    return "\n\n".join(x for x in (
        "## What the advert stresses most\n" + _list(d.get("top_five", [])),
        "## Each requirement\n" + "\n".join(
            f"- {'✓' if r.get('have') == 'yes' else '✗'} **{r.get('requirement')}**"
            + (f": \"{r.get('evidence')}\"" if r.get("evidence") else "")
            for r in d.get("requirements", [])),
        ("## What you lack, and how to handle it\n" + "\n".join(
            f"- **{m.get('requirement')}**: {m.get('how_to_handle')}"
            for m in d.get("missing", []))) if d.get("missing") else "",
        ("## What to prepare for\n" + "\n".join(
            f"- **{f.get('flag')}**: {f.get('how_to_prepare')}"
            for f in d.get("red_flags", []))) if d.get("red_flags") else "",
        f"## Lead with\n{d.get('angle', '')}" if d.get("angle") else "") if x)


TAILORING = Spec(
    kind="prep_tailoring", label="Tailoring report", post=True, fields=(),
    blurb="What the advert stresses, what your resume shows for each, what to "
          "prepare for, and how to handle a requirement you lack.",
    system=f"""You read one job advert against one resume, as a recruiter and \
an applicant tracking system would, and report what the advert asks for and \
what the resume shows for it.

"requirements": each skill, qualification or duty the advert asks for, as \
the advert words it, at most 15, most emphasised first ("emphasis" 1 to 5: \
said once is 1, repeated, required or first is 5). "have" is "yes" only when \
"evidence" quotes the resume's own words that show it, else "no" with \
"evidence" empty. "top_five": the five the advert stresses most, as worded \
there. "missing": each required item the resume lacks, with \
"how_to_handle": a related skill the resume does show, being willing to \
learn it, or saying plainly it is a gap; never pretend. "red_flags": what a \
recruiter may question (a gap in the dates, too senior or too junior, a \
change of field), each with "how_to_prepare". "angle": one sentence on what \
a summary at the top of the resume should lead with, from the resume only.

{_DATA} {_FACTS}""",
    schema=_str({
        "requirements": {"type": "array", "items": {
            "type": "object", "properties": {"requirement": S, "emphasis": {"type": "integer"},
                                             "have": {"type": "string", "enum": ["yes", "no"]},
                                             "evidence": S},
            "required": ["requirement", "emphasis", "have", "evidence"],
            "additionalProperties": False}},
        "top_five": SL, "missing": _obj_list(requirement=1, how_to_handle=1),
        "red_flags": _obj_list(flag=1, how_to_prepare=1), "angle": S}),
    render=_render_tailoring,
)


def _tailoring_checks(data: dict, resume: str, given: dict) -> list[str]:
    """A "yes" must quote the resume; one that does not is turned to "no"."""
    out = []
    low = " ".join(resume.lower().split())
    for r in data.get("requirements", []):
        ev = " ".join(str(r.get("evidence") or "").lower().split())
        if r.get("have") == "yes" and (not ev or ev not in low):
            r["have"], r["evidence"] = "no", ""
            out.append(f"\"{r.get('requirement')}\" was marked as yours with no words of "
                       "your resume to show it: turned to missing")
    return out


def _render_star(d: dict) -> str:
    return "\n\n".join(x for x in (
        f"**Situation.** {d.get('situation', '')}", f"**Task.** {d.get('task', '')}",
        f"**Action.** {d.get('action', '')}", f"**Result.** {d.get('result', '')}",
        f"## Said aloud\n{d.get('tailored', '')}",
        "## They may ask next\n" + "\n".join(
            f"- **{f.get('question')}** {f.get('answer')}" for f in d.get("follow_ups", [])),
        ("## Read this before you use it\n" + _list(d.get("red_flags", [])))
        if d.get("red_flags") else "") if x)

STAR = Spec(
    kind="prep_star", label="Interview story (STAR)", post=True,
    blurb="Turns what happened, in your words, into a 60 to 90 second answer: "
          "situation, task, action, result.",
    fields=(Field("question", "The question", 300, True,
                  hint="e.g. Tell me about a time you handled a conflict"),
            Field("story", "What happened, in your words", 2_000, True, True,
                  hint="Three to five sentences: who, what, what you did, how it ended"),
            Field("wants", "What you think they want to hear (optional)", 300)),
    system=f"""You coach one person to answer one interview question with a \
story of their own, in the situation, task, action, result shape (STAR).

From <<YOUR NOTES>> only (the story is theirs; the resume may add a title or \
a date): "situation" two sentences at most, "task" one, "action" three or \
four in the first person ("I", never "we"), the longest part, "result" one \
or two with a number only if the story gives one, else what they learned. \
"tailored": the same answer in 150 to 220 words, said aloud in 60 to 90 \
seconds, leaning on what the job post asks for. "follow_ups": three \
questions an interviewer may ask next, each with a short answer from the \
story. "red_flags": anything in the story that could sound like blaming \
others, poor judgement or a conflict left open, and how to reword it; empty \
when there is none.

{_DATA} {_FACTS}""",
    schema=_str({"situation": S, "task": S, "action": S, "result": S, "tailored": S,
                 "follow_ups": _obj_list(question=1, answer=1), "red_flags": SL}),
    render=_render_star,
    copy=("tailored",),
)


def _star_checks(data: dict, resume: str, given: dict) -> list[str]:
    out = []
    spoken = words(data.get("tailored", ""))
    if spoken and not 120 <= spoken <= 240:
        out.append(f"the answer said aloud is {spoken} words: about {round(spoken / 2.5)} "
                   "seconds, outside 60 to 90")
    parts = {k: words(data.get(k, "")) for k in ("situation", "task", "action", "result")}
    if sum(parts.values()) and parts["action"] / sum(parts.values()) < 0.4:
        out.append("the action is less than half the story: say more of what you did")
    if re.search(r"\bwe\b", data.get("action", ""), re.IGNORECASE):
        out.append("the action says \"we\": say what you did")
    return out


def _render_thank_you(d: dict) -> str:
    return (f"**Subject:** {d.get('subject', '')}\n\n{d.get('body', '')}"
                      + (f"\n\n*{d.get('note')}*" if d.get("one_each") == "yes" and d.get("note")
                         else ""))

THANK_YOU = Spec(
    kind="prep_thank_you", label="Thank-you email", post=True,
    blurb="Sent within a day of the interview: specific to what you talked about.",
    fields=(Field("interviewers", "Who interviewed you", 300, True,
                  hint="Names and roles, e.g. Dana Brooks, unit manager"),
            Field("when", "When", 60, hint="e.g. Tuesday"),
            Field("discussed", "Something specific you talked about", 600, True, True),
            Field("clarify", "Something you wish you had said better (optional)", 600, False, True),
            Field("concern", "A concern they raised about your fit (optional)", 600, False, True)),
    system=f"""You write one thank-you email after a job interview, to be \
sent within a day.

"subject": specific to the conversation, never "Thank you for your time". \
"body": 150 to 200 words: one sentence of thanks naming something specific \
from <<YOUR NOTES>>; two or three linking what was discussed to what the \
person would do in this job, from the resume; when a concern is given, one \
or two answering it from the resume; one sentence of continued interest and \
the next step. Plain and warm, not effusive. "one_each": "yes" when \
several people interviewed and each should get their own version, with \
"note" saying what to change in each; otherwise "no".

{_DATA} {_FACTS} Never write "I really enjoyed learning about the role" or \
any line that could follow any interview.""",
    schema=_str({"subject": S, "body": S, "one_each": {"type": "string", "enum": ["yes", "no"]},
                 "note": S}),
    render=_render_thank_you,
    copy=("subject", "body"),
)


def _thank_checks(data: dict, resume: str, given: dict) -> list[str]:
    n = words(data.get("body", ""))
    return ([f"the email is {n} words; aim for 150 to 200"] if n and not 120 <= n <= 230 else [])


def _render_offer(d: dict) -> str:
    return "\n\n".join(x for x in (
        f"## Say this\n{d.get('opening', '')}",
        "## Why you are worth it\n" + _list(d.get("talking_points", [])),
        "## If they say\n" + "\n".join(f"- **{o.get('objection')}** {o.get('reply')}"
                                       for o in d.get("objections", [])),
        "## If the salary cannot move\n" + _list(d.get("beyond_salary", [])),
        f"## Your minimum\n{d.get('walk_away', '')}", f"## Silence\n{d.get('silence', '')}")
        if x)

OFFER = Spec(
    kind="prep_offer", label="Offer negotiation", post=True,
    blurb="Words for countering an offer: firm, grateful, and never an ultimatum.",
    fields=(Field("offered", "What they offered", 200, True, hint="e.g. 92,000 a year"),
            Field("target", "What you want", 200, True, hint="e.g. 105,000"),
            Field("market", "What the market pays, and where you read it (optional)", 400),
            Field("strengths", "Your strongest points (optional)", 800, False, True,
                  hint="Years, results, another offer"),
            Field("flexible", "What else you would take (optional)", 400,
                  hint="Signing bonus, equity, days off, remote work, title")),
    system=f"""You coach one person to negotiate one job offer: firm and \
collaborative, grateful and professional.

"opening": the exact words to counter with, in their own voice, naming the \
figure they want and why in one breath; never "I was hoping for more". \
"talking_points": three or four, each tied to the market figure given, to \
something the resume shows, or to what the job asks. "objections": replies \
to "This is the most for this level", "We can look again in six months", \
"We have internal pay bands" and "The budget is fixed". "beyond_salary": \
what to ask for instead when the salary cannot move, best first, from what \
they said they would take. "walk_away": how to settle their true minimum \
before the call. "silence": where to stop talking and let the offer sit.

{_DATA} {_FACTS} Never suggest an ultimatum or a threat, and never invent \
another offer or a market figure they did not give.""",
    schema=_str({"opening": S, "talking_points": SL,
                 "objections": _obj_list(objection=1, reply=1), "beyond_salary": SL,
                 "walk_away": S, "silence": S}),
    render=_render_offer,
    copy=("opening",),
)


def _render_outreach(d: dict) -> str:
    return "\n\n".join(x for x in (
        f"## Connection request\n{d.get('connection_request', '')}",
        f"## InMail\n{d.get('inmail', '')}", f"## A week later\n{d.get('follow_up', '')}",
        "## If they say yes\n" + _list(d.get("call_topics", []))) if x)

OUTREACH = Spec(
    kind="prep_outreach", label="Outreach message", post=True,
    blurb="A short, specific note to someone at the employer, with a small ask "
          "and an easy way to say no.",
    fields=(Field("person", "Their role", 200, True, hint="e.g. Charge nurse on the ICU"),
            Field("found", "How you found them", 200, hint="e.g. a talk they gave, a mutual contact"),
            Field("ask", "The one thing you want to learn", 400, True, True),
            Field("shared", "Something you share (optional)", 200,
                  hint="A school, a past employer, an interest")),
    system=f"""You write a cold message on LinkedIn to one person who works \
at the employer of this job post.

"connection_request": under 300 characters. "inmail": under 500. Each: why \
this person, specifically (not flattery); one line on who the sender is, \
from the resume; one small, specific ask ("I have one question about…"); \
an easy way to decline. Never mention looking for a job, applying or this \
opening in either; never "pick your brain". "follow_up": a short note for \
a week later if there is no reply. "call_topics": three or four things to \
be ready to talk about if they say yes.

{_DATA} {_FACTS}""",
    schema=_str({"connection_request": S, "inmail": S, "follow_up": S, "call_topics": SL}),
    render=_render_outreach,
    copy=("connection_request", "inmail", "follow_up"),
)

_JOB_WORDS = re.compile(r"\b(?:job|jobs|hiring|hire|opening|position|vacanc\w*|apply|applying|"
                        r"application|role)\b", re.IGNORECASE)


def _outreach_checks(data: dict, resume: str, given: dict) -> list[str]:
    out = []
    for key, most in (("connection_request", 300), ("inmail", 500)):
        n = len(data.get(key, ""))
        if n > most:
            out.append(f"the {key.replace('_', ' ')} is {n} characters; LinkedIn allows {most}")
        if _JOB_WORDS.search(data.get(key, "")):
            out.append(f"the {key.replace('_', ' ')} mentions a job or applying: leave that out "
                       "of a first message")
    return out


# ── from the resume alone ─────────────────────────────────────────────────────


def _render_linkedin(d: dict) -> str:
    return "\n\n".join(x for x in (
        f"## Headline\n{d.get('headline', '')}", f"## About\n{d.get('about', '')}",
        "## Skills\n" + _list(d.get("skills", [])),
        "## Phrases for your Experience entries\n" + _list(d.get("phrases", [])),
        "## Quick wins\n" + _list(d.get("quick_wins", []))) if x)

LINKEDIN = Spec(
    kind="prep_linkedin", label="LinkedIn headline and About", post=False,
    blurb="Text for you to copy into your LinkedIn profile: jobdork never logs "
          "into LinkedIn or posts there.",
    fields=(Field("target", "The job you want", 200, True, hint="e.g. ICU charge nurse"),
            Field("headline", "Your headline now (optional)", 300),
            Field("about", "Your About section now (optional)", 2_600, False, True),
            Field("aim", "Fields or employers you aim for (optional)", 300)),
    system=f"""You write one person's LinkedIn headline and About section, \
so recruiters searching for their target job find them and want to read on.

"headline": at most 220 characters: the target job's words, what they \
offer, their speciality; never "seeking opportunities" or a job title \
alone. "about": about 1,500 characters, never more than 2,600, in the first \
person: who they help and how; two or three achievements from the resume, \
with its numbers only; what they know, in the words recruiters search for; \
a line inviting contact. "skills": ten for the Skills section, each one \
the resume shows. "phrases": five to work into the Experience entries. \
"quick_wins": three or four small things (photo, a custom address, the \
Featured section).

{_DATA} {_FACTS} No buzzwords: every word says something about this \
person.""",
    schema=_str({"headline": S, "about": S, "skills": SL, "phrases": SL, "quick_wins": SL}),
    render=_render_linkedin,
    copy=("headline", "about"),
)


def _linkedin_checks(data: dict, resume: str, given: dict) -> list[str]:
    out = []
    if len(data.get("headline", "")) > 220:
        out.append(f"the headline is {len(data['headline'])} characters; LinkedIn allows 220")
    if len(data.get("about", "")) > 2_600:
        out.append(f"the About section is {len(data['about'])} characters; LinkedIn allows 2,600")
    low = resume.lower()
    missing = [s for s in data.get("skills", []) if s and s.lower() not in low]
    if missing:
        data["skills"] = [s for s in data.get("skills", []) if s not in missing]
        out.append("left out of the skills, not on your resume: " + ", ".join(missing))
    return out


def _render_pivot(d: dict) -> str:
    return "\n\n".join(x for x in (
        "## What carries over\n" + "\n".join(
            f"- {m.get('experience')} → {m.get('translates')} (*{m.get('their_words')}*)"
            for m in d.get("mapping", [])),
        f"## In 30 seconds\n{d.get('pitch_30s', '')}", f"## In 2 minutes\n{d.get('pitch_2min', '')}",
        "## Gaps\n" + "\n".join(f"- **{g.get('gap')}**{' (employers screen for it)' if g.get('matters') == 'yes' else ''}: {g.get('how')}"
                                for g in d.get("gaps", [])),
        f"## Positioning\n{d.get('positioning', '')}",
        "## If they ask\n" + "\n".join(f"- **{o.get('question')}** {o.get('answer')}"
                                       for o in d.get("objections", []))) if x)

PIVOT = Spec(
    kind="prep_pivot", label="Changing field", post=False,
    blurb="How your background carries over to a new field, honestly: what "
          "translates, what is a real gap, and how to say it.",
    fields=(Field("target", "The field you are moving to", 200, True, hint="e.g. health informatics"),
            Field("role", "The kind of job there (optional)", 200),
            Field("why", "Why you are moving (optional)", 600, False, True)),
    system=f"""You help one person move from the field their resume is in to \
a new one, honestly.

"mapping": five to seven rows: "experience" from the resume, "translates" \
how it carries over, "their_words" what the new field calls it. \
"pitch_30s" and "pitch_2min": why the move, without sounding like running \
from the old field. "gaps": what they lack, each with "how" (a course, a \
project, a certificate) and "matters" ("yes" when employers screen for it, \
"no" when it can be worked around). "positioning": one paragraph for a \
resume summary or LinkedIn that makes the move a strength. "objections": \
answers to "Why you over someone with direct experience?" and "What if you \
go back?". Be plain about what does not translate.

{_DATA} {_FACTS}""",
    schema=_str({"mapping": _obj_list(experience=1, translates=1, their_words=1),
                 "pitch_30s": S, "pitch_2min": S,
                 "gaps": {"type": "array", "items": _str({"gap": S, "how": S, "matters": {
                     "type": "string", "enum": ["yes", "no"]}})},
                 "positioning": S, "objections": _obj_list(question=1, answer=1)}),
    render=_render_pivot,
    copy=("positioning",),
)


def _render_plan(d: dict) -> str:
    return "\n\n".join(x for x in (
        "\n\n".join(f"## {w.get('week')}: {w.get('focus')}\n" + _list(w.get("actions", []))
                    for w in d.get("weeks", [])),
        "## A day\n" + "\n".join(f"- **{b.get('block')}** ({b.get('minutes')} min): {b.get('what')}"
                                 for b in d.get("daily", [])),
        "## Each week, count\n" + "\n".join(f"- {t.get('what')}: {t.get('per_week')}"
                                            for t in d.get("targets", [])),
        "## Your tracking sheet\n" + _list(d.get("tracking", [])),
        "## Look after yourself\n" + _list(d.get("energy", []))) if x)


PLAN = Spec(
    kind="prep_plan", label="30-day search plan", post=False, guarded=False,
    blurb="A month of job search sized to the hours you have: weekly focus, "
          "daily blocks, targets you can count, and rest.",
    fields=(Field("target", "The job you want", 200, True),
            Field("status", "Where you are now", 100, True, hint="Working, not working, studying"),
            Field("hours", "Hours a week you can give it", 10, True, hint="e.g. 10"),
            Field("challenge", "Your biggest hurdle (optional)", 300,
                  hint="e.g. applications get no answer"),
            Field("resources", "What you have to help (optional)", 300)),
    system=f"""You plan one person's next 30 days of job search, sized to the \
hours a week they give.

"weeks": four, each with "focus" and three to five specific "actions" \
(not "work on applications"): build the base, reach out, fill the \
pipeline, sharpen and keep going. "daily": the time blocks of a typical \
day, "minutes" each, whose week adds up to their hours and no more: \
tailored applications, outreach, interview practice, and skills only if \
the hurdle calls for it. "targets": what to count each week (tailored \
applications, conversations, follow-ups), few and tailored over many and \
generic. "tracking": the columns of a simple sheet. "energy": how to take \
a rejection, when to rest, the signs of burning out.

{_DATA}""",
    schema=_str({"weeks": {"type": "array", "items": _str({"week": S, "focus": S, "actions": SL})},
                 "daily": {"type": "array", "items": _str({"block": S, "minutes": {"type": "integer"},
                                                           "what": S})},
                 "targets": {"type": "array", "items": _str({"what": S, "per_week": {"type": "integer"}})},
                 "tracking": SL, "energy": SL}),
    render=_render_plan,
)


def _plan_checks(data: dict, resume: str, given: dict) -> list[str]:
    try:
        hours = float(re.sub(r"[^\d.]", "", given.get("hours", "")) or 0)
    except ValueError:
        return []
    per_day = sum(int(b.get("minutes") or 0) for b in data.get("daily", []))
    if hours and per_day * 5 > hours * 60 * 1.15:
        return [f"a day here is {per_day} minutes, about {per_day * 5 / 60:.0f} hours over "
                f"five days: more than the {hours:g} you have"]
    return []


SPECS: dict[str, Spec] = {s.kind: s for s in
                          (TAILORING, STAR, THANK_YOU, OFFER, OUTREACH, LINKEDIN, PIVOT, PLAN)}

# The script checks each tool's answer gets: they put right what they can
# (a skill not on the resume left out) and say what they find.
CHECKS = {"prep_tailoring": _tailoring_checks, "prep_star": _star_checks,
          "prep_thank_you": _thank_checks, "prep_outreach": _outreach_checks,
          "prep_linkedin": _linkedin_checks, "prep_plan": _plan_checks}


# ── running one ───────────────────────────────────────────────────────────────


@dataclass
class PrepResult:
    kind: str
    data: dict = field(default_factory=dict)
    text: str = ""                     # markdown, shown and checked
    given: dict = field(default_factory=dict)
    guard: guard.GuardReport = field(default_factory=guard.GuardReport)
    problems: list[str] = field(default_factory=list)
    tells: int = 0
    at: str = ""

    def to_dict(self) -> dict:
        spec = SPECS[self.kind]
        return {"kind": self.kind, "label": spec.label, "data": self.data, "text": self.text,
                "given": self.given, "guard": self.guard.to_dict(), "problems": self.problems,
                "tells": self.tells, "at": self.at, "copy": list(spec.copy)}


def form_fields(kind: str, given: dict) -> dict:
    """What the tool's form sent, cut to its fields and their lengths;
    LLMError naming a required one left empty."""
    spec = SPECS.get(kind)
    if spec is None:
        raise LLMError(f"no tool called {kind!r}")
    out = {}
    for f in spec.fields:
        value = re.sub(r"[ \t]+", " ", str(given.get(f.name) or "")).strip()[:f.most]
        if f.required and not value:
            raise LLMError(f"give {f.label.lower()}")
        out[f.name] = value
    return out


# Any block marker in what you typed, taken out before it is fenced: a
# pasted note cannot close <<YOUR NOTES>> and talk on as instructions.
_MARKER = re.compile(r"<{2,}\s*/?\s*[A-Za-z][A-Za-z ]{0,30}\s*>{2,}")


def _notes(spec: Spec, given: dict) -> str:
    return "\n".join(f"{f.label}: {_MARKER.sub(' ', given[f.name])}"
                     for f in spec.fields if given.get(f.name))


def _clean_data(value, limit: int = 3_000):
    """Every string a model wrote, humanized and clipped; structure kept."""
    if isinstance(value, str):
        return humanize.clean(re.sub(r"[ \t]+", " ", value).strip()[:limit], keep_quotes=True)
    if isinstance(value, list):
        return [_clean_data(v, limit) for v in value[:20]]
    if isinstance(value, dict):
        return {k: _clean_data(v, limit) for k, v in value.items()}
    return value


def write(settings: Settings, kind: str, resume_text: str, given: dict, row=None,
          check: bool = True) -> PrepResult:
    """One tool's answer, cleaned, script-checked and guarded. Writes nothing."""
    spec = SPECS[kind]
    if not resume_text:
        raise LLMError("no resume loaded. Upload one on the Resume page")
    if spec.post and row is None:
        raise LLMError("this one is for a job post: open the post first")
    telemetry.tick(total=2)
    notes = _notes(spec, given)
    user = ((_role_header(row) + _fenced("ADVERT", _advert(row), MAX_ADVERT) + "\n\n")
            if spec.post else "")
    user += _fenced("RESUME", resume_text, MAX_RESUME)
    if notes:
        user += "\n\n" + _fenced("YOUR NOTES", notes, 6_000)
    raw = complete_json(settings, spec.system, user, spec.schema, max_tokens=3_000,
                        purpose=kind)
    data = _clean_data(raw if isinstance(raw, dict) else {})
    result = PrepResult(kind=kind, given=given, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    check_it = CHECKS.get(kind)
    result.problems = check_it(data, resume_text, given) if check_it else []
    result.data = data
    # A section the model gave nothing for is left out, heading and all.
    result.text = re.sub(r"(?m)^## [^\n]+\n(?=\s*(?:## |\Z))", "", spec.render(data)).strip()
    if not result.text:
        raise LLMError("the model gave an empty answer")
    stock = stock_phrases(result.text)
    if stock:
        result.problems.append("stock phrases a reader sees through: " + ", ".join(stock))
    result.tells = len(humanize.find(result.text, markdown=True))
    sources = {"resume": resume_text, **({"advert": guard.advert_source(row)} if spec.post else {}),
               **({"your notes": notes} if notes else {})}
    result.guard = (guard.check(settings, result.text, sources)
                    if check and spec.guarded else guard.GuardReport(error=OFF))
    telemetry.tick(done=2)
    return result


def career_dir(cfg) -> Path:
    """Where the tools that need no job post keep their answers."""
    from ..core import storage
    return storage.resume_dir(cfg) / "career"


def run(cfg, store, kind: str, uid: str = "", given: dict | None = None,
        progress=None) -> PrepResult:
    """One tool, saved and recorded: a post's in its folder and as its
    document, the others beside the resume."""
    from ..writing import generate
    from .writer import _resume_text, _row, _settings

    spec = SPECS.get(kind)
    if spec is None:
        raise LLMError(f"no tool called {kind!r}")
    given = form_fields(kind, given or {})
    settings = _settings(cfg)
    row = _row(store, uid) if spec.post else None
    # For a job post with the resume you sent uploaded, that one (writer):
    # a thank-you or a negotiation goes by what the employer has.
    resume_text = _resume_text(cfg, store, uid) if spec.post else _resume_text(cfg)
    if progress:
        progress(f"{settings.label}: {spec.label.lower()}"
                 + (f" for {row['title']} at {row['company']}" if row is not None else ""))
    result = write(settings, kind, resume_text, given, row, check=cfg.llm.guard)
    store.add_ai_output(kind, result.text, uid=uid if spec.post else "",
                        model=(settings.answered or settings).label,
                        guard=result.guard.to_dict(with_pending=True) if spec.guarded else None)
    if spec.post:
        folder = generate.folder_for(row)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{kind.replace('prep_', '')}.json"
        path.write_text(json.dumps(result.to_dict(), indent=1), encoding="utf-8")
        store.add_artifact(uid, kind, str(path))
    else:
        folder = career_dir(cfg)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{kind.replace('prep_', '')}.json").write_text(
            json.dumps(result.to_dict(), indent=1), encoding="utf-8")
    store.conn.commit()
    return result


def latest(cfg, store, uid: str = "") -> dict:
    """The newest answer of each tool: a post's (with `uid`), or the ones
    that need no post."""
    out = {}
    if uid:
        for kind, spec in SPECS.items():
            if not spec.post:
                continue
            row = store.conn.execute(
                "SELECT id, path FROM artifacts WHERE uid = ? AND kind = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 1", (uid, kind)).fetchone()
            if row is not None and Path(row["path"] or "").is_file():
                try:
                    out[kind] = {**json.loads(Path(row["path"]).read_text(encoding="utf-8")),
                                 "id": row["id"]}
                except (OSError, json.JSONDecodeError):
                    continue
    else:
        for kind, spec in SPECS.items():
            path = career_dir(cfg) / f"{kind.replace('prep_', '')}.json"
            if not spec.post and path.is_file():
                try:
                    out[kind] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
    return out


def catalog() -> list[dict]:
    """The tools and their forms, for the page."""
    return [{"kind": s.kind, "label": s.label, "post": s.post, "blurb": s.blurb,
             "fields": [{"name": f.name, "label": f.label, "required": f.required,
                         "long": f.long, "hint": f.hint, "most": f.most} for f in s.fields]}
            for s in SPECS.values()]
