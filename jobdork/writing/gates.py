"""
jobdork.writing.gates
=====================
Mechanical checks on a generated document.

These are scripts, not judgement. A model asked to re-read its own draft will
usually say it looks fine; a script counting em-dashes says how many there are.
So the checks here are all things that can be counted or matched, and none of
them is an opinion about quality.

Nothing is redrafted automatically. A failed gate means *read this before you
send it*, not *this is broken* — and a second pass would cost tokens you did
not ask for. The results are recorded against the document either way.

The most important one is `unsupported_figures`. A tailored CV is the easiest
place in a job search to end up with a number nobody can back up, and a model
writing prose about your career will reach for one. Any figure or scale word in
a draft that is not in your résumé is surfaced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Six is long enough that a shared run is reuse rather than coincidence.
NGRAM = 6

# Words that assert a magnitude. A draft may only use one your résumé used.
SCALE_WORDS = (
    "million", "billion", "thousand", "hundreds", "dozens", "doubled",
    "tripled", "quadrupled", "halved", "fold", "%", "percent",
)

_WORD = re.compile(r"[a-z0-9']+")
_FIGURE = re.compile(r"\b\d[\d,.]*\s*(?:%|percent|k\b|m\b|bn\b|million|billion)?", re.I)


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str = ""
    items: list[str] = field(default_factory=list)

    def line(self) -> str:
        mark = "ok  " if self.passed else "READ"
        text = f"  {mark} {self.name}: {self.detail}"
        for item in self.items[:6]:
            text += f"\n         · {item}"
        return text


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _ngrams(text: str, n: int = NGRAM) -> set[tuple[str, ...]]:
    words = _words(text)
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


# ── the checks ─────────────────────────────────────────────────────────────────

def em_dashes(draft: str, limit: int = 2) -> Gate:
    """Counted because it is the single most legible tell of generated prose."""
    count = draft.count("—") + draft.count("–")
    return Gate(
        name="em dashes",
        passed=count <= limit,
        detail=f"{count} found (at most {limit} reads as written by a person)",
    )


def overlap(draft: str, sibling: str, sibling_name: str = "the CV") -> Gate:
    """No run of six words may appear in both the CV and the cover letter.

    The CV carries the facts and the letter carries judgement. If they share
    sentences, the letter is repeating the CV back at a reader who has it
    open in the next tab.
    """
    if not sibling:
        return Gate(name="phrase overlap", passed=True,
                    detail=f"nothing to compare: {sibling_name} is not drafted yet")
    shared = _ngrams(draft) & _ngrams(sibling)
    return Gate(
        name="phrase overlap",
        passed=not shared,
        detail=(f"{len(shared)} shared {NGRAM}-word runs with {sibling_name}"
                if shared else f"nothing shared with {sibling_name}"),
        items=[" ".join(run) for run in sorted(shared)[:6]],
    )


def unsupported_figures(draft: str, resume_text: str) -> Gate:
    """Every number and scale word in the draft must appear in the résumé.

    This is the gate that matters. A tailored CV is the easiest place in a job
    search to acquire a statistic nobody can back up, and a model writing about
    your career will reach for one. Years and small integers are ignored — they
    are almost always dates or list counts, not claims.
    """
    if not resume_text:
        return Gate(name="unsupported figures", passed=True,
                    detail="no résumé to check against")

    resume_numbers = set(re.findall(r"\d[\d,.]*", resume_text))
    resume_lower = resume_text.lower()
    suspect: list[str] = []

    # Numbers inside URLs and code spans are identifiers, not claims about a
    # career. The first live run flagged `5792028474` — an Adzuna posting id
    # the draft had quoted back as a link.
    body = re.sub(r"https?://\S+", " ", draft)
    body = re.sub(r"`[^`]*`", " ", body)

    for raw in re.findall(r"\d[\d,.]*", body):
        if raw in resume_numbers:
            continue
        plain = raw.rstrip(".,").replace(",", "")
        if plain.isdigit() and (len(plain) <= 1 or 1900 <= int(plain) <= 2100):
            continue                       # a date, or a bullet number
        suspect.append(raw)

    body_lower = body.lower()
    for word in SCALE_WORDS:
        if word in body_lower and word not in resume_lower:
            suspect.append(word)

    unique = sorted(set(suspect))
    return Gate(
        name="unsupported figures",
        passed=not unique,
        detail=(f"{len(unique)} not found in your résumé"
                if unique else "every figure appears in your résumé"),
        items=unique,
    )


def not_empty(draft: str, minimum: int = 400) -> Gate:
    return Gate(
        name="length",
        passed=len(draft.strip()) >= minimum,
        detail=f"{len(draft.strip())} characters",
    )


def slop(draft: str, linter_path: str = "") -> Gate:
    """Optional: the natural-writing linter, when it is installed.

    Absent, this reports that it did not run rather than passing silently — a
    gate that quietly stops checking is worse than one that is not there.
    """
    import subprocess
    from pathlib import Path

    script = Path(linter_path or
                  "~/.claude/skills/natural-writing/scripts/detect.py").expanduser()
    if not script.is_file():
        return Gate(name="slop score", passed=True,
                    detail="natural-writing linter not installed; not checked")
    try:
        done = subprocess.run(
            ["python3", str(script)], input=draft, capture_output=True,
            text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Gate(name="slop score", passed=True,
                    detail=f"linter did not run: {exc}")
    output = (done.stdout or done.stderr or "").strip()
    hits = [ln for ln in output.splitlines() if ln.strip()][:6]
    return Gate(name="slop score", passed=done.returncode == 0,
                detail=output.splitlines()[0] if output else "clean",
                items=hits[1:])


def ai_tells(draft: str) -> Gate:
    """Signs of AI writing, by the humanizer rules the draft was written to.

    Every recognised tell is listed with its rule number in the bundled
    data/humanizer/SKILL.md, so the fix is one lookup away. This replaced
    counting em dashes alone, and the external linter that was rarely
    installed and so rarely ran.
    """
    from . import humanize

    tells = humanize.find(draft)
    if not tells:
        return Gate(name="AI tells", passed=True, detail="none found")
    rules = sorted({t.rule for t in tells})
    return Gate(name="AI tells", passed=False,
                detail=f"{len(tells)} found (humanizer rules "
                       f"{', '.join(f'§{r}' for r in rules)})",
                items=[t.line() for t in tells])


def run_all(draft: str, kind: str, resume_text: str = "",
            sibling: str = "", sibling_name: str = "the CV") -> list[Gate]:
    """The checks that apply to this kind of document.

    A screen gets almost none of them, and that is the point. These gates
    guard documents you SEND — a figure in a CV that is not in your résumé is
    a claim nobody can back up. A screen is notes to yourself, and it is
    *supposed* to quote the advert: the first live run flagged
    "$140,000 - $170,000" as unsupported when that was the advertised salary,
    read correctly off the posting. Applying a send-time gate to reading notes
    produced a warning that was not only useless but wrong.
    """
    # Every draft is read by you, so every draft is checked for AI tells —
    # a screen included, even though its figures are the advert's own.
    gates = [not_empty(draft, 200 if kind == "screen" else 400), ai_tells(draft)]
    if kind == "screen":
        return gates
    gates += [unsupported_figures(draft, resume_text)]
    if kind == "cover_letter":
        gates.append(overlap(draft, sibling, sibling_name))
    return gates


def summarise(gates: list[Gate]) -> dict:
    return {g.name: {"passed": g.passed, "detail": g.detail, "items": g.items}
            for g in gates}
