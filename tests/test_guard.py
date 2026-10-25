"""
Hallucination guardrail: claims are checked against the source, and a model's
"supported" only counts with a quote that is really in that source.

    python tests/test_guard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.ai import guard, llm

RESUME = "Seven years of Python. Led a team of four at Acme. Built CI with Jenkins."


class _Ready(llm.Settings):
    def problem(self):
        return ""


def _fake(answers):
    calls = iter(answers)
    return lambda *a, **k: next(calls)


def test_a_supported_claim_needs_a_quote_found_in_the_source():
    original = guard.complete_json
    guard.complete_json = _fake([
        {"claims": ["Has seven years of Python", "Led a team of ten",
                    "Built CI with Jenkins"]},
        {"results": [
            {"claim": "Has seven years of Python", "verdict": "supported",
             "source": "resume", "quote": "Seven years of Python"},
            {"claim": "Led a team of ten", "verdict": "supported",
             "source": "resume", "quote": "Led a team of ten"},
            {"claim": "Built CI with Jenkins", "verdict": "unsupported",
             "source": "", "quote": ""},
        ]},
    ])
    try:
        report = guard.check(_Ready("ollama", "m"), "letter text", {"resume": RESUME})
    finally:
        guard.complete_json = original
    assert report.checked and len(report.claims) == 3
    flagged = {c.claim for c in report.unsupported}
    assert flagged == {"Led a team of ten", "Built CI with Jenkins"}
    assert abs(report.rate - 2 / 3) < 1e-9


def test_support_from_several_places_is_quoted_in_parts():
    """Skills listed in different sections of a resume are still supported,
    but every excerpt must be found."""
    original = guard.complete_json
    guard.complete_json = _fake([
        {"claims": ["Knows Python and Jenkins", "Knows Python and Rust"]},
        {"results": [
            {"claim": "Knows Python and Jenkins", "verdict": "supported",
             "source": "resume", "quote": "Seven years of Python ... Jenkins"},
            {"claim": "Knows Python and Rust", "verdict": "supported",
             "source": "resume", "quote": "Seven years of Python ... Rust"},
        ]},
    ])
    try:
        report = guard.check(_Ready("ollama", "m"), "text",
                             {"resume": RESUME + "\nTools: Jenkins"})
    finally:
        guard.complete_json = original
    assert [c.claim for c in report.unsupported] == ["Knows Python and Rust"]


def test_a_failed_check_is_reported_not_raised():
    original = guard.complete_json

    def boom(*a, **k):
        raise llm.LLMError("Ollama is not answering")
    guard.complete_json = boom
    try:
        report = guard.check(_Ready("ollama", "m"), "text", {"resume": RESUME})
    finally:
        guard.complete_json = original
    assert not report.checked and "not answering" in report.error
    assert report.to_dict()["rate"] is None


def test_a_second_model_checks_when_one_is_chosen_and_ready():
    seen = []

    def fake(settings, *a, **k):
        seen.append(settings.model)
        return ({"claims": ["Seven years of Python"]} if len(seen) == 1 else
                {"results": [{"claim": "Seven years of Python", "verdict": "supported",
                              "source": "resume", "quote": "Seven years of Python"}]})

    original = guard.complete_json
    guard.complete_json = fake
    try:
        first = _Ready("ollama", "writer", checkers=[_Ready("ollama", "checker")])
        report = guard.check(first, "text", {"resume": RESUME})
    finally:
        guard.complete_json = original
    assert seen == ["checker", "checker"]
    assert report.second and report.model.endswith("· checker") and not report.note


def test_a_second_model_that_cannot_be_called_falls_back_and_says_so():
    original = guard.complete_json
    guard.complete_json = _fake([{"claims": []}])
    try:
        # No key held for it, so Settings.problem() names that.
        first = _Ready("ollama", "writer", checkers=[llm.Settings("anthropic", "x")])
        report = guard.check(first, "text", {"resume": RESUME})
    finally:
        guard.complete_json = original
    assert report.checked and not report.second
    assert report.note.startswith("second model ") and "x not used" in report.note


def _claims_then_verdicts(seen, down=()):
    """A fake model call: records who was asked, fails for the names in
    `down`, and otherwise answers one claim, then its supported verdict."""
    def fake(settings, *a, **k):
        for one in settings.chain():
            seen.append(one.model)
            if one.model in down:
                continue
            settings.answered = one
            if k.get("purpose") == "guard_extract":
                return {"claims": ["Seven years of Python"]}
            return {"results": [{"claim": "Seven years of Python", "verdict": "supported",
                                 "source": "resume", "quote": "Seven years of Python"}]}
        raise llm.LLMError("no AI reader could answer")
    return fake


def test_a_checker_that_cannot_answer_hands_over_to_the_next():
    """2026-10-23: one second model, and when it was down or rate limited the
    output went unchecked, though up to six readers could fall back."""
    seen = []
    original = guard.complete_json
    guard.complete_json = _claims_then_verdicts(seen, down={"c1"})
    try:
        first = _Ready("ollama", "writer",
                       checkers=[_Ready("ollama", "c1"), _Ready("ollama", "c2")])
        report = guard.check(first, "text", {"resume": RESUME})
    finally:
        guard.complete_json = original
    assert seen == ["c1", "c2", "c1", "c2"]
    assert report.checked and report.second and report.model.endswith("· c2")


def test_with_no_checker_another_reader_checks_and_the_writer_comes_last():
    order, _ = guard.checking(_Ready("ollama", "r1", fallbacks=[_Ready("ollama", "r2")]))
    assert [s.model for s in order.chain()] == ["r2", "r1"]
    # The second reader wrote it (the first could not answer): the first checks.
    writer = _Ready("ollama", "r1", fallbacks=[_Ready("ollama", "r2")])
    writer.answered = writer.fallbacks[0]
    order, _ = guard.checking(writer)
    assert [s.model for s in order.chain()] == ["r1", "r2"]
    # One reader alone checks itself, as before.
    order, note = guard.checking(_Ready("ollama", "solo"))
    assert [s.model for s in order.chain()] == ["solo"] and not note


def test_a_checker_that_is_the_writer_is_passed_over():
    first = _Ready("ollama", "r1", checkers=[_Ready("ollama", "r1"), _Ready("ollama", "c")],
                   fallbacks=[_Ready("ollama", "r2")])
    order, _ = guard.checking(first)
    assert [s.model for s in order.chain()] == ["c", "r2", "r1"]
    assert first.checker_chain().model == "c"


def test_the_ai_verdict_reads_your_projects_and_education_too():
    """2026-10-23: it read the resume file alone, while fit scores and
    tailored resumes already counted what the Resume page adds."""
    import tempfile

    from jobdork.ai import judging
    from jobdork.core.config import Config
    from jobdork.db.store import Role, Store

    prompts, checked = [], []

    def fake_json(settings, system, user, schema, **_):
        prompts.append(user)
        return {"score": 70, "verdict": "possible", "summary": "Plausible.",
                "reasons": ["Built a rota tool"], "concerns": [], "enough_evidence": True}

    saved = (llm.complete_json, judging.Settings.from_config, judging.check_verdict)
    llm.complete_json = fake_json
    # lambda: settings that are always ready, so no model is needed.
    judging.Settings.from_config = staticmethod(lambda cfg: _Ready("ollama", "m"))
    # lambda: records what the claim check would be given as the record.
    judging.check_verdict = lambda s, st, row, v, record, **_: checked.append(record)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            resume = Path(tmp) / "resume.md"
            resume.write_text(RESUME, encoding="utf-8")
            cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"),
                         resume_path=str(resume))
            with Store(cfg.db_path) as store:
                role = Role(platform="greenhouse", company="Initech", title="Engineer",
                            url="https://x.test/1", description="Build tools. " * 40)
                store.upsert(role)
                store.save_project({"name": "Ward rota tool", "action": "Built it in Python."})
                store.save_education({"credential": "MS Computer Science", "school": "Georgia Tech"})
                store.conn.commit()
                judging.run(cfg, store, uid=role.uid)
    finally:
        llm.complete_json, judging.Settings.from_config, judging.check_verdict = saved
    user = prompts[0]
    assert user.index("<</RESUME>>") < user.index("<<ADDED>>")
    assert "Project: Ward rota tool" in user and "Education: MS Computer Science" in user
    assert "Ward rota tool" in checked[0] and RESUME in checked[0]


def test_two_scores_far_apart_are_marked_as_a_disagreement():
    from jobdork.ai import judging

    original = judging.judge
    try:
        # lambda: a second model that always scores 40, whatever it is given.
        judging.judge = lambda s, role, resume, notes="": {"score": 40, "verdict": "weak",
                                                           "summary": "thin match"}
        verdict = {"score": 85, "verdict": "strong"}
        judging.second_opinion(_Ready("ollama", "a", checkers=[_Ready("ollama", "b")]),
                               {}, RESUME, verdict)
        assert verdict["disagree"] and verdict["second"]["score"] == 40
        close = {"score": 50, "verdict": "possible"}
        judging.second_opinion(_Ready("ollama", "a", checkers=[_Ready("ollama", "b")]),
                               {}, RESUME, close)
        assert not close["disagree"]
        alone = {"score": 85}
        judging.second_opinion(_Ready("ollama", "a"), {}, RESUME, alone)
        assert "second" not in alone
    finally:
        judging.judge = original


def _verified(claims, results, sources):
    """verify() with the checker's answer given; no model is called."""
    original = guard.complete_json
    # lambda: the checker's answer, fixed.
    guard.complete_json = lambda *a, **k: {"results": results}
    try:
        return {c.claim: c.verdict for c in guard.verify(_Ready("ollama", "m"), claims, sources)}
    finally:
        guard.complete_json = original


