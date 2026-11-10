"""
jobdork.core.uninstall
======================
Everything jobdork put on this computer, and taking it off again: for the
Windows uninstaller, Settings' "Remove jobdork from this computer" and
`jobdork uninstall`.

The program's own traces always go: the scheduled scan (a LaunchAgent, a
Task Scheduler task or a crontab line, which would otherwise go on starting
a program that is gone), the app window's storage, and every key jobdork
kept in the computer's keychain, AI and job source alike: left there, they
would outlive the program in the system's store, where the person would not
think to look (and an old plain source-keys.env with them). Everything else is the
person's, and goes only when they choose it, item by item: their settings,
job posts, resume, letters and tailored resumes, saved job-source keys,
logs, and the installers Update downloaded. Nothing is chosen unless they
choose it.

Only these places are ever touched: the app's folder (web/app.py app_home),
the folder jobdork writes documents to (~/Documents/job-applications),
jobdork's own installers in Downloads, and on a Mac what macOS keeps for the
app window under ~/Library by the app's bundle id (mac_traces). A path that
resolves anywhere else is left alone, whatever asked for it.

Last, when the app quits after a removal (web/app.py), the program itself:
the Mac app and a Linux AppImage move themselves to the Trash (trash_app). A
.deb needs `sudo apt remove jobdork`, and Windows has its own uninstaller.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

# The Mac app's bundle id (packaging/jobdork.spec): macOS keeps the window's
# storage, caches and saved state under it, outside jobdork's own folder.
BUNDLE_ID = "io.github.jessn-dev.jobdork"

# What the person can choose, in the order they are shown. Each is its own
# choice: someone may keep their letters and drop the rest, or the reverse.
ITEMS = (
    ("settings", "Settings", "what you search for, where, pay, the AI page, notifications"),
    ("jobs", "Job posts", "every job post found, with your statuses, notes and AI "
     "verdicts, and the backups of them"),
    ("resume", "Your resume", "the resume file you uploaded"),
    ("documents", "Letters and tailored resumes",
     "the cover letters, tailored resumes and job descriptions jobdork wrote"),
    ("logs", "Logs", "what jobdork wrote down while it ran"),
    ("downloads", "Downloaded installers", "installers the Update button left in Downloads"),
)
CHOICES = tuple(key for key, _, _ in ITEMS)
# Items in the person's own folders, Documents and Downloads, looked into
# only when they ask: on a Mac the first look there makes macOS ask to allow
# it, and on every system it is their folder, not the app's.
GUARDED = ("documents", "downloads")

# jobdork's installers, as the release names them, and Update's leftovers.
_INSTALLER_GLOBS = ("jobdork-*-macos-*.dmg", "jobdork-*-windows-*-setup.exe",
                    "jobdork-*-linux-*.AppImage", "jobdork_*.deb", "jobdork-*-linux-*.deb",
                    "jobdork-*.part", ".jobdork-*-SHA256SUMS.txt")


@dataclass
class Item:
    key: str
    label: str
    what: str
    paths: list[Path]
    unchecked: bool = False      # not looked at yet (see GUARDED)

    @property
    def present(self) -> bool:
        return bool(self.paths)

    @property
    def size(self) -> int:
        return sum(_size(p) for p in self.paths)


def app_home() -> Path:
    from ..web.app import app_home as home
    return home()


def documents_root() -> Path:
    """The folder job applications are written to, wherever this copy keeps
    them (storage.container_documents_root is only a container's)."""
    from ..writing import generate
    return Path(generate.default_root()).expanduser()


def downloads() -> Path:
    return Path.home() / "Downloads"


def inventory(home: Path | None = None, docs: Path | None = None,
              dl: Path | None = None, guarded: bool = True) -> list[Item]:
    """What there is to remove, item by item: only paths that exist.

    `guarded=False` does not look into Documents or Downloads: those items
    come back `unchecked`, with only what lies in the app's own folder.
    """
    home = Path(home or app_home())
    data = home / "data"
    docs = Path(docs or documents_root())
    dl = Path(dl or downloads())
    found = {
        "settings": [home / "config.yaml", home / "config.local.yaml"],
        # The backups are copies of the job posts, made before every delete.
        "jobs": [data / f"jobdork.db{end}" for end in ("", "-wal", "-shm", "-journal")]
        + [data / "backups", data / "version-check.json", data / "scan.lock"],
        "resume": sorted(data.glob("resume.*")),
        "documents": [docs, home / "out"] if guarded else [home / "out"],
        "logs": [home / "logs"],
        "downloads": sorted({p for g in _INSTALLER_GLOBS for p in dl.glob(g)}) if guarded else [],
    }
    return [Item(key, label, what, [p for p in found[key] if p.exists()],
                 unchecked=not guarded and key in GUARDED)
            for key, label, what in ITEMS]


def mac_traces(library: Path) -> list[Path]:
    """What macOS keeps for the app window, under ~/Library, by bundle id:
    WebKit's storage, caches, cookies, saved window state and preferences."""
    return [library / "WebKit" / BUNDLE_ID,
            library / "Caches" / BUNDLE_ID,
            library / "HTTPStorages" / BUNDLE_ID,
            library / "HTTPStorages" / f"{BUNDLE_ID}.binarycookies",
            library / "Saved Application State" / f"{BUNDLE_ID}.savedState",
            library / "Preferences" / f"{BUNDLE_ID}.plist"]


def remove(choose, home: Path | None = None, docs: Path | None = None,
           dl: Path | None = None, sched=None, unschedule=True,
           library: Path | None = None) -> dict:
    """Remove the program's traces, and the items in `choose`.

    `library` is ~/Library on a Mac, for the window's traces there. Left out,
    it is the real one only when `home` is too (the app's own folder): a
    folder given for a test never reaches the real ~/Library.

    Returns {"removed": [paths], "failed": [[path, why]], "unscheduled": bool,
    "left": [items kept]}. Never raises for one path that will not go: the
    rest are still removed, and the failure is said.
    """
    if library is None and home is None and sys.platform == "darwin":
        library = Path.home() / "Library"
    home = Path(home or app_home())
    docs = Path(docs or documents_root())
    dl = Path(dl or downloads())
    choose = {c for c in choose or () if c in CHOICES}
    traces = mac_traces(Path(library)) if library else []
    allowed = [home, docs, dl, *traces]
    out = {"removed": [], "failed": [], "unscheduled": False, "left": []}

    if unschedule:
        out["unscheduled"] = _unschedule(home, sched)

    def gone(path: Path) -> None:
        if not _inside(path, allowed):
            out["failed"].append([str(path), "outside jobdork's folders; left alone"])
            return
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            out["removed"].append(str(path))
        except FileNotFoundError:
            pass
        except OSError as exc:
            out["failed"].append([str(path), exc.strerror or type(exc).__name__])

    # The window's storage, and Ask's working folder: the program's, not yours.
    for trace in (home / "window", home / "data" / "ask", *traces):
        if trace.exists():
            gone(trace)
    # Always: keys kept in the keychain, and an old plain keys file.
    from . import keystore
    if _keychain_has_keys():
        keystore.forget_all()
        out["removed"].append("keys kept in this computer's keychain")
    old_keys = home / "data" / "source-keys.env"
    if old_keys.exists():
        gone(old_keys)
    for item in inventory(home, docs, dl):
        if item.key in choose:
            for path in item.paths:
                gone(path)
        elif item.present:
            out["left"].append(item.key)
    # Folders jobdork made and that are now empty go too.
    for folder in (home / "data", home):
        try:
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
                out["removed"].append(str(folder))
        except OSError:
            pass
    return out


def app_location(executable: str | None = None, environ=None,
                 platform: str | None = None) -> tuple[str, Path | None]:
    """Where the running program is, when it can move itself to the Trash:
    ("mac", the jobdork.app bundle) or ("appimage", the AppImage file).
    ("", None) for anything else: a .deb, Windows, a copy run from source, or
    a Mac app run from its disk image or from where macOS moved it to check
    it (App Translocation), which is not the copy in Applications."""
    environ = os.environ if environ is None else environ
    platform = platform or sys.platform
    if platform == "darwin":
        bundle = Path(executable or sys.executable).resolve().parents[2]
        where = str(bundle)
        if (bundle.suffix != ".app" or "/AppTranslocation/" in where
                or where.startswith("/Volumes/")):
            return "", None
        try:
            with open(bundle / "Contents" / "Info.plist", "rb") as fh:
                ident = plistlib.load(fh).get("CFBundleIdentifier")
        except (OSError, plistlib.InvalidFileException):
            return "", None
        return ("mac", bundle) if ident == BUNDLE_ID else ("", None)
    image = (environ.get("APPIMAGE") or "").strip()
    if platform.startswith("linux") and image and Path(image).is_file():
        return "appimage", Path(image)
    return "", None


def trash_app(executable: str | None = None, environ=None, platform: str | None = None,
              trash_dir: Path | None = None) -> str:
    """Move the running program to the Trash, once the app has quit after a
    removal. Returns where it went, or "" when it could not (it is then left
    in place; nothing else is touched)."""
    kind, path = app_location(executable, environ, platform)
    if kind == "mac":
        try:
            from Foundation import NSURL, NSFileManager
        except ImportError:
            return ""
        ok, moved, _ = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
            NSURL.fileURLWithPath_(str(path)), None, None)
        return str(moved.path()) if ok and moved is not None else ""
    if kind == "appimage":
        return _to_xdg_trash(path, trash_dir)
    return ""


