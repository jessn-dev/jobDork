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
import re
from dataclasses import dataclass, field

from ..core import telemetry
from ..db import grouping
from ..search import freshness
from ..writing import resume_doc
from . import guard
from .llm import LLMError, Settings, judge, rewrite_summary

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
    # "Title, Company" of each post judged, in order: the run's summary names
    # them, so a run is not only a count (2026-11-10).
    names: list[str] = field(default_factory=list)
    rewritten: int = 0                 # verdicts written again with fewer flags (rewrite)

    NAMED = 5                          # named in the summary; the rest counted

    def lines(self) -> list[str]:
        out = [f"{self.model}: judged {self.judged}"]
        if self.names:
            more = len(self.names) - self.NAMED
            out.append("; ".join(self.names[:self.NAMED])
                       + (f"; and {more} more (Job posts, AI-judged: in the last run)"
                          if more > 0 else ""))
        if self.flagged:
            out.append(f"{self.flagged} with a claim the advert and resume do "
                       "not support")
        if self.rewritten:
            out.append(f"{self.rewritten} written again without the claims flagged")
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
    # Counted from the resume's dates here, not added up by the model.
    span = resume_mod.work_span(resume_text)
    work = span.line() if span else ""
    # What the person added on the Resume page: read with the resume, and
    # accepted by the claim check as part of their record.
    notes = resume_doc.store_notes(store)
    record = resume_text + ("\n\n" + notes if notes else "")

    checker = settings.checker_chain()
    report = JudgeReport(model=settings.label + (
        f", checked by {checker.label}" if checker else ""))
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
                    grouping.earliest_seen(store.conn, uid=row["uid"]), cfg.freshness),
                "work": work}
        try:
            verdict = judge_checked(settings, role, resume_text, notes)
        except LLMError as exc:
            report.failed.append(row["uid"])
            telemetry.tick(done=report.judged + len(report.failed), count="failed")
            if progress:
                progress(f"  failed   {row['uid']}: {exc}")
            # A refused key, a stopped Ollama or a free allowance spent (by
            # every reader) fails every role the same way.
            if "key was refused" in str(exc) or "not answering" in str(exc) \
                    or "could not reach" in str(exc) or "rate limited" in str(exc):
                raise
            continue
        second_opinion(settings, role, resume_text, verdict, notes)
        if verdict.get("disagree"):
            report.disagreed += 1
            telemetry.tick(count="models disagree")
        check_verdict(settings, store, row, verdict, record,
                      enabled=cfg.llm.guard, posting=role["posting"], work=work)
        if cfg.llm.guard and cfg.llm.rewrite:
            better = rewrite(settings, store, row, role, verdict, resume_text, record,
                             notes, work)
            if better is not verdict:
                verdict = better
                report.rewritten += 1
                telemetry.tick(count="written again")
        if verdict.get("guard", {}).get("unsupported"):
            report.flagged += 1
            telemetry.tick(count="unsupported claims")
        store.set_judgement(row["uid"], verdict)
        report.judged += 1
        report.names.append(", ".join(x for x in ((row["title"] or "").strip(),
                                                  (row["company"] or "").strip()) if x))
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
    checker = settings.checker_chain()
    if checker is None:
        return
    try:
        # The chosen checkers in order: the next scores when one cannot.
        other = judge(checker, role, resume_text, notes)
    except LLMError as exc:
        verdict["second"] = {"model": checker.label, "error": str(exc)[:300]}
        return
    verdict["second"] = {"model": checker.label, "score": other["score"],
                         "verdict": other["verdict"], "summary": other["summary"]}
    verdict["disagree"] = abs(other["score"] - verdict["score"]) >= DISAGREE_POINTS


def false_gaps(verdict: dict, record: str) -> list[str]:
    """What the verdict's concerns call missing that the resume has.

    Models wrote "the resume does not mention Linux" over a skills line
    listing Linux (8 of 50 flags on 2026-10-26, across five resumes). The
    script that checks a gap settles these for certain.
    """
    return [found for c in verdict.get("concerns", [])
            if (found := guard.gap_filled(c, record))]


def correct_false_gaps(verdict: dict, record: str) -> list[str]:
    """Turn each false gap into what it is, a match: the concern goes, and
    "The resume lists Linux." becomes a reason, which the guard checks like
    any other. Returns what was found; `found` on the verdict keeps it."""
    found = []
    keep = []
    for concern in verdict.get("concerns", []):
        thing = guard.gap_filled(concern, record)
        if thing:
            found.append(thing)
        else:
            keep.append(concern)
    if found:
        verdict["concerns"] = keep
        verdict["reasons"] = [*verdict.get("reasons", []),
                              *(f"The resume lists {t}." for t in found)]
        verdict["found"] = list(dict.fromkeys([*verdict.get("found", []), *found]))
    return found


def judge_checked(settings, role: dict, resume_text: str, notes: str = "") -> dict:
    """judge(), then once more when it called missing what the resume has.

    A gap that was not one also pulled the score down, so the reader is told
    what the tool found (<<FOUND>>) and scores again; whatever it still gets
    wrong is turned into a reason (correct_false_gaps). One extra call, only
    for a verdict with a false gap.
    """
    record = resume_text + ("\n\n" + notes if notes else "")
    verdict = judge(settings, role, resume_text, notes)
    found = false_gaps(verdict, record)
    if found:
        try:
            again = judge(settings, {**role, "found": "\n".join(
                f"- the resume lists {t}" for t in found)}, resume_text, notes)
        except LLMError:
            again = None
        if again is not None:
            again["rescored_from"] = verdict["score"]
            verdict = again
            verdict["found"] = found
    correct_false_gaps(verdict, record)
    return verdict