def test_a_gap_is_settled_by_script_not_counted_as_made_up():
    """Naming what the resume lacks is half a verdict's job; a script checks
    the thing named really is nowhere in the resume."""
    claims = ["The resume does not mention Django.", "The candidate lacks Python experience",
              "The candidate has 5 years of DevOps", "No Rust experience is shown"]
    got = _verified(claims, [
        {"n": 1, "claim": claims[0], "verdict": "absent", "source": "resume", "quote": "Django"},
        # It is there: a false gap is the verdict's mistake, and is caught.
        {"n": 2, "claim": claims[1], "verdict": "absent", "source": "resume", "quote": "Python"},
        # Not a gap at all: "absent" cannot be used to wave a claim through.
        {"n": 3, "claim": claims[2], "verdict": "absent", "source": "resume", "quote": "DevOps"},
        # A gap with no source named: the advert would count as filling it.
        {"n": 4, "claim": claims[3], "verdict": "absent", "source": "", "quote": "Rust"},
    ], {"resume": RESUME, "advert": "Wanted: Django, Rust."})
    assert got == {claims[0]: "supported", claims[1]: "contradicted",
                   claims[2]: "unsupported", claims[3]: "unsupported"}, got


def test_a_gap_must_name_the_thing_the_claim_says_is_missing():
    claim = "The candidate lacks cloud experience"
    got = _verified([claim], [{"n": 1, "claim": claim, "verdict": "absent",
                               "source": "resume", "quote": "Kubernetes"}], {"resume": RESUME})
    assert got[claim] == "unsupported"


