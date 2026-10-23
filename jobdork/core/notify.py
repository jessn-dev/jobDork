"""
jobdork.core.notify
===================
A notification from the operating system, with its sound, when something you
would want to know happens while you are not looking: a scan found new job
posts (one you started, or the schedule's), a scan failed, or a newer
jobdork is out.

Each system's own way, so it looks and sounds like every other app's:

  macOS    Notification Center. The desktop app posts through the system's
           notification framework (UserNotifications) under its own name and
           icon, after asking once for permission as every app does; run any
           other way, through `osascript`, which macOS shows under Script
           Editor. The sound is the system's "Glass", a bell.
  Windows  A toast in the Action Center, under the app's name: the installer
           gives the Start menu shortcut jobdork's AppUserModelID, which is
           how Windows ties a toast to an app. Run any other way, under
           Windows PowerShell's. The sound is the default notification sound.
  Linux    `notify-send`, with the freedesktop "bell" sound where the
           desktop plays one.
  Docker   none: a container has no desktop. The page shows a notice and
           rings its own bell instead.

`notifications: {enabled, sound}` in config.yaml turns either off (the
Settings page's buttons write it). `JOBDORK_NOTIFY=off` turns both off for
one run; the tests set it, so no test ever pops anything up.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time

log = logging.getLogger(__name__)

ENV = "JOBDORK_NOTIFY"
APP_ID = "io.github.jessn-dev.jobdork"     # the macOS bundle id and Windows AUMID
# Windows PowerShell's own AUMID: what a toast is shown under when jobdork is
# not the installed app, so Windows has no shortcut that names jobdork.
POWERSHELL_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
MAC_SOUND = "Glass"
TIMEOUT = 15


def off() -> bool:
    return os.environ.get(ENV, "").strip().lower() in ("off", "0", "no", "false")


def native() -> bool:
    """Whether this system can show one at all (not in a container)."""
    from .config import CONTAINER_ENV
    if off() or os.environ.get(CONTAINER_ENV):
        return False
    if sys.platform in ("darwin", "win32"):
        return True
    return bool(shutil.which("notify-send"))


def wanted(cfg) -> tuple[bool, bool]:
    """(show notifications, with sound) for these settings."""
    n = getattr(cfg, "notifications", None)
    enabled = bool(getattr(n, "enabled", True)) and not off()
    return enabled, enabled and bool(getattr(n, "sound", True))


def notify(cfg, title: str, body: str, run=subprocess.run) -> bool:
    """Show one, if the settings want it. True if one was handed to the
    system. Never raises: a notification is never worth a failed scan."""
    enabled, sound = wanted(cfg)
    if not enabled or not native():
        return False
    try:
        return send(title, body, sound=sound, run=run)
    except Exception as exc:                 # any failure: log it, carry on
        log.warning("notification not shown: %s", exc)
        return False


def scan_finished(cfg, new: int, kept: int, origin: str = "", run=subprocess.run) -> bool:
    """After a scan: told only when it found something new, since a daily
    "nothing new" trains you to ignore the one that matters."""
    if new <= 0:
        return False
    what = "job post" if new == 1 else "job posts"
    where = {"schedule": "The scheduled scan", "": "The scan"}.get(origin, "The scan")
    return notify(cfg, f"{new} new {what}",
                  f"{where} found {new} new {what} ({kept} kept in all). "
                  "Open jobdork to see them.", run=run)


def scan_failed(cfg, why: str, origin: str = "", run=subprocess.run) -> bool:
    where = "The scheduled scan" if origin == "schedule" else "The scan"
    return notify(cfg, "Scan failed", f"{where} stopped: {why}", run=run)


def send(title: str, body: str, sound: bool = True, run=subprocess.run) -> bool:
    title, body = _clean(title, 80), _clean(body, 240)
    if sys.platform == "darwin":
        if getattr(sys, "frozen", False) and _mac_framework(title, body, sound):
            return True
        return _mac_osascript(title, body, sound, run)
    if sys.platform == "win32":
        return _windows_toast(title, body, sound, run)
    return _linux(title, body, sound, run)


def _clean(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ── macOS ─────────────────────────────────────────────────────────────────────


def _mac_framework(title: str, body: str, sound: bool) -> bool:
    """Notification Center through UserNotifications, as the app itself.
    False when the framework is missing or permission was refused, so the
    caller falls back to osascript."""
    try:
        import UserNotifications as UN
    except ImportError:
        return False
    center = UN.UNUserNotificationCenter.currentNotificationCenter()
    if center is None:
        return False
    granted = {}

    def answered(ok, error):
        granted["ok"] = bool(ok)

    # Asked once; macOS remembers the answer and returns it at once after.
    center.requestAuthorizationWithOptions_completionHandler_(
        UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound, answered)
    for _ in range(50):                      # the answer comes on another thread
        if "ok" in granted:
            break
        time.sleep(0.1)
    if not granted.get("ok"):
        return False
    content = UN.UNMutableNotificationContent.alloc().init()
    content.setTitle_(title)
    content.setBody_(body)
    if sound:
        content.setSound_(UN.UNNotificationSound.defaultSound())
    request = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(
        f"jobdork-{time.time_ns()}", content, None)
    center.addNotificationRequest_withCompletionHandler_(request, None)
    return True


def _applescript_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _mac_osascript(title: str, body: str, sound: bool, run) -> bool:
    script = (f'display notification "{_applescript_text(body)}" '
              f'with title "{_applescript_text(title)}"'
              + (f' sound name "{MAC_SOUND}"' if sound else ""))
    done = run(["osascript", "-e", script], capture_output=True, text=True,
               timeout=TIMEOUT, check=False)
    return done.returncode == 0


# ── Windows ───────────────────────────────────────────────────────────────────


def _xml_text(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def toast_xml(title: str, body: str, sound: bool) -> str:
    audio = ('<audio src="ms-winsoundevent:Notification.Default"/>' if sound
             else '<audio silent="true"/>')
    return ('<toast><visual><binding template="ToastGeneric">'
            f"<text>{_xml_text(title)}</text><text>{_xml_text(body)}</text>"
            f"</binding></visual>{audio}</toast>")


def _windows_toast(title: str, body: str, sound: bool, run) -> bool:
    aumid = APP_ID if getattr(sys, "frozen", False) else POWERSHELL_AUMID
    # The toast's XML and the app id go in as environment variables, not into
    # the script's text, so nothing in a title can change what PowerShell runs.
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] > $null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] > $null; "
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        "$x.LoadXml($env:JOBDORK_TOAST); "
        "$t = [Windows.UI.Notifications.ToastNotification]::new($x); "
        "[Windows.UI.Notifications.ToastNotificationManager]::"
        "CreateToastNotifier($env:JOBDORK_AUMID).Show($t)")
    env = {**os.environ, "JOBDORK_TOAST": toast_xml(title, body, sound),
           "JOBDORK_AUMID": aumid}
    done = run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-Command", script], capture_output=True, text=True, env=env,
               timeout=TIMEOUT, check=False,
               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return done.returncode == 0


# ── Linux ─────────────────────────────────────────────────────────────────────


def _linux(title: str, body: str, sound: bool, run) -> bool:
    argv = ["notify-send", "--app-name=jobdork", title, body]
    if sound:
        argv.insert(1, "--hint=string:sound-name:bell")
    done = run(argv, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    return done.returncode == 0
