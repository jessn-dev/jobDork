"""
jobdork.core.telemetry
======================
What a running job is doing, written where any process can read it.

A scan started from the terminal and one started from the dashboard are
different processes, and the dashboard's live log only ever saw its own. So
every job records itself in the database — the `activity` row for the job,
`activity_events` for its log lines — and the Activity page reads from
there, whoever started it.

What is recorded, and nothing else:

  progress   done / total, and named counters ("closed": 3, "kept": 41)
  network    per host: requests, 2xx, 4xx, 429, errors, time spent
  ai         per model: calls, failures, time spent; and one `llm_calls`
             row per call (model, purpose, seconds, ok) for percentiles
  heartbeat  every few seconds while the job lives, so a job whose process
             died is shown as dead rather than as running forever

No request bodies, no page text, no keys, no advert text. Hosts and counts.

Writes are batched — at most one flush a second, plus the heartbeat — and
go through their own connection. They never make the job wait: a flush from
the job's own thread gives up after a quarter of a second if the database is
busy (the job holding a write open, say), and whatever it could not write is
kept for the next one. `rescreen` once took minutes, then failed with
"database is locked", because every progress tick waited ten seconds on the
write `rescreen` itself was holding.

Instrumented code calls the module functions (`tick`, `line`, `fetch`,
`llm`), which do nothing when no job is being recorded. Tests and one-off
calls pay nothing. The one exception is a model call: one made outside a job
(setup's test and suggestions, the AI page's Save and test) is still a call
the AI tiles should count, so it is written as an `llm_calls` row with no job
when the process has said where (`record_calls_to`).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path

HEARTBEAT_SECONDS = 5
FLUSH_SECONDS = 1.0
EVENTS_KEPT = 400          # per job; older lines are pruned
APP_EVENTS_KEPT = 500      # warnings and errors from outside any job
JOBS_KEPT = 200            # jobs whose log lines are kept
DAYS_KEPT = 120            # job rows and model calls, for the 90-day metrics

_lock = threading.Lock()
_current: Recorder | None = None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Recorder:
    """One job's telemetry. Thread-safe: a scan fetches on a thread pool."""

    def __init__(self, db_path: str, job: str, origin: str):
        self.conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        self.conn.execute("PRAGMA busy_timeout = 10000")
        # Readers never block a writer's commit (store.py sets it too).
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.lock = threading.Lock()
        self._writing = threading.Lock()     # one flush at a time on self.conn
        self.done = 0
        self.total: int | None = None
        self.counters: dict[str, int] = {}
        self.hosts: dict[str, dict] = {}
        self.ai: dict[str, dict] = {}
        self.last_line = ""
        self._events: list[tuple[str, str, str]] = []
        self._calls: list[tuple[str, str, str, float, int]] = []
        self._last_flush = 0.0
        self._stop = threading.Event()
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO activity(job, origin, pid, started_at, heartbeat_at, "
                "state) VALUES(?,?,?,?,?, 'running')",
                (job, origin, os.getpid(), _now(), _now()))
            self.id = cur.lastrowid
            # Logs are the bulk, so only the last JOBS_KEPT jobs keep theirs.
            # A job's own row and its model calls are a few hundred bytes and
            # are what the Dashboard's 90-day numbers count, so those are kept
            # by age: pruning them by count undercounted a busy quarter.
            self.conn.execute(
                "DELETE FROM activity_events WHERE activity_id IN (SELECT id "
                "FROM activity ORDER BY id DESC LIMIT -1 OFFSET ?)", (JOBS_KEPT,))
            cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                                   time.localtime(time.time() - DAYS_KEPT * 86400))
            self.conn.execute(
                "DELETE FROM llm_calls WHERE activity_id IN (SELECT id "
                "FROM activity WHERE started_at < ?)", (cutoff,))
            self.conn.execute(
                "DELETE FROM activity WHERE started_at < ?", (cutoff,))
        self._beat = threading.Thread(target=self._heartbeat, daemon=True)
        self._beat.start()

    # ── what instrumented code reports ────────────────────────────────────────

    def tick(self, done: int | None = None, total: int | None = None,
             count: str = "", add: int = 1) -> None:
        with self.lock:
            if total is not None:
                self.total = total
            if done is not None:
                self.done = done
            if count:
                self.counters[count] = self.counters.get(count, 0) + add
        self.flush()

    def line(self, text: str, level: str = "info") -> None:
        text = str(text).rstrip()[:500]
        if not text:
            return
        text, level = labelled(text, level)
        with self.lock:
            self.last_line = text.strip()
            self._events.append((_now(), level, text))
        self.flush()

    def fetch(self, host: str, status: int, seconds: float, error: str = "") -> None:
        with self.lock:
            h = self.hosts.setdefault(host or "?", {
                "requests": 0, "ok": 0, "client": 0, "limited": 0,
                "errors": 0, "seconds": 0.0, "slowest": 0.0})
            h["requests"] += 1
            h["seconds"] += seconds
            h["slowest"] = max(h["slowest"], seconds)
            if status == 429:
                h["limited"] += 1
            elif 200 <= status < 400:
                h["ok"] += 1
            elif 400 <= status < 500:
                h["client"] += 1
            else:
                h["errors"] += 1
            if error and status == 0 and "blocked" in error.lower():
                h["blocked"] = True
        self.flush()

    def llm(self, model: str, seconds: float, ok: bool, purpose: str = "") -> None:
        with self.lock:
            self._calls.append((_now(), model, purpose, round(seconds, 3),
                                1 if ok else 0))
            m = self.ai.setdefault(model, {"calls": 0, "failed": 0,
                                           "seconds": 0.0, "slowest": 0.0})
            m["calls"] += 1
            m["failed"] += 0 if ok else 1
            m["seconds"] += seconds
            m["slowest"] = max(m["slowest"], seconds)
        self.flush()

    # ── writing ───────────────────────────────────────────────────────────────

    def flush(self, force: bool = False, state: str = "", summary: str = "",
              wait: float = 0.25) -> None:
        """Write what is pending. Gives up after `wait` seconds if busy.

        The job's own thread calls this with the default, so a busy database
        costs it a quarter of a second at most; the heartbeat and `finish`
        pass longer waits. Whatever is not written stays queued.
        """
        now = time.monotonic()
        if not force and now - self._last_flush < FLUSH_SECONDS:
            return
        # Another thread is mid-write on this connection: leave it to that one.
        if not self._writing.acquire(timeout=wait):
            return
        try:
            self._flush(now, state, summary, wait)
        finally:
            self._writing.release()

    def _flush(self, now: float, state: str, summary: str, wait: float) -> None:
        with self.lock:
            self._last_flush = now
            events, self._events = self._events, []
            calls, self._calls = self._calls, []
            row = (self.done, self.total, json.dumps(self.counters),
                   json.dumps(self.hosts), json.dumps(self.ai),
                   self.last_line, _now())
        self.conn.execute(f"PRAGMA busy_timeout = {int(wait * 1000)}")
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE activity SET done=?, total=?, counters=?, hosts=?, "
                    "ai=?, last_line=?, heartbeat_at=? WHERE id=?",
                    (*row, self.id))
                if events:
                    self.conn.executemany(
                        "INSERT INTO activity_events(activity_id, at, level, text) "
                        "VALUES(?,?,?,?)", [(self.id, *e) for e in events])
                    self.conn.execute(
                        "DELETE FROM activity_events WHERE activity_id = ? AND id "
                        "<= (SELECT id FROM activity_events WHERE activity_id = ? "
                        "ORDER BY id DESC LIMIT 1 OFFSET ?)",
                        (self.id, self.id, EVENTS_KEPT))
                if calls:
                    self.conn.executemany(
                        "INSERT INTO llm_calls(at, activity_id, model, purpose, "
                        "seconds, ok) VALUES(?,?,?,?,?,?)",
                        [(at, self.id, *rest) for at, *rest in calls])
                if state:
                    self.conn.execute(
                        "UPDATE activity SET state=?, summary=?, finished_at=? "
                        "WHERE id=?", (state, summary[:1000], _now(), self.id))
        except sqlite3.Error:
            # Telemetry must never break the job it describes. The job
            # carries on, and what was not written goes back in the queue for
            # the next flush (bounded, so a database that stays locked cannot
            # grow it without end).
            with self.lock:
                self._events = (events + self._events)[-EVENTS_KEPT:]
                self._calls = (calls + self._calls)[-5000:]

    def _heartbeat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            self.flush(force=True, wait=2.0)

    def finish(self, state: str, summary: str = "") -> None:
        self._stop.set()
        self._beat.join(timeout=5)
        # The one write that must land: without it the run shows as died.
        self.flush(force=True, state=state, summary=summary, wait=15.0)
        self.conn.close()


