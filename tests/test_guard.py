"""
Hallucination guardrail: claims are checked against the source, and a model's
"supported" only counts with a quote that is really in that source.

    python tests/test_guard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.ai import guard, llm

RESUME = "Seven years of Python. Led a team of four at Acme. Built CI with Jenkins."


class _Ready(llm.Settings):
    def problem(self):
        return ""


def _fake(answers):
    calls = iter(answers)
    return lambda *a, **k: next(calls)


def test_a_supported_claim_needs_a_quote_found_in_the_source():
    original = guard.complete_json
    guard.complete_json = _fake([
        {"claims": ["Has seven years of Python", "Led a team of ten",
                    "Built CI with Jenkins"]},
        {"results": [
            {"claim": "Has seven years of Python", "verdict": "supported",
             "source": "resume", "quote": "Seven years of Python"},
            {"claim": "Led a team of ten", "verdict": "supported",
             "source": "resume", "quote": "Led a team of ten"},
            {"claim": "Built CI with Jenkins", "verdict": "unsupported",
             "source": "", "quote": ""},
        ]},
    ])
    try:
        report = guard.check(_Ready("ollama", "m"), "letter text", {"resume": RESUME})
    finally:
        guard.complete_json = original
    assert report.checked and len(report.claims) == 3
    flagged = {c.claim for c in report.unsupported}
    assert flagged == {"Led a team of ten", "Built CI with Jenkins"}
    assert abs(report.rate - 2 / 3) < 1e-9


def test_support_from_several_places_is_quoted_in_parts():
    """Skills listed in different sections of a resume are still supported,
    but every excerpt must be found."""
    original = guard.complete_json
    guard.complete_json = _fake([
        {"claims": ["Knows Python and Jenkins", "Knows Python and Rust"]},
        {"results": [
            {"claim": "Knows Python and Jenkins", "verdict": "supported",
             "source": "resume", "quote": "Seven years of Python ... Jenkins"},
            {"claim": "Knows Python and Rust", "verdict": "supported",
             "source": "resume", "quote": "Seven years of Python ... Rust"},
        ]},
    ])
    try:
        report = guard.check(_Ready("ollama", "m"), "text",
                             {"resume": RESUME + "\nTools: Jenkins"})
    finally:
        guard.complete_json = original
    assert [c.claim for c in report.unsupported] == ["Knows Python and Rust"]


def test_a_failed_check_is_reported_not_raised():
    original = guard.complete_json

    def boom(*a, **k):
        raise llm.LLMError("Ollama is not answering")
    guard.complete_json = boom
    try:
        report = guard.check(_Ready("ollama", "m"), "text", {"resume": RESUME})
    finally:
        guard.complete_json = original
    assert not report.checked and "not answering" in report.error
    assert report.to_dict()["rate"] is None


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
