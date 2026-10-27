"""Removing jobdork: what goes always, what goes only when chosen, and what is
never touched (core/uninstall.py). Temporary folders and a pretend scheduler:
nothing real is removed."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.core import uninstall  # noqa: E402


class _Scheduler:
    def __init__(self, scheduled=True):
        self.scheduled, self.removed = scheduled, False

    def read(self):
        return ("plan", ["argv"]) if self.scheduled else None

    def remove(self):
        self.removed = True


def _computer(tmp: Path) -> tuple[Path, Path, Path]:
    """An app folder, a documents folder and Downloads, as jobdork leaves them."""
    home, docs, dl = tmp / "jobdork", tmp / "Documents" / "job-applications", tmp / "Downloads"
    for path, text in {
        home / "config.yaml": "titles: {}",
        home / "data" / "jobdork.db": "db",
        home / "data" / "jobdork.db-wal": "wal",
        home / "data" / "backups" / "jobdork-2026-10-26.db": "backup",
        home / "data" / "resume.pdf": "pdf",
        home / "data" / "source-keys.env": "ADZUNA_APP_ID=x",
        home / "data" / "version-check.json": "{}",
        home / "logs" / "app.log": "log",
        home / "window" / "Local Storage" / "x": "x",
        home / "out" / "index.html": "<html>",
        docs / "2026-10-26-acme-nurse" / "cover-letter.md": "Dear",
        dl / "jobdork-0.15.1-macos-arm64.dmg": "dmg",
        dl / "holiday-photos.zip": "not jobdork's",
    }.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return home, docs, dl


def test_nothing_of_yours_goes_unless_you_choose_it():
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        sched = _Scheduler()
        out = uninstall.remove(set(), home, docs, dl, sched=sched)
        assert sched.removed and out["unscheduled"]
        assert not (home / "window").exists()                 # the program's own
        for kept in ("config.yaml", "data/jobdork.db", "data/resume.pdf",
                     "data/source-keys.env", "logs/app.log"):
            assert (home / kept).exists(), kept
        assert docs.exists() and (dl / "jobdork-0.15.1-macos-arm64.dmg").exists()
        assert set(out["left"]) == set(uninstall.CHOICES)


def test_each_item_goes_on_its_own():
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        out = uninstall.remove({"jobs", "keys", "downloads"}, home, docs, dl, sched=_Scheduler())
        assert not (home / "data" / "jobdork.db").exists()
        assert not (home / "data" / "jobdork.db-wal").exists()
        assert not (home / "data" / "backups").exists()
        assert not (home / "data" / "source-keys.env").exists()
        assert not (dl / "jobdork-0.15.1-macos-arm64.dmg").exists()
        assert (dl / "holiday-photos.zip").exists()           # not jobdork's
        assert (home / "data" / "resume.pdf").exists() and (home / "config.yaml").exists()
        assert docs.exists() and (home / "logs").exists()
        assert {"settings", "resume", "documents", "logs"} <= set(out["left"])


def test_everything_chosen_leaves_no_jobdork_folder():
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        out = uninstall.remove(set(uninstall.CHOICES), home, docs, dl, sched=_Scheduler())
        assert not home.exists() and not docs.exists(), out
        assert (Path(tmp) / "Documents").exists()             # only jobdork's folder in it
        assert out["failed"] == [] and out["left"] == []


def test_the_list_says_what_is_there_and_how_big():
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        items = {i.key: i for i in uninstall.inventory(home, docs, dl)}
        assert list(uninstall.CHOICES) == list(items)
        assert items["resume"].paths == [home / "data" / "resume.pdf"]
        assert items["downloads"].paths == [dl / "jobdork-0.15.1-macos-arm64.dmg"]
        assert items["jobs"].size == len("db") + len("wal") + len("backup") + len("{}")


def test_a_path_outside_jobdorks_folders_is_never_removed():
    """A link in the app folder pointing elsewhere is not followed out."""
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        precious = Path(tmp) / "precious"
        precious.mkdir()
        (precious / "thesis.docx").write_text("years of work")
        (home / "data" / "resume.pdf").unlink()
        (home / "data" / "resume.pdf").symlink_to(precious / "thesis.docx")
        uninstall.remove({"resume"}, home, docs, dl, sched=_Scheduler())
        assert (precious / "thesis.docx").read_text() == "years of work"


def test_a_scheduler_that_cannot_be_asked_does_not_stop_the_rest():
    class Broken(_Scheduler):
        def read(self):
            raise OSError("launchctl is not there")

    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        out = uninstall.remove({"logs"}, home, docs, dl, sched=Broken())
        assert out["unscheduled"] is False and not (home / "logs").exists()


def test_the_command_removes_what_it_is_told_and_keeps_the_rest():
    """`jobdork uninstall --remove`, with the scheduler, Documents and
    Downloads swapped for temporary ones: a test must not touch the real."""
    from jobdork import cli

    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        saved = uninstall._unschedule, uninstall.documents_root, uninstall.downloads
        try:
            # lambda: a scheduler that says nothing was scheduled, asking nothing real.
            uninstall._unschedule = lambda home, sched: False
            # lambda: the temporary folders in place of the real ones, read at each use.
            uninstall.documents_root, uninstall.downloads = (lambda: docs), (lambda: dl)
            code = cli.main(["uninstall", "--home", str(home), "--remove", "logs,keys"])
            assert code == 0
            assert not (home / "logs").exists() and not (home / "data" / "source-keys.env").exists()
            assert (home / "config.yaml").exists() and docs.exists()
            assert cli.main(["uninstall", "--home", str(home), "--remove", "everything"]) == 2
        finally:
            uninstall._unschedule, uninstall.documents_root, uninstall.downloads = saved


def test_the_windows_uninstaller_offers_exactly_the_items_jobdork_removes():
    """The uninstaller's page and core/uninstall.py name the same items, so a
    box ticked on Windows is one jobdork.exe --uninstall knows."""
    import re

    iss = (ROOT / "packaging" / "jobdork.iss").read_text(encoding="utf-8")
    keys = re.findall(r"Keys\[\d\] := '(\w+)';", iss)
    assert keys == list(uninstall.CHOICES), keys
    assert '--uninstall {code:RemoveChoices}' in iss
    app = (ROOT / "packaging" / "jobdork_app.py").read_text(encoding="utf-8")
    assert '"--uninstall"' in app


def test_the_settings_page_removes_only_in_the_desktop_app_and_not_on_windows():
    import contextlib

    from jobdork.web import api

    @contextlib.contextmanager
    def system(name, frozen):
        saved_platform, had = sys.platform, hasattr(sys, "frozen")
        sys.platform = name
        if frozen:
            sys.frozen = True
        elif had:
            del sys.frozen
        try:
            yield
        finally:
            sys.platform = saved_platform
            if not had and hasattr(sys, "frozen"):
                del sys.frozen

    def refused(fn, *args):
        try:
            fn(*args)
        except api.ApiError as exc:
            return exc.status
        return None

    with system("darwin", frozen=False):              # a source checkout
        assert refused(api.uninstall_items) == 409
    with system("win32", frozen=True):                # its uninstaller does it
        assert refused(api.uninstall_now, {"remove": []}) == 409
    saved = uninstall.remove
    try:
        # lambda: records what was asked instead of removing anything.
        uninstall.remove = lambda choose: {"removed": [], "failed": [], "unscheduled": True,
                                           "left": sorted(choose)}
        with system("darwin", frozen=True):
            out = api.uninstall_now({"remove": ["logs"]})
            assert out["finish"] == "mac" and out["left"] == ["logs"]
            assert refused(api.uninstall_now, {"remove": "logs"}) == 400
    finally:
        uninstall.remove = saved
