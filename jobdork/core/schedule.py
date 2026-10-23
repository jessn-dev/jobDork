"""
jobdork.core.schedule
=====================
Scans that run by themselves, from the operating system's own scheduler, so
they happen whether or not jobdork is open.

One entry per user, in the scheduler each system already has:

  macOS    a LaunchAgent, ~/Library/LaunchAgents/io.github.jessn-dev.jobdork.scan.plist.
           launchd runs a time missed while the Mac slept once it wakes.
  Windows  a task, "jobdork scan", in Task Scheduler. Made from XML, since
           `schtasks /Create` alone cannot say "run a missed time when the
           PC is next on" or "on battery too".
  Linux    a line in the user's crontab, ending `# jobdork-scan`.

The entry starts this install, whichever it is: the desktop app's own program
with `--scan` (packaging/jobdork_app.py), or this Python with
`-m jobdork -c <config> scan --scheduled`. The dork tool's `--cron` wrote
`sys.executable generator.py` instead, which in the desktop app is a path
inside the app that nothing can run.

The scheduler is the only record: what the page shows is read back from it,
so an entry removed by hand reads as off, and one that starts another copy
of jobdork (the app moved, a second install) says so. Nothing is kept in
config.yaml. A container has no scheduler of its own; there the host's
starts `docker exec`, as docs/DEPLOY.md shows.
"""

from __future__ import annotations

import os
import plistlib
import re
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .config import CONTAINER_ENV, ConfigError

EVERY = ("daily", "weekdays", "weekly")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday")

LABEL = "io.github.jessn-dev.jobdork.scan"   # launchd; the app's own id + .scan
TASK_NAME = "jobdork scan"                     # Task Scheduler
CRON_MARKER = "# jobdork-scan"                 # crontab
LOG_FILE = "logs/scheduled-scan.log"

_AT = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_TASK_NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"


@dataclass(frozen=True)
class Plan:
    """When to scan: every day, every weekday, or one day a week, at a time."""

    every: str = "daily"
    at: str = "08:00"
    day: str = "mon"                       # for "weekly" only

    def check(self) -> Plan:
        """The same plan, tidied; ConfigError for one that cannot be."""
        every = str(self.every or "").strip().lower()
        if every not in EVERY:
            raise ConfigError(f"scan schedule: every must be one of {', '.join(EVERY)}")
        match = _AT.match(str(self.at or "").strip())
        if not match:
            raise ConfigError("scan schedule: the time must be like 08:00 (24-hour)")
        day = str(self.day or "mon").strip().lower()[:3]
        if day not in DAYS:
            raise ConfigError("scan schedule: the day must be one of mon to sun")
        return Plan(every, f"{int(match[1]):02d}:{match[2]}", day)

    @property
    def hour(self) -> int:
        return int(self.at.split(":")[0])

    @property
    def minute(self) -> int:
        return int(self.at.split(":")[1])

    def weekdays(self) -> list[int]:
        """The days it runs, Monday 0 to Sunday 6."""
        if self.every == "daily":
            return list(range(7))
        if self.every == "weekdays":
            return list(range(5))
        return [DAYS.index(self.day)]

    def describe(self) -> str:
        when = {"daily": "every day", "weekdays": "every weekday (Monday to Friday)",
                "weekly": f"every {DAY_NAMES[DAYS.index(self.day)]}"}[self.every]
        return f"{when} at {self.at}"


def _plan_from_days(days: list[int], hour: int, minute: int) -> Plan | None:
    days = sorted(set(days))
    at = f"{hour:02d}:{minute:02d}"
    if days == list(range(7)):
        return Plan("daily", at)
    if days == list(range(5)):
        return Plan("weekdays", at)
    if len(days) == 1:
        return Plan("weekly", at, DAYS[days[0]])
    return None                            # made by hand; shown as "other"


# ── What the entry runs ───────────────────────────────────────────────────────


def frozen() -> bool:
    """True in the desktop app, where sys.executable is the app itself."""
    return bool(getattr(sys, "frozen", False))


