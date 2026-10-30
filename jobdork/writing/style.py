"""
jobdork.writing.style
=====================
How a resume's lines are written: the rules a recruiter reads a bullet by,
checked by script.

The rules and their weights follow Resume Matcher's writing check
(github.com/srbhr/resume-matcher, Apache-2.0, services/writing_quality.py),
rewritten for jobdork's Markdown and for resumes read from a file. Long
dashes and stock AI phrases are left to the checks every draft already gets
(writing/gates.py), so they are not counted twice.

- **weak opener** (hard): a bullet that starts "Responsible for", "Helped
  with", "Worked on": it says the person was near the work, not what they did;
- **first person** (soft): "I", "my", "me" (a resume is written without them);
- **long bullet** (soft): over 35 words, more than two lines;
- **repeated opener** (soft): three or more bullets of one job starting with
  the same word, each after the first;
- **no figure** (soft, lighter): a bullet with no number, where a result
  could be measured.

Each line scores 100, less 40 for a hard finding, 10 for a soft one and 5
for no figure; the score is the mean. English only: the rules are English
words, so a resume in another language is not scored by them.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

WEAK_OPENERS = ("responsible for", "helped with", "helped to", "helped", "assisted with",
                "assisted in", "assisted", "involved in", "participated in", "worked on",
                "tasked with", "duties included", "duties include", "in charge of")
_WEAK = re.compile(r"^\W*(?:" + "|".join(re.escape(o) for o in WEAK_OPENERS) + r")\b",
                   re.IGNORECASE)
_FIRST_PERSON = re.compile(r"\bI\b|\b(?i:me|my|mine|myself)\b")
_DIGIT = re.compile(r"\d")
_WORD = re.compile(r"[^\W_][\w+#./&-]*")
_BULLET = re.compile(r"^\s*(?:[-*•●▪◦‣·]|\d+[.)])\s+")
_ENGLISH = re.compile(r"\b(?:the|and|with|for|of|to|in)\b", re.IGNORECASE)
LONG_BULLET_WORDS = 35
REPEATED_OPENER = 3
HARD, SOFT, NO_FIGURE = 40, 10, 5

RULES = {
    "weak_opener": ("hard", "Starts by saying you were near the work",
                    "Start with what you did: \"Led\", \"Built\", \"Cut\", \"Trained\"."),
    "first_person": ("soft", "Written in the first person",
                     "Leave out \"I\" and \"my\": \"Led a team of eight\", not \"I led my team\"."),
    "long_bullet": ("soft", f"Over {LONG_BULLET_WORDS} words",
                    "Keep a bullet to two lines: one action and its result."),
    "repeated_opener": ("soft", "Same first word as other bullets of this job",
                        "Vary the opening verbs so each bullet reads as its own."),
    "no_figure": ("soft", "No figure",
                  "Where the result can be counted (people, time, money, percent), say how much."),
}


@dataclass
class Finding:
    rule: str
    severity: str
    line: str                      # the line, shortened

    @property
    def title(self) -> str:
        return RULES[self.rule][1]

    @property
    def advice(self) -> str:
        return RULES[self.rule][2]


@dataclass
class Report:
    score: int | None              # None when there is nothing to score
    lines: int = 0
    findings: list[Finding] = field(default_factory=list)
    note: str = ""                 # why it was not scored

    @property
    def hard(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "hard"]

    def to_dict(self) -> dict:
        return {"score": self.score, "lines": self.lines, "note": self.note,
                "findings": [{**asdict(f), "title": f.title, "advice": f.advice}
                             for f in self.findings]}


def _short(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def units_markdown(markdown: str) -> list[tuple[str, str, bool]]:
    """(group, text, is_bullet) from the resume template's Markdown: the
    summary's paragraph, and each bullet, grouped by the job it is under."""
    out, section, group = [], "", ""
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section, group = line[3:].strip().upper(), line[3:].strip()
        elif line.startswith("### "):
            group = line[4:].split("\t")[0].strip()
        elif line.startswith("- ") and section not in ("SKILLS", "CERTIFICATIONS"):
            out.append((group, line[2:].strip(), True))
        elif line and section == "PROFESSIONAL SUMMARY":
            out.append(("summary", line, False))
    return out


