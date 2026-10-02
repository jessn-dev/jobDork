"""
jobdork.search.dealbreakers
===========================
Dealbreakers in plain words: "security clearance", "us citizen",
"client-site travel". Nobody should need a regular expression to say what
they will not do, so a phrase is turned into one here.

A phrase matches the way people write it, not only the way you typed it:

  - capitals never matter, and words may be joined by a space, a hyphen or
    nothing ("client-site travel", "client site travel", "on-call", "oncall");
  - a short word in capitals may have dots ("US" finds "U.S.");
  - the last word may end in s, es, ed, ing or ship ("us citizen" finds
    "U.S. citizenship");
  - it matches whole words only, so "us" never matches inside "focus".

Common dealbreakers come with the other ways adverts say the same thing
(CATALOG): "security clearance" also finds "TS/SCI", "top secret" and
"polygraph". A phrase not in the catalog is matched as written.

**A negation is not a match.** "No security clearance required" and "does not
require a clearance" are the opposite of the dealbreaker, so a match with no,
not, without or never shortly before it in the same sentence is skipped. A
dealbreaker that is itself a negation ("no visa sponsorship") is matched
as written.

A regular expression is still accepted (`pattern:` in config.yaml, Advanced
on the dashboard) for anything the words cannot say.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Common dealbreakers: the name shown, the ways adverts phrase it, and whether
# it usually hides the post. Variants are phrases, matched like your own; a
# variant starting "re:" is a regular expression, for a number ("travel up
# to 50%") that a phrase cannot spell.
@dataclass(frozen=True)
class Known:
    name: str
    variants: tuple[str, ...]
    hard: bool = True


CATALOG: tuple[Known, ...] = (
    Known("Security clearance", (
        "security clearance", "clearance required", "active clearance",
        "secret clearance", "top secret", "TS/SCI", "TS SCI", "polygraph",
        "DoD clearance", "public trust clearance", "clearable")),
    Known("US citizen", (
        "US citizen", "United States citizen", "American citizen",
        "citizen of the United States", "must be a citizen",
        "citizenship required", "citizenship is required")),
    Known("No visa sponsorship", (
        "no visa sponsorship", "no sponsorship", "unable to sponsor",
        "cannot sponsor", "will not sponsor", "not able to sponsor",
        "does not sponsor", "without sponsorship", "sponsorship is not available",
        "not eligible for sponsorship")),
    Known("Client-site travel", (
        "client-site travel", "client site", "travel to client sites",
        "travel to clients", "at client locations", "on-site at client",
        "customer site travel", "travel to customer sites"), hard=False),
    Known("Heavy travel", (
        "extensive travel", "frequent travel", "travel required", "overnight travel",
        r"re:travel(?:ing)? (?:up to |approximately |about )?(?:[3-9]\d|100)\s?%"),
        hard=False),
    Known("Relocation required", (
        "must relocate", "relocation required", "relocation is required",
        "required to relocate", "willing to relocate")),
    Known("On-call", (
        "on call", "on call rotation", "24/7 support", "24x7 support", "pager duty",
        "after hours support"), hard=False),
    Known("Night shift", (
        "night shift", "overnight shift", "graveyard shift", "third shift",
        "3rd shift", "nights required"), hard=False),
    Known("Weekend work", (
        "weekends required", "work weekends", "weekend shifts", "weekend availability",
        "available weekends"), hard=False),
    Known("Fully on-site", (
        "fully on site", "100% on site", "five days in office", "5 days in office",
        "five days a week in office", "in office five days"), hard=False),
    Known("Drug test", (
        "drug test", "drug screen", "drug screening", "drug free workplace"), hard=False),
    Known("Driver's license", (
        "driver's license", "drivers license", "driving licence", "valid license",
        "CDL"), hard=False),
    Known("Heavy lifting", (
        r"re:lift(?:ing)? (?:up to )?(?:[4-9]\d|1\d\d)\s?(?:lbs?|pounds)",
        "heavy lifting"), hard=False),
    Known("Contract or agency", (
        "C2C", "corp to corp", "staffing agency", "staffing firm", "contract to hire",
        "contract position", "1099"), hard=False),
    Known("Commission only", (
        "commission only", "100% commission", "commission based", "quota"), hard=False),
    Known("Unpaid take-home", (
        "take home test", "take home project", "take home assignment",
        "unpaid trial", "unpaid project"), hard=False),
    Known("Bilingual required", (
        "bilingual required", "must be bilingual", "bilingual is required"), hard=False),
)

_NEGATION = re.compile(r"\b(?:no|not|without|never|non|neither|nor)\b|n['’]t\b", re.I)
_SENTENCE_END = re.compile(r"[.!?;\n•]")
_SUFFIX = r"(?:s|es|ed|ing|ship)?"
# Joins between words: nothing, a space, a hyphen, a slash.
_JOIN = r"[\s\-\u2010\u2013/]*"


def _key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


_BY_KEY = {}
for _known in CATALOG:
    for _phrase in (_known.name, *_known.variants):
        if not _phrase.startswith("re:"):
            _BY_KEY.setdefault(_key(_phrase), _known)


def known(phrase: str) -> Known | None:
    """The catalog entry a phrase names, if any ("US citizen" = "us citizen")."""
    return _BY_KEY.get(_key(phrase))


def _word(token: str) -> str:
    """One word of a phrase as a pattern."""
    core = re.sub(r"[^\w'’%&+/]", "", token)
    if re.fullmatch(r"[A-Za-z]{2,3}", core) and core.isupper():
        # US, TS, DoD-style short capitals: each letter may take a dot.
        return "".join(re.escape(c) + r"\.?" for c in core)
    out = []
    for ch in core:
        if ch in "'’":
            out.append("['’]?")
        elif ch == "/":
            out.append(_JOIN)
        else:
            out.append(re.escape(ch))
    return "".join(out)


def phrase_pattern(phrase: str) -> str:
    """A phrase as a regular expression, matched as described above."""
    if phrase.startswith("re:"):
        return phrase[3:]
    tokens = [t for t in re.split(r"[\s\-\u2010\u2013_]+", phrase.strip()) if t]
    words = [w for w in (_word(t) for t in tokens) if w]
    if not words:
        return ""
    words[-1] += _SUFFIX
    return r"(?<![A-Za-z0-9])" + _JOIN.join(words) + r"(?![A-Za-z0-9])"


def expand(words: list[str]) -> list[str]:
    """Your words, each with the catalog's other wordings of it."""
    out: list[str] = []
    for word in words:
        entry = known(word)
        out.extend([word, *entry.variants] if entry else [word])
    return list(dict.fromkeys(out))


def compile_words(words: list[str]) -> re.Pattern:
    patterns = [p for p in (phrase_pattern(w) for w in expand(words)) if p]
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def negates(words: list[str]) -> bool:
    """Whether the dealbreaker is itself a negation, so negations count."""
    return any(_NEGATION.search(w) or w.lower().startswith(("unable", "cannot"))
               for w in expand(words) if not w.startswith("re:"))


def negated(text: str, start: int) -> bool:
    """A no, not, without or never in the few words before, same sentence."""
    before = text[max(0, start - 80):start]
    cut = list(_SENTENCE_END.finditer(before))
    if cut:
        before = before[cut[-1].end():]
    return bool(_NEGATION.search(" ".join(before.split()[-6:])))


def find(regex: re.Pattern, text: str, negations_count: bool = False) -> str:
    """The first match that is not negated, or ""."""
    for match in regex.finditer(text or ""):
        if negations_count or not negated(text, match.start()):
            return match.group(0)
    return ""


def suggestions() -> list[dict]:
    """The catalog, for the dashboard's one-click suggestions."""
    return [{"name": k.name, "words": [k.name], "hard": k.hard,
             "also": [v for v in k.variants if not v.startswith("re:")][:6]}
            for k in CATALOG]