def test_words_match_whole_and_punctuation_does_not_matter():
    claims = ["Knows Java", "Built CI with Jenkins"]
    got = _verified(claims, [
        {"n": 1, "claim": claims[0], "verdict": "supported", "source": "resume", "quote": "Java"},
        {"n": 2, "claim": claims[1], "verdict": "supported", "source": "resume",
         "quote": "built CI, with Jenkins"},
    ], {"resume": "JavaScript and TypeScript. Built CI with Jenkins."})
    assert got == {claims[0]: "unsupported", claims[1]: "supported"}, got


def test_a_claim_echoed_back_a_little_differently_is_still_matched():
    """Unmatched counted as made up, and a checker that dropped a full stop
    or a word was enough to flag a true claim."""
    claims = ["The candidate has experience with Jenkins.", "Led a team of four at Acme"]
    got = _verified(claims, [
        {"n": 1, "claim": "The candidate has experience with Jenkins", "verdict": "supported",
         "source": "resume", "quote": "Built CI with Jenkins"},
        {"n": 2, "claim": "Led a team of four people at Acme", "verdict": "supported",
         "source": "resume", "quote": "Led a team of four at Acme"},
    ], {"resume": RESUME})
    assert set(got.values()) == {"supported"}, got


def test_a_verdict_numbered_for_another_claim_is_not_used():
    claims = ["Has ten years of Go", "Built CI with Jenkins"]
    got = _verified(claims, [
        {"n": 1, "claim": "Built CI with Jenkins", "verdict": "supported",
         "source": "resume", "quote": "Built CI with Jenkins"},
    ], {"resume": RESUME})
    assert got == {claims[0]: "unsupported", claims[1]: "supported"}, got


