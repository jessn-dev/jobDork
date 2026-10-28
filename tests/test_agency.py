"""
Who posted a job (search/agency.py): the employer or a recruitment firm, and
the posts you are pursuing that may be the same job reached the other way.
Projects from the Resume page counting toward fit scores is here too: both
came in on 2026-10-23.

    python tests/test_agency.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config
from jobdork.db.store import Role, Store
from jobdork.search import agency, scan
from jobdork.web import api


def test_a_recruiter_is_told_by_its_name_or_by_an_advert_for_a_client():
    assert agency.classify("Robert Half").agency
    assert agency.classify("Kforce Inc.").agency
    assert agency.classify("Acme Staffing LLC").agency
    assert agency.classify("Initech", "Our client, a Fortune 500 bank, seeks a nurse.").agency
    assert agency.classify("Initech", "We are hiring on behalf of our client.").agency
    assert agency.classify("Globex", industry="staffing").agency
    poster = agency.classify("Initech", "My client is a hospital in Ohio.")
    assert poster.why.startswith("the advert speaks for a client")


def test_an_employer_that_serves_clients_is_not_a_recruiter():
    """Live false positives, 2026-10-23, and names a recruiter's could match."""
    for company, advert in (
            ("State Street", "Our client base includes the largest investment firms."),
            ("Atria Health", "Accelerate the work of our client teams."),
            ("Accenture", "You will serve our clients across industries."),
            ("Capital One", "Deliver for a client every sprint."),
            ("Atrium Health", ""), ("Kelly-Moore Paints", ""), ("Temple University", "")):
        assert not agency.classify(company, advert).agency, company


def test_names_and_titles_are_compared_loosely():
    assert agency.core_name("JPMorgan Chase & Co.") == "jpmorgan chase"
    assert agency.names("Our client JPMorgan Chase is hiring", "JPMorgan Chase & Co.")
    assert not agency.names("We use GE turbines", "GE")          # too short to trust
    # A product or plain word is not the client: "Oracle", "Target".
    assert not agency.names("Our client is a bank. " + "x" * 200 + " on Oracle Database",
                            "Oracle")
    assert not agency.names("Hit every target. Our client is a bank. " + "x" * 200
                            + " target", "Target")
    assert agency.names("About our client: Target, the retailer.", "Target")
    assert agency.names("Company: Northrop Grumman Position: Embedded", "Northrop Grumman")
    assert agency.same_title("Sr. Software Engineer", "Senior Software Engineer")
    assert not agency.same_title("Software Engineer", "Software Engineer II")


def _post(uid, company, title="Registered Nurse", description="", status="new",
          city="Chicago", state="IL"):
    post = {"uid": uid, "company": company, "title": title, "description": description,
            "work_mode": "office", "city": city, "state": state,
            "location": f"{city}, {state}", "status": status}
    post["agency"] = agency.classify(company, description).agency
    return post


def test_a_recruiters_post_for_a_job_you_applied_to_directly_is_found():
    applied = _post("a", "Northwestern Medicine", status="applied")
    named = _post("b", "Aya Healthcare", "ICU Nurse",
                  "Our client Northwestern Medicine needs an ICU nurse.")
    same = _post("c", "Cross Country Healthcare")
    elsewhere = _post("d", "Cross Country Healthcare", city="Dallas", state="TX")
    direct = _post("e", "Rush University Medical Center")
    assert agency.overlaps(named, [applied])[0]["why"] == \
        "Aya Healthcare's advert names Northwestern Medicine"
    assert agency.overlaps(same, [applied])[0]["why"] == "the same title and place"
    assert agency.overlaps(elsewhere, [applied]) == []
    # Two employers' posts are two jobs, however alike.
    assert agency.overlaps(direct, [applied]) == []
    # And the other way: the employer's post, when you went through a recruiter.
    through = _post("f", "Cross Country Healthcare", status="submitted")
    hit = agency.overlaps(_post("g", "Northwestern Medicine"), [through])
    assert hit and hit[0]["agency"] and hit[0]["status"] == "submitted"
    # Several applications at one employer the advert names: one line.
    many = [_post(f"n{i}", "Northwestern Medicine", f"Job {i}", status="applied")
            for i in range(3)]
    merged = agency.overlaps(named, many)
    assert len(merged) == 1 and merged[0]["more"] == 2
    # Remote is no place: one title, both remote, is not called the same job.
    remote = [dict(_post("r1", "Cross Country Healthcare"), work_mode="remote"),
              dict(_post("r2", "Northwestern Medicine", status="applied"), work_mode="remote")]
    assert agency.overlaps(remote[0], [remote[1]]) == []


