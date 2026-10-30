"""
The AI cover letter and resume review: facts from the sources only, quotes
checked by script, every output guarded and recorded. No live model: the
model's answers are scripted.

    python tests/test_writer.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.ai import guard, llm, writer
from jobdork.core.config import Config
from jobdork.db.store import Role, Store
from jobdork.web import api

RESUME = """Jane Doe
Platform engineer. Seven years of Python and Go.
- Ran the Kubernetes platform for 40 services at Acme.
- Built CI pipelines in GitHub Actions.
"""

ADVERT = ("We are hiring a platform engineer to run Kubernetes for our "
          "product teams. You will own CI, on-call and the path to production. "
          "Python or Go required. Remote in the EU. " * 3)


class _Ready(llm.Settings):
    def problem(self):
        return ""


SETTINGS = _Ready("ollama", "m")


class _Script:
    """Stand-in for complete_json in writer and guard, answering in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.purposes = []

    def __call__(self, *a, purpose="", **k):
        self.purposes.append(purpose)
        self.prompts = [*getattr(self, "prompts", []), a[2] if len(a) > 2 else ""]
        return self.answers.pop(0)

    def __enter__(self):
        self.saved = (writer.complete_json, guard.complete_json)
        writer.complete_json = guard.complete_json = self
        return self

    def __exit__(self, *exc):
        writer.complete_json, guard.complete_json = self.saved


GUARD_OK = ({"claims": ["Jane ran Kubernetes for 40 services"]},
            {"results": [{"claim": "Jane ran Kubernetes for 40 services",
                          "verdict": "supported", "source": "resume",
                          "quote": "Ran the Kubernetes platform for 40 services"}]})


def _setup(tmp: str):
    resume = Path(tmp) / "resume.md"
    resume.write_text(RESUME, encoding="utf-8")
    cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"),
                 resume_path=str(resume))
    role = Role(platform="greenhouse", company="Initech", title="Platform Engineer",
                url="https://boards.greenhouse.io/initech/jobs/1",
                location_raw="Remote", description=ADVERT)
    with Store(cfg.db_path) as store:
        store.upsert(role)
    return cfg, role.uid


def _patched_settings():
    saved = writer._settings
    writer._settings = lambda cfg: SETTINGS
    return saved


def test_a_letter_is_humanized_gated_guarded_and_recorded():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        saved = _patched_settings()
        try:
            with _Script({"paragraphs": [
                    "I ran the Kubernetes platform for 40 services at Acme — "
                    "the work your advert describes.",
                    "I also grew revenue by 300%."]}, *GUARD_OK) as script, \
                    Store(cfg.db_path) as store:
                draft = writer.letter(cfg, store, uid, root=tmp)
                output = store.ai_output(draft.output_id)
                artifact = store.artifacts(uid, "cover_letter")[0]
        finally:
            writer._settings = saved
        assert script.purposes == ["cover_letter", "guard_extract", "guard_verify"]
        assert "—" not in draft.text                       # humanize.clean
        assert draft.path.name == writer.LETTER_FILE and draft.path.is_file()
        by_name = {g.name: g for g in draft.gates}
        assert not by_name["unsupported figures"].passed   # 300% is not in the resume
        assert by_name[writer.GUARD_GATE].passed
        assert (output["kind"], output["uid"], output["checked"]) == \
            ("cover_letter", uid, 1)
        assert f'"output_id": {draft.output_id}' in artifact["gates_json"]


PREP = {
    "fit": ["Ran the Kubernetes platform for 40 services, the work this advert describes."],
    "questions": [{"question": "How did you keep 40 services running on one cluster?",
                   "tests": "Run Kubernetes for product teams",
                   "points": ["Ran the Kubernetes platform for 40 services at Acme."]}],
    "follow_ups": [{"question": "What would you change about the CI pipelines?",
                    "tests": "Own CI", "points": ["Built CI pipelines in GitHub Actions."]}],
    "gaps": [{"skill": "On-call", "why": "The advert asks you to own on-call.",
              "prepare": "Say plainly it is not on your resume, and how you would learn it."},
             {"skill": "Terraform", "why": "Platform teams often use it.",
              "prepare": "Mention your experience with Terraform."}],
    "talking_points": ["Seven years of Python and Go."],
}