@contextlib.contextmanager
def job(db_path: str, name: str, origin: str) -> Iterator[Recorder | None]:
    """Record one job for as long as the block runs.

    Yields None — and records nothing — when another job in this process is
    already being recorded, or the database cannot be written: telemetry is
    never a reason for a job to fail.
    """
    global _current
    with _lock:
        busy = _current is not None
    if busy:
        yield None
        return
    try:
        rec = Recorder(db_path, name, origin)
    except sqlite3.Error:
        yield None
        return
    with _lock:
        _current = rec
    try:
        yield rec
    except KeyboardInterrupt:
        rec.line("stopped: interrupted", "warning")
        rec.finish("stopped", "interrupted")
        raise
    except BaseException as exc:
        # In the job's log too, marked as an error, not only as its summary.
        rec.line(f"failed: {type(exc).__name__}: {exc}", "error")
        rec.finish("failed", f"{type(exc).__name__}: {exc}")
        raise
    else:
        rec.finish("done", rec.last_line)
    finally:
        with _lock:
            _current = None


def summary(text: str) -> None:
    """The line a finished job is remembered by."""
    rec = _current
    if rec is not None:
        with rec.lock:
            rec.last_line = str(text)[:1000]


# ── what instrumented code calls; no-ops outside a recorded job ───────────────


