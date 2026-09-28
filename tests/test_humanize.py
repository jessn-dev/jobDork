"""
Signs of AI writing (humanizer rules): found in drafts, fixed in verdicts,
and kept out of the app's own wording.

    python tests/test_humanize.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.ai import llm  # noqa: E402
from jobdork.writing import gates, humanize  # noqa: E402

# Dashes that are data, not prose: counted, or matched in addresses.
DATA = {("gates.py", "—"), ("geo.py", r"\s*[-–—]\s*")}


def rules(text: str) -> set[int]:
    return {t.rule for t in humanize.find(text)}


def test_the_strong_tells_are_found():
    assert 1 in rules("It's not just a job, it's a calling.")
    assert 8 in rules("The team — remote — is hiring.")
    assert 12 in rules("Additionally, this role is pivotal.")
    assert 19 in rules("- **Speed:** faster")
    assert 22 in rules("Here is your CV. I hope this helps!")


def test_plain_writing_and_number_ranges_are_not_tells():
    assert humanize.find("The role pays $140,000 – $170,000, 9–5, in Chicago.") == []
    assert humanize.find("Run `git log -- file` to see it.") == []


def test_clean_fixes_dashes_but_not_ranges_code_or_quotes():
    assert humanize.clean("Remote — Chicago") == "Remote, Chicago"
    assert humanize.clean("Pays 100–120k") == "Pays 100-120k"
    assert humanize.clean("Run `a -- b` now") == "Run `a -- b` now"
    quoted = 'The advert says "on-call — weekends" and it matters — a lot.'
    assert humanize.clean(quoted, keep_quotes=True) == \
        'The advert says "on-call — weekends" and it matters, a lot.'


def test_every_draft_is_checked_for_tells():
    for kind in ("screen", "cv", "cover_letter"):
        found = {g.name: g for g in gates.run_all(
            "A plain draft — with a dash.", kind, sibling="x")}
        assert not found["AI tells"].passed, kind
        assert "§8" in found["AI tells"].detail


def test_a_verdict_is_cleaned_but_its_quotes_of_the_advert_are_not():
    raw = {"score": 70, "verdict": "possible",
           "summary": "Good match — mostly.",
           "reasons": ['The advert asks for "Python — 5 years"'], "concerns": []}
    clean = llm._clean_judgement(raw, llm.Settings("ollama", "m"), 900)
    assert clean["summary"] == "Good match, mostly."
    assert clean["reasons"] == ['The advert asks for "Python — 5 years"']


def test_drafts_are_given_the_full_humanizer_guide():
    from jobdork.writing import generate

    guide = humanize.style_guide()
    assert guide.startswith("---\nname: humanizer") and "### 8. Dashes" in guide
    for kind in ("screen", "cv", "cover_letter"):
        assert "writing-style.md" in generate.PROMPTS[kind], kind


def _app_strings():
    """Every string the app shows: dashboard text and non-docstring literals."""
    page = (ROOT / "jobdork/data/dashboard.html").read_text(encoding="utf-8")
    for n, line in enumerate(page.split("\n"), 1):
        line = re.sub(r"^\s*//.*$|\s//\s.*$|/\*.*?\*/", "", line)
        yield f"dashboard.html:{n}", line
    for path in sorted((ROOT / "jobdork").rglob("*.py")):
        if path.name == "humanize.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = {id(node.body[0].value) for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef,
                                     ast.AsyncFunctionDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docs
                    and (path.name, node.value) not in DATA):
                yield f"{path.name}:{node.lineno}", node.value


def test_the_apps_own_wording_has_no_ai_tells():
    """The UI copy was written by a model too. Keep it clean."""
    found = [f"{where} {t.line()}" for where, text in _app_strings()
             for t in humanize.find(text, markdown=not where.startswith("dashboard"))]
    assert not found, "\n".join(found[:20])


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
