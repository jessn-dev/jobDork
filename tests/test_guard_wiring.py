"""
The guard wired into judging, page reads and claude -p drafts: every AI
output is recorded, checked when the guard is on, and never blocked by it.
No live model.

    python tests/test_guard_wiring.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.ai import guard, judging, llm, writer
from jobdork.core.config import Config, Llm
from jobdork.db.store import Role, Store
from jobdork.search import listing
from jobdork.writing import gates, generate

RESUME = "Jane Doe. Seven years of Python. Ran Kubernetes at Acme."
ADVERT = "Platform engineer to run Kubernetes. Python required. " * 8

VERDICT = {"score": 82, "verdict": "strong", "summary": "Close match.",
           "reasons": ["Seven years of Python"], "concerns": ["No Go"],
           "enough_evidence": True, "model": "Ollama · m", "advert_chars": len(ADVERT),
           "at": "2026-09-28T10:00:00"}


def _setup(tmp: str, guard_on: bool = True):
    resume = Path(tmp) / "resume.md"
    resume.write_text(RESUME, encoding="utf-8")
    cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"),
                 resume_path=str(resume))
    cfg.llm = Llm(provider="ollama", model="m", guard=guard_on)
    role = Role(platform="greenhouse", company="Initech", title="Platform Engineer",
                url="https://boards.greenhouse.io/initech/jobs/1",
                location_raw="Remote", description=ADVERT)
    with Store(cfg.db_path) as store:
        store.upsert(role)
    return cfg, role.uid


class _Patch:
    def __init__(self, target, name, value):
        self.target, self.name, self.value = target, name, value

    def __enter__(self):
        self.saved = getattr(self.target, self.name)
        setattr(self.target, self.name, self.value)

    def __exit__(self, *exc):
        setattr(self.target, self.name, self.saved)


def _report(unsupported: int) -> guard.GuardReport:
    claims = [guard.ClaimCheck("Seven years of Python", "supported")]
    claims += [guard.ClaimCheck("Knows Go", "unsupported")] * unsupported
    return guard.GuardReport(checked=True, claims=claims)


def test_a_judged_verdict_carries_its_guard_and_output_row():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        seen = {}

        def fake_check(settings, text, sources):
            seen.update(text=text, sources=sources)
            return _report(1)
        with _Patch(judging, "judge", lambda *a: dict(VERDICT)), \
                _Patch(guard, "check", fake_check), Store(cfg.db_path) as store:
            report = judging.run(cfg, store, uid=uid)
            stored = json.loads(store.get(uid)["llm_judgement"])
            output = store.ai_output(stored["ai_output_id"])
        assert report.judged == 1 and report.flagged == 1
        assert "claim the advert and résumé do not support" in " ".join(report.lines())
        assert stored["guard"]["unsupported"] == 1
        assert seen["text"].splitlines() == ["Close match.", "Seven years of Python",
                                             "No Go"]
        assert seen["sources"]["advert"].startswith("Role: Platform Engineer")
        assert (output["kind"], output["checked"], output["unsupported"]) == ("judge", 1, 1)


def test_with_the_guard_off_a_verdict_is_still_recorded_but_not_checked():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp, guard_on=False)

        def must_not_run(*a):
            raise AssertionError("the guard is off")
        with _Patch(judging, "judge", lambda *a: dict(VERDICT)), \
                _Patch(guard, "check", must_not_run), Store(cfg.db_path) as store:
            judging.run(cfg, store, uid=uid)
            stored = json.loads(store.get(uid)["llm_judgement"])
            output = store.ai_output(stored["ai_output_id"])
        assert "guard" not in stored and output["checked"] == 0
        assert guard.settings_for(cfg) is None


def test_a_model_that_says_it_cannot_judge_is_recorded_as_such():
    raw = dict(VERDICT, enough_evidence=False)
    assert llm._clean_judgement(raw, llm.Settings("ollama", "m"), 900)[
        "enough_evidence"] is False
    old = {k: v for k, v in VERDICT.items() if k != "enough_evidence"}
    assert llm._clean_judgement(old, llm.Settings("ollama", "m"), 900)[
        "enough_evidence"] is True


class _Settings:
    label = "test model"

    def problem(self):
        return ""


def test_each_page_read_is_an_output_checked_by_its_quote():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        with Store(cfg.db_path) as store:
            checker = listing.Checker(None, _Settings(), read_pages=True, store=store)
            for evidence in ("we stopped hiring", "Sorry, this job is gone"):
                with _Patch(llm, "classify_listing",
                            lambda *_, e=evidence: {"state": "closed", "evidence": e}):
                    checker._ask("Engineer", "<p>We stopped hiring.</p>", uid)
            with _Patch(llm, "classify_listing",
                        lambda *_: {"state": "unknown", "evidence": ""}):
                checker._ask("Engineer", "<p>Hello</p>", uid)
            rows = store.conn.execute(
                "SELECT kind, claims, unsupported, checked FROM ai_outputs "
                "ORDER BY id").fetchall()
        assert [tuple(r) for r in rows] == [("page_read", 1, 0, 1),
                                            ("page_read", 1, 1, 1),
                                            ("page_read", 0, 0, 1)]


def test_a_draft_is_recorded_with_its_guard_gate_pointing_at_the_output():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp)
        path = Path(tmp) / "CV.md"
        path.write_text("CV", encoding="utf-8")
        report = _report(2)
        result = generate.Result(kind="cv", folder=Path(tmp), path=path, text="CV",
                                 gates=[gates.not_empty("CV"),
                                        writer.guard_gate(report)],
                                 guard=report)
        unchecked = generate.Result(kind="screen", folder=Path(tmp), path=path,
                                    text="notes", gates=[gates.not_empty("notes")])
        with Store(cfg.db_path) as store:
            row = store.get(uid)
            summary = generate.record(store, row, result)
            generate.record(store, row, unchecked)
            outputs = store.conn.execute(
                "SELECT id, kind, model, unsupported, checked FROM ai_outputs "
                "ORDER BY id").fetchall()
            kinds = [a["kind"] for a in store.artifacts(uid)]
        first = outputs[0]
        assert summary[writer.GUARD_GATE]["output_id"] == first["id"]
        assert not summary[writer.GUARD_GATE]["passed"]
        assert (first["kind"], first["model"], first["unsupported"], first["checked"]) \
            == ("draft", "claude -p", 2, 1)
        assert outputs[1]["checked"] == 0              # counts against coverage
        assert sorted(kinds) == ["cv", "screen"]


def test_the_page_can_rate_a_verdict_and_any_draft_checked_or_not():
    from jobdork.web import api

    with tempfile.TemporaryDirectory() as tmp:
        cfg, uid = _setup(tmp, guard_on=False)
        with _Patch(judging, "judge", lambda *a: dict(VERDICT)), Store(cfg.db_path) as store:
            judging.run(cfg, store, uid=uid)
            path = Path(tmp) / "screen.md"
            path.write_text("notes", encoding="utf-8")
            generate.record(store, store.get(uid), generate.Result(
                kind="screen", folder=Path(tmp), path=path, text="notes",
                gates=[gates.not_empty("notes")]))
            output_id = store.conn.execute(
                "SELECT id FROM ai_outputs WHERE kind = 'draft'").fetchone()[0]
            store.set_feedback(output_id, -1)
        detail = api.role_detail(cfg, uid)
        assert detail["ai"]["feedback"] is None
        api.feedback(cfg, detail["ai"]["ai_output_id"], 1)
        assert api.role_detail(cfg, uid)["ai"]["feedback"] == 1

        artifact = detail["artifacts"][0]
        assert "_output" not in artifact["gates"]           # not shown as a gate
        doc = api.artifact_text(cfg, artifact["id"])
        assert "_output" not in doc["gates"]
        assert doc["output"] == {"id": output_id, "feedback": -1}


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