def command(config_path: str) -> list[str]:
    """The program and arguments the scheduler starts."""
    if frozen():
        return [sys.executable, "--scan"]
    python = sys.executable
    if sys.platform == "win32":
        # pythonw has no console, so a scan at 8 a.m. does not open a black
        # window in front of whatever the user is doing.
        quiet = Path(python).with_name("pythonw.exe")
        python = str(quiet) if quiet.exists() else python
    return [python, "-m", "jobdork", "-c", str(Path(config_path).resolve()),
            "scan", "--scheduled"]


def workdir(config_path: str) -> str:
    """Where the scan starts: the config's folder, where .env and data/ are."""
    return str(Path(config_path).resolve().parent)


def unsupported() -> str:
    """Why this copy cannot schedule scans, or '' when it can."""
    if os.environ.get(CONTAINER_ENV):
        return ("jobdork is running in a container, which has no scheduler of "
                "its own. Schedule `docker exec jobdork jobdork scan` on the "
                "host instead (docs/DEPLOY.md).")
    if sys.platform not in ("darwin", "win32") and not _which("crontab"):
        return "this system has no crontab command to schedule with"
    return ""


def _which(name: str) -> str:
    import shutil
    return shutil.which(name) or ""


# ── The three schedulers ──────────────────────────────────────────────────────
# Each has write(plan, argv, cwd), read() -> (plan, argv) or None, remove().
# `run` is subprocess.run, replaced in tests so nothing is installed.


