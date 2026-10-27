"""
jobdork.web.app
===============
The desktop app: the dashboard in a window of its own, with no terminal.

It is `jobdork serve` with three differences.

- **A folder of its own.** Everything else in jobdork is found relative to
  the folder it was started from (config.yaml, data/, .env). An app opened
  from the Dock or the Start menu starts in no particular folder, so this
  moves into a per-user one first: Application Support on macOS, Local
  AppData on Windows, ~/.local/share elsewhere. Letters and CVs still go to
  ~/Documents/job-applications.
- **A window, not a browser tab.** The server runs on a thread and the window
  on the main thread, which macOS requires. Closing the window ends the run
  the way Ctrl-C does, so held API keys are forgotten the same way; while a
  scan or another job runs, it asks first.
- **A bridge for what a window cannot do.** A browser opens new tabs and
  saves downloads; this window does neither reliably (on macOS it ignores
  `window.open` outright). The page asks `Bridge` instead: job posts and other
  links open in the user's own browser, files are saved through a save
  dialog, and a PDF opens in the system's viewer.

`--debug` turns on the window's developer tools (right-click, Inspect) and
debug logging, for a problem that shows in the app but not in a browser.

Needs pywebview: `pip install '.[app]'`. The installers are built from this
by packaging/build.py.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path

log = logging.getLogger(__name__)

APP_NAME = "jobdork"
HOME_ENV = "JOBDORK_HOME"
LOG_FILE = "logs/app.log"
# A generated PDF or a resume is well under this; the cap stops the page
# handing the app something absurd to hold in memory twice.
MAX_FILE_BYTES = 25 * 1024 * 1024
WINDOW_SIZE = (1280, 860)
MIN_SIZE = (900, 600)
READY_SECONDS = 15

_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def app_home() -> Path:
    """The per-user folder the app keeps its config, database and resume in."""
    raw = os.environ.get(HOME_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        # Local, not Roaming: a roaming profile copies the folder between
        # machines, and an SQLite database copied mid-write is a broken one.
        base = os.environ.get("LOCALAPPDATA", "").strip()
        return (Path(base) if base else Path.home() / "AppData" / "Local") / APP_NAME
    base = os.environ.get("XDG_DATA_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".local" / "share") / APP_NAME


def safe_name(name: str, default: str = "download") -> str:
    """A file name for a save dialog: no folders, no characters Windows refuses."""
    name = _UNSAFE_NAME.sub("-", str(name or "")).strip(" .-")
    return name[:120] or default


def _decode(data: str) -> bytes:
    if not isinstance(data, str) or len(data) > MAX_FILE_BYTES * 4 // 3 + 4:
        raise ValueError("that file is too big to save")
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("that file did not arrive whole") from None


def open_with_system(path: Path) -> None:
    """Open a file in whatever the system opens that kind of file with."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif sys.platform == "win32":
        os.startfile(str(path))
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class Bridge:
    """What the page may ask of the app: the three calls in CALLS, each
    checking what it is given. The page asks through the local server
    (`POST /api/desk`, with its token), which runs in this process.

    Not through pywebview's `js_api`: pywebview builds that in the page with
    `new Function`, and returns answers with `eval`, both of which the
    page's Content-Security-Policy refuses (and should: no 'unsafe-eval'),
    so the calls never existed in the app.

    The window only ever shows this app's own page: links leave through
    `open_url`, so no other site's script can reach these.
    """

    CALLS = ("open_url", "save_file", "open_file", "quit_app")
    # A request carrying the largest file, base64 encoded, and its name.
    BODY_LIMIT = MAX_FILE_BYTES * 4 // 3 + 64 * 1024

    def __init__(self, downloads: Path | None = None) -> None:
        self._window = None                  # set once the window exists
        self._downloads = downloads or Path.home() / "Downloads"
        self._temp = None

    def call(self, name, args) -> object:
        """One of CALLS by name, as the page sent it. ValueError for anything
        else, which the server answers with 400."""
        if name not in self.CALLS or not isinstance(args, list):
            raise ValueError("not something the app does")
        try:
            return getattr(self, name)(*args)
        except TypeError:
            raise ValueError(f"{name} was not given what it needs") from None

    def quit_app(self) -> bool:
        """Close the window, which stops jobdork: on a Mac the new version
        cannot replace this one while it runs. The page asks first."""
        if self._window is None:
            return False
        self._window.destroy()
        return True

    def open_url(self, url: str) -> bool:
        """Open a web address in the user's own browser."""
        if not isinstance(url, str) or not re.match(r"^https?://", url, re.I):
            return False
        webbrowser.open(url)
        return True

    def save_file(self, name: str, data: str) -> str:
        """Ask where to save a file, and save it. Returns the path, or '' if
        the user cancelled."""
        import webview

        body = _decode(data)
        chosen = self._window.create_file_dialog(
            webview.FileDialog.SAVE, directory=str(self._downloads),
            save_filename=safe_name(name))
        if not chosen:
            return ""
        path = Path(chosen if isinstance(chosen, str) else chosen[0])
        path.write_bytes(body)
        return str(path)

    def open_file(self, name: str, data: str) -> str:
        """Show a PDF in the system's viewer, from a temporary copy that is
        deleted when the app closes. Only a PDF: the system opens a file by
        its kind, and a `.command` or `.app` would run."""
        body = _decode(data)
        if not body.startswith(b"%PDF-"):
            raise ValueError("only a PDF opens this way")
        name = Path(safe_name(name, "document")).stem + ".pdf"
        if self._temp is None:
            self._temp = Path(tempfile.mkdtemp(prefix="jobdork-"))
        path = self._temp / name
        path.write_bytes(body)
        open_with_system(path)
        return str(path)

    def forget(self) -> None:
        """Delete the temporary copies `open_file` made."""
        if self._temp is not None:
            shutil.rmtree(self._temp, ignore_errors=True)
            self._temp = None


