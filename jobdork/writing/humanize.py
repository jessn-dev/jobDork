"""
jobdork.writing.humanize
========================
Signs of AI writing, found by script, in text a model wrote for you.

The rules come from humanizer (github.com/blader/humanizer, MIT), which is
bundled at data/humanizer/SKILL.md and given in full to the model that drafts
CVs and cover letters. That file is guidance for a writer. This module is
the part of it a script can check: the patterns with a fixed wording. It
cannot tell whether a triad was needed or a sentence adds anything; those
stay with the writer and with you.

Two uses:

  `find(text)` lists every tell it recognises, with the rule number from
  SKILL.md, so a draft's gate results say what to fix and where.

  `clean(text)` fixes the two that have one right answer — dashes used as
  connectors, and curly double quotes — in short text the app stores and
  shows (the AI verdict). It never rewrites wording.

Quotes from a posting are left alone by the callers: they must stay the
posting's own words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent.parent / "data" / "humanizer" / "SKILL.md"

# Condensed from SKILL.md for prompts where the whole file will not fit — a
# 3B local model has little room — or would be out of proportion to a
# one-paragraph answer.
RULES = """Write plainly, like a careful person, not like a chatbot:
- No em dashes or en dashes. Use a comma, colon, period or parentheses.
- State the point directly. No "not X but Y", no "it's not just X, it's Y".
- No closing line that restates the point; end on the last concrete fact.
- Use is, are and has, not "serves as", "stands as", "boasts" or "features".
- Avoid these words: additionally, crucial, delve, enhance, pivotal,
  robust, showcase, testament, underscore, valuable, vibrant, landscape,
  seamless, leverage, meticulous, intricate, key (as an adjective).
- No filler openers ("Here's the thing", "Let's dive in") and no chat
  wrappers ("I hope this helps", "Let me know").
