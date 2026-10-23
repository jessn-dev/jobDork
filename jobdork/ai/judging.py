"""
jobdork.ai.judging
==================
Has the configured model read the best roles against your resume.

The resume is read with the projects and education added on the Resume
page. Bounded by `llm.judge_top` (or an explicit limit): roles are taken best
match first, duplicates collapsed, and only those with enough advert to read
and no verdict on their current advert. A role whose advert grew — pasted in,
or fetched by enrich — is judged again, because the old verdict was on text
it no longer has.

The verdict is stored beside the rule score and never replaces it, and it
never hides a role.

With `llm.guard` on, each verdict's summary, reasons and concerns are checked
against the advert and the resume (guard.py), and the result is stored inside
the verdict (`guard`) and as an `ai_outputs` row (`ai_output_id`). A claim
neither source supports is shown struck out; the score is left as the model
gave it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from ..core import telemetry
from ..db import grouping
from ..search import freshness
from ..writing import resume_doc
from . import guard
from .llm import LLMError, Settings, judge

log = logging.getLogger("jobdork.ai.judging")

MIN_ADVERT = 200


@dataclass
class JudgeReport:
    judged: int = 0
    flagged: int = 0                   # verdicts with a claim no source supports
    failed: list[str] = field(default_factory=list)
    skipped_thin: int = 0
    model: str = ""
    disagreed: int = 0                 # the second model scored it 20+ apart

    def lines(self) -> list[str]:
        out = [f"{self.model}: judged {self.judged}"]
        if self.flagged:
            out.append(f"{self.flagged} with a claim the advert and resume do "
                       "not support")
        if self.disagreed:
            out.append(f"{self.disagreed} where the second model disagrees")
        if self.skipped_thin:
            out.append(f"{self.skipped_thin} skipped, advert too short to judge")
        if self.failed:
            out.append(f"{len(self.failed)} failed")
        return out


def _stale(row) -> bool:
    try:
        old = json.loads(row["llm_judgement"] or "null")
    except (json.JSONDecodeError, TypeError):
        return True
    return not old or old.get("advert_chars") != len(row["description"] or "")


def run(cfg, store, limit: int = 0, uid: str = "", force: bool = False,
        progress=None) -> JudgeReport:
    from ..search import resume as resume_mod

    settings = Settings.from_config(cfg)
    problem = settings.problem()
    if problem:
        raise LLMError(problem)
    if not cfg.resume_path:
        raise LLMError("no resume configured. Upload one on the Resume page")
    resume_text = resume_mod.load(cfg.resume_path).text
    # What the person added on the Resume page: read with the resume, and
    # accepted by the claim check as part of their record.
    notes = resume_doc.record_notes(store.projects(), store.education())
    record = resume_text + ("\n\n" + notes if notes else "")

    report = JudgeReport(model=settings.label + (
        f", checked by {settings.usable_checker().label}"
        if settings.usable_checker() else ""))
    if uid:
        row = store.get(uid)
        rows = [row] if row is not None else []
        force = True
    else:
        rows = store.list_roles()                 # best first, dupes collapsed
    limit = limit or cfg.llm.judge_top
    telemetry.tick(total=1 if uid else limit)

    for row in rows:
        if report.judged + len(report.failed) >= limit:
            break
        if len(row["description"] or "") < MIN_ADVERT:
            report.skipped_thin += 1
            telemetry.tick(count="too short to judge")
            continue
        if not force and not _stale(row):
            continue
        if progress:
            progress(f"  reading {row['uid']}  {(row['title'] or '')[:50]}")
        role = {"title": row["title"], "company": row["company"],
                "location": row["location_raw"], "description": row["description"],
                # Measured here, from the board's dates: the model has no clock.
                "posting": freshness.prompt_block(
                    row["posted_at"] or "",
                    grouping.earliest_seen(store.conn, uid=row["uid"]), cfg.freshness)}
        try:
            verdict = judge(settings, role, resume_text, notes)
        except LLMError as exc:
            report.failed.append(row["uid"])
            telemetry.tick(done=report.judged + len(report.failed), count="failed")
            if progress:
                progress(f"  failed   {row['uid']}: {exc}")
            # A refused key or a stopped Ollama fails every role the same way.
            if "key was refused" in str(exc) or "not answering" in str(exc) \
                    or "could not reach" in str(exc):
                raise
            continue
        second_opinion(settings, role, resume_text, verdict, notes)
        if verdict.get("disagree"):
            report.disagreed += 1
            telemetry.tick(count="models disagree")
        check_verdict(settings, store, row, verdict, record,
                      enabled=cfg.llm.guard)
        if verdict.get("guard", {}).get("unsupported"):
            report.flagged += 1
            telemetry.tick(count="unsupported claims")
        store.set_judgement(row["uid"], verdict)
        report.judged += 1
        telemetry.tick(done=report.judged + len(report.failed),
                       count=verdict["verdict"])
        if progress:
            second = verdict.get("second") or {}
            also = (f"  (second model: {second['score']}"
                    f"{', disagrees' if verdict.get('disagree') else ''})"
                    if "score" in second else "")
            progress(f"  {verdict['score']:>3} {verdict['verdict']:<8} "
                     f"{row['uid']}  {verdict['summary'][:80]}{also}")
    return report


# Points apart, out of 100, at which the two models' scores are called a
# disagreement: more than one verdict band (llm.verdict_for) is 30.
DISAGREE_POINTS = 20


def second_opinion(settings, role: dict, resume_text: str, verdict: dict,
                   notes: str = "") -> None:
    """The second model scores the same job post; adds `second` and `disagree`.

    Never blocks the verdict: a failure is recorded on it, and the first
    model's score stands either way.
    """
    checker = settings.usable_checker()
    if checker is None:
        return
    try:
        other = judge(checker, role, resume_text, notes)
    except LLMError as exc:
        verdict["second"] = {"model": checker.label, "error": str(exc)[:300]}
        return
    verdict["second"] = {"model": checker.label, "score": other["score"],
                         "verdict": other["verdict"], "summary": other["summary"]}
    verdict["disagree"] = abs(other["score"] - verdict["score"]) >= DISAGREE_POINTS


def verdict_text(verdict: dict) -> str:
    """The prose of a verdict, one statement per line, as the guard reads it."""
    return "\n".join([verdict.get("summary", ""), *verdict.get("reasons", []),
                      *verdict.get("concerns", [])]).strip()


def check_verdict(settings, store, row, verdict: dict, resume_text: str,
                  enabled: bool = True) -> None:
    """Guard one verdict and record it. Adds `guard` and `ai_output_id` to it."""
    text = verdict_text(verdict)
    if enabled:
        report = guard.check(settings, text, {"advert": guard.advert_source(row),
                                              "resume": resume_text})
        verdict["guard"] = report.to_dict()
    verdict["ai_output_id"] = store.add_ai_output(
        "judge", text, uid=row["uid"], model=settings.label,
        guard=verdict.get("guard"))
