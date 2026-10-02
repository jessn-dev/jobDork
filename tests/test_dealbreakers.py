"""
Dealbreakers in plain words: matched the ways adverts write them, with the
usual other wordings, and never on a negation. A regular expression still
works for whoever writes one.

    python tests/test_dealbreakers.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import config as config_mod
from jobdork.core.config import Config, Dealbreaker
from jobdork.db.store import Role
from jobdork.search import dealbreakers as d
from jobdork.search import screen

CASES = [
    # words, advert sentence, what is found ("" for nothing)
    (["security clearance"], "This role requires an active TS/SCI clearance.", "TS/SCI"),
    (["security clearance"], "Candidates must be able to pass a polygraph.", "polygraph"),
    (["security clearance"], "No security clearance is required for this role.", ""),
    (["us citizen"], "Applicants must be U.S. citizens.", "U.S. citizens"),
    (["us citizen"], "U.S. citizenship is required.", "U.S. citizenship"),
    (["us citizen"], "You do not need to be a US citizen.", ""),
    (["us citizen"], "Help us build the future; citizen developers welcome.", ""),
    (["client-site travel"], "Up to 50% travel to client sites.", "travel to client sites"),
    (["client-site travel"], "Work at the client site in Reston.", "client site"),
    (["no visa sponsorship"], "We are unable to sponsor visas for this position.", "unable to sponsor"),
    (["no visa sponsorship"], "Visa sponsorship is available.", ""),
    (["heavy travel"], "Travel up to 75% of the time.", "Travel up to 75%"),
    (["heavy travel"], "Travel up to 10%.", ""),
    (["on call"], "Participate in the on-call rotation.", "on-call"),
    (["forklift certified"], "Must be Forklift-certified.", "Forklift-certified"),
    (["C2C"], "No C2C, W2 only.", ""),
    (["driver's license"], "A valid drivers license is required.", "drivers license"),
    (["heavy lifting"], "Must be able to lift up to 50 lbs.", "lift up to 50 lbs"),
]


def test_words_find_what_adverts_say_and_skip_negations():
    for words, text, want in CASES:
        rx = d.compile_words(words)
        assert d.find(rx, text, d.negates(words)) == want, (words, text)


def test_a_negation_is_only_read_in_the_same_sentence():
    rx = d.compile_words(["security clearance"])
    assert d.find(rx, "No relocation. Requires a security clearance.") == "security clearance"


def test_a_phrase_names_its_catalog_entry_however_it_is_typed():
    assert d.known("US Citizen").name == d.known("us-citizen").name == "US citizen"
    assert d.known("forklift certified") is None
    assert "TS/SCI" in d.expand(["security clearance"])


def _load(text: str) -> Config:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text("titles:\n  include: [nurse]\n" + text, encoding="utf-8")
        return config_mod.load(str(path))


def test_config_takes_a_bare_phrase_words_or_a_pattern():
    cfg = _load("dealbreakers:\n"
                "  - security clearance\n"
                "  - name: Travel\n    words: client-site travel, extensive travel\n    hard: false\n"
                "  - name: On-call\n    pattern: 'on.?call'\n")
    clearance, travel, oncall = cfg.dealbreakers
    assert (clearance.name, clearance.words, clearance.hard) == (
        "Security clearance", ["security clearance"], True)
    assert travel.words == ["client-site travel", "extensive travel"] and not travel.hard
    assert oncall.pattern == "on.?call" and oncall.negations_count


def test_a_dealbreaker_with_nothing_to_look_for_stops_the_load():
    try:
        _load("dealbreakers:\n  - name: Empty\n")
    except config_mod.ConfigError as exc:
        assert "has no words" in str(exc)
    else:
        raise AssertionError("loaded")


def test_screening_reads_words_and_a_negation_does_not_hide_the_post():
    cfg = Config(titles_include=["nurse"])
    rule = Dealbreaker(name="US citizen", words=["us citizen"])
    rule.regex, rule.negations_count = d.compile_words(rule.words), d.negates(rule.words)
    cfg.dealbreakers = [rule]
    hidden = Role(platform="x", title="Nurse", description="Must be a U.S. citizen.")
    kept = Role(platform="x", title="Nurse", description="You need not be a U.S. citizen.")
    assert screen.dealbreaker_verdict(hidden, cfg)[:2] == (False, "dealbreaker: US citizen")
    assert screen.dealbreaker_verdict(kept, cfg)[0]


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
