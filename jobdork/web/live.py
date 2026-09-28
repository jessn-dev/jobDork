"""
jobdork.web.live
================
The parts of the dashboard that move: running a scan from the page, and
watching it happen.

A scan takes minutes. Doing it behind a request means the page hangs, the
browser gives up, and you learn nothing about what happened until it is over —
which is exactly when a scan is most worth watching, because a rate limit or a
dead board shows up in the middle rather than at the end.

So a scan runs on a background thread and reports through an event stream.
Server-sent events rather than websockets: this is one-directional, it is
plain HTTP, and `http.server` can hold the connection open without a library.

**One scan at a time, and the tool refuses rather than queues.** Two scans
racing would double every request to hosts that are already paced, and the
second would earn a rate limit the first was carefully avoiding.
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# Kept per connection. A page that has been open all day should not replay a
# morning's scan, so a late subscriber is only sent what is still relevant.
BACKLOG = 200


@dataclass
class Event:
    kind: str                      # progress | done | error | status
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def encode(self) -> bytes:
        payload = {"kind": self.kind, "text": self.text, **self.data}
        return f"data: {json.dumps(payload)}\n\n".encode()


class Broker:
    """Fans one running job out to every open event stream.

    Each subscriber gets its own queue. A subscriber that has stopped reading
    — a closed tab that the server has not noticed — fills its queue and is
    dropped, rather than blocking the scan that is trying to report progress.
    """

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._history: list[Event] = []

    def subscribe(self) -> queue.Queue:
        channel: queue.Queue = queue.Queue(maxsize=BACKLOG)
        with self._lock:
            for event in self._history[-BACKLOG:]:
                with_room(channel, event)
            self._subscribers.append(channel)
        return channel

    def unsubscribe(self, channel: queue.Queue) -> None:
        with self._lock:
            if channel in self._subscribers:
                self._subscribers.remove(channel)

    def publish(self, event: Event) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > BACKLOG:
                del self._history[:-BACKLOG]
            dead = [c for c in self._subscribers if not with_room(c, event)]
            for channel in dead:
                self._subscribers.remove(channel)

    @property
    def listeners(self) -> int:
        """Open dashboard tabs, near enough: one event stream per tab."""
        with self._lock:
            return len(self._subscribers)

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()


def with_room(channel: queue.Queue, event: Event) -> bool:
    """Put unless full. A full queue is a subscriber that stopped reading."""
    try:
        channel.put_nowait(event)
        return True
    except queue.Full:
        return False


class Runner:
    """Runs one background job at a time and reports it to a Broker."""

    def __init__(self, db_path=None) -> None:
        # A callable returning the database path, so a config edit that moves
        # the database is followed. None records no telemetry (tests).
        self.db_path = db_path
        self.broker = Broker()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.last_finished: float = 0.0
        self.last_summary: str = ""
        # What is running, so the page can say "scanning" or "drafting a CV"
        # rather than a bare spinner, and so a refusal can name the holder.
        self.current: str = ""

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, name: str, work) -> tuple[bool, str]:
        """Begin a job. Returns (started, why_not).

        Refuses rather than queues: two scans at once would double every
        request to hosts that are deliberately paced, and the second would
        earn the rate limit the first was avoiding.
        """
        with self._lock:
            if self.busy:
                return False, f"{self.current or 'a job'} is already running"
            self.broker.clear_history()
            self.current = name
            self._thread = threading.Thread(
                target=self._wrap, args=(name, work), daemon=True)
            self._thread.start()
            return True, ""

    def _wrap(self, name: str, work) -> None:
        from ..core import telemetry

        self.broker.publish(Event("status", f"{name} started"))

        def progress(line: str) -> None:
            self.broker.publish(Event("progress", line))
            telemetry.line(line)

        recording = (telemetry.job(self.db_path(), name, "dashboard")
                     if self.db_path else contextlib.nullcontext())
        try:
            with recording:
                summary = work(progress)
                telemetry.summary(summary or f"{name} finished")
        except Exception as exc:                # one job, not the server
            self.broker.publish(Event(
                "error", f"{name} failed: {type(exc).__name__}: {exc}"))
            self.last_summary = f"{name} failed"
        else:
            self.last_summary = summary or f"{name} finished"
            self.broker.publish(Event("done", self.last_summary))
        finally:
            self.last_finished = time.time()
            self.current = ""