def verdict_text(verdict: dict) -> str:
    """The prose of a verdict, one statement per line, as the guard reads it."""
    return "\n".join([verdict.get("summary", ""), *verdict.get("reasons", []),
                      *verdict.get("concerns", [])]).strip()


def guard_sources(row, resume_text: str, posting: str = "",
                  work: str = "") -> dict[str, str]:
    """What a verdict is checked against: what its model was given, the
    measured work history with the resume it was counted from. The work
    history goes first, so no cut can take it: after a long resume it was
    cut off, and "10 years 10 months of work" was flagged (2026-11-10)."""
    return {"advert": guard.advert_source(row, posting),
            "resume": (f"{work}\n\n" if work else "") + resume_text}


# What a verdict that lost to its rewrite (or a rewrite that did not beat
# it) is recorded as: kept for the numbers, left out of the Dashboard's
# hallucination rate, which counts what you are shown.
DRAFT = "judge_draft"


# Words too common to tell one sentence of a verdict from another.
_COMMON = frozenset(["a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with", "by", "from", "as", "is", "are", "was", "were", "be", "been", "has", "have", "had", "does", "do", "did", "not", "no", "candidate", "candidates", "resume", "shows", "lists", "mentions", "experience", "their", "they", "this", "that", "it", "its", "which", "who", "required", "requirement", "requirements", "role", "job"])


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#./-]+", (text or "").lower())
            if len(w) > 1 and w not in _COMMON}


def _source_of(claim: str, sentences: list[str]) -> int:
    """Which sentence of the verdict a claim was split from: the one sharing
    most of its words, when that is at least half of them; -1 for none."""
    words = _words(claim)
    if not words:
        return -1
    scores = [len(words & _words(s)) / len(words) for s in sentences]
    best = max(range(len(sentences)), key=scores.__getitem__, default=-1)
    return best if best >= 0 and scores[best] >= 0.5 else -1


def rewrite(settings, store, row, role: dict, verdict: dict, resume_text: str,
            record: str, notes: str = "", work: str = "") -> dict:
    """The verdict, or a version without its flagged claims when that one
    flags fewer.

    The reasons and concerns the flagged claims were split from are taken
    out by script; when one came from the summary, the reader writes that
    one sentence again without it (llm.rewrite_summary). The result is
    checked as the first was; the better one is kept and shown, the other
    recorded as a draft. Nothing to take out, a summary that cannot be
    written again, or as many flags as before leave the verdict as it was."""
    first = verdict.get("guard") or {}
    flagged = [c["claim"] for c in first.get("flagged") or [] if c.get("claim")]
    if not (first.get("checked") and flagged):
        return verdict
    again = revise(settings, role, resume_text, verdict, flagged, notes, uid=row["uid"])
    if again is None:
        return verdict
    check_verdict(settings, store, row, again, record, enabled=True,
                  posting=role.get("posting", ""), work=work)
    second = again.get("guard") or {}
    if second.get("checked") and second.get("claims") \
            and second.get("unsupported", 0) < first.get("unsupported", 0):
        store.set_ai_output_kind(verdict["ai_output_id"], DRAFT)
        again["rewritten"] = {"flagged_before": first.get("unsupported", 0),
                              "flagged_after": second.get("unsupported", 0)}
        return again
    store.set_ai_output_kind(again["ai_output_id"], DRAFT)
    return verdict


def revise(settings, role: dict, resume_text: str, verdict: dict, flagged: list[str],
           notes: str = "", uid: str = "") -> dict | None:
    """The verdict without what `flagged` came from, unchecked; None when
    nothing could be taken out or the summary could not be written again.
    The benchmark measures with this as a scan runs it."""
    items = [("summary", 0, verdict.get("summary") or "")]
    items += [(key, i, text) for key in ("reasons", "concerns")
              for i, text in enumerate(verdict.get(key) or [])]
    hits: dict[int, list[str]] = {}
    for claim in flagged:
        at = _source_of(claim, [text for _, _, text in items])
        if at >= 0:
            hits.setdefault(at, []).append(claim)
    if not hits:
        return None
    again = {**verdict}
    for key in ("reasons", "concerns"):
        again[key] = [text for (k, i, text) in items[1:] if k == key
                      and items.index((k, i, text)) not in hits]
    if 0 in hits:
        try:
            summary = rewrite_summary(settings, role, resume_text, verdict.get("summary") or "",
                                      hits[0], notes)
        except LLMError as exc:
            log.info("summary of %s not written again: %s", uid, exc)
            summary = ""
        if not summary:
            return None
        again["summary"] = summary
    again.pop("guard", None)
    again.pop("ai_output_id", None)
    return again


def check_verdict(settings, store, row, verdict: dict, resume_text: str,
                  enabled: bool = True, posting: str = "", work: str = "") -> None:
    """Guard one verdict and record it. Adds `guard` and `ai_output_id` to it."""
    text = verdict_text(verdict)
    stored = None
    if enabled:
        report = guard.check(settings, text,
                             guard_sources(row, resume_text, posting, work), work=work)
        verdict["guard"] = report.to_dict()
        stored = report.to_dict(with_pending=True)
    verdict["ai_output_id"] = store.add_ai_output(
        "judge", text, uid=row["uid"], model=settings.label, guard=stored)