def test_interview_prep_is_laid_out_checked_and_recorded_and_gaps_are_never_claimed():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        saved = _patched_settings()
        try:
            with _Script(PREP, *GUARD_OK) as script, Store(cfg.db_path) as store:
                store.confirm_skill("terraform")
                draft = writer.prep(cfg, store, uid, root=tmp)
                artifact = store.artifacts(uid, "interview_prep")[0]
                output = store.ai_output(draft.output_id)
        finally:
            writer._settings = saved
        assert script.purposes == ["interview_prep", "guard_extract", "guard_verify"]
        assert "Skills I confirm I have: terraform" in script.prompts[0], "the whole record"
        text = draft.text
        assert text.startswith("# Interview prep: Platform Engineer at Initech\n")
        order = [text.index(h) for h in ("## Why you fit", "## Questions about your resume",
                                         "## Follow-ups on your work", "## Gaps to prepare",
                                         "## Talking points")]
        assert order == sorted(order)
        assert "### How did you keep 40 services running on one cluster?\nTests: Run Kubernetes" in text
        assert draft.path.name == writer.PREP_FILE and artifact["path"] == str(draft.path)
        assert output["kind"] == "interview_prep"
        gaps = next(g for g in draft.gates if g.name == "gaps not claimed")
        # "Mention your experience with Terraform" claims what the resume does not show.
        assert not gaps.passed and gaps.items == ["Terraform"]


def test_a_recruiter_message_is_short_checked_and_never_sent():
    words = ("Initech's product teams need someone to run Kubernetes and own the path to "
             "production. I ran the Kubernetes platform for 40 services at Acme and built "
             "its CI pipelines in GitHub Actions, in Python and Go, for seven years of "
             "platform work across several product teams that shipped every day with it. "
             "Worth a quick chat about the role?")
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        saved = _patched_settings()
        try:
            with _Script({"message": words}, *GUARD_OK) as script, Store(cfg.db_path) as store:
                draft = writer.message(cfg, store, uid, root=tmp)
                artifact = store.artifacts(uid, "recruiter_message")[0]
        finally:
            writer._settings = saved
        assert script.purposes == ["recruiter_message", "guard_extract", "guard_verify"]
        assert draft.path.name == writer.MESSAGE_FILE and artifact["path"] == str(draft.path)
        length = next(g for g in draft.gates if g.name == writer.MESSAGE_GATE)
        assert length.passed and length.detail.startswith(f"{len(words.split())} words")
        assert next(g for g in draft.gates if g.name == "length").passed, "short by design"
        long = writer.recruiter_message
        with _Script({"message": words * 3}, *GUARD_OK):
            with Store(cfg.db_path) as store:
                too_long = long(SETTINGS, store.get(uid), RESUME)
        assert not next(g for g in too_long.gates if g.name == writer.MESSAGE_GATE).passed


def test_a_letter_needs_a_real_advert():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        with Store(cfg.db_path) as store:
            store.conn.execute("UPDATE roles SET description = 'short' WHERE uid = ?",
                               (uid,))
            row = store.get(uid)
        try:
            writer.cover_letter(SETTINGS, row, RESUME)
        except llm.LLMError as exc:
            assert "Paste the full advert" in str(exc)
        else:
            raise AssertionError("a five-character advert cannot be written to")


