"""
Tests for scans that run by themselves (core/schedule.py), the lock that
keeps two scans from running at once (search/scan.py), and the check for a
newer release (core/updates.py).

Nothing here touches the real scheduler or goes online: every scheduler is
given a stand-in for subprocess.run, and the release check a stand-in fetch.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import contextlib
import json
import os
import plistlib
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import schedule, updates
from jobdork.core.config import ConfigError
from jobdork.search import scan as scan_mod


@contextlib.contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _frozen(exe: str):
    saved = sys.executable
    sys.frozen = True
    sys.executable = exe
    try:
        yield
    finally:
        del sys.frozen
        sys.executable = saved


class _Calls:
    """Records what would have been run; answers like the real command."""

    def __init__(self, answers=None):
        self.calls: list[list[str]] = []
        self.inputs: list[str] = []
        self.answers = answers or {}

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        if "input" in kw:
            self.inputs.append(kw["input"])
        code, out = self.answers.get(argv[0], (0, ""))
        if callable(out):
            out = out(argv, kw)
        return types.SimpleNamespace(returncode=code, stdout=out, stderr="")


# ── the plan ──────────────────────────────────────────────────────────────────


def test_a_plan_is_tidied_and_described():
    plan = schedule.Plan("Weekly", "7:05", "Friday").check()
    assert plan == schedule.Plan("weekly", "07:05", "fri")
    assert plan.describe() == "every Friday at 07:05"
    assert schedule.Plan("weekdays", "18:30").check().weekdays() == [0, 1, 2, 3, 4]
    assert schedule.Plan("daily", "08:00").check().describe() == "every day at 08:00"


def test_a_plan_that_cannot_be_is_refused():
    for bad in (schedule.Plan("hourly", "08:00"), schedule.Plan("daily", "25:00"),
                schedule.Plan("daily", "8am"), schedule.Plan("weekly", "08:00", "xyz")):
        try:
            bad.check()
        except ConfigError:
            continue
        raise AssertionError(f"accepted {bad}")


# ── what it runs ──────────────────────────────────────────────────────────────


def test_a_pip_install_runs_this_python_on_its_own_config():
    argv = schedule.command("some/dir/config.yaml")
    assert argv[0] == sys.executable or argv[0].endswith("pythonw.exe")
    assert argv[1:3] == ["-m", "jobdork"]
    assert argv[3] == "-c" and Path(argv[4]).is_absolute()
    assert argv[-2:] == ["scan", "--scheduled"]
    assert schedule.workdir("some/dir/config.yaml") == str(Path("some/dir").resolve())


def test_the_desktop_app_runs_itself_not_a_path_inside_it():
    with _frozen("/Applications/jobdork.app/Contents/MacOS/jobdork"):
        assert schedule.command("/x/config.yaml") == [
            "/Applications/jobdork.app/Contents/MacOS/jobdork", "--scan"]


def test_a_container_cannot_schedule_and_says_what_to_do():
    with _env(JOBDORK_IN_CONTAINER="1"):
        assert "docker exec" in schedule.unsupported()
        assert schedule.status("/x/config.yaml")["supported"] is False
        try:
            schedule.install("/x/config.yaml", schedule.Plan())
        except ConfigError as exc:
            assert "container" in str(exc)
        else:
            raise AssertionError("installed in a container")


# ── macOS ─────────────────────────────────────────────────────────────────────


def test_macos_writes_a_launch_agent_and_reads_it_back():
    with tempfile.TemporaryDirectory() as tmp:
        run = _Calls()
        agent = schedule.LaunchAgent(folder=Path(tmp) / "LaunchAgents", run=run, uid=501)
        config = str(Path(tmp) / "config.yaml")
        state = schedule.install(config, schedule.Plan("weekdays", "07:30"), sched=agent)
        assert state["on"] and state["every"] == "weekdays" and state["at"] == "07:30"
        assert not state["other_copy"]

        data = plistlib.loads(agent.path.read_bytes())
        assert data["Label"] == schedule.LABEL
        assert data["ProgramArguments"] == schedule.command(config)
        assert data["WorkingDirectory"] == str(Path(tmp).resolve())
        # Monday to Friday is 1 to 5 to launchd.
        assert sorted(t["Weekday"] for t in data["StartCalendarInterval"]) == [1, 2, 3, 4, 5]
        assert data["StandardOutPath"].endswith(schedule.LOG_FILE)
        assert ["launchctl", "bootstrap", "gui/501", str(agent.path)] in run.calls

        # Saved again: unloaded first, so launchd takes the new times.
        schedule.install(config, schedule.Plan("weekly", "09:00", "sun"), sched=agent)
        assert ["launchctl", "bootout", "gui/501", str(agent.path)] in run.calls
        times = plistlib.loads(agent.path.read_bytes())["StartCalendarInterval"]
        assert times == [{"Hour": 9, "Minute": 0, "Weekday": 0}]
        assert schedule.status(config, agent)["describe"] == "every Sunday at 09:00"

        state = schedule.uninstall(config, sched=agent)
        assert not agent.path.exists() and state == {"supported": True, "on": False}


def test_macos_daily_is_one_time_a_day():
    agent = schedule.LaunchAgent(folder=Path("/nowhere"), run=_Calls(), uid=1)
    data = plistlib.loads(agent.plist(schedule.Plan("daily", "08:15"), ["x"], "/w"))
    assert data["StartCalendarInterval"] == [{"Hour": 8, "Minute": 15}]


def test_a_launchctl_refusal_is_reported():
    with tempfile.TemporaryDirectory() as tmp:
        agent = schedule.LaunchAgent(folder=Path(tmp), uid=1,
                                     run=_Calls({"launchctl": (5, "")}))
        try:
            agent.write(schedule.Plan(), ["x"], tmp)
        except ConfigError as exc:
            assert "macOS would not load" in str(exc)
        else:
            raise AssertionError("no error")


def test_an_entry_starting_another_copy_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        agent = schedule.LaunchAgent(folder=Path(tmp), run=_Calls(), uid=1)
        agent.path.write_bytes(agent.plist(schedule.Plan(), ["/old/jobdork", "--scan"], tmp))
        state = schedule.status(str(Path(tmp) / "config.yaml"), agent)
        assert state["on"] and state["other_copy"]


# ── Windows ───────────────────────────────────────────────────────────────────


def test_windows_task_xml_reads_back_with_awkward_paths():
    task = schedule.WindowsTask(run=_Calls())
    argv = [r"C:\Program Files\jobdork\jobdork.exe", "--scan"]
    xml = task.xml(schedule.Plan("weekly", "06:45", "wed"), argv, r"C:\Users\Al & Bo\jobdork")
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in xml
    assert "Al &amp; Bo" in xml
    plan, back = schedule.WindowsTask.parse(xml)
    assert plan == schedule.Plan("weekly", "06:45", "wed") and back == argv

    plan, _ = schedule.WindowsTask.parse(
        task.xml(schedule.Plan("daily", "08:00"), argv, "C:\\w"))
    assert plan == schedule.Plan("daily", "08:00")


def test_windows_arguments_survive_the_round_trip():
    for args in (["-m", "jobdork", "-c", r"C:\My Files\config.yaml", "scan"],
                 ['say "hi"', "a\\b\\", ""], []):
        import subprocess
        assert schedule._split_windows(subprocess.list2cmdline(args)) == args, args


def test_windows_creates_the_task_from_a_file():
    with tempfile.TemporaryDirectory() as tmp:
        seen = {}

        def created(argv, kw):
            seen["xml"] = Path(argv[argv.index("/XML") + 1]).read_text(encoding="utf-16")
            return ""
        run = _Calls({"schtasks": (0, created)})
        schedule.WindowsTask(run=run).write(schedule.Plan(), ["prog.exe", "--scan"], tmp)
        assert run.calls[0][:5] == ["schtasks", "/Create", "/F", "/TN", schedule.TASK_NAME]
        assert "<Command>prog.exe</Command>" in seen["xml"]


# ── Linux ─────────────────────────────────────────────────────────────────────


def test_crontab_keeps_other_lines_and_replaces_its_own():
    table = {"text": "0 1 * * * backup.sh\n"}

    def crontab(argv, kw):
        if argv[1:] == ["-l"]:
            return table["text"]
        table["text"] = kw["input"]
        return ""

    with tempfile.TemporaryDirectory() as tmp:
        cron = schedule.Crontab(run=_Calls({"crontab": (0, crontab)}))
        config = str(Path(tmp) / "my dir" / "config.yaml")
        schedule.install(config, schedule.Plan("daily", "08:00"), sched=cron)
        schedule.install(config, schedule.Plan("weekly", "21:05", "sun"), sched=cron)
        lines = table["text"].splitlines()
        assert lines[0] == "0 1 * * * backup.sh"
        assert len(lines) == 2 and lines[1].startswith("5 21 * * 0 cd ")
        assert lines[1].endswith(schedule.CRON_MARKER)
        state = schedule.status(config, cron)
        assert state["every"] == "weekly" and state["day"] == "sun"
        assert not state["other_copy"], state

        schedule.uninstall(config, sched=cron)
        assert table["text"] == "0 1 * * * backup.sh\n"


def test_an_entry_edited_by_hand_shows_as_other():
    plan, argv = schedule.Crontab.parse(
        f"*/30 * * * * cd /w && jobdork scan {schedule.CRON_MARKER}")
    assert plan is None and argv == ["jobdork", "scan"]


# ── the scan lock ─────────────────────────────────────────────────────────────


def test_a_second_scan_of_the_same_database_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "data" / "jobdork.db")
        with scan_mod.scan_lock(db):
            try:
                with scan_mod.scan_lock(db):
                    raise AssertionError("two scans held the lock")
            except scan_mod.ScanBusy as exc:
                assert "already running" in str(exc)
        with scan_mod.scan_lock(db):      # let go of, so the next one runs
            pass
        # Another database is another lock.
        with scan_mod.scan_lock(db), scan_mod.scan_lock(str(Path(tmp) / "other" / "x.db")):
            pass


def test_a_scheduled_scan_that_finds_one_running_steps_aside():
    from jobdork import cli

    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "config.yaml"
        db = Path(tmp) / "data" / "jobdork.db"
        config.write_text("titles: {include: [nurse]}\n"
                          "locations: {countries: [US]}\n"
                          f"db: {db}\n", encoding="utf-8")
        saved = sys.stdout, sys.stderr
        try:
            with scan_mod.scan_lock(str(db)):
                code = cli.main(["-c", str(config), "scan", "--scheduled"])
        finally:
            sys.stdout.close()
            sys.stdout, sys.stderr = saved
            import logging
            logging.basicConfig(force=True)
        assert code == 0
        log = (Path(tmp) / schedule.LOG_FILE).read_text(encoding="utf-8")
        assert "scheduled scan" in log and "already running" in log


def test_the_scheduled_log_keeps_its_newest_half():
    from jobdork import cli

    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / schedule.LOG_FILE
        log.parent.mkdir(parents=True)
        log.write_text("old line\n" * (cli.SCHEDULED_LOG_BYTES // 9 + 10), encoding="utf-8")
        saved = sys.stdout, sys.stderr
        try:
            cli._log_scheduled(types.SimpleNamespace(
                path=str(Path(tmp) / "config.yaml"),
                db_path=str(Path(tmp) / "data" / "jobdork.db")))
        finally:
            sys.stdout.close()
            sys.stdout, sys.stderr = saved
            import logging
            logging.basicConfig(force=True)
        text = log.read_text(encoding="utf-8")
        assert len(text) < cli.SCHEDULED_LOG_BYTES * 0.6
        assert text.startswith("old line\n")


# ── a newer release ───────────────────────────────────────────────────────────


def _release(tag, prerelease=False):
    # lambda: stands in for the fetch, ignoring the URL it is given.
    return lambda url: {"tag_name": tag, "prerelease": prerelease,
                        "html_url": f"https://github.com/jessn-dev/jobDork/releases/tag/{tag}"}


def test_a_newer_release_is_reported_with_what_to_do():
    with tempfile.TemporaryDirectory() as tmp, _env(JOBDORK_UPDATE_CHECK=None):
        found = updates.check(tmp, current="0.14.3", fetch=_release("v0.14.4"))
        assert found["newer"] and found["latest"] == "0.14.4"
        assert found["url"].endswith("/v0.14.4") and found["how"]
        assert not updates.check(tmp, current="0.14.4", fetch=_release("v0.14.4"))["newer"]
        assert not updates.check(tmp, current="0.15.0", fetch=_release("v0.14.4"))["newer"]


def test_github_is_asked_once_a_day():
    calls = []

    def fetch(url):
        calls.append(url)
        return {"tag_name": "v1.0.0", "html_url": "https://github.com/x"}

    def clock(at):
        # lambda: a clock stopped at `at`, called as time.time() would be.
        return lambda: at

    with tempfile.TemporaryDirectory() as tmp, _env(JOBDORK_UPDATE_CHECK=None):
        updates.check(tmp, current="0.14.3", fetch=fetch, now=clock(1000.0))
        updates.check(tmp, current="0.14.3", fetch=fetch, now=clock(2000.0))
        assert len(calls) == 1
        kept = json.loads((Path(tmp) / updates.CACHE_FILE).read_text())
        assert kept["release"]["version"] == "1.0.0"
        updates.check(tmp, current="0.14.3", fetch=fetch,
                      now=clock(1000.0 + updates.CHECK_SECONDS + 1))
        assert len(calls) == 2


def test_no_answer_off_or_a_prerelease_shows_nothing():
    def offline(url):
        raise OSError("no network")

    with tempfile.TemporaryDirectory() as tmp, _env(JOBDORK_UPDATE_CHECK=None):
        assert not updates.check(tmp, current="0.14.3", fetch=offline)["newer"]
    with tempfile.TemporaryDirectory() as tmp, _env(JOBDORK_UPDATE_CHECK=None):
        assert not updates.check(tmp, current="0.14.3",
                                 fetch=_release("v0.15.0", prerelease=True))["newer"]
    with tempfile.TemporaryDirectory() as tmp, _env(JOBDORK_UPDATE_CHECK="off"):
        assert not updates.check(tmp, current="0.14.3", fetch=_release("v9.0.0"))["newer"]
    # A clone has no version to compare.
    assert updates.parse("0.0.0+source") is None


def test_the_setting_turns_the_check_off_and_asks_nothing():
    asked = []

    def fetch(url):
        asked.append(url)
        return {"tag_name": "v9.0.0", "html_url": "https://github.com/x"}

    with tempfile.TemporaryDirectory() as tmp, _env(JOBDORK_UPDATE_CHECK=None):
        assert not updates.check(tmp, current="0.14.3", fetch=fetch, enabled=False)["newer"]
        assert asked == []
        assert updates.check(tmp, current="0.14.3", fetch=fetch)["newer"]


def test_update_check_is_a_setting_the_page_can_write():
    from jobdork.core import config as config_mod
    from jobdork.core import setup

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text("titles: {include: [nurse]}\n", encoding="utf-8")
        assert config_mod.load(str(path)).update_check is True
        assert setup.write(str(path), {"update_check": False}).update_check is False
        assert "update_check: false" in path.read_text(encoding="utf-8")
        assert setup.write(str(path), {"update_check": "true"}).update_check is True
        path.write_text("titles: {include: [nurse]}\nupdate_check: sometimes\n",
                        encoding="utf-8")
        try:
            config_mod.load(str(path))
        except ConfigError as exc:
            assert "update_check" in str(exc)
        else:
            raise AssertionError("accepted update_check: sometimes")


def test_the_windows_installer_shows_the_privacy_page_first():
    root = Path(__file__).resolve().parent.parent / "packaging"
    script = (root / "jobdork.iss").read_text(encoding="utf-8")
    assert "InfoBeforeFile=privacy.txt" in script
    text = (root / "privacy.txt").read_text(encoding="utf-8")
    assert "api.github.com" in text and "Check once a day whether a newer" in text
    assert "PRIVACY.md" in text


def test_the_tests_never_ask_github():
    assert updates.off()


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except BaseException:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc(limit=3)
    raise SystemExit(1 if failed else 0)
