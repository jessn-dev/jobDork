"""
jobdork.search.master
=====================
A master resume or the resume you send: which one was uploaded.

A master resume is a private archive: every job, project, award,
certification and bullet point, never sent as it is. Tailored one- and
two-page resumes are cut from it for each job post (ai/writer.py already
writes them that way). The resume you send is one of those, or the only one
there is. jobdork uses either; the master gives the AI more true facts to
work from, and so fewer claims it cannot back.

The guess is by script. "master" in the file's name decides it. Otherwise
it takes a lot of text, since many resumes people send run to three to five
pages (a CV in much of the world, a pharmacist's, a designed one with little
text on each page): a long text counts most, and three pages or more, many
dated entries and sections an archive keeps (volunteer work, awards,
presentations, publications) add to it. You can always say which it is
(config `resume.kind`); the guess only fills in until you do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MASTER, REGULAR = "master", "regular"
KINDS = (MASTER, REGULAR)

# Sections an archive keeps and a sent resume usually trims, as headings on a
# line of their own.
_ARCHIVE = re.compile(
    r"^[ \t•*#\-]*(volunteer(?:ing| work| experience)?|awards?(?: and \w+)?|honou?rs|"
    r"presentations?|publications?|speaking|talks|conferences?|freelance(?: work)?|"
    r"part[- ]time(?: work| experience| jobs?)?|(?:hard|soft) skills|"
    r"patents?|community(?: involvement| service)?|achievements?|"
    r"professional development|additional experience|other experience)[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE)
_NAMED = re.compile(r"(?:^|[^a-z])master(?:[^a-z]|$)", re.IGNORECASE)
# Tried on eight real resumes (2026-11-05): a 1,849-word master, and sent
# ones of 290 to 1,566 words over two to five pages.
LONG_WORDS = 1_700
MANY_DATED = 10
MASTER_POINTS = 3


@dataclass
class Guess:
    kind: str                                  # MASTER or REGULAR
    why: list[str] = field(default_factory=list)


def guess(text: str, pages: int | None = None, filename: str = "") -> Guess:
    """Master or regular, and the reasons, from the resume's text, its page
    count (None for Markdown and plain text) and the name it was uploaded
    under."""
    from .resume import _SPAN

    # "MasterResumeJaneDoe" as "Master Resume Jane Doe"; "Mastercard" stays one word.
    named = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", Path(filename or "").stem).replace("_", " ")
    if filename and _NAMED.search(named):
        return Guess(MASTER, ["its file name says master"])
    text = text or ""
    words = len(text.split())
    points, why = 0, []
    if words >= LONG_WORDS:
        points += 2
        why.append(f"{words:,} words")
    if pages and pages >= 3:
        points += 1
        why.append(f"{pages} pages")
    dated = len(_SPAN.findall(text))
    if dated >= MANY_DATED:
        points += 1
        why.append(f"{dated} dated entries")
    kept = sorted({m.group(1).strip().lower() for m in _ARCHIVE.finditer(text)})
    if len(kept) >= 2:
        points += 1
        why.append("sections such as " + " and ".join(kept[:2]))
    return Guess(MASTER if points >= MASTER_POINTS else REGULAR, why)


def kind_of(chosen: str, text: str, pages: int | None = None, filename: str = "") -> str:
    """What jobdork treats the resume as: your choice when you made one,
    the guess otherwise."""
    return chosen if chosen in KINDS else guess(text, pages, filename).kind