class LaunchAgent:
    def __init__(self, folder: Path | None = None, run=subprocess.run,
                 uid: int | None = None) -> None:
        self.path = (folder or Path.home() / "Library" / "LaunchAgents") / f"{LABEL}.plist"
        self.run = run
        self.uid = os.getuid() if uid is None else uid

    def plist(self, plan: Plan, argv: list[str], cwd: str) -> bytes:
        # launchd counts Sunday as 0 and Monday as 1.
        times = [{"Hour": plan.hour, "Minute": plan.minute, "Weekday": (d + 1) % 7}
                 for d in plan.weekdays()]
        if plan.every == "daily":
            times = [{"Hour": plan.hour, "Minute": plan.minute}]
        log = str(Path(cwd) / LOG_FILE)
        return plistlib.dumps({
            "Label": LABEL,
            "ProgramArguments": argv,
            "WorkingDirectory": cwd,
            "StartCalendarInterval": times,
            "StandardOutPath": log,
            "StandardErrorPath": log,
            "ProcessType": "Background",
        })

    def write(self, plan: Plan, argv: list[str], cwd: str) -> None:
        (Path(cwd) / LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._unload()
        self.path.write_bytes(self.plist(plan, argv, cwd))
        done = self.run(["launchctl", "bootstrap", f"gui/{self.uid}", str(self.path)],
                        capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise ConfigError("macOS would not load the schedule: "
                              + (done.stderr or done.stdout or "").strip()[:300])

    def read(self) -> tuple[Plan | None, list[str]] | None:
        if not self.path.is_file():
            return None
        try:
            data = plistlib.loads(self.path.read_bytes())
        except Exception:                   # not ours to fix; shown as "other"
            return None, []
        times = data.get("StartCalendarInterval") or []
        if isinstance(times, dict):
            times = [times]
        plan = None
        if times and all("Hour" in t for t in times):
            hour, minute = times[0]["Hour"], times[0].get("Minute", 0)
            if len(times) == 1 and "Weekday" not in times[0]:
                plan = Plan("daily", f"{hour:02d}:{minute:02d}")
            elif all("Weekday" in t for t in times):
                plan = _plan_from_days([(t["Weekday"] - 1) % 7 for t in times],
                                       hour, minute)
        return plan, list(data.get("ProgramArguments") or [])

    def remove(self) -> None:
        self._unload()
        self.path.unlink(missing_ok=True)

    def _unload(self) -> None:
        if self.path.is_file():
            self.run(["launchctl", "bootout", f"gui/{self.uid}", str(self.path)],
                     capture_output=True, text=True, check=False)


class WindowsTask:
    def __init__(self, run=subprocess.run) -> None:
        self.run = run

    def xml(self, plan: Plan, argv: list[str], cwd: str) -> str:
        start = (date.today() + timedelta(days=1)).isoformat()
        if plan.every == "daily":
            when = "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
        else:
            days = "".join(f"<{DAY_NAMES[d]} />" for d in plan.weekdays())
            when = (f"<ScheduleByWeek><DaysOfWeek>{days}</DaysOfWeek>"
                    "<WeeksInterval>1</WeeksInterval></ScheduleByWeek>")
        program = _xml_text(argv[0])
        arguments = _xml_text(subprocess.list2cmdline(argv[1:]))
        return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="{_TASK_NS}">
  <RegistrationInfo><Description>jobdork: scan for new job posts</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}T{plan.at}:00</StartBoundary>
      <Enabled>true</Enabled>
      {when}
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{program}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{_xml_text(cwd)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""

    def write(self, plan: Plan, argv: list[str], cwd: str) -> None:
        (Path(cwd) / LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        # schtasks reads the file as UTF-16, as its first line says.
        with tempfile.TemporaryDirectory(prefix="jobdork-") as tmp:
            path = Path(tmp) / "task.xml"
            path.write_text(self.xml(plan, argv, cwd), encoding="utf-16")
            done = self.run(["schtasks", "/Create", "/F", "/TN", TASK_NAME,
                             "/XML", str(path)],
                            capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise ConfigError("Windows would not create the task: "
                              + (done.stderr or done.stdout or "").strip()[:300])

    def read(self) -> tuple[Plan | None, list[str]] | None:
        done = self.run(["schtasks", "/Query", "/TN", TASK_NAME, "/XML", "ONE"],
                        capture_output=True, text=True, check=False)
        if done.returncode != 0 or "<Task" not in (done.stdout or ""):
            return None
        return self.parse(done.stdout)

    @staticmethod
    def parse(text: str) -> tuple[Plan | None, list[str]]:
        # ElementTree refuses a str that declares an encoding.
        text = re.sub(r"^<\?xml[^>]*\?>", "", text.strip())
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return None, []
        ns = {"t": _TASK_NS}
        program = root.findtext(".//t:Exec/t:Command", "", ns)
        argv = [program, *_split_windows(root.findtext(".//t:Exec/t:Arguments", "", ns))]
        start = root.findtext(".//t:CalendarTrigger/t:StartBoundary", "", ns)
        match = re.search(r"T(\d\d):(\d\d)", start)
        if not match:
            return None, argv
        hour, minute = int(match[1]), int(match[2])
        if root.find(".//t:ScheduleByDay", ns) is not None:
            interval = root.findtext(".//t:ScheduleByDay/t:DaysInterval", "1", ns)
            return (_plan_from_days(list(range(7)), hour, minute)
                    if interval == "1" else None), argv
        days = root.find(".//t:ScheduleByWeek/t:DaysOfWeek", ns)
        if days is None:
            return None, argv
        picked = [DAY_NAMES.index(el.tag.split("}")[-1]) for el in days
                  if el.tag.split("}")[-1] in DAY_NAMES]
        return _plan_from_days(picked, hour, minute), argv

    def remove(self) -> None:
        self.run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
                 capture_output=True, text=True, check=False)


class Crontab:
    def __init__(self, run=subprocess.run) -> None:
        self.run = run

    def line(self, plan: Plan, argv: list[str], cwd: str) -> str:
        dow = {"daily": "*", "weekdays": "1-5"}.get(
            plan.every, str((DAYS.index(plan.day) + 1) % 7))
        return (f"{plan.minute} {plan.hour} * * {dow} "
                f"cd {shlex.quote(cwd)} && {shlex.join(argv)} {CRON_MARKER}")

    def _lines(self) -> list[str]:
        done = self.run(["crontab", "-l"], capture_output=True, text=True, check=False)
        return (done.stdout or "").splitlines() if done.returncode == 0 else []

    def _save(self, lines: list[str]) -> None:
        done = self.run(["crontab", "-"], input="".join(f"{x}\n" for x in lines),
                        capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise ConfigError("crontab would not take the schedule: "
                              + (done.stderr or "").strip()[:300])

    def write(self, plan: Plan, argv: list[str], cwd: str) -> None:
        (Path(cwd) / LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        lines = [x for x in self._lines() if not x.rstrip().endswith(CRON_MARKER)]
        self._save([*lines, self.line(plan, argv, cwd)])

    def read(self) -> tuple[Plan | None, list[str]] | None:
        for line in self._lines():
            if line.rstrip().endswith(CRON_MARKER):
                return self.parse(line)
        return None

    @staticmethod
    def parse(line: str) -> tuple[Plan | None, list[str]]:
        fields = line.split(None, 5)
        if len(fields) < 6:
            return None, []
        minute, hour, _dom, _mon, dow, rest = fields
        rest = rest.rsplit(CRON_MARKER, 1)[0]
        try:
            argv = shlex.split(rest.split("&&", 1)[-1])
        except ValueError:
            argv = []
        if not (minute.isdigit() and hour.isdigit()):
            return None, argv
        if dow == "*":
            days = list(range(7))
        elif dow == "1-5":
            days = list(range(5))
        elif dow.isdigit():
            days = [(int(dow) - 1) % 7]
        else:
            return None, argv
        return _plan_from_days(days, int(hour), int(minute)), argv

    def remove(self) -> None:
        lines = self._lines()
        kept = [x for x in lines if not x.rstrip().endswith(CRON_MARKER)]
        if kept != lines:
            self._save(kept)


def scheduler():
    """This system's scheduler."""
    if sys.platform == "darwin":
        return LaunchAgent()
    if sys.platform == "win32":
        return WindowsTask()
    return Crontab()


# ── What the page calls ───────────────────────────────────────────────────────


def status(config_path: str, sched=None) -> dict:
    """What is scheduled, for the page. Never raises."""
    why = unsupported() if sched is None else ""
    if why:
        return {"supported": False, "why": why, "on": False}
    sched = sched or scheduler()
    try:
        found = sched.read()
    except Exception as exc:                 # a scheduler that cannot be asked
        return {"supported": True, "on": False, "problem": f"could not read it: {exc}"}
    if found is None:
        return {"supported": True, "on": False}
    plan, argv = found
    report = {"supported": True, "on": True, "log": LOG_FILE,
              "other_copy": bool(argv) and argv != command(config_path)}
    if plan is None:
        report.update(every="other", describe="at times set outside jobdork")
    else:
        report.update(every=plan.every, at=plan.at, day=plan.day,
                      describe=plan.describe())
    return report


def install(config_path: str, plan: Plan, sched=None) -> dict:
    """Schedule scans for this install, replacing any schedule there was."""
    if not config_path:
        raise ConfigError("save your settings first: there is no config file to scan with")
    why = unsupported() if sched is None else ""
    if why:
        raise ConfigError(why)
    plan = plan.check()
    sched = sched or scheduler()
    sched.write(plan, command(config_path), workdir(config_path))
    return status(config_path, sched)


def uninstall(config_path: str, sched=None) -> dict:
    why = unsupported() if sched is None else ""
    if why:
        raise ConfigError(why)
    sched = sched or scheduler()
    sched.remove()
    return status(config_path, sched)


def _xml_text(value: str) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _split_windows(text: str) -> list[str]:
    """The reverse of subprocess.list2cmdline, for what it writes."""
    out, cur, quoted, slashes, any_ = [], [], False, 0, False
    for ch in text or "":
        if ch == "\\":
            slashes += 1
            continue
        if ch == '"':
            cur.append("\\" * (slashes // 2))
            if slashes % 2:
                cur.append('"')
            else:
                quoted = not quoted
                any_ = True
            slashes = 0
            continue
        cur.append("\\" * slashes)
        slashes = 0
        if ch in " \t" and not quoted:
            if "".join(cur) or any_:
                out.append("".join(cur))
            cur, any_ = [], False
            continue
        cur.append(ch)
    cur.append("\\" * slashes)
    if "".join(cur) or any_:
        out.append("".join(cur))
    return out