def test_the_posts_dates_are_part_of_the_advert_source():
    row = {"title": "Nurse", "company": "Mercy", "location_raw": "Ohio",
           "description": "Night shifts."}
    text = guard.advert_source(row, "Posted 5 days ago (2026-10-19).")
    assert "Posted 5 days ago" in text and text.endswith("Night shifts.")
    assert "Posted" not in guard.advert_source(row)


def test_a_source_named_the_way_the_model_sees_it_is_still_that_source():
    """Asked for "resume", a model wrote "JESSE NGOLAB resume" 403 times in
    420, and every gap it found was thrown out for naming no source."""
    claim = "The resume does not mention Django"
    got = _verified([claim], [{"n": 1, "claim": claim, "verdict": "absent",
                               "source": "JANE DOE resume", "quote": "Django"}],
                    {"resume": RESUME, "advert": "Wanted: Django."})
    assert got[claim] == "supported"


def test_pdf_text_with_words_run_together_still_holds_a_quote():
    claim, missing = "Worked freelance and remote", "The resume lacks Remote work"
    text = "Freelance RemoteFreelance Web Developer August 2018"
    got = _verified([claim, missing], [
        {"n": 1, "claim": claim, "verdict": "supported", "source": "resume",
         "quote": "Freelance Remote"},
        # Glued to the next word, it is still there: the gap is wrong.
        {"n": 2, "claim": missing, "verdict": "absent", "source": "resume", "quote": "Remote"},
    ], {"resume": text})
    assert got == {claim: "supported", missing: "contradicted"}, got


def test_work_history_is_counted_from_the_resumes_dates_not_by_a_model():
    from jobdork.search.resume import work_span
    text = ("University of the Cordilleras June 2012 - December 2015Bachelor's\n"
            "Freelance Web Developer August 2018 - September 2023\n"
            "DevOps Engineer August 2022 - February 2023\n"
            "Software Engineer September 2018 - June 2022\n"
            "Application Developer March 2016 - April 2017\n")
    span = work_span(text)
    # Mar 2016-Apr 2017 is 14 months, Aug 2018-Sep 2023 is 62; overlaps once,
    # the degree not at all.
    assert (span.first, span.last, span.months) == ("March 2016", "September 2023", 76)
    assert "6 years 4 months" in span.line()
    nurse = work_span("Nurse, Mercy, May 2021 - Present.\n"
                      "BSN, Ohio State University, Sept 2017 - May 2021", today=(2026, 10))
    assert (nurse.first, nurse.last, nurse.months) == ("May 2021", "Present", 66)
    assert work_span("Seven years of Python.") is None


