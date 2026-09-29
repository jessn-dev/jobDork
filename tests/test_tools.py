"""
The AI tools for resumes and cover letters: whatever a script cannot find
where the model said it came from is dropped, wording is humanized, claims
are guarded, and each result is recorded and kept beside the job. No live
model: its answers are scripted.

Also the privacy rule: a hosted model never sees an email or phone number.

    python tests/test_tools.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.ai import guard, llm, tools, writer
from jobdork.core.config import Config
from jobdork.db.store import Role, Store
from jobdork.web import api

RESUME = """Jane Doe · jane@example.com · +1 (312) 555-0199
Platform engineer. Seven years of Python and Go.
- Ran the Kubernetes platform for 40 services at Acme.
- Built CI pipelines in GitHub Actions.
- Wrote runbooks for the on-call rotation.
"""

ADVERT = ("We are hiring a platform engineer to run Kubernetes for our product "
          "teams. You will own CI/CD, on-call and the path to production. Python "
          "or Go required; Terraform a plus. Experience with incident response. " * 2)


class _Ready(llm.Settings):
    def problem(self):
        return ""


SETTINGS = _Ready("ollama", "m")
GUARD_OK = ({"claims": ["Jane ran Kubernetes for 40 services"]},
            {"results": [{"claim": "Jane ran Kubernetes for 40 services",
                          "verdict": "supported", "source": "resume",
                          "quote": "Ran the Kubernetes platform for 40 services"}]})


class _Script:
    """Stand-in for complete_json in tools and guard, answering in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.users = []

    def __call__(self, settings, system, user, *a, purpose="", **k):
        self.users.append(user)
        return self.answers.pop(0)

    def __enter__(self):
        self.saved = (tools.complete_json, guard.complete_json)
        tools.complete_json = guard.complete_json = self
        return self

    def __exit__(self, *exc):
        tools.complete_json, guard.complete_json = self.saved


def _row():
    return {"uid": "abc123def456", "title": "Platform Engineer", "company": "Initech",
            "description": ADVERT, "location_raw": "Remote", "url": "https://x.test/1"}


def test_tailored_edits_must_quote_a_real_line_and_keep_its_figures():
    with _Script({"edits": [
            {"quote": "Ran the Kubernetes platform for 40 services at Acme.",
             "suggestion": "Ran the Kubernetes platform for 40 product services at Acme, on call for it.",
             "why": "The ad wants someone to run Kubernetes."},
            {"quote": "Led a team of 12 SREs.",                     # not in the resume
             "suggestion": "Led 12 SREs.", "why": "Leadership."},
            {"quote": "Built CI pipelines in GitHub Actions.",
             "suggestion": "Built CI/CD pipelines in GitHub Actions for 300 repositories.",
             "why": "The ad says CI/CD."}],
            "move_up": ["Built CI pipelines in GitHub Actions.", "Won an award."]},
            *GUARD_OK):
        result = tools.tailor_resume(SETTINGS, _row(), RESUME)
    edits = result.data["edits"]
    assert [e["quote"][:10] for e in edits] == ["Ran the Ku", "Built CI p"]
    assert result.dropped == 2                  # the invented line, the invented move
    assert edits[0]["new_figures"] == []
    assert edits[1]["new_figures"], "300 is not in the resume"
    # The skills line is the script's: in the ad and on the resume.
    assert "Kubernetes" in result.data["skills"] and "Python" in result.data["skills"]
    assert "Terraform" in result.data["missing"]
    assert result.guard.checked


def test_an_edit_that_swaps_a_tool_or_rewrites_another_line_is_marked():
    """Both seen in a live run: Datadog became Splunk, and an Oracle support
    line came back as a sentence about on-call rotations."""
    resume = RESUME + "- Began a monitoring model using Datadog.\n- Provided Oracle database support.\n"
    with _Script({"edits": [
            {"quote": "Began a monitoring model using Datadog.",
             "suggestion": "Implemented a monitoring model using Splunk.", "why": "SIEM."},
            {"quote": "Provided Oracle database support.",
             "suggestion": "Resolved production issues during on-call rotations.", "why": "On-call."},
            {"quote": "Built CI pipelines in GitHub Actions.",
             "suggestion": "Built CI pipelines in GitHub Actions for product teams.", "why": "CI."}],
            "move_up": []},
            {"claims": ["Jane implemented a monitoring model using Splunk"]},
            {"results": [{"claim": "Jane implemented a monitoring model using Splunk",
                          "verdict": "unsupported", "source": "", "quote": ""}]}):
        result = tools.tailor_resume(SETTINGS, _row(), resume)
    splunk, oracle, ci = result.data["edits"]
    assert any("Splunk" in p for p in splunk["problems"])
    assert any("Not supported" in p for p in splunk["problems"])
    assert any("different line" in p for p in oracle["problems"])
    assert ci["problems"] == []


def test_an_edit_may_not_make_unfinished_or_shared_work_sound_finished_and_solo():
    """Seen live: "Designed and began implementing" became "Implemented"."""
    assert any("began" in p for p in tools._edit_problems(
        "Designed and began implementing a hybrid monitoring model using Datadog and Splunk.",
        "Implemented a hybrid monitoring model using Splunk for SIEM."))
    assert any("with the other" in p for p in tools._edit_problems(
        "Handled code reviews with the other senior developer.",
        "Led code reviews for the team."))
    # A fair condensation of a long line is not "a different line".
    assert tools._edit_problems(
        "Handled code reviews and technical documentation, built a training module "
        "on the team's API standards, and documented all APIs I wrote for handoff.",
        "Handled code reviews and technical documentation for the team's APIs.") == []