- No bold labels, no emojis, no invented facts or numbers."""


@dataclass(frozen=True)
class Tell:
    rule: int          # section number in SKILL.md
    name: str
    found: str         # the words, with a little context

    def line(self) -> str:
        return f"§{self.rule} {self.name}: …{self.found}…"


def _p(rule: int, name: str, *patterns: str, flags=re.IGNORECASE):
    return rule, name, [re.compile(p, flags) for p in patterns]


PATTERNS = [
    _p(1, "not X but Y",
       r"\bnot (?:just|only|merely|simply)\b[^.?!\n]{1,80}?\bbut\b",
       r"\bit'?s not\b[^.?!\n]{1,60}?[,;]\s*it'?s\b",
       r"\b(?:this|that) (?:does not|doesn't) mean\b[^.\n]*\.\s*it means\b"),
    _p(2, "one-line closer",
       r"\b(?:that is|that's) the real \w+", r"\bthat distinction matters\b",
       r"\bread that again\b", r"\blet that sink in\b"),
    _p(3, "saying that sounds deep",
       r"\bthe real question is\b", r"\bat its core\b", r"\bwhat really matters\b",
       r"\bthe heart of the matter\b", r"\bthe deeper issue\b"),
    _p(4, "staged run-up",
       r"\blet'?s (?:dive in|dive into|explore|break (?:this|it) down)\b",
       r"\bhere'?s what you need to know\b", r"\bwithout further ado\b",
       r"\bhere'?s the thing\b", r"\blet'?s be honest\b", r"\breal talk\b",
       r"(?:^|\n)\s*honestly\?"),
    _p(5, "arguing with no one",
       r"\bi'?m not saying\b", r"\bdon'?t get me wrong\b",
       r"\bthis is not to say\b", r"\ba tempting approach would be\b",
       r"\bone might be tempted\b"),
    _p(8, "dash as connector",
       r"\S*\s?—\s?\S*", r"[^\d\s]\s?–\s?\S*|\S*\s–\s\S*", r"\S+ -- \S+",
       flags=0),
    _p(12, "overused AI word",
       r"\b(?:additionally|bolstered|crucial|delve[sd]?|delving|enhanc(?:e|es|ed|ing)|"
       r"garner(?:s|ed)?|interplay|intricac(?:y|ies)|intricate|meticulous(?:ly)?|"
       r"pivotal|showcas(?:e|es|ed|ing)|tapestry|testament|underscor(?:e|es|ed|ing)|"
       r"vibrant|seamless(?:ly)?|leverag(?:e|es|ed|ing))\b"),
    _p(13, "inflated significance",
       r"\bstands as a testament\b", r"\bplays? a (?:key|crucial|pivotal|vital) role\b",
       r"\bsetting the stage for\b", r"\bevolving landscape\b", r"\bindelible mark\b",
       r"\bthe future looks bright\b", r"\bexciting times\b",
       r"\ba step in the right direction\b", r"\breflects a broader\b"),
    _p(15, "-ing rider",
       r",\s+(?:highlighting|underscoring|emphasizing|showcasing|fostering|"
       r"cultivating|symbolizing|reflecting)\b"),
    _p(16, "sales language",
       r"\bnestled\b", r"\bin the heart of\b", r"\bbreathtaking\b", r"\bmust-visit\b",
       r"\bstunning\b", r"\brenowned\b", r"\bdiverse array\b", r"\bgroundbreaking\b"),
    _p(17, "borrowed authority",
       r"\bexperts (?:argue|believe|say|agree)\b", r"\bindustry reports\b",
       r"\bobservers have\b"),
    _p(18, "avoiding is/has",
       r"\b(?:serves|stands|functions|operates) as\b", r"\bboasts\b"),
    _p(19, "bold label", r"(?m)^\s*(?:[-*]|\d+\.)\s+\*\*[^*\n]+:?\*\*:?", flags=0),
    _p(21, "curly quotes", r"[“”]", flags=0),
    _p(22, "chatbot residue",
       r"\bi hope this helps\b", r"\bof course!", r"\bcertainly!", r"\bgreat question\b",
       r"\byou'?re absolutely right\b", r"\blet me know\b", r"\bwould you like\b",
       r"\bwant me to\b", r"\bshould i continue\b"),
    _p(23, "knowledge-limit disclaimer",
       r"\bas of my (?:last|latest)\b", r"\btraining (?:data|update)\b",
       r"\bnot publicly available\b", r"\bnot widely documented\b",
       r"\bbased on (?:the )?available information\b", r"\bit is believed that\b"),
]


def _context(text: str, match: re.Match) -> str:
    start, end = max(0, match.start() - 25), min(len(text), match.end() + 25)
    return re.sub(r"\s+", " ", text[start:end]).strip()


_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
# A number range ("$140,000 – $170,000", "9–5") is typography, not a
# connector, so it is neither a tell nor something to rewrite as a comma.
_RANGE = re.compile(r"(\d)\s*[–—]\s*([$£€]?\d)")


def _without_code(text: str, markdown: bool = True) -> str:
    """Code, commands and paths keep their dashes (SKILL.md §8).

    Backticks mean code only in Markdown. In JavaScript they wrap ordinary
    text (template strings), so there only fenced blocks are skipped.
    """
    if markdown:
        text = _CODE.sub(" ", text)
    return _RANGE.sub(r"\1-\2", text)


def find(text: str, markdown: bool = True) -> list[Tell]:
    """Every recognised tell in `text`, strongest rules first."""
    prose = _without_code(text or "", markdown)
    tells: list[Tell] = []
    for rule, name, patterns in PATTERNS:
        for pattern in patterns:
            for match in pattern.finditer(prose):
                tells.append(Tell(rule, name, _context(prose, match)))
    return tells


# Dashes between words become commas; between numbers, a plain hyphen.
_SPACED = re.compile(r"\s+(?:—|–|--)\s+")
_TIGHT = re.compile(r"(?<=\w)[—–](?=\w)")


_QUOTED = re.compile(r"```.*?```|`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”", re.DOTALL)


def clean(text: str, keep_quotes: bool = False) -> str:
    """Fix the tells with one right answer: dashes and curly double quotes.

    `keep_quotes` leaves anything in quotation marks as written, for text
    that quotes a source (a verdict quoting the advert): a quotation is the
    source's wording, dashes and all.
    """
    if not text:
        return text
    protected = _QUOTED if keep_quotes else _CODE
    out, last = [], 0
    for code in protected.finditer(text):       # code (and quotes) keep dashes
        out += [_clean_prose(text[last:code.start()]), code.group(0)]
        last = code.end()
    out.append(_clean_prose(text[last:]))
    return "".join(out)


def _clean_prose(text: str) -> str:
    text = _RANGE.sub(r"\1-\2", text)
    text = _SPACED.sub(", ", text)
    text = _TIGHT.sub(", ", text)
    text = text.replace("—", ",").replace("–", "-")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r",\s*,", ",", text).replace(" ,", ",")


def style_guide() -> str:
    """The full humanizer text, for a writer that can read a file."""
    try:
        return SKILL_PATH.read_text(encoding="utf-8")
    except OSError:
        return RULES