def test_the_list_and_the_post_say_who_posted_it_and_what_it_may_repeat():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["nurse"], db_path=str(Path(tmp) / "t.db"))
        with Store(cfg.db_path) as store:
            mine = Role(platform="greenhouse", company="Northwestern Medicine",
                        title="Registered Nurse", url="https://x.test/1",
                        location_raw="Chicago, IL", city="Chicago", state="IL")
            theirs = Role(platform="adzuna", company="Aya Healthcare",
                          title="Registered Nurse", url="https://x.test/2",
                          location_raw="Chicago, IL", city="Chicago", state="IL",
                          description="Our client, a Chicago hospital, needs nurses.")
            for role in (mine, theirs):
                store.upsert(role)
            store.set_status(mine.uid, "applied")
            store.conn.commit()
            marks = api.recruiters(store, store.list_roles())
        assert not marks[mine.uid]["poster"]["agency"]
        assert marks[theirs.uid]["poster"]["agency"]
        assert [o["uid"] for o in marks[theirs.uid]["overlap"]] == [mine.uid]
        detail = api.role_detail(cfg, theirs.uid)
        assert detail["poster"]["agency"] and detail["overlap"][0]["status"] == "applied"


def test_a_skill_shown_only_in_a_project_counts_toward_fit():
    with tempfile.TemporaryDirectory() as tmp:
        resume = Path(tmp) / "resume.md"
        resume.write_text("Jo Bloggs\nNurse. Ten years of ICU care.\n", encoding="utf-8")
        cfg = Config(titles_include=["nurse"], db_path=str(Path(tmp) / "t.db"),
                     resume_path=str(resume))
        with Store(cfg.db_path) as store:
            assert "python" not in scan._load_resume(cfg, store).skills
            store.save_project({"name": "Ward rota tool", "kind": "App or software",
                                "tools": "Python, SQL", "action": "Built it."})
            cv = scan._load_resume(cfg, store)
        assert {"python", "sql"} <= cv.skills and "Ward rota tool" in cv.text


def test_education_added_counts_too():
    with tempfile.TemporaryDirectory() as tmp:
        resume = Path(tmp) / "resume.md"
        resume.write_text("Jo Bloggs\nAnalyst.\n", encoding="utf-8")
        cfg = Config(titles_include=["analyst"], db_path=str(Path(tmp) / "t.db"),
                     resume_path=str(resume))
        with Store(cfg.db_path) as store:
            store.save_education({"credential": "Data Analytics Certificate",
                                  "school": "Coursera", "details": "SQL, Tableau"})
            cv = scan._load_resume(cfg, store)
        assert "sql" in cv.skills and "Education: Data Analytics Certificate | Coursera" in cv.text


def test_a_re_screen_that_removes_a_post_remembers_it_as_dropped():
    from jobdork.core.config import Locations
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["nurse"], db_path=str(Path(tmp) / "t.db"),
                     locations=Locations(cities=[], radius="any", countries=[]))
        with Store(cfg.db_path) as store:
            gone = Role(platform="greenhouse", company="Acme", title="Welder",
                        url="https://x.test/w", location_raw="Remote", work_mode="remote")
            kept = Role(platform="greenhouse", company="Acme", title="Welder II",
                        url="https://x.test/w2", location_raw="Remote", work_mode="remote")
            store.upsert(gone)
            store.upsert(kept)
            store.set_status(kept.uid, "interested")
            store.conn.commit()
            _checked, stale, removed = scan.rescreen(cfg, store, remove=True)
            dropped = {r["uid"]: r for r in store.list_dropped()}
            assert (stale, removed) == (2, 1)
            assert gone.uid in dropped and dropped[gone.uid]["rule"]
            assert store.get(kept.uid) is not None      # you acted on it: stays


if __name__ == "__main__":
    failures = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