def test_the_judge_is_given_the_measured_work_history_and_the_guard_too():
    from jobdork.ai import judging
    sent = {}
    original = llm.complete_json

    def fake(settings, system, user, schema, **_):
        sent["user"] = user
        return {"score": 60, "verdict": "possible", "summary": "x", "reasons": [],
                "concerns": [], "enough_evidence": True}
    llm.complete_json = fake
    try:
        llm.judge(_Ready("ollama", "m"), {"title": "T", "description": "d" * 300,
                                          "work": "Work history in the resume: 6 years"},
                  RESUME)
    finally:
        llm.complete_json = original
    assert "<<MEASURED>>\nWork history in the resume: 6 years" in sent["user"]
    row = {"title": "T", "company": "C", "location_raw": "", "description": "d"}
    assert judging.guard_sources(row, RESUME, work="6 years in all")["resume"].endswith(
        "6 years in all")


def test_a_gap_the_checker_calls_supported_is_still_settled_by_script():
    """Checkers answer a gap with "supported" and the missing thing as the
    quote, which is in no source; it is a gap, and the script decides."""
    gap, wave = "The resume does not mention audio processing", \
        "He doesn't just know Python, he led teams of forty"
    got = _verified([gap, wave], [
        {"n": 1, "claim": gap, "verdict": "supported", "source": "resume",
         "quote": "audio processing"},
        # Not gap wording: a made-up claim cannot pass this way.
        {"n": 2, "claim": wave, "verdict": "supported", "source": "resume",
         "quote": "teams of forty"},
    ], {"resume": RESUME})
    assert got == {gap: "supported", wave: "unsupported"}, got


def test_a_quote_with_the_space_the_pdf_lost_still_holds():
    claim = "Was a freelance web developer"
    got = _verified([claim], [{"n": 1, "claim": claim, "verdict": "supported",
                               "source": "resume", "quote": "Remote Freelance Web Developer"}],
                    {"resume": "Freelance RemoteFreelance Web Developer August 2018"})
    assert got[claim] == "supported"


def test_a_gap_with_no_quote_is_read_from_the_claims_own_words():
    gaps = ["The resume does not mention building web crawlers.", "Jenkins is not mentioned"]
    got = _verified(gaps, [{"n": i, "claim": c, "verdict": "supported", "source": "resume",
                            "quote": ""} for i, c in enumerate(gaps, 1)], {"resume": RESUME})
    assert got == {gaps[0]: "supported", gaps[1]: "contradicted"}, got


def test_reading_a_gap_takes_no_time_on_a_hostile_claim():
    """Claims come from models reading job posts, so a claim can be built to
    make the pattern backtrack: "no any  any  any ..." once took exponential
    time (CodeQL py/redos)."""
    import time
    assert guard._missing("Lacks any direct experience in Kubernetes") == "Kubernetes"
    started = time.monotonic()
    for claim in ("no " + "any  " * 28 + "\n!\n!", "no" + " any" * 5000 + "\n!"):
        guard._missing(claim)
    assert time.monotonic() - started < 1



def test_what_the_text_says_about_itself_is_not_a_claim_to_check():
    """A letter applying, or a resume summary naming the role wanted, is the
    text describing itself: no source can support it. A company seeking
    someone is a claim about the advert, and is checked."""
    kept = ["The company is seeking a candidate for the role.",
            "The advert seeks someone with five years of Go for this job.",
            "Jane led a team of four at Acme."]
    said = ["The candidate is seeking a Software Engineer role to build software.",
            "Jane wants a senior backend position.",
            "Jane is applying for the Platform Engineer job."]
    original = guard.complete_json
    guard.complete_json = _fake([{"claims": said + kept}])
    try:
        got = guard.extract_claims(_Ready("ollama", "m"), "text")
    finally:
        guard.complete_json = original
    assert got == kept, got

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
