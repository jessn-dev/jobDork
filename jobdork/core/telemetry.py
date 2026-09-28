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
calls pay nothing.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterator

HEARTBEAT_SECONDS = 5
FLUSH_SECONDS = 1.0
EVENTS_KEPT = 400          # per job; older lines are pruned
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
        rec.finish("stopped", "interrupted")
        raise
    except BaseException as exc:
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


def llm(model: str, seconds: float, ok: bool, purpose: str = "") -> None:
    rec = _current
    if rec is not None:
        rec.llm(model, seconds, ok, purpose)


def current_id() -> int | None:
    """The `activity` id of the job being recorded, or None outside one."""
    rec = _current
    return rec.id if rec is not None else None