def test_review_quotes_not_in_the_resume_are_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        saved = _patched_settings()
        try:
            with _Script({
                "enough_evidence": True,
                "health": [
                    {"issue": "No outcome", "quote": "Built CI pipelines in GitHub Actions",
                     "fix": "Say what it changed."},
                    {"issue": "Vague", "quote": "Led a team of twelve",
                     "fix": "Invented line."},
                    {"issue": "No summary section", "quote": "", "fix": "Add two lines."}],
                "alignment": {
                    "summary": "A close match on Kubernetes and CI.",
                    "missing": ["On-call experience"],
                    "move_up": ["Kubernetes platform"],
                    "reword": [
                        {"quote": "Ran the Kubernetes platform for 40 services at Acme.",
                         "suggestion": "Lead with the production path."},
                        {"quote": "Managed AWS spend", "suggestion": "Not in the resume."}]},
            }, *GUARD_OK), Store(cfg.db_path) as store:
                result = writer.review(cfg, store, uid, root=tmp)
                artifact = store.artifacts(uid, "resume_review")[0]
        finally:
            writer._settings = saved
        assert [h["quote"] for h in result.health] == [
            "Built CI pipelines in GitHub Actions", ""]
        assert len(result.alignment["reword"]) == 1
        assert result.dropped == 2
        assert "2 suggestion(s) were dropped" in result.text
        assert result.path.name == writer.REVIEW_FILE
        assert artifact["path"] == str(result.path)


def test_a_general_review_is_recorded_without_a_file_and_takes_feedback():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, _ = _setup(tmp)
        saved = _patched_settings()
        try:
            with _Script({"enough_evidence": False, "health": []}, *GUARD_OK), \
                    Store(cfg.db_path) as store:
                result = writer.review(cfg, store, root=tmp)
        finally:
            writer._settings = saved
        assert result.path is None and result.alignment is None
        assert "Not enough to review honestly" in result.text
        latest = api.latest_review(cfg)
        assert latest["id"] == result.output_id and latest["feedback"] is None
        assert api.feedback(cfg, result.output_id, -1)["feedback"] == -1
        assert api.feedback(cfg, result.output_id, 0)["feedback"] is None
        try:
            api.feedback(cfg, result.output_id, 3)
        except api.ApiError:
            pass
        else:
            raise AssertionError("feedback is 1, -1 or 0")


def test_a_guard_that_cannot_run_does_not_stop_the_letter():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        with Store(cfg.db_path) as store:
            row = store.get(uid)

        def flaky(*a, purpose="", **k):
            if purpose == "cover_letter":
                return {"paragraphs": ["I ran the Kubernetes platform at Acme."]}
            raise llm.LLMError("Ollama is not answering")

        saved = (writer.complete_json, guard.complete_json)
        writer.complete_json = guard.complete_json = flaky
        try:
            draft = writer.cover_letter(SETTINGS, row, RESUME)
        finally:
            writer.complete_json, guard.complete_json = saved
        gate = next(g for g in draft.gates if g.name == writer.GUARD_GATE)
        assert draft.text and not draft.guard.checked
        assert gate.passed and "not checked" in gate.detail


