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

Only three places are ever touched: the app's folder (web/app.py app_home),
the folder jobdork writes documents to (~/Documents/job-applications), and
jobdork's own installers in Downloads. A path that resolves anywhere else is
left alone, whatever asked for it.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

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
    from ..writing import generate
    return Path(generate.default_root()).expanduser()


def downloads() -> Path:
    return Path.home() / "Downloads"


def inventory(home: Path | None = None, docs: Path | None = None,
              dl: Path | None = None) -> list[Item]:
    """What there is to remove, item by item: only paths that exist."""
    home = Path(home or app_home())
    docs = Path(docs or documents_root())
    dl = Path(dl or downloads())
    data = home / "data"
    found = {
        "settings": [home / "config.yaml", home / "config.local.yaml"],
        # The backups are copies of the job posts, made before every delete.
        "jobs": [data / f"jobdork.db{end}" for end in ("", "-wal", "-shm", "-journal")]
        + [data / "backups", data / "version-check.json", data / "scan.lock"],
        "resume": sorted(data.glob("resume.*")),
        "documents": [docs, home / "out"],
        "logs": [home / "logs"],
        "downloads": sorted({p for g in _INSTALLER_GLOBS for p in dl.glob(g)}),
    }
    return [Item(key, label, what, [p for p in found[key] if p.exists()])
            for key, label, what in ITEMS]


def remove(choose, home: Path | None = None, docs: Path | None = None,
           dl: Path | None = None, sched=None, unschedule=True) -> dict:
    """Remove the program's traces, and the items in `choose`.

    Returns {"removed": [paths], "failed": [[path, why]], "unscheduled": bool,
    "left": [items kept]}. Never raises for one path that will not go: the
    rest are still removed, and the failure is said.
    """
    home = Path(home or app_home())
    docs = Path(docs or documents_root())
    dl = Path(dl or downloads())
    choose = {c for c in choose or () if c in CHOICES}
    allowed = [home, docs, dl]
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

    window = home / "window"
    if window.exists():
        gone(window)
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