def _log_to_file(home: Path, level: int) -> None:
    """A packaged app has no terminal: what would be printed goes to a file."""
    path = home / LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the app
    sys.stdout = sys.stderr = stream
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s",
                        stream=stream, force=True)


def no_terminal() -> bool:
    """True for an installed app opened from Finder or the Start menu: on
    Windows it has no stdout at all, on macOS one that leads nowhere."""
    if sys.stdout is None:
        return True
    return bool(getattr(sys, "frozen", False)) and not sys.stdout.isatty()


# Where tools installed for one user live. An app opened from Finder gets the
# system's bare PATH, not the one a terminal builds from the shell's startup
# files, so without these the `claude` CLI that drafts letters is not found.
# Windows hands a Start-menu app the user's full PATH already.
USER_TOOL_DIRS = ("~/.local/bin", "~/.claude/local", "/opt/homebrew/bin",
                  "/usr/local/bin")


def widen_path() -> None:
    """Add the user's tool folders that exist to PATH, after what is there."""
    if sys.platform == "win32":
        return
    have = os.environ.get("PATH", "").split(os.pathsep)
    extra = [str(p) for p in (Path(d).expanduser() for d in USER_TOOL_DIRS)
             if p.is_dir() and str(p) not in have]
    if extra:
        os.environ["PATH"] = os.pathsep.join([*filter(None, have), *extra])


# What a packaged app must carry to work, beyond what PyInstaller finds by
# following imports: the window's backend for this platform, the extras that
# are imported only inside functions, and the files read from disk. A build
# missing one starts, or even opens a window, and fails later in front of the
# user; self_test() finds it in the build instead.
SELF_TEST_MODULES = ("webview", "anthropic", "pypdf", "jobdork.web.serve",
                     "jobdork.cli")
WINDOW_BACKENDS = {"darwin": "webview.platforms.cocoa",
                   "win32": "webview.platforms.winforms"}
# Per platform, more that a build must carry: Notification Center on macOS.
PLATFORM_MODULES = {"darwin": ("UserNotifications",)}
SELF_TEST_FILES = ("dashboard.html", "boards.csv", "cities.csv", "regions.csv",
                   "humanizer")