def test_a_tailored_resume_keeps_to_the_resume_and_is_named_for_the_role():
    tailored = {
        "stage": "experienced", "industry": "tech", "stage_reason": "Years of it.",
        "summary": "Platform engineer with seven years of Python and Go \u2014 "
                   "looking for platform work.",
        "skills": ["Kubernetes", "Python", "Go", "python", "GitHub Actions"],
        "experience": [
            {"title": "Platform engineer", "company": "Acme", "location": "",
             "start": "", "end": "", "bullets": [
                 "Ran the Kubernetes platform for 40 services.",
                 "Built CI pipelines in GitHub Actions."]},
            {"title": "Staff engineer", "company": "Globex", "location": "Berlin",
             "start": "Jan 2019", "end": "Dec 2020", "bullets": ["Led a team."]}],
        "education": [], "certifications": ["CKA"], "projects": []}
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        saved = _patched_settings()
        try:
            with _Script(tailored, *GUARD_OK) as script, Store(cfg.db_path) as store:
                result = writer.tailor(cfg, store, uid, root=tmp)
                artifact = store.artifacts(uid, "tailored_resume")[0]
        finally:
            writer._settings = saved
        assert script.purposes == ["tailored_resume", "guard_extract", "guard_verify"]
        assert result.pdf_path.name == "Jane_Doe_Platform_Engineer_Resume.pdf"
        assert result.pdf_path.read_bytes().startswith(b"%PDF-")
        assert result.path.suffix == ".md" and artifact["path"] == str(result.path)
        text = result.markdown
        assert text.startswith("# Jane Doe\n")
        assert "## PROFESSIONAL SUMMARY" in text and "\u2014" not in text
        assert "## SKILLS\nKubernetes | Python | Go | GitHub Actions\n" in text
        # Globex and the CKA are not in the resume: left out, and said so.
        assert "Globex" not in text and "CKA" not in text
        facts = next(g for g in result.gates if g.name == writer.FACTS_GATE)
        assert not facts.passed and len(facts.items) == 2

        body, name = api.artifact_pdf(cfg, result.artifact_id)
        assert name == result.pdf_path.name and body.startswith(b"%PDF-")
        # The same resume as Word, beside the PDF and from the page.
        assert result.docx_path.name == "Jane_Doe_Platform_Engineer_Resume.docx"
        assert result.docx_path.read_bytes().startswith(b"PK")
        body, name = api.artifact_docx(cfg, result.artifact_id)
        assert name == result.docx_path.name and body.startswith(b"PK")
        # Its own PDF, read back as a tracking system reads it.
        readback = next(g for g in result.gates if g.name == writer.READABLE_GATE)
        # Its own layout passes every check; what is said is about the test
        # resume's content (no email, phone, education or dates in it).
        assert "/100 when read back" in readback.detail
        content = ("Email and phone", "Standard section headings", "Dates")
        assert all(i.startswith(content) for i in readback.items), readback.items
        # A card on the Resume page: the job, its checks, its readability score.
        card = api.list_resumes(cfg)["resumes"][0]
        assert card["id"] == result.artifact_id and card["exists"] and card["kind"] == "tailored_resume"
        assert card["readable"] == int(readback.detail.split("/")[0]) and card["to_read"] >= 1
        assert card["docs"] == {}, "no other document for this job post yet"
        # The job post's other documents become the preview's tabs: the
        # newest of each kind.
        with Store(cfg.db_path) as store:
            store.add_artifact(uid, "cover_letter", str(Path(tmp) / "old.md"))
            newest = store.add_artifact(uid, "cover_letter", str(Path(tmp) / "new.md"))
            store.conn.commit()
        card = api.list_resumes(cfg)["resumes"][0]
        assert card["docs"] == {"cover_letter": newest}, card["docs"]
        fits = next(g for g in result.gates if g.name == writer.LENGTH_GATE)
        assert fits.passed and fits.detail.startswith("1 page, within the 1 Indeed suggests")


DATED = RESUME + "Platform engineer, Acme, March 2016 - April 2017\n"


