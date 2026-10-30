"""
How a resume's lines are written (writing/style.py), and the gate that
reports it. No model involved.

    python tests/test_style.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.writing import gates, style

MD = """# Jo Bloggs
## PROFESSIONAL SUMMARY
Accountant with eight years of experience in payables and the month-end close.
## EXPERIENCE
### Senior Accountant\tMarch 2021 - Present
Acme, Chicago, IL
- Responsible for the month-end close for the whole of the company.
- Closed the books two days sooner by moving the team to NetSuite.
- Closed vendor accounts each month and kept them clean for the auditors.
- Closed the payroll accounts with the help of the payroll team in 2022.
- I trained my team of five on the new reconciliation process.
### Staff Accountant\tJune 2018 - February 2021
Initech, Chicago, IL
- Reconciled 40 vendor accounts a month, and wrote the notes for every one of them so that the auditors, the controller and the new hires could follow each balance without asking anyone on the team where a figure came from or why.
## SKILLS
- Excel
"""


def _rules(report):
    return [f.rule for f in report.findings]


def test_each_rule_finds_its_line_and_the_score_is_the_weights():
    report = style.check_markdown(MD)
    rules = _rules(report)
    assert rules.count("weak_opener") == 1 and rules.count("first_person") == 1
    assert rules.count("long_bullet") == 1
    # Three bullets of one job start "Closed": the second and third are told.
    assert rules.count("repeated_opener") == 2
    # Skills are not bullets to score; the summary is a line, not a bullet.
    assert report.lines == 7
    assert report.findings[0].rule == "weak_opener", "the hard rule comes first"
    penalties = [40 + 5, 10, 5, 10, 10 + 5, 10]        # per line with findings
    assert report.score == round((700 - sum(penalties)) / 7)


def test_plain_text_from_a_pdf_without_bullet_marks():
    text = ("Jo Bloggs\nEXPERIENCE\nSenior Accountant, Acme 2021 - Present\n"
            "Responsible for the month-end close for the whole\ncompany and its two branches.\n"
            "Closed the books two days sooner by moving to NetSuite.\n"
            "Trained a team of five on the new reconciliation process.\n"
            "EDUCATION\nB.S. in Accounting, a long name for a school of business 2009\n")
    units = style.units_text(text)
    assert units[0][1] == ("Responsible for the month-end close for the whole "
                                        "company and its two branches.")
    assert len(units) == 3, "Education is not experience"
    assert "weak_opener" in _rules(style.check(units))


def test_too_little_or_another_language_is_not_scored():
    assert style.check_text("Jo Bloggs\n- One line\n").score is None
    spanish = "\n".join(f"- Gestioné el cierre mensual número {i} con NetSuite." for i in range(5))
    report = style.check_text(spanish)
    assert report.score is None and "English" in report.note


def test_the_gate_fails_only_for_the_hard_rule_and_lists_each_rule_once():
    gate = gates.resume_writing(MD)
    assert not gate.passed and gate.name == "resume writing"
    assert "weak_opener" not in gate.detail and "starts by saying" in gate.detail
    assert len(gate.items) == len({f.rule for f in style.check_markdown(MD).findings})
    fine = MD.replace("- Responsible for the", "- Ran the")
    assert gates.resume_writing(fine).passed
    assert any(g.name == "resume writing" for g in gates.run_all(MD, "cv", resume_text=MD))
    assert not any(g.name == "resume writing" for g in gates.run_all(MD, "cover_letter"))


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
