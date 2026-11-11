"""
The Notifications page and notifications that stay (asked 2026-11-11):
every notification is kept, listed newest first, counted until seen and
cleared; desktop ones stay until closed. No network, no desktop: the
system's notifier is stood in for.

    python tests/test_notifications_page.py
"""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import notify
from jobdork.core.config import Config
from jobdork.db.store import Store
from jobdork.web import api


def _cfg(tmp: str) -> Config:
    cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"))
    with Store(cfg.db_path):
        pass
    return cfg


def test_every_notification_is_kept_even_when_none_is_shown():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        was = notify.native
        notify.native = lambda: False     # lambda: a computer that shows none (Docker)
        try:
            notify.scan_finished(cfg, new=3, kept=40)
            notify.scan_failed(cfg, "no network")
        finally:
            notify.native = was
        listed = api.notifications_list(cfg)
        assert [n["title"] for n in listed["notifications"]] == ["Scan failed", "3 new job posts"]
        assert [n["kind"] for n in listed["notifications"]] == ["activity", "posts"]
        assert listed["unseen"] == 2 == api.notifications_unseen(cfg)


def test_seen_clears_the_count_and_clear_all_empties_the_list():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store:
            store.add_notification("A", "a", "posts")
            store.add_notification("B", "b", "apps")
        api.notifications_seen(cfg)
        assert api.notifications_unseen(cfg) == 0
        assert len(api.notifications_list(cfg)["notifications"]) == 2
        assert api.notifications_clear(cfg)["cleared"] == 2
        assert api.notifications_list(cfg)["notifications"] == []


def test_the_same_words_within_a_day_are_kept_once_and_only_the_newest_500():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg.db_path) as store:
            store.add_notification("Due", "Call Acme", "apps")
            store.add_notification("Due", "Call Acme", "apps")
            assert len(store.notifications()) == 1
            was = Store.NOTIFICATIONS_KEPT
            Store.NOTIFICATIONS_KEPT = 3
            try:
                for i in range(5):
                    store.add_notification(f"N{i}", "", "")
            finally:
                Store.NOTIFICATIONS_KEPT = was
            assert [n["title"] for n in store.notifications()] == ["N4", "N3", "N2"]


def test_nothing_is_kept_before_there_is_a_database():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "none.db"))
        notify._keep(cfg, "t", "b", "")
        assert not Path(cfg.db_path).exists()
        assert api.notifications_list(cfg) == {"notifications": [], "unseen": 0}


def test_desktop_notifications_stay_until_closed():
    xml = notify.toast_xml("t", "b", sound=True)
    assert 'scenario="reminder"' in xml and 'arguments="dismiss"' in xml
    calls = []

    def run(argv, **kw):
        calls.append(list(argv))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    was = sys.platform
    sys.platform = "linux"
    try:
        notify.send("t", "b", sound=False, run=run)
    finally:
        sys.platform = was
    assert "--urgency=critical" in calls[0] and "--expire-time=0" in calls[0]
    spec = (Path(__file__).resolve().parent.parent / "packaging" / "jobdork.spec").read_text()
    assert '"NSUserNotificationAlertStyle": "alert"' in spec


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