def tick(done: int | None = None, total: int | None = None,
         count: str = "", add: int = 1) -> None:
    rec = _current
    if rec is not None:
        rec.tick(done, total, count, add)


def line(text: str, level: str = "info") -> None:
    rec = _current
    if rec is not None:
        rec.line(text, level)


def fetch(host: str, status: int, seconds: float, error: str = "") -> None:
    rec = _current
    if rec is not None:
        rec.fetch(host, status, seconds, error)


# Where a model call made outside a recorded job is written: a callable
# returning the database path, set by `jobdork serve` and `jobdork setup`.
_calls_db = None


def record_calls_to(db_path) -> None:
    """Write model calls made outside a job to this database (path or callable).

    A path is made absolute now: a relative one would follow the working
    directory, and tests that changed it once wrote their calls into the
    real data/jobdork.db of the folder they were run from.
    """
    global _calls_db
    if callable(db_path):
        _calls_db = db_path
        return
    fixed = str(Path(db_path).resolve())
    # lambda: a fixed path is wrapped so both kinds are called the same way.
    _calls_db = lambda: fixed  # noqa: E731


def llm(model: str, seconds: float, ok: bool, purpose: str = "") -> None:
    rec = _current
    if rec is not None:
        rec.llm(model, seconds, ok, purpose)
        return
    if _calls_db is None:
        return
    try:
        with contextlib.closing(sqlite3.connect(_calls_db(), timeout=2)) as conn, conn:
            conn.execute(
                "INSERT INTO llm_calls(at, activity_id, model, purpose, seconds, ok) "
                "VALUES(?, NULL, ?, ?, ?, ?)",
                (_now(), model, purpose, round(seconds, 3), 1 if ok else 0))
    except (sqlite3.Error, OSError):
        pass                 # telemetry never breaks the call it describes


# ── warnings and errors from Python's logging ─────────────────────────────────
# jobdork's modules report trouble with logging.warning and logging.error
# ("example.com blocked for 60s", "resume not used for scoring", a source
# that raised). That went to the terminal only, which a dashboard user never
# sees. This handler copies each one where the Activity page reads it: the
# running job's log, marked warning or error, or, outside a job, app_events.

_app_db = None

