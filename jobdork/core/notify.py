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
           icon, after asking once for permission as every app does (when
           its window opens: web/app.py); a click opens jobdork. Run any
           other way, through `osascript`, which macOS shows under Script
           Editor. The sound is the system's "Glass", a bell.
  Windows  A toast in the Action Center, under the app's name: the installer
           gives the Start menu shortcut jobdork's AppUserModelID, which is
           how Windows ties a toast to an app, and registers `jobdork://`,
           which a click on the app's toast opens (LAUNCH). Run any other
           way, under Windows PowerShell's. The sound is the default
           notification sound.
  Linux    `notify-send`, with the freedesktop "bell" sound where the
           desktop plays one. The desktop app's has an "Open jobdork"
           action where notify-send has `--action` (libnotify 0.7.9+).

A click on the desktop app's notification opens jobdork; with jobdork open
already, its window comes to the front (web/app.py, `show_open_window`).
Clicking one used to open Script Editor on a Mac and a folder on Windows,
as they had nothing to open (2026-11-10).
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

from .textutil import xml_text as _xml_text

log = logging.getLogger(__name__)

ENV = "JOBDORK_NOTIFY"
APP_ID = "io.github.jessn-dev.jobdork"     # the macOS bundle id and Windows AUMID
# Windows PowerShell's own AUMID: what a toast is shown under when jobdork is
# not the installed app, so Windows has no shortcut that names jobdork.
POWERSHELL_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
MAC_SOUND = "Glass"
TIMEOUT = 15
# What a click on the Windows app's toast opens: the installer registers it
# to start jobdork.exe (packaging/jobdork.iss), which shows jobdork.
LAUNCH = "jobdork://open"


def off() -> bool:
    from .config import env_off
    return env_off(ENV)


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


def first_scan_ready(cfg, kept: int, run=subprocess.run) -> bool:
    """The end of setup's first scan: said whatever was new, since this is
    the one someone closed the window to wait for."""
    what = "job post" if kept == 1 else "job posts"
    return notify(cfg, "Your job posts are ready",
                  f"jobdork has read every employer board: {kept} {what} to look at. "
                  "Open jobdork and choose View job posts.", run=run)


def scan_failed(cfg, why: str, origin: str = "", run=subprocess.run) -> bool:
    where = "The scheduled scan" if origin == "schedule" else "The scan"
    return notify(cfg, "Scan failed", f"{where} stopped: {why}", run=run)


def send(title: str, body: str, sound: bool = True, run=subprocess.run) -> bool:
    title, body = _clean(title, 80), _clean(body, 240)
    if sys.platform == "darwin":
        if getattr(sys, "frozen", False):
            # The app's own notification, which opens jobdork when clicked.
            # Never osascript for the app: macOS files those under Script
            # Editor, and a click opened Script Editor.
            if _mac_framework(title, body, sound):
                return True
            log.warning("macOS did not let jobdork show a notification: allow it in "
                        "System Settings, Notifications, jobdork")
            return False
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
    if center is None or not _mac_allowed(UN, center):
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


def _mac_allowed(UN, center) -> bool:
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
    return bool(granted.get("ok"))


def ask_permission() -> bool:
    """The Mac app asks for permission to notify when its window opens, while
    you are there to answer: a scheduled scan or a reminder runs with no
    window, and a question it asked could go unseen, leaving every later
    notification refused. True when allowed; elsewhere nothing to ask."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False) or off():
        return True
    try:
        import UserNotifications as UN
    except ImportError:
        return False
    center = UN.UNUserNotificationCenter.currentNotificationCenter()
    return center is not None and _mac_allowed(UN, center)


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


def toast_xml(title: str, body: str, sound: bool) -> str:
    audio = ('<audio src="ms-winsoundevent:Notification.Default"/>' if sound
             else '<audio silent="true"/>')
    return ('<toast><visual><binding template="ToastGeneric">'
            f"<text>{_xml_text(title)}</text><text>{_xml_text(body)}</text>"
            f"</binding></visual>{audio}</toast>")


def _windows_toast(title: str, body: str, sound: bool, run) -> bool:
    from . import store

    app = getattr(sys, "frozen", False)
    # The Store's package has an app id of its own (core/store.py).
    aumid = store.aumid() or (APP_ID if app else POWERSHELL_AUMID)
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
    toast = toast_xml(title, body, sound)
    if app:
        # What a click opens (LAUNCH). Without it a click had nothing to open,
        # and Windows opened a folder. Only the installed app has
        # `jobdork://` registered; anywhere else a click would ask which app
        # opens it.
        toast = toast.replace("<toast>", f'<toast launch="{LAUNCH}" activationType="protocol">', 1)
    env = {**os.environ, "JOBDORK_TOAST": toast,
           "JOBDORK_AUMID": aumid}
    done = run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-Command", script], capture_output=True, text=True, env=env,
               timeout=TIMEOUT, check=False,
               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return done.returncode == 0


# ── Linux ─────────────────────────────────────────────────────────────────────


# Starts the shell that waits for a click on the app's notification (_linux),
# here so a test can stand in for it.
_spawn = subprocess.Popen

# Waits for the notification's answer, and opens jobdork when it was "open".
# The program and notify-send's arguments come in as $1 and the rest, never
# inside the script's text, so nothing in a title can change what it runs.
_OPEN_ON_CLICK = ('prog=$1; shift; '
                  'answer=$(notify-send --action=open="Open jobdork" "$@"); '
                  '[ "$answer" = open ] && exec "$prog"')


def _has_actions(run) -> bool:
    """Whether this notify-send takes --action (libnotify 0.7.9 and later)."""
    try:
        done = run(["notify-send", "--help"], capture_output=True, text=True,
                   timeout=TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return "--action" in f"{done.stdout or ''}{done.stderr or ''}"


def _linux(title: str, body: str, sound: bool, run) -> bool:
    argv = ["notify-send", "--app-name=jobdork", title, body]
    if sound:
        argv.insert(1, "--hint=string:sound-name:bell")
    if getattr(sys, "frozen", False):
        # The app: grouped under its desktop entry, and a click opens it.
        # notify-send waits for the click, so a shell of its own waits, which
        # outlives a scheduled scan that ends before anyone clicks.
        argv.insert(1, "--hint=string:desktop-entry:jobdork")
        if _has_actions(run):
            from .schedule import program
            try:
                _spawn(["sh", "-c", _OPEN_ON_CLICK, "sh", program(), *argv[1:]],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, start_new_session=True)
                return True
            except OSError:
                pass                 # shown below without the action instead
    done = run(argv, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    return done.returncode == 0
