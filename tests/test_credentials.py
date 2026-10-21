"""
Certifications and licenses an advert asks for (search/credentials.py):
found in the advert's lines, marked required or preferred, checked against
the resume, and quiet about lines that only mention a job title.

    python tests/test_credentials.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.search import credentials

NURSE = """Job Summary
The RN will provide care to ICU patients and learn our team culture.
Requirements:
• Current RN license in Illinois
• BLS and ACLS certification required within 30 days
• Bachelor's degree in nursing
Preferred Qualifications
CCRN certification preferred
No CDL required for this role."""


def test_a_nurses_advert_names_its_licences():
    found = credentials.find(NURSE, "Sam Rivera, RN. BLS certified.")
    assert [f["line"] for f in found] == [
        "Current RN license in Illinois",
        "BLS and ACLS certification required within 30 days",
        "CCRN certification preferred"]
    assert [f["need"] for f in found] == ["required", "required", "preferred"]
    assert found[1]["names"] == ["BLS", "ACLS"] and found[1]["have"] == ["BLS"]


def test_a_job_title_alone_is_not_a_requirement():
    """"RN" is in every line of a nurse's advert; "EA" is in "team"."""
    assert credentials.find("The RN will round on patients.\nOur team values each RN.") == []
    assert credentials.named_in("Learn with the team each day") == []


def test_one_that_is_not_needed_is_left_out():
    assert credentials.find("No license required. We train you.") == []


def test_the_employers_own_certifications_are_not_asked_of_you():
    assert credentials.find("As a certified B-Corp we build trust.\n"
                            "We are ISO 27001 certified.") == []


def test_a_certifications_heading_makes_its_lines_credentials():
    found = credentials.find("Certifications (one or more required):\nIAT I\nIAM I\n"
                             "Experience:\nMinimum of 2 years")
    assert [(f["line"], f["need"]) for f in found] == [("IAT I", "required"),
                                                       ("IAM I", "required")]


def test_yours_count_even_when_the_list_does_not_know_them():
    found = credentials.find(NURSE, "", held=["ACLS", "RN"])
    assert found[0]["have"] == ["RN"] and found[1]["have"] == ["ACLS"]
    dod = credentials.find("Certifications (one or more required):\nIAT I\nIAM I",
                           held=["IAT I"])
    assert dod[0]["names"] == ["IAT I"] and dod[0]["have"] == ["IAT I"]
    assert dod[1]["have"] == []


def test_other_fields_are_found_too():
    found = credentials.find("Qualifications:\nActive CPA preferred\n"
                             "Valid CDL Class A with clean driving record\n"
                             "CISSP or Security+ required")
    assert [f["names"] for f in found] == [["CPA"], ["CDL"], ["CISSP", "Security+"]]


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
