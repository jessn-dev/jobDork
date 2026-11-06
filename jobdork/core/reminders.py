"""
jobdork.core.reminders
======================
Follow-up reminders as the computer's own notifications: an application's
next step (My applications, the Application tab) on the day it is due, or
the first time jobdork runs after it.

jobdork runs only while its window is open or a scheduled scan is going, so
those are when it looks: when the app starts, every few minutes while it
stays open (a date comes due at midnight), and after each scheduled scan.
Each next step is told once, for its date: set a new date and that one is
told in its turn. What was told is kept in the database (meta
`follow_ups_told`), so a reminder seen in the morning does not come back
when the window is opened again in the afternoon.

`notifications.reminders` in config.yaml turns them off (Settings); so does
turning notifications off.
"""

from __future__ import annotations

import datetime
import json
import logging
import subprocess

from . import notify

log = logging.getLogger(__name__)

# Statuses an application has ended at: no next step of theirs is worth a
# reminder. My applications counts them under Closed (web/api.py APP_STAGES).
ENDED = ("rejected", "withdrawn", "skipped", "closed")
TOLD_KEY = "follow_ups_told"
# The most named in one notification; the rest are counted.
NAMED = 3


def wanted(cfg) -> bool:
    enabled, _ = notify.wanted(cfg)
    return enabled and bool(getattr(cfg.notifications, "reminders", True))


def due(store, today: str = "") -> list[dict]:
    """Next steps due today or before, on applications still going: one per
    job (its copies share them), the oldest date first."""
    today = today or datetime.date.today().isoformat()
    out = []
    for a in store.applications():
        r, d = a["row"], a["details"]
        when = ((d["next_date"] if d else "") or "")[:10]
        if not when or when > today or r["status"] in ENDED:
            continue
        out.append({"uid": r["uid"], "title": r["title"] or "",
                    "company": r["company"] or "",
                    "step": ((d["next_step"] if d else "") or "").strip(),
                    "date": when})
    out.sort(key=lambda a: (a["date"], a["company"]))  # lambda: oldest date first, then by employer
    return out


def message(items: list[dict], today: str) -> tuple[str, str]:
    """The notification's title and body for these next steps."""
    def one(a: dict) -> str:
        step = a["step"] or "Follow up"
        who = a["company"] or a["title"] or "a job you applied to"
        return f"{step}, {who}"

    if len(items) == 1:
        a = items[0]
        when = "today" if a["date"] == today else f"since {_day(a['date'])}"
        role = f" ({a['title']})" if a["title"] and a["company"] else ""
        return (f"Follow-up due {when}",
                f"{one(a)}{role}. Open jobdork, My applications.")
    named = "; ".join(one(a) for a in items[:NAMED])
    more = len(items) - NAMED
    rest = f"; and {more} more" if more > 0 else ""
    return (f"{len(items)} follow-ups due",
            f"{named}{rest}. Open jobdork, My applications.")


def _day(iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def remind(cfg, store, today: str = "", run=subprocess.run) -> int:
    """Notify the next steps due and not yet told. Returns how many were
    told. Never raises: a reminder is never worth a failed scan."""
    if not wanted(cfg):
        return 0
    today = today or datetime.date.today().isoformat()
    try:
        items = due(store, today)
        try:
            told = json.loads(store.get_meta(TOLD_KEY, "{}")) or {}
        except ValueError:
            told = {}
        new = [a for a in items if told.get(a["uid"]) != a["date"]]
        if not new:
            return 0
        title, body = message(new, today)
        if not notify.notify(cfg, title, body, run=run):
            return 0
        # Only what is still due is kept: a step done or moved drops out.
        still = {a["uid"] for a in items}
        kept = {uid: when for uid, when in told.items() if uid in still}
        kept.update({a["uid"]: a["date"] for a in new})
        store.set_meta(TOLD_KEY, json.dumps(kept, sort_keys=True))
        return len(new)
    except Exception as exc:                 # any failure: log it, carry on
        log.warning("follow-up reminders not checked: %s", exc)
        return 0
