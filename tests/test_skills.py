"""
The resume's skills for every field, not only tech (search/resume.py): which
skills a resume and an advert name, which field a resume is in, and which of
an advert's skills count for it.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.search import resume as r

NURSE = ("Registered Nurse (RN), BSN. Six years on a med-surg and telemetry unit. "
         "ACLS and BLS. Epic charting, IV therapy, wound care, patient education, "
         "discharge planning. Go-to preceptor for new graduates; covered rest breaks.")
DEVELOPER = ("Senior engineer: Python, Go, REST APIs, Kubernetes, AWS and PostgreSQL. "
             "Built a patient care scheduling app.")
ACCOUNTANT = ("CPA. Month-end close, account reconciliation, journal entries, NetSuite, "
              "Excel (VLOOKUP, pivot tables), SOX controls, GAAP reporting.")
DRIVER = ("Class A CDL, clean record. Forklift and pallet jack certified, RF scanner, "
          "shipping and receiving, cycle counting, DOT regulations, hazmat endorsement.")


def test_a_nurses_resume_has_a_nurses_skills():
    skills = r.resume_skills(NURSE)
    assert {"rn", "bsn", "med-surg", "acls", "bls", "iv therapy", "wound care"} <= skills
    # "Go-to" and "rest breaks" are English here, not a language and an API.
    assert "go" not in skills and "rest" not in skills
    assert r.fields_of(skills) == {"healthcare"}


def test_every_field_is_recognised():
    assert r.fields_of(r.resume_skills(ACCOUNTANT)) == {"finance"}
    assert "logistics" in r.fields_of(r.resume_skills(DRIVER))
    assert r.fields_of(r.resume_skills("Lesson planning, classroom management, "
                                       "special education and IEP writing.")) == {"education"}


def test_one_passing_mention_does_not_change_a_resumes_field():
    skills = r.resume_skills(DEVELOPER)
    assert r.fields_of(skills) == {"technology"}
    assert "patient care" not in skills and {"go", "rest", "python"} <= skills


def test_an_adverts_words_from_other_fields_do_not_count():
    nurse = r.Resume(text=NURSE, skills=r.resume_skills(NURSE))
    advert = ("Med-Surg RN. BLS and ACLS required; Epic EHR. Must be able to go up "
              "and down stairs; rest breaks per policy. Python a plus.")
    fit = r.fit(nurse, advert)
    assert {"rn", "med-surg", "bls", "acls"} <= set(fit.matched)
    assert fit.missing == ["ehr"], fit.missing
    assert fit.score > 15

    developer = r.Resume(text=DEVELOPER, skills=r.resume_skills(DEVELOPER))
    fit = r.fit(developer, "Go and Python on AWS, for patient care teams; BLS not needed.")
    assert "bls" not in fit.missing and "patient care" not in fit.matched


def test_a_resume_in_no_field_counts_every_skill_as_before():
    blank = r.Resume(text="hello", skills=set())
    assert r.near(set(), {"python", "bls"}) == {"python", "bls"}
    assert r.fit(blank, "Python and BLS").matched == []


def test_words_that_are_skills_only_in_capitals():
    assert "fair" not in r.extract_skills("We are a fair chance employer.")
    assert "fair" in r.extract_skills("Quantify risk with FAIR.")
    assert "rest" not in r.extract_skills("Paid rest breaks.")
    assert "rest" in r.extract_skills("Design REST APIs.")
    assert "pos" in r.extract_skills("Run the POS at close.")


def test_every_term_is_in_a_field_and_every_weak_term_is_a_term():
    assert all(t in r.SKILL_TERMS for t in r.WEAK)
    assert len(r.SKILL_TERMS) == len(set(r.SKILL_TERMS)) > 500
    assert all(t == t.lower() for t in r.SKILL_TERMS)
    assert all(t in r.SKILL_TERMS for t in r.CASED)


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except BaseException:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc(limit=3)
    raise SystemExit(1 if failed else 0)
