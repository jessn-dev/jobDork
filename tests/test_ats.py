"""
A job post's ATS match (search/ats.py), and skills confirmed with "I have
this" counting as part of the record. No model, no network.

    python tests/test_ats.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.db.store import Store
from jobdork.search import ats
from jobdork.writing import resume_doc

RESUME = """Jo Bloggs
Senior Accountant
jo@example.com | (312) 555-0199 | Chicago, IL

PROFESSIONAL SUMMARY
Accountant with eight years in payables and the month-end close.

EXPERIENCE
Senior Accountant, Acme  March 2021 - Present
Closed the books in NetSuite each month; reconciliation of 40 vendor accounts in Excel.

EDUCATION
B.S. in Accounting, UT  May 2013

SKILLS
Excel, NetSuite, reconciliation
"""

ADVERT = """We are hiring a Senior Accountant for our finance team.

What you'll do
Own the month-end close.

Requirements
- GAAP and reconciliation
- NetSuite and Excel
- Payroll experience

Benefits
Health cover, and audit support from our partners.
"""


def test_the_requirements_part_is_found_and_ends_at_the_next_part():
    part = ats.requirements(ADVERT)
    assert "GAAP" in part and "Payroll" in part and "Benefits" not in part and "audit" not in part
    assert ats.requirements("No headings at all, just text.") == ""


def test_the_title_counts_most_at_the_top_then_in_the_summary_then_by_words():
    assert ats.title_match("Senior Accountant (Hybrid)", RESUME) == 100
    lower = RESUME.replace("Senior Accountant\n", "", 1)
    assert ats.title_match("Senior Accountant", lower.replace("Accountant with", "Senior Accountant with")) == 75
    # "Staff Accountant II" against the headline "Senior Accountant": half its words.
    assert ats.title_match("Staff Accountant II", RESUME) == 25
    assert ats.title_match("Staff Accountant II", lower) == 0
    assert ats.title_match("", RESUME) is None


def test_dates_in_one_format_and_sections():
    assert ats.date_consistency(RESUME) == 100
    assert ats.date_consistency("March 2021 - Present\n03/2019 - 02/2021") == 66.7
    assert ats.date_consistency("2021") is None
    assert ats.sections(RESUME) == 100
    assert ats.sections("Jo Bloggs\nEXPERIENCE\nAcme") == 20


def test_the_match_scores_the_file_and_sorts_the_advert_skills_three_ways():
    record = RESUME + "\n\n" + resume_doc.record_notes([], [], ["gaap"])
    m = ats.match(RESUME, record, ADVERT, "Senior Accountant")
    assert m.have == ["excel", "month-end close", "netsuite", "reconciliation"]
    assert m.can_add == ["gaap"], "confirmed: in the record, not in the file"
    assert "payroll" in m.missing and "gaap" not in m.missing
    # Required: the five under Requirements, three of them on the file; the
    # audit in Benefits is not one.
    assert set(m.required) == {"gaap", "reconciliation", "netsuite", "excel", "payroll"}
    assert m.parts["required"] == 60.0
    weights = sum(ats.WEIGHTS.values())
    assert m.score == round(sum(m.parts[k] * ats.WEIGHTS[k] for k in ats.WEIGHTS) / weights, 1)
    assert any("GAAP" in tip or "gaap" in tip.lower() for tip in m.advice)
    assert ats.match("", "", ADVERT).score is None


def test_a_confirmed_skill_is_kept_and_joins_the_record():
    with tempfile.TemporaryDirectory() as tmp:
        with Store(str(Path(tmp) / "j.db")) as store:
            assert store.confirm_skill("  GAAP ") and not store.confirm_skill("gaap")
            store.confirm_skill("SQL")
            assert store.confirmed_skills() == ["gaap", "sql"]
            assert "Skills I confirm I have: gaap, sql." in resume_doc.store_notes(store)
            assert store.confirm_skill("sql", have=False)
            assert store.confirmed_skills() == ["gaap"]
            try:
                store.confirm_skill("")
                raise AssertionError("an empty skill must be refused")
            except ValueError:
                pass


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