def self_test() -> list[str]:
    """What this build is missing, one line each; empty when nothing is.

    The installed app runs it with `--self-test <report>` (packaging/build.py
    does, after every build). It opens no window, so CI can run it.
    """
    import importlib

    from .. import __version__
    from .serve import PAGE_PATH

    problems = []
    backend = WINDOW_BACKENDS.get(sys.platform)
    for name in (*SELF_TEST_MODULES, *([backend] if backend else []),
                 *PLATFORM_MODULES.get(sys.platform, ())):
        try:
            importlib.import_module(name)
        except Exception as exc:             # any failure to load is the finding
            problems.append(f"cannot import {name}: {type(exc).__name__}: {exc}")
    data = PAGE_PATH.parent
    problems += [f"missing data file {name}" for name in SELF_TEST_FILES
                 if not (data / name).exists()]
    if __version__.endswith("+source"):
        problems.append("no package metadata: the version reads as " + __version__)
    # The GPL's text travels with every built copy (packaging/jobdork.spec).
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle and not (Path(bundle) / "LICENSE").exists():
        problems.append("missing LICENSE: the GPL's text must ship with the app")
    # Updates are opened only once their build attestation verifies
    # (core/updates.py): prove the whole Sigstore check works in this build.
    from ..core import updates
    why = updates.check_bundled_attestation()
    if why:
        problems.append(f"cannot verify a build attestation: {why}")
    # Remember keys must reach the system's keychain (core/keystore.py). Only
    # finds the backend: asks the keychain nothing, so no prompt.
    if sys.platform in ("darwin", "win32"):
        from ..core import keystore
        why = keystore.unavailable()
        if why:
            problems.append(f"cannot keep keys: {why}")
    return problems


def scheduled_scan(home: Path | None = None) -> int:
    """What the scan schedule starts: a scan in the app's folder, no window.

    The schedule (core/schedule.py) runs the app's own program with `--scan`,
    since an installed app has no `jobdork` command to run. It writes to
    logs/scheduled-scan.log in the app's folder, and shows in the Dashboard's
    runs like any other scan.
    """
    from ..cli import main

    home = (home or app_home()).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    os.chdir(home)
    if sys.stdout is None:                   # a Windows app has none until
        sys.stdout = sys.stderr = open(os.devnull, "w")  # noqa: SIM115 - the scan opens its log
    widen_path()
    return main(["scan", "--scheduled"])


def ask_before_closing(busy):
    """A handler for the window's `closing` event: while a job runs, closing
    (the red button, Ctrl-F4, Cmd-Q) asks first, since it stops the job.

    It only says whether to ask and what: pywebview shows the question itself
    after this returns. Showing a dialog from inside the handler would wait
    on the main thread that is busy running the handler.
    """
    def closing(window) -> None:
        job = busy()
        window.confirm_close = bool(job)
        if job:
            window.localization.update({
                "global.quitConfirmation":
                    f"{job[:1].upper()}{job[1:]} is still running. Closing jobdork "
                    "stops it, and what it has not saved yet is lost.",
                "global.quit": "Close anyway",
            })
    return closing


def run(port: int, home: Path | None = None, debug: bool = False) -> int:
    """Open the app window. Returns an exit code once it is closed."""
    try:
        import webview
    except ImportError:
        print("The app window needs pywebview: pip install '.[app]'. "
              "Or use `jobdork serve`, which opens the dashboard in your browser.")
        return 1
    from ..core import config
    from .serve import serve

    home = (home or app_home()).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    if no_terminal():
        _log_to_file(home, level)
    elif debug:
        logging.getLogger().setLevel(level)
    widen_path()
    os.chdir(home)
    print(f"jobdork app: keeping settings and job posts in {home}")

    cfg = config.load(require=False)
    for warning in cfg.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    ready = threading.Event()
    running: dict = {}

    def on_ready(url, stop, busy):
        running.update(url=url, stop=stop, busy=busy)
        ready.set()

    bridge = Bridge()

    def server():
        running["code"] = serve(cfg, port=port, open_browser=False, on_ready=on_ready,
                                desk=bridge)
        ready.set()                          # a server that never started

    thread = threading.Thread(target=server, name="jobdork-server", daemon=True)
    thread.start()
    if not ready.wait(READY_SECONDS) or "url" not in running:
        print("the dashboard did not start; see the lines above")
        return running.get("code") or 1

    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["ALLOW_DOWNLOADS"] = True
    # text_select: pywebview makes a page unselectable unless asked, so no
    # log line, error or letter could be copied out of the app. No js_api:
    # the page reaches the Bridge through the server (see Bridge).
    bridge._window = webview.create_window(
        "jobdork", running["url"], width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1], min_size=MIN_SIZE, text_select=True)
    bridge._window.events.closing += ask_before_closing(running["busy"])
    # Not private: the page keeps small conveniences (a remembered tab) in
    # local storage. The token is never stored; it lives in the page.
    webview.start(private_mode=False, storage_path=str(home / "window"), debug=debug)

    # shutdown() waits for the server loop to notice, so it runs on a thread
    # that a stuck request cannot hold the app open with.
    threading.Thread(target=running["stop"], daemon=True).start()
    thread.join(10)
    bridge.forget()
    return running.get("code", 0)