def test_keywords_not_in_the_ad_are_dropped_and_found_is_decided_by_script():
    with _Script({"keywords": ["Kubernetes", "Terraform", "Rust", "Python", "incident response"]}):
        result = tools.ats_keywords(SETTINGS, _row(), RESUME)
    rows = {r["keyword"]: r["in_resume"] for r in result.data["keywords"]}
    assert "Rust" not in rows and result.dropped == 1
    assert rows == {"Kubernetes": True, "Terraform": False, "Python": True,
                    "incident response": False}


def test_highlight_quotes_are_checked_and_flagged_verbs_are_dropped():
    with _Script({"skills": [{"skill": "Kubernetes", "ad_quote": "run Kubernetes for our product teams"},
                             {"skill": "Rust", "ad_quote": "Rust expert"}],
                  "experiences": [{"skill": "Kubernetes", "why": "Direct match.",
                                   "quote": "Ran the Kubernetes platform for 40 services at Acme."}],
                  "verbs": ["Ran", "Built", "Showcased", "leveraged", "two words"]},
                 *GUARD_OK):
        result = tools.highlight(SETTINGS, _row(), RESUME)
    assert [s["skill"] for s in result.data["skills"]] == ["Kubernetes"]
    assert result.dropped == 1
    assert result.data["verbs"] == ["Ran", "Built"]


def test_feedback_on_a_letter_quotes_the_letter_and_the_ad():
    letter = "I ran Kubernetes for 40 services and I like on-call work."
    with _Script({"summary": "A solid case. Say more about CI/CD.",
                  "strengths": [{"point": "Direct Kubernetes experience",
                                 "quote": "I ran Kubernetes for 40 services"},
                                {"point": "Loves Rust", "quote": "I love Rust"}],
                  "gaps": [{"point": "No Terraform", "ad_quote": "Terraform a plus"},
                           {"point": "No PhD", "ad_quote": "PhD required"}]},
                 *GUARD_OK):
        result = tools.feedback(SETTINGS, _row(), RESUME, letter=letter)
    assert result.data["target"] == "cover letter"
    assert len(result.data["strengths"]) == 1 and len(result.data["gaps"]) == 1
    assert result.dropped == 2


def test_revisions_mark_a_figure_the_text_did_not_have():
    with _Script({"versions": ["Ran Kubernetes for 40 services.",
                               "Ran Kubernetes for 400 services."]}, *GUARD_OK):
        result = tools.revise(SETTINGS, _row(), RESUME,
                              "Ran the Kubernetes platform for 40 services at Acme.")
    versions = result.data["versions"]
    assert versions[0]["new_figures"] == [] and versions[1]["new_figures"]
    assert all("problems" in v for v in versions)
    assert result.data["what"] == "resume bullet"


def test_a_tool_run_is_recorded_and_kept_beside_the_job():
    with tempfile.TemporaryDirectory() as tmp:
        resume = Path(tmp) / "resume.md"
        resume.write_text(RESUME, encoding="utf-8")
        cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"),
                     resume_path=str(resume))
        role = Role(platform="greenhouse", company="Initech", title="Platform Engineer",
                    url="https://boards.greenhouse.io/initech/jobs/1",
                    location_raw="Remote", description=ADVERT)
        with Store(cfg.db_path) as store:
            store.upsert(role)
        saved = writer._settings
        writer._settings = lambda cfg: SETTINGS
        import jobdork.writing.generate as gen
        saved_root = gen.default_root
        gen.default_root = lambda: tmp
        try:
            with _Script({"keywords": ["Kubernetes", "Terraform"]}), Store(cfg.db_path) as store:
                tools.run(cfg, store, role.uid, "keywords")
                output = store.conn.execute(
                    "SELECT kind, text FROM ai_outputs").fetchone()
        finally:
            writer._settings = saved
            gen.default_root = saved_root
        assert tuple(output) == ("keywords", "Kubernetes, Terraform")
        latest = api.latest_tools(cfg, role.uid)["tools"]["keywords"]
        assert [r["keyword"] for r in latest["data"]["keywords"]] == ["Kubernetes", "Terraform"]


def test_a_hosted_model_never_sees_contact_details():
    text = llm.redact(RESUME + "\nLinkedIn: https://linkedin.com/in/jane-doe")
    assert "jane@example.com" not in text and "555-0199" not in text
    assert "linkedin.com/in/jane-doe" not in text
    assert "40 services" in text and "Seven years" in text
    # Year ranges, figures and standards are not phone numbers.
    for keep in ("Worked 2019-2023", "1,200 hosts", "NIST 800-53", "140,000 - 170,000"):
        assert llm.redact(keep) == keep, keep


def test_the_privacy_rule_applies_to_hosted_providers_only():
    seen = {}

    def fake(provider):
        def call(s, system, user, schema, max_tokens):
            seen[provider] = user
            return json.dumps({"ok": True})
        return call

    saved = {n: getattr(llm, n) for n in ("_ollama", "_anthropic")}
    llm._ollama, llm._anthropic = fake("ollama"), fake("anthropic")

    class Ready(llm.Settings):
        def problem(self):
            return ""
    try:
        for provider in ("ollama", "anthropic"):
            llm.complete_json(Ready(provider, "m"), "sys", "Reach me at jane@example.com",
                              {"type": "object"})
    finally:
        for n, f in saved.items():
            setattr(llm, n, f)
    assert "jane@example.com" in seen["ollama"]
    assert "jane@example.com" not in seen["anthropic"]


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
