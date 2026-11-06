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
        for kept in ("config.yaml", "data/jobdork.db", "data/resume.pdf", "logs/app.log"):
            assert (home / kept).exists(), kept
        assert not (home / "data" / "source-keys.env").exists()   # keys always go
        assert docs.exists() and (dl / "jobdork-0.15.1-macos-arm64.dmg").exists()
        assert set(out["left"]) == set(uninstall.CHOICES)


def test_each_item_goes_on_its_own():
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        out = uninstall.remove({"jobs", "downloads"}, home, docs, dl, sched=_Scheduler())
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


def test_documents_and_downloads_are_not_looked_into_until_asked():
    """On a Mac the first look there asks for permission: Settings opening
    must not be it. Unlooked items say so; the app's own folder is listed."""
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        looked = []
        real_exists, real_glob = Path.exists, Path.glob

        def exists(self, *a, **k):
            looked.append(self)
            return real_exists(self, *a, **k)

        def glob(self, *a, **k):
            looked.append(self)
            return real_glob(self, *a, **k)
        Path.exists, Path.glob = exists, glob
        try:
            items = {i.key: i for i in uninstall.inventory(home, docs, dl, guarded=False)}
        finally:
            Path.exists, Path.glob = real_exists, real_glob
        assert not [p for p in looked if p.is_relative_to(docs) or p.is_relative_to(dl)]
        assert items["documents"].unchecked and items["downloads"].unchecked
        assert items["downloads"].paths == [] and not items["resume"].unchecked
        assert items["resume"].paths == [home / "data" / "resume.pdf"]


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
            code = cli.main(["uninstall", "--home", str(home), "--remove", "logs"])
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
            assert {"logs"} == api.REMOVED, "the server answers only quitting from now on"
    finally:
        uninstall.remove = saved
        api.REMOVED = None


def test_saved_keys_always_go_whatever_is_chosen():
    """Kept in the keychain, keys would outlive jobdork in the system's store,
    where nobody would think to look (2026-10-27)."""
    from jobdork.core import keystore

    assert "keys" not in uninstall.CHOICES
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        keystore.save("ai:groq", "gsk_FakeKeyForTests012345")
        try:
            out = uninstall.remove(set(), home, docs, dl, sched=_Scheduler())
            assert keystore.load("ai:groq") == ""
            assert "keys kept in this computer's keychain" in out["removed"]
            assert (home / "config.yaml").exists()                  # nothing else chosen
        finally:
            keystore.forget_all()


# ── the program's traces outside its folder, and the program itself ───────────

def test_the_windows_traces_on_a_mac_go_and_nothing_else_in_library():
    with tempfile.TemporaryDirectory() as tmp:
        home, docs, dl = _computer(Path(tmp))
        library = Path(tmp) / "Library"
        for trace in uninstall.mac_traces(library):
            # A folder with a file in it, or a file (cookies, preferences).
            target = trace if trace.suffix in (".binarycookies", ".plist") else trace / "x"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x")
        other = library / "WebKit" / "com.example.someone-else" / "x"
        other.parent.mkdir(parents=True)
        other.write_text("theirs")
        (home / "data" / "ask").mkdir(parents=True)
        uninstall.remove(set(), home, docs, dl, sched=_Scheduler(), library=library)
        assert not any(t.exists() for t in uninstall.mac_traces(library))
        assert other.exists(), "another app's storage is never touched"
        assert not (home / "data" / "ask").exists(), "Ask's working folder is the program's"


def test_a_given_app_folder_never_reaches_the_real_library():
    # remove() with a folder of its own (a test, a script) is never given the
    # real ~/Library unless it asks for it by name.
    seen = []
    saved = uninstall.mac_traces
    try:
        # lambda: records which Library would be cleaned, and cleans nothing.
        uninstall.mac_traces = lambda library: seen.append(library) or []
        with tempfile.TemporaryDirectory() as tmp:
            home, docs, dl = _computer(Path(tmp))
            uninstall.remove(set(), home, docs, dl, sched=_Scheduler())
    finally:
        uninstall.mac_traces = saved
    assert seen == []


def _mac_app(root: Path, ident: str = uninstall.BUNDLE_ID) -> Path:
    import plistlib

    app = root / "Applications" / "jobdork.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "jobdork").write_text("#!")
    with open(app / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleIdentifier": ident}, fh)
    return app


def test_only_the_mac_app_in_its_place_or_an_appimage_moves_itself_to_the_trash():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app = _mac_app(root)
        exe = str(app / "Contents" / "MacOS" / "jobdork")
        assert uninstall.app_location(exe, {}, "darwin") == ("mac", app.resolve())
        other = _mac_app(root / "x", ident="com.example.other")
        assert uninstall.app_location(str(other / "Contents" / "MacOS" / "jobdork"), {},
                                      "darwin") == ("", None), "not jobdork's bundle"
        loose = root / "bin" / "python"
        loose.parent.mkdir()
        loose.write_text("")
        assert uninstall.app_location(str(loose), {}, "darwin") == ("", None)   # from source
        image = root / "jobdork-0.16.2-linux-x86_64.AppImage"
        image.write_text("ELF")
        assert uninstall.app_location("/tmp/.mount_x/usr/bin/jobdork", {"APPIMAGE": str(image)},
                                      "linux") == ("appimage", image)
        assert uninstall.app_location("/usr/lib/jobdork/jobdork", {}, "linux") == ("", None)
        assert uninstall.app_location("C:/jobdork/jobdork.exe", {}, "win32") == ("", None)


def test_a_translocated_or_mounted_mac_app_is_left_in_place():
    assert uninstall.app_location(
        "/private/var/folders/x/AppTranslocation/ABC/d/jobdork.app/Contents/MacOS/jobdork",
        {}, "darwin") == ("", None)
    assert uninstall.app_location("/Volumes/jobdork 0.16.2/jobdork.app/Contents/MacOS/jobdork",
                                  {}, "darwin") == ("", None)


def test_an_appimage_goes_to_the_trash_as_the_desktop_lays_it_out():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        trash = root / "Trash"
        for _ in range(2):                           # the second is named apart
            image = root / "jobdork.AppImage"
            image.write_text("ELF")
            went = uninstall.trash_app("/x", {"APPIMAGE": str(image)}, "linux", trash_dir=trash)
            assert went and Path(went).is_file() and not image.exists()
        assert sorted(p.name for p in (trash / "files").iterdir()) == [
            "jobdork.2.AppImage", "jobdork.AppImage"]
        info = (trash / "info" / "jobdork.AppImage.trashinfo").read_text()
        assert info.startswith("[Trash Info]\n") and "Path=" in info and "DeletionDate=" in info


def test_quitting_after_no_removal_moves_nothing():
    from jobdork.web import app

    assert app.finish_removal(None) == ""


def test_closing_the_window_ends_the_program_even_with_a_thread_still_busy():
    # A scan's fetches run on threads Python would wait for at exit; the app
    # ends with exit_now so nothing keeps it running once its window closes.
    import subprocess
    import time

    code = ("import threading, time\n"
            "from jobdork.web import app\n"
            "threading.Thread(target=time.sleep, args=(60,)).start()\n"
            "app.exit_now(3)\n")
    started = time.monotonic()
    done = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), timeout=30)
    assert done.returncode == 3 and time.monotonic() - started < 20
