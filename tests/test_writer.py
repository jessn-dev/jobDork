"""
The AI cover letter and résumé review: facts from the sources only, quotes
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
        assert not by_name["unsupported figures"].passed   # 300% is not in the résumé
        assert by_name[writer.GUARD_GATE].passed
        assert (output["kind"], output["uid"], output["checked"]) == \
            ("cover_letter", uid, 1)
        assert f'"output_id": {draft.output_id}' in artifact["gates_json"]


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
                        {"quote": "Managed AWS spend", "suggestion": "Not in the résumé."}]},
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
