"""
The Dashboard's numbers: runs and errors, model-call percentiles, the
hallucination rate and its coverage, feedback, and the per-day split.

    python tests/test_metrics.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core.config import Config
from jobdork.db.store import Store
from jobdork.web import api


def _day(ago: int, clock: str = "10:00:00") -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - ago * 86400)) + "T" + clock


def _seed(tmp: str) -> Config:
    cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"))
    with Store(cfg.db_path) as store:
        c = store.conn
        for job, state, ago in (("scan", "done", 0), ("checking postings", "done", 0),
                                ("judge", "failed", 1), ("letter", "done", 1),
                                ("rescreen", "stopped", 3), ("scan", "done", 40)):
            c.execute("INSERT INTO activity(job, origin, pid, started_at, heartbeat_at, "
                      "finished_at, state) VALUES(?, 'terminal', 1, ?, ?, ?, ?)",
                      (job, _day(ago), _day(ago), _day(ago), state))
        for i, seconds in enumerate((1.0, 2.0, 3.0, 4.0, 10.0)):
            c.execute("INSERT INTO llm_calls(at, activity_id, model, purpose, seconds, ok) "
                      "VALUES(?, 1, 'm', 'judge', ?, ?)", (_day(0), seconds, int(i != 4)))
        c.execute("INSERT INTO llm_calls(at, activity_id, model, purpose, seconds, ok) "
                  "VALUES(?, 1, 'm', 'judge', 99, 1)", (_day(40),))
        for kind, claims, bad, checked, fb, ago in (
                ("judge", 10, 1, 1, 1, 0), ("cover_letter", 20, 4, 1, -1, 1),
                ("draft", 0, 0, 0, 1, 1), ("page_read", 1, 0, 1, None, 0),
                ("judge", 50, 50, 1, None, 40)):
            c.execute("INSERT INTO ai_outputs(kind, created_at, claims, unsupported, "
                      "checked, feedback) VALUES(?,?,?,?,?,?)",
                      (kind, _day(ago), claims, bad, checked, fb))
        c.commit()
    return cfg


def test_the_numbers_count_only_the_period_asked_for():
    with tempfile.TemporaryDirectory() as tmp:
        m = api.metrics(_seed(tmp), 7)
    assert m["runs"]["total"] == 5 and m["runs"]["errored"] == 2
    assert m["runs"]["by_state"] == {"failed": 1, "died": 0, "stopped": 1}
    assert abs(m["runs"]["error_rate"] - 0.4) < 1e-9
    calls = m["ai_calls"]
    assert (calls["total"], calls["failed"], calls["p50"], calls["p95"]) == (5, 1, 3.0, 10.0)
    h = m["hallucination"]
    assert (h["outputs"], h["checked"], h["claims"], h["unsupported"]) == (4, 3, 31, 5)
    assert abs(h["rate"] - 5 / 31) < 1e-9 and abs(h["coverage"] - 0.75) < 1e-9
    assert [k["label"] for k in h["by_kind"]] == ["verdicts", "page reads",
                                                  "cover letters", "claude drafts"]
    assert m["feedback"] == {"up": 2, "down": 1, "approval": 2 / 3}


def test_every_day_is_present_and_runs_are_grouped_by_tool():
    with tempfile.TemporaryDirectory() as tmp:
        m = api.metrics(_seed(tmp), 7)
    assert len(m["per_day"]) == 7
    today, yesterday = m["per_day"][-1], m["per_day"][-2]
    assert today["runs"]["scan"] == 1 and today["runs"]["check"] == 1
    assert yesterday["runs"]["AI judging"] == 1 and yesterday["runs"]["AI writing"] == 1
    assert m["per_day"][-4]["runs"]["other"] == 1
    assert (today["up"], yesterday["up"], yesterday["down"]) == (1, 1, 1)


def test_ninety_days_reaches_back_and_other_periods_are_refused():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _seed(tmp)
        m = api.metrics(cfg, 90)
        assert m["runs"]["total"] == 6 and m["ai_calls"]["p95"] == 99
        for bad in (0, 14, "x"):
            try:
                api.metrics(cfg, bad)
            except api.ApiError:
                continue
            raise AssertionError(f"{bad!r} days should be refused")


def test_an_empty_database_gives_empty_numbers_not_errors():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"))
        m = api.metrics(cfg, 30)
    assert m["runs"]["error_rate"] is None and m["ai_calls"]["p50"] is None
    assert m["hallucination"]["rate"] is None and m["feedback"]["approval"] is None
    assert len(m["per_day"]) == 30


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