def _to_xdg_trash(path: Path, trash_dir: Path | None = None) -> str:
    """Move a file to the desktop's Trash, as the freedesktop.org Trash spec
    lays it out: the file under files/, its .trashinfo under info/."""
    base = Path(trash_dir) if trash_dir else Path(
        os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Trash"
    try:
        (base / "files").mkdir(parents=True, exist_ok=True)
        (base / "info").mkdir(parents=True, exist_ok=True)
        name, n = path.name, 1
        while (base / "files" / name).exists() or (base / "info" / f"{name}.trashinfo").exists():
            n += 1
            name = f"{path.stem}.{n}{path.suffix}"
        (base / "info" / f"{name}.trashinfo").write_text(
            "[Trash Info]\n"
            f"Path={quote(str(path.resolve()))}\n"
            f"DeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n", encoding="utf-8")
        shutil.move(str(path), str(base / "files" / name))
    except OSError:
        return ""
    return str(base / "files" / name)


def _keychain_has_keys() -> bool:
    from . import keystore
    return any(keystore.load(name) for name in keystore.names())


def _unschedule(home: Path, sched) -> bool:
    """Take the scheduled scan out of this system's scheduler. True if one
    was there. Never raises: a scheduler that cannot be asked is no reason
    to keep the rest."""
    from . import schedule

    try:
        if sched is None and schedule.unsupported():
            return False
        sched = sched or schedule.scheduler()
        was = sched.read() is not None
        sched.remove()
        return was
    except Exception:
        return False


def _inside(path: Path, roots: list[Path]) -> bool:
    try:
        real = Path(os.path.realpath(path))
    except OSError:
        return False
    for root in roots:
        top = Path(os.path.realpath(root))
        if real == top or top in real.parents:
            return True
    return False


def _size(path: Path) -> int:
    try:
        if path.is_dir():
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return path.stat().st_size
    except OSError:
        return 0
