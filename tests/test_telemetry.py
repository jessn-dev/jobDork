"""
Activity telemetry: a job records itself where another process can read it,
and telemetry never breaks the job it describes.

    python tests/test_telemetry.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import telemetry
from jobdork.core.config import Config
from jobdork.db.store import Store
from jobdork.web import api


def _cfg(tmp: str) -> Config:
    cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"))
    Store(cfg.db_path).close()
    return cfg


def test_a_job_is_readable_from_another_connection_while_it_runs():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with telemetry.job(cfg.db_path, "check", "terminal") as rec:
            telemetry.tick(total=10)
            telemetry.tick(done=3, count="closed")
            telemetry.fetch("jobs.workable.com", 410, 0.2)
            telemetry.fetch("jobs.workable.com", 429, 0.1)
            telemetry.llm("Ollama · gemma4:26b", 1.5, ok=True)
            telemetry.line("  closed   abc — the posting answers HTTP 410")
            rec.flush(force=True)

            live = api.activity_report(cfg)
            assert len(live["running"]) == 1
            job = live["chosen"]
            assert (job["done"], job["total"]) == (3, 10)
            assert job["counters"] == {"closed": 1}
            host = job["hosts"]["jobs.workable.com"]
            assert (host["requests"], host["client"], host["limited"]) == (2, 1, 1)
            assert job["ai"]["Ollama · gemma4:26b"]["calls"] == 1
            assert "HTTP 410" in live["events"][-1]["text"]

        after = api.activity_report(cfg)
        assert after["running"] == [] and after["recent"][0]["state"] == "done"


def test_a_failing_job_is_recorded_as_failed_and_still_raises():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        try:
            with telemetry.job(cfg.db_path, "scan", "dashboard"):
                raise RuntimeError("board exploded")
        except RuntimeError:
            pass
        else:
            raise AssertionError("the job's own error must propagate")
        job = api.activity_report(cfg)["recent"][0]
        assert job["state"] == "failed" and "board exploded" in job["summary"]


def test_a_job_whose_process_died_is_shown_as_died():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store:
            store.conn.execute(
                "INSERT INTO activity(job, origin, pid, started_at, heartbeat_at, "
                "state) VALUES('scan', 'terminal', 999999, '2026-01-01T00:00:00', "
                "'2026-01-01T00:00:05', 'running')")
            store.conn.commit()
        job = api.activity_report(cfg)["recent"][0]
        assert job["health"] == "died" and job["state"] == "died"


def test_outside_a_job_the_hooks_do_nothing():
    telemetry.tick(done=1)
    telemetry.fetch("x", 200, 0.1)
    telemetry.line("nothing records this")


def test_telemetry_that_cannot_write_does_not_stop_the_job():
    with tempfile.TemporaryDirectory() as tmp:
        missing = str(Path(tmp) / "no-such-dir" / "t.db")
        with telemetry.job(missing, "check", "terminal") as rec:
            assert rec is None
            telemetry.tick(done=1)


def test_the_last_scan_line_says_what_went_wrong():
    """Adzuna returning 0 went unnoticed for a month; this would have said so."""
    import json

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store:
            for started, finished, sources in (
                    ("2026-01-01T08:00:00", "2026-01-01T08:05:00",
                     {"adzuna": 800, "workable": 500}),
                    ("2026-01-02T08:00:00", "2026-01-02T08:01:00",
                     {"adzuna": 0, "ashby": 100}),
                    ("2026-01-03T08:00:00", None, None)):
                store.conn.execute(
                    "INSERT INTO runs(started_at, finished_at, counts_json) VALUES(?,?,?)",
                    (started, finished, json.dumps({"fetched": 1, "sources": sources})
                     if sources else None))
            store.conn.commit()
        scan = api.activity_report(cfg)["last_runs"][0]
        text = " ".join(scan["warnings"])
        assert scan["when"] == "2026-01-02T08:00:00"
        assert "days ago" in text
        assert "Adzuna returned 0" in text
        assert "Workable did not run" in text
        assert "never finished" in text


def test_a_scan_running_now_and_a_skipped_source_are_not_called_failures():
    """A first scan's background part read as "never finished" while it ran,
    and a source skipped for want of a key as "returned 0"."""
    import json
    import time

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        with Store(cfg.db_path) as store:
            store.conn.execute(
                "INSERT INTO runs(started_at, finished_at, counts_json) VALUES(?,?,?)",
                (now, now, json.dumps({"fetched": 1, "skipped": ["adzuna"],
                                       "sources": {"adzuna": 0, "workable": 5}})))
            store.conn.execute("INSERT INTO runs(started_at) VALUES(?)", (now,))
            store.conn.execute(
                "INSERT INTO activity(job, origin, started_at, heartbeat_at, state) "
                "VALUES('full scan', 'dashboard', ?, ?, 'running')", (now, now))
            store.conn.commit()
        text = " ".join(api.activity_report(cfg)["last_runs"][0]["warnings"])
        assert "Adzuna" not in text
        assert "still running" in text and "never finished" not in text


def test_a_first_scans_two_parts_read_as_one_scan():
    """The rest part has no keyword sources by design; read alone, the card
    said Adzuna, USAJOBS, Himalayas and Workable "did not run"."""
    import json

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store:
            for started, finished, counts in (
                    ("2026-10-02T23:10:14", "2026-10-02T23:12:59",
                     {"fetched": 1914, "kept": 947, "new": 947, "part": "quick",
                      "skipped": ["kalibrr"],
                      "sources": {"kalibrr": 0, "adzuna": 812, "workable": 588,
                                  "workday": 12}}),
                    ("2026-10-02T23:12:59", "2026-10-02T23:25:06",
                     {"fetched": 7899, "kept": 1057, "new": 1057, "part": "rest",
                      "skipped": [], "sources": {"workday": 233, "ashby": 347}})):
                store.conn.execute(
                    "INSERT INTO runs(started_at, finished_at, counts_json) VALUES(?,?,?)",
                    (started, finished, json.dumps(counts)))
            store.conn.commit()
        scan = api.activity_report(cfg)["last_runs"][0]
        text = " ".join(scan["warnings"])
        assert "did not run" not in text and "returned 0" not in text, text
        assert scan["when"] == "2026-10-02T23:10:14"
        assert scan["summary"].startswith("9,813 fetched, 2,004 kept")
        assert "Workday 245" in scan["summary"]


def test_a_zero_is_a_warning_only_when_it_failed_or_used_to_find_posts():
    """2026-10-23: "Oracle returned 0 job posts" for one board with no jobs
    matching the titles, while other Oracle boards were still being read."""
    import json

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store:
            for started, counts in (
                    ("2026-10-22T08:00:00", {"sources": {"lever": 80}}),
                    ("2026-10-23T05:19:24",
                     {"fetched": 1, "skipped": [], "failed": ["usajobs"],
                      "sources": {"oracle": 0, "usajobs": 0, "lever": 0,
                                  "workable": 5}})):
                store.conn.execute(
                    "INSERT INTO runs(started_at, finished_at, counts_json) VALUES(?,?,?)",
                    (started, started, json.dumps(counts)))
            store.conn.commit()
        text = " ".join(api.activity_report(cfg)["last_runs"][0]["warnings"])
        assert "Oracle" not in text, text
        assert "USAJOBS returned 0 job posts: it failed" in text
        assert "Lever returned 0 job posts, where earlier scans found some" in text


def test_failures_of_a_first_scans_two_parts_are_kept_together():
    merged = api._merge_counts({"sources": {"usajobs": 0}, "failed": ["usajobs"]},
                               {"sources": {"oracle": 66}, "failed": []})
    assert merged["failed"] == ["usajobs"]
    assert "failed" not in api._merge_counts({"sources": {}}, {"sources": {}})


def test_a_source_is_skipped_only_when_every_board_of_it_skipped():
    from jobdork import fetch
    from jobdork.search import scan as scan_mod

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        results = [fetch.SourceResult(source="workday", skipped="robots.txt"),
                   fetch.SourceResult(source="workday"),
                   fetch.SourceResult(source="adzuna", skipped="no key")]
        saved_jobs, saved_get = scan_mod._jobs_for, fetch.get
        scan_mod._jobs_for = lambda _cfg, _part="all": [("x", {})] * len(results)
        queue = iter(results)
        fetch.get = lambda name: (lambda fetcher, cfg, **kw: next(queue))
        try:
            with Store(cfg.db_path) as store:
                scan_mod.run(cfg, store)
                import json
                counts = json.loads(store.conn.execute(
                    "SELECT counts_json FROM runs").fetchone()[0])
        finally:
            scan_mod._jobs_for, fetch.get = saved_jobs, saved_get
        assert counts["skipped"] == ["adzuna"] and counts["part"] == "all"


def test_a_model_call_outside_a_job_is_still_counted():
    """Setup's Save and test and its suggestions ran no job, so Gemma's calls
    left the AI calls tile at 0."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path):
            pass
        telemetry.llm("Ollama · gemma4:26b", 1.0, True, purpose="test")   # nowhere set
        telemetry.record_calls_to(cfg.db_path)
        try:
            telemetry.llm("Ollama · gemma4:26b", 4.1, True, purpose="setup_suggest")
        finally:
            telemetry._calls_db = None
        with Store(cfg.db_path) as store:
            rows = store.conn.execute(
                "SELECT activity_id, purpose, seconds FROM llm_calls").fetchall()
        assert [tuple(r) for r in rows] == [(None, "setup_suggest", 4.1)]
        assert api.metrics(cfg, 7)["ai_calls"]["total"] == 1