# A key that is missing or refused is a setting to fix, not a failure of
# jobdork: logged as a warning that says so, and where the docs explain it.
# Job-source keys first: "adzuna: skipped (no key. Get a free one ...)".
_KEY_PROBLEMS = (
    (re.compile(r"\b(adzuna|usajobs)\b.*\b(no key|key was refused|"
                r"HTTP 40[13]|unauthori[sz]ed|forbidden)", re.I | re.S),
     "job source",
     "docs/CONFIG.md, sections \"sources\" and \"Environment\""),
    (re.compile(r"key was refused|enter an? \w+ key first|no api key|"
                r"(ANTHROPIC|GEMINI|GOOGLE|OPENAI)_API_KEY", re.I),
     "AI",
     "docs/CONFIG.md, section \"llm\", or the AI page"),
)


def labelled(text: str, level: str) -> tuple[str, str]:
    """A warning or error about a missing or refused key, said plainly as one.

    Anything else comes back as it was. Info lines are left alone: a key
    problem worth flagging is one something logged as a warning or error.
    """
    if level not in ("warning", "error") or text.startswith("Missing or refused key"):
        return text, level
    for pattern, what, docs in _KEY_PROBLEMS:
        if pattern.search(text):
            return (f"Missing or refused key ({what}): {text}. You see this because "
                    f"the {what} key is not set or was not accepted; see {docs}.",
                    "warning")
    return text, level


class _Handler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                exc = record.exc_info[1]
                text += f": {type(exc).__name__}: {exc}"   # no traceback
        except Exception:                   # a bad format string, say
            return
        level = "error" if record.levelno >= logging.ERROR else "warning"
        text, level = labelled(text, level)
        rec = _current
        if rec is not None:
            rec.line(text, level)
            return
        # Never creates a database: one that is not there yet has no table.
        path = _app_db() if _app_db is not None else ""
        if not path or not Path(path).is_file():
            return
        try:
            with contextlib.closing(sqlite3.connect(path, timeout=2)) as conn, conn:
                conn.execute(
                    "INSERT INTO app_events(at, level, source, text) VALUES(?,?,?,?)",
                    (_now(), level, record.name, text[:1000]))
                conn.execute(
                    "DELETE FROM app_events WHERE id <= (SELECT MAX(id) FROM "
                    "app_events) - ?", (APP_EVENTS_KEPT,))
        except (sqlite3.Error, OSError):
            pass                 # telemetry never breaks the code that logged


_handler = _Handler(logging.WARNING)


class _NotJobdork(logging.Filter):
    """For the root logger's copy: jobdork's own records already have one."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("jobdork")


# Errors from the libraries jobdork uses (the HTTP client, the PDF reader,
# the app's window), which log under their own names: errors only, as their
# warnings are mostly noise about other people's files.
_others = _Handler(logging.ERROR)
_others.addFilter(_NotJobdork())
_crash_log = logging.getLogger("jobdork.crash")


def _thread_crashed(args) -> None:
    """A thread that died of an exception: in the log, and so on the page."""
    if args.exc_type is SystemExit:
        return
    _crash_log.error("a background task stopped (%s)",
                     getattr(args.thread, "name", "thread"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    _thread_hook_before(args)


_thread_hook_before = threading.excepthook


def capture_logs(db_path) -> None:
    """Copy jobdork's logged warnings and errors to the Activity page, with
    other libraries' errors and threads that crash.

    `db_path` is where ones from outside a job go (a path or a callable, as
    for record_calls_to). Installed once; calling again only moves the path.
    """
    global _app_db
    if callable(db_path):
        _app_db = db_path
    else:
        fixed = str(Path(db_path).resolve())
        # lambda: a fixed path is wrapped so both kinds are called the same way.
        _app_db = lambda: fixed  # noqa: E731
    logger = logging.getLogger("jobdork")
    if _handler not in logger.handlers:
        logger.addHandler(_handler)
    # Everything else that goes wrong is reported too (2026-10-23: "warnings
    # and errors should log all errors encountered by the app"): other
    # libraries' errors, and a thread that dies of an exception, which Python
    # would only print to a terminal the app does not have.
    root = logging.getLogger()
    if _others not in root.handlers:
        root.addHandler(_others)
    if threading.excepthook is not _thread_crashed:
        threading.excepthook = _thread_crashed


def current_id() -> int | None:
    """The `activity` id of the job being recorded, or None outside one."""
    rec = _current
    return rec.id if rec is not None else None