def test_letters_and_resumes_get_the_measured_years_and_are_checked_with_them():
    """A model adding up dates gets the years wrong, and a check cannot
    confirm a total the resume never states: both are given the one the
    tool counted, as the judge is."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        with Store(cfg.db_path) as store:
            row = store.get(uid)
    seen = []

    def script(answers):
        def answer(settings, system, user, schema, purpose="", **_):
            seen.append((purpose, user))
            return answers.pop(0)
        return answer

    tailored = {**BASE, "stage": "experienced", "industry": "tech", "stage_reason": "",
                "projects": []}
    for write, first in ((writer.cover_letter, {"paragraphs": ["I ran it."]}),
                         (writer.tailored_resume, tailored)):
        saved = (writer.complete_json, guard.complete_json)
        writer.complete_json = guard.complete_json = script([first, *GUARD_OK])
        try:
            write(SETTINGS, row, DATED)
        finally:
            writer.complete_json, guard.complete_json = saved
    measured = "Work history in the resume: March 2016 to April 2017, 1 year 2 months"
    for purpose in ("cover_letter", "tailored_resume"):
        assert "<<MEASURED>>\n" + measured in dict(seen)[purpose], purpose
    checked = [user for purpose, user in seen if purpose == "guard_verify"]
    assert len(checked) == 2 and all(measured in user for user in checked)


def test_a_skill_the_resume_does_not_have_is_left_off_and_said_so():
    result = _tailor_with({**BASE, "stage": "experienced", "industry": "tech",
                           "stage_reason": "", "projects": [],
                           "skills": ["Kubernetes", "Django", "Python (Go)"]})
    assert "## SKILLS\nKubernetes | Python (Go)\n" in result.markdown
    facts = next(g for g in result.gates if g.name == writer.FACTS_GATE)
    assert not facts.passed and facts.items == ["skill: Django"]


def _tailor_with(answer, notes_rows=()):
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        saved = _patched_settings()
        try:
            with _Script(answer, *GUARD_OK), Store(cfg.db_path) as store:
                for fields in notes_rows:
                    store.save_project(fields)
                return writer.tailor(cfg, store, uid, root=tmp)
        finally:
            writer._settings = saved


BASE = {"summary": "Platform engineer with seven years of Python and Go.",
        "skills": ["Kubernetes", "Python", "Go"],
        "experience": [{"title": "Platform engineer", "company": "Acme", "location": "",
                        "start": "", "end": "", "bullets": ["Ran the Kubernetes platform."]}],
        "education": [], "certifications": []}


def test_an_experienced_person_gets_no_projects_section():
    result = _tailor_with({**BASE, "stage": "experienced", "industry": "tech",
                           "stage_reason": "Seven years of platform work.",
                           "projects": [{"name": "CI pipelines", "bullets": ["Built them."]}]})
    assert "PROJECTS" not in result.markdown
    gate = next(g for g in result.gates if g.name == writer.PROJECTS_GATE)
    assert gate.passed and "experienced" in gate.detail and "no projects section" in gate.detail


def test_a_career_changer_leads_with_projects_from_their_own_notes():
    notes = [{"name": "Kubernetes homelab", "tools": "k3s, Grafana",
              "situation": "Wanted to learn cluster operations.",
              "task": "Run my own services.", "action": "Built a three-node cluster.",
              "result": "Hosts 12 services with 99% uptime."}]
    result = _tailor_with({**BASE, "stage": "career_changer", "industry": "tech",
                           "stage_reason": "Moving from support into platform work.",
                           "projects": [
                               {"name": "Kubernetes homelab", "bullets": [
                                   "Built a three-node cluster that hosts 12 services with 99% uptime."]},
                               {"name": "Invented project", "bullets": ["Did things."]}]},
                          notes)
    md = result.markdown
    assert md.index("## TECHNICAL PROJECTS") < md.index("## EXPERIENCE")
    assert "Kubernetes homelab" in md and "Invented project" not in md
    # Figures from the notes are the person's own: not "unsupported".
    figures = next(g for g in result.gates if g.name == "unsupported figures")
    assert figures.passed, figures.detail
    facts = next(g for g in result.gates if g.name == writer.FACTS_GATE)
    assert "project: Invented project" in facts.items


def test_your_own_projects_are_shown_even_when_experienced_and_left_out_by_the_model():
    """2026-10-23: projects added on the Resume page are always shown, after
    the jobs for someone experienced, in the person's own words."""
    notes = [{"name": "Release notes newsletter", "kind": "Writing or articles",
              "role": "Editor", "link": "https://example.com/notes",
              "task": "Explain each platform release to 300 engineers.",
              "action": "Wrote a monthly issue from the changelog.",
              "result": "Read by 220 engineers a month."}]
    result = _tailor_with({**BASE, "stage": "experienced", "industry": "tech",
                           "stage_reason": "Seven years of platform work.",
                           "projects": []}, notes)
    md = result.markdown
    assert md.index("## EXPERIENCE") < md.index("## TECHNICAL PROJECTS")
    assert "### Release notes newsletter\nEditor | https://example.com/notes\n" in md
    assert "- Wrote a monthly issue from the changelog." in md
    assert "- Read by 220 engineers a month." in md
    gate = next(g for g in result.gates if g.name == writer.PROJECTS_GATE)
    assert "for the projects you added only" in gate.detail
    figures = next(g for g in result.gates if g.name == "unsupported figures")
    assert figures.passed, figures.detail


