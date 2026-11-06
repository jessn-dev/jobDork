"""
Follow-up reminders (core/reminders.py): which next steps are due, the
words of the notification, and that each is told once for its date. On a
temporary database; nothing is shown (the command is a stand-in) and
nothing goes online.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import config, notify, reminders, setup
from jobdork.core.config import Config, Notifications
from jobdork.db.store import Role, Store

TODAY = "2026-11-05"


class _Run:
    def __init__(self, code=0):
        self.calls, self.code = [], code

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        return types.SimpleNamespace(returncode=self.code, stdout="", stderr="")


@contextlib.contextmanager
def _shown():
    """Notifications on for the test, on Linux's notify-send, a stand-in."""
    saved = (os.environ.pop(notify.ENV, None), sys.platform, notify.shutil.which)
    sys.platform = "linux"
    # lambda: shutil.which's signature; notify-send is "there" for the test.
    notify.shutil.which = lambda name: "/usr/bin/" + name
    try:
        yield
    finally:
        if saved[0] is not None:
            os.environ[notify.ENV] = saved[0]
        sys.platform, notify.shutil.which = saved[1], saved[2]


def _cfg(**note) -> Config:
    cfg = Config()
    cfg.notifications = Notifications(**note)
    return cfg


def _apply(store, n: int, title: str = "Nurse", company: str = "Acme",
           status: str = "applied", step: str = "Phone screen", date: str = TODAY) -> str:
    role = Role(platform="ashby", company=company, title=f"{title} {n}",
                url=f"https://x.test/{n}", location_raw="Chicago, IL")
    store.upsert(role)
    store.conn.commit()
    store.set_status(role.uid, "applied")
    if status != "applied":
        store.set_status(role.uid, status)
    store.save_application(role.uid, {"next_step": step, "next_date": date})
    return role.uid


def test_due_is_today_and_before_on_applications_still_going():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        today = _apply(store, 1)
        past = _apply(store, 2, date="2026-11-01")
        _apply(store, 3, date="2026-11-06")                  # not yet
        _apply(store, 4, status="rejected")                  # ended
        _apply(store, 5, date="")                            # no date
        got = reminders.due(store, TODAY)
        assert [a["uid"] for a in got] == [past, today], "oldest first"


def test_one_follow_up_names_the_step_and_employer():
    title, body = reminders.message(
        [{"uid": "u", "title": "Nurse", "company": "Acme", "step": "Phone screen",
          "date": TODAY}], TODAY)
    assert title == "Follow-up due today"
    assert body.startswith("Phone screen, Acme (Nurse).")
    title, _ = reminders.message(
        [{"uid": "u", "title": "Nurse", "company": "Acme", "step": "", "date": "2026-11-02"}],
        TODAY)
    assert title == "Follow-up due since Mon 2 Nov"


def test_several_are_one_notification():
    items = [{"uid": str(i), "title": "", "company": f"Co {i}", "step": "", "date": TODAY}
             for i in range(5)]
    title, body = reminders.message(items, TODAY)
    assert title == "5 follow-ups due"
    assert "Follow up, Co 0; Follow up, Co 1; Follow up, Co 2; and 2 more." in body


def test_each_is_told_once_for_its_date():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store, _shown():
        uid = _apply(store, 1)
        run = _Run()
        assert reminders.remind(_cfg(), store, TODAY, run=run) == 1
        assert run.calls and run.calls[0][0] == "notify-send"
        assert reminders.remind(_cfg(), store, TODAY, run=run) == 0, "told already"
        assert len(run.calls) == 1
        store.save_application(uid, {"next_step": "Interview", "next_date": "2026-11-09"})
        assert reminders.remind(_cfg(), store, "2026-11-09", run=run) == 1, "a new date"
        assert json.loads(store.get_meta(reminders.TOLD_KEY)) == {uid: "2026-11-09"}


def test_not_shown_is_not_counted_as_told():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store, _shown():
        _apply(store, 1)
        assert reminders.remind(_cfg(), store, TODAY, run=_Run(code=1)) == 0
        assert reminders.remind(_cfg(), store, TODAY, run=_Run()) == 1, "tried again"


def test_off_tells_nothing():
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store, _shown():
        _apply(store, 1)
        run = _Run()
        assert reminders.remind(_cfg(reminders=False), store, TODAY, run=run) == 0
        assert reminders.remind(_cfg(enabled=False), store, TODAY, run=run) == 0
        assert not run.calls
    with tempfile.TemporaryDirectory() as tmp, Store(Path(tmp) / "x.db") as store:
        _apply(store, 1)
        assert reminders.remind(_cfg(), store, TODAY, run=_Run()) == 0, "JOBDORK_NOTIFY=off"


def test_the_setting_is_read_and_written():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text("titles:\n  include: [nurse]\n")
        assert config.load(str(path)).notifications.reminders is True, "on by default"
        setup.write(str(path), {"notifications": {"reminders": False}})
        cfg = config.load(str(path))
        assert cfg.notifications.reminders is False
        assert cfg.notifications.enabled is True, "the rest left as it was"


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