def test_each_model_call_is_a_row_with_its_purpose():
    """P50 and P95 need one row per call, not the per-model totals."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with telemetry.job(cfg.db_path, "judge", "terminal") as rec:
            telemetry.llm("Ollama · m", 1.25, ok=True, purpose="judge")
            telemetry.llm("Ollama · m", 0.5, ok=False, purpose="guard_verify")
            job_id = telemetry.current_id()
            assert job_id == rec.id
        assert telemetry.current_id() is None
        with Store(cfg.db_path) as store:
            rows = store.conn.execute(
                "SELECT activity_id, model, purpose, seconds, ok FROM llm_calls "
                "ORDER BY id").fetchall()
        assert [tuple(r) for r in rows] == [
            (job_id, "Ollama · m", "judge", 1.25, 1),
            (job_id, "Ollama · m", "guard_verify", 0.5, 0)]


def test_an_ai_output_keeps_its_guard_counts_and_takes_feedback():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with telemetry.job(cfg.db_path, "letter", "dashboard") as rec, \
                Store(cfg.db_path) as store:
            checked = store.add_ai_output(
                "cover_letter", "Dear team", uid="abc", model="Ollama · m",
                guard={"checked": True, "claims": 18, "unsupported": 2,
                       "rate": 2 / 18, "flagged": []})
            unchecked = store.add_ai_output("judge", "{}", uid="abc")
            row = store.ai_output(checked)
            assert (row["claims"], row["unsupported"], row["checked"]) == (18, 2, 1)
            assert row["activity_id"] == rec.id and row["feedback"] is None
            other = store.ai_output(unchecked)
            assert other["checked"] == 0 and other["guard_json"] is None

            assert store.set_feedback(checked, 1)
            assert store.ai_output(checked)["feedback"] == 1
            assert store.set_feedback(checked, None)
            assert store.ai_output(checked)["feedback"] is None
            assert not store.set_feedback(9999, -1)
            try:
                store.set_feedback(checked, 5)
            except ValueError:
                pass
            else:
                raise AssertionError("feedback is 1, -1 or None")


def test_a_one_post_judging_still_shows_on_its_card():
    """The card said "recorded before run history" the day a post was judged."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with telemetry.job(cfg.db_path, "judge", "terminal"):
            telemetry.tick(total=1)
            telemetry.summary("judged 1")
        card = api.activity_report(cfg)["last_runs"][2]
        assert card["kind"] == "judge" and card["id"]
        assert card["summary"] == "one job post only: judged 1"

        with telemetry.job(cfg.db_path, "judge", "terminal"):
            telemetry.tick(total=25)
            telemetry.summary("judged 25")
        assert api.activity_report(cfg)["last_runs"][2]["summary"] == "judged 25"