def test_a_project_the_resume_only_links_to_is_described_from_your_notes():
    notes = [{"name": "Kubernetes homelab", "link": "https://github.com/jane/homelab",
              "action": "Built a three-node cluster.", "result": "Hosts 12 services."}]
    result = _tailor_with({**BASE, "stage": "career_changer", "industry": "tech",
                           "stage_reason": "Moving into platform work.",
                           "projects": [{"name": "homelab", "bullets": [
                               "https://github.com/jane/homelab"]}]}, notes)
    md = result.markdown
    assert "### homelab" in md and "- Built a three-node cluster." in md
    assert "- https://github.com/jane/homelab" not in md


def test_with_more_projects_than_room_the_least_related_are_named():
    found = writer.with_own_projects([], [
        {"name": f"Bake sale {i}", "kind": "", "role": "", "tools": "", "link": "",
         "situation": "", "task": "", "action": "Sold cakes.", "result": ""}
        for i in range(3)] + [
        {"name": "Cluster upgrade", "kind": "", "role": "", "tools": "Kubernetes, Python",
         "link": "", "situation": "", "task": "", "action": "Upgraded the platform.",
         "result": ""}], ADVERT)
    assert found[0]["name"] == "Cluster upgrade" and all(p["own"] for p in found)


def _tailor_with_education(answer, entries):
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        saved = _patched_settings()
        try:
            with _Script(answer, *GUARD_OK), Store(cfg.db_path) as store:
                for fields in entries:
                    store.save_education(fields)
                return writer.tailor(cfg, store, uid, root=tmp)
        finally:
            writer._settings = saved


def test_education_added_on_the_resume_page_is_shown_newest_first():
    """2026-10-23: a resume written before a degree was finished."""
    result = _tailor_with_education(
        {**BASE, "stage": "experienced", "industry": "tech", "stage_reason": "Years.",
         "education": [{"credential": "BS Computer Science", "school": "Acme University",
                        "location": "", "start": "", "end": "2015"}],
         "projects": []},
        [{"credential": "MS Computer Science", "school": "Georgia Tech",
          "location": "Online", "end": "May 2026"},
         {"credential": "B.S. in Computer Science", "school": "Acme University",
          "end": "June 2015", "location": "Springfield"}])
    md = result.markdown
    edu = md[md.index("## EDUCATION"):]
    assert edu.index("### MS Computer Science") < edu.index("### B.S. in Computer Science")
    assert "Georgia Tech, Online" in edu and "Acme University, Springfield" in edu
    assert "### BS Computer Science" not in edu      # replaced by your own line
    facts = next(g for g in result.gates if g.name == writer.FACTS_GATE)
    assert not any("Georgia Tech" in i for i in facts.items), facts.items


def test_a_tutorial_project_is_flagged_not_hidden():
    notes = [{"name": "To-Do List App", "action": "Built a to-do list in React."}]
    result = _tailor_with({**BASE, "stage": "student", "industry": "tech",
                           "stage_reason": "A new graduate.",
                           "projects": [{"name": "To-Do List App",
                                         "bullets": ["Built a to-do list in React."]}]},
                          notes)
    assert "To-Do List App" in result.markdown
    gate = next(g for g in result.gates if g.name == writer.TUTORIAL_GATE)
    assert not gate.passed and gate.items == ["To-Do List App"]


def test_projects_are_saved_checked_and_flagged_through_the_api():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, _uid = _setup(tmp)
        for bad, why in (({"name": ""}, "name"),
                         ({"name": "X", "link": "javascript:alert(1)"}, "http")):
            try:
                api.save_project(cfg, bad)
            except api.ApiError as exc:
                assert why in str(exc)
            else:
                raise AssertionError(f"{bad} should be refused")
        saved = api.save_project(cfg, {"name": "Weather App", "tools": "React"})["project"]
        assert saved["tutorial"] is True
        changed = api.save_project(cfg, {"id": saved["id"], "name": "Flood alerts for 3 towns"})
        assert changed["project"]["tutorial"] is False
        listed = api.list_projects(cfg)
        assert [p["name"] for p in listed["projects"]] == ["Flood alerts for 3 towns"]
        assert listed["tutorial_pattern"]
        api.delete_project(cfg, saved["id"])
        assert api.list_projects(cfg)["projects"] == []


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