def units_text(text: str) -> list[tuple[str, str, bool]]:
    """Bullets from a resume read from a file. With bullet marks, each marked
    line, a run of them a group. A PDF's bullets are usually drawn shapes and
    come out as nothing, so without marks: the lines of the Experience section
    long enough to be a sentence, a dated line (a job's heading) starting the
    next group. A line wrapped onto the next is joined back either way."""
    from ..search.readable import HEADINGS

    lines = text.splitlines()
    if sum(1 for ln in lines if _BULLET.match(ln)) >= 3:
        out, group, last = [], 0, None
        for raw in lines:
            if _BULLET.match(raw):
                if last is None:
                    group += 1
                last = [str(group), _BULLET.sub("", raw).strip(), True]
                out.append(last)
            elif raw.strip() and last is not None and raw.strip()[:1].islower():
                last[1] += " " + raw.strip()
            else:
                last = None
        return [tuple(u) for u in out if u[1]]

    def heading(line: str) -> str:
        low = line.strip(" :•|*#-\t").lower()
        if len(low.split()) > 6:
            return ""
        return next((k for k, names in HEADINGS.items()
                     if any(low == n or low == n + "s" for n in names)), "other"
                    if low and low.upper() == line.strip(" :•|*#-\t").upper()
                    and line.strip().isupper() else "")

    out, group, inside, last = [], 0, False, None
    for raw in lines:
        line = raw.strip()
        if not line:
            last = None
            continue
        kind = heading(line)
        if kind:
            inside, last = kind == "experience", None
            continue
        if not inside:
            continue
        if re.search(r"\b(?:19|20)\d\d\b", line) and len(line.split()) <= 12:
            group, last = group + 1, None              # a job's heading or its dates
        elif last is not None and line[:1].islower():
            last[1] += " " + line
        elif len(line.split()) >= 6:
            last = [str(group), line, True]
            out.append(last)
        else:
            last = None
    return [tuple(u) for u in out]


def check(units: list[tuple[str, str, bool]]) -> Report:
    if len(units) < 3:
        return Report(None, lines=len(units), note="too few bullets found to check")
    if len(_ENGLISH.findall(" ".join(t for _, t, _ in units))) < max(3, len(units) // 3):
        return Report(None, lines=len(units), note="not in English: these rules are English")
    findings: list[tuple[int, Finding]] = []
    openers: dict[str, dict[str, list[int]]] = {}
    for n, (group, text, bullet) in enumerate(units):
        def add(rule, n=n, text=text):
            findings.append((n, Finding(rule, RULES[rule][0], _short(text))))
        if bullet and _WEAK.search(text):
            add("weak_opener")
        if _FIRST_PERSON.search(text):
            add("first_person")
        if bullet and len(text.split()) > LONG_BULLET_WORDS:
            add("long_bullet")
        if bullet and not _DIGIT.search(text):
            add("no_figure")
        if bullet and (word := _WORD.search(text)):
            openers.setdefault(group, {}).setdefault(word.group(0).casefold(), []).append(n)
    for by_word in openers.values():
        for lines in by_word.values():
            if len(lines) >= REPEATED_OPENER:
                findings += [(n, Finding("repeated_opener", "soft", _short(units[n][1])))
                             for n in lines[1:]]
    penalty = [0] * len(units)
    for n, f in findings:
        penalty[n] += HARD if f.severity == "hard" else NO_FIGURE if f.rule == "no_figure" else SOFT
    score = round(sum(max(0, 100 - p) for p in penalty) / len(units))
    order = {"weak_opener": 0, "first_person": 1, "long_bullet": 2, "repeated_opener": 3,
             "no_figure": 4}
    # lambda: hard rules first, then the rest, each in the resume's order.
    findings.sort(key=lambda nf: (order[nf[1].rule], nf[0]))
    return Report(score, len(units), [f for _, f in findings])


def check_markdown(markdown: str) -> Report:
    return check(units_markdown(markdown))


def check_text(text: str) -> Report:
    return check(units_text(text))