def test_a_run_twenty_minutes_old_is_not_just_now():
    import time as _t

    stamp = lambda s: _t.strftime("%Y-%m-%dT%H:%M:%S", _t.localtime(_t.time() - s))  # noqa: E731
    assert api._ago(stamp(20 * 60)) == "20 min ago"
    assert api._ago(stamp(10)) == "just now"
    assert api._ago(stamp(3 * 3600)) == "3 h ago"


def test_old_runs_are_pruned_by_age_and_recent_ones_are_all_kept():
    """A count limit of 200 undercounted the 90-day metrics on a busy quarter."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store:
            for started in ["2020-01-01T00:00:00"] + ["2099-01-01T00:00:00"] * 250:
                store.conn.execute(
                    "INSERT INTO activity(job, origin, pid, started_at, heartbeat_at, "
                    "state) VALUES('check', 'terminal', 1, ?, ?, 'done')", (started, started))
            store.conn.execute("INSERT INTO llm_calls(at, activity_id, seconds, ok) "
                               "VALUES('2020-01-01T00:00:00', 1, 1.0, 1)")
            store.conn.commit()
        with telemetry.job(cfg.db_path, "check", "terminal"):
            pass
        with Store(cfg.db_path) as store:
            kept = store.conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0]
            calls = store.conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
        assert kept == 251 and calls == 0


def test_a_job_holding_a_write_open_is_not_slowed_by_its_telemetry():
    """rescreen held one write over every post; each tick then waited 10 s."""
    import time as _t

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store, \
                telemetry.job(cfg.db_path, "rescreen", "terminal") as rec:
            store.conn.execute("UPDATE meta SET value = value")   # write held open
            started = _t.monotonic()
            for i in range(6):
                telemetry.line(f"line {i}")
                rec._last_flush = 0                                 # force a flush attempt
                telemetry.tick(done=i)
            assert _t.monotonic() - started < 3, "each tick waited on the lock"
            store.conn.commit()
            rec.flush(force=True, wait=5)
        texts = [e["text"] for e in api.activity_report(cfg)["events"]]
        assert texts == [f"line {i}" for i in range(6)], "unwritten lines were kept"


def test_rescreen_under_telemetry_finishes():
    from jobdork.db.store import Role
    from jobdork.search import scan

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        cfg.titles_include = ["engineer"]
        with Store(cfg.db_path) as store:
            for i in range(120):
                store.upsert(Role(platform="lever", company="Acme", title=f"Engineer {i}",
                                  url=f"https://jobs.lever.co/acme/{i}"))
            store.conn.commit()
        with telemetry.job(cfg.db_path, "rescreen", "terminal"), \
                Store(cfg.db_path) as store:
            checked, _, _ = scan.rescreen(cfg, store)
        assert checked == 120
        assert api.activity_report(cfg)["recent"][0]["state"] == "done"


def test_logged_warnings_and_errors_reach_the_activity_page():
    import logging

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        log = logging.getLogger("jobdork.test")
        telemetry.capture_logs(cfg.db_path)
        try:
            log.warning("outside any job")
            with telemetry.job(cfg.db_path, "scan", "terminal") as rec:
                log.info("not a problem")
                log.warning("example.com blocked for 60s")
                try:
                    raise ValueError("bad page")
                except ValueError:
                    log.exception("greenhouse raised")
                rec.flush(force=True)
            try:
                with telemetry.job(cfg.db_path, "check", "terminal"):
                    raise RuntimeError("board exploded")
            except RuntimeError:
                pass
        finally:
            logging.getLogger("jobdork").removeHandler(telemetry._handler)
        problems = api.activity_report(cfg)["problems"]
        seen = {(p["level"], p["job"], p["text"]) for p in problems}
        assert ("warning", "", "outside any job") in seen, seen
        assert ("warning", "scan", "example.com blocked for 60s") in seen
        assert ("error", "scan", "greenhouse raised: ValueError: bad page") in seen
        assert ("error", "check", "failed: RuntimeError: board exploded") in seen
        assert not any("not a problem" in p["text"] for p in problems)


def test_a_missing_or_refused_key_is_a_warning_that_says_so():
    text, level = telemetry.labelled(
        "adzuna: skipped (no key. Get a free one at https://developer.adzuna.com/signup)",
        "warning")
    assert level == "warning" and text.startswith("Missing or refused key (job source)")
    assert "docs/CONFIG.md" in text
    text, level = telemetry.labelled("failed: LLMError: the key was refused", "error")
    assert level == "warning" and "(AI)" in text and '"llm"' in text
    assert telemetry.labelled("example.com blocked", "error") == ("example.com blocked", "error")
    assert telemetry.labelled("adzuna: no key", "info") == ("adzuna: no key", "info")


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
