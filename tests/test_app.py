"""
Tests for the desktop app (web/app.py): the folder it keeps things in, the
bridge the page calls for links and files, and a whole run with the window
stood in for, so no screen is needed.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import base64
import contextlib
import io
import logging
import os
import sys
import tempfile
import types
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.web import app


@contextlib.contextmanager
def _env(**values):
    """Set (or, with None, remove) environment variables for one test."""
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
def _platform(name):
    saved = sys.platform
    sys.platform = name
    try:
        yield
    finally:
        sys.platform = saved


@contextlib.contextmanager
def _fake_webview(on_start=None):
    """A stand-in for pywebview: records the window and returns from start()
    at once, after running `on_start(url)` while the server is up."""
    module = types.ModuleType("webview")
    module.settings = {}
    module.FileDialog = types.SimpleNamespace(OPEN=10, FOLDER=20, SAVE=30)
    module.made = {}

    class Hook(list):
        """pywebview's event: handlers are added with +=."""
        def __iadd__(self, handler):
            self.append(handler)
            return self

    def create_window(title, url, **kw):
        module.made.update(title=title, url=url, **kw)
        module.made["closing"] = Hook()
        return types.SimpleNamespace(
            # lambda: a window whose save dialog is never opened in these tests.
            create_file_dialog=lambda *a, **k: None,
            events=types.SimpleNamespace(closing=module.made["closing"]))

    def start(**kw):
        module.made["start"] = kw
        if on_start:
            on_start(module.made["url"])

    module.create_window = create_window
    module.start = start
    saved = sys.modules.get("webview")
    sys.modules["webview"] = module
    try:
        yield module
    finally:
        if saved is None:
            sys.modules.pop("webview", None)
        else:
            sys.modules["webview"] = saved


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_home_is_the_platforms_own_place_for_app_data():
    home = Path.home()
    with _env(JOBDORK_HOME=None, LOCALAPPDATA=None, XDG_DATA_HOME=None):
        with _platform("darwin"):
            assert app.app_home() == home / "Library" / "Application Support" / "jobdork"
        with _platform("win32"):
            assert app.app_home() == home / "AppData" / "Local" / "jobdork"
        with _platform("linux"):
            assert app.app_home() == home / ".local" / "share" / "jobdork"
    with _env(JOBDORK_HOME=None, LOCALAPPDATA=r"D:\Users\me\AppData\Local",
              XDG_DATA_HOME="/data/me"):
        with _platform("win32"):
            assert app.app_home() == Path(r"D:\Users\me\AppData\Local") / "jobdork"
        with _platform("linux"):
            assert app.app_home() == Path("/data/me/jobdork")


def test_jobdork_home_wins_everywhere():
    with _env(JOBDORK_HOME="~/elsewhere"), _platform("darwin"):
        assert app.app_home() == Path.home() / "elsewhere"


def test_a_saved_name_cannot_name_a_folder():
    assert app.safe_name("../../etc/passwd") == "etc-passwd"
    assert app.safe_name(r"C:\Windows\x.pdf") == "C-Windows-x.pdf"
    assert app.safe_name('a<b>:"c"?.txt') == "a-b-c-.txt"
    assert app.safe_name("") == "download"
    assert app.safe_name("...") == "download"
    assert len(app.safe_name("x" * 500)) == 120


def test_only_web_addresses_leave_for_the_browser():
    opened = []
    saved = app.webbrowser.open
    # lambda: stands in for the browser, recording instead of opening.
    app.webbrowser.open = lambda url: opened.append(url)
    try:
        bridge = app.Bridge()
        assert bridge.open_url("https://example.com/job/1")
        assert bridge.open_url("HTTP://example.com/")
        for bad in ("javascript:alert(1)", "file:///etc/passwd", "", None, 42,
                    "  https://example.com"):
            assert not bridge.open_url(bad), bad
    finally:
        app.webbrowser.open = saved
    assert opened == ["https://example.com/job/1", "HTTP://example.com/"]


def test_a_file_is_saved_where_the_dialog_says():
    with tempfile.TemporaryDirectory() as tmp, _fake_webview():
        target = Path(tmp) / "Letter.md"
        asked = {}

        def dialog(kind, **kw):
            asked.update(kind=kind, **kw)
            return (str(target),)

        bridge = app.Bridge(downloads=Path(tmp))
        bridge._window = types.SimpleNamespace(create_file_dialog=dialog)
        assert bridge.save_file("../Letter.md", _b64(b"# Dear")) == str(target)
        assert target.read_bytes() == b"# Dear"
        assert asked == {"kind": 30, "directory": tmp, "save_filename": "Letter.md"}

        # lambda: a dialog the user cancelled.
        bridge._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: None)
        assert bridge.save_file("x.md", _b64(b"x")) == ""


def test_a_damaged_or_huge_file_is_refused():
    bridge = app.Bridge()
    for data in ("not base64!", 7, "A" * (app.MAX_FILE_BYTES * 2)):
        try:
            bridge.open_file("x.pdf", data)
        except ValueError:
            continue
        raise AssertionError(f"accepted {str(data)[:20]!r}")


def test_only_a_pdf_is_opened_and_always_as_a_pdf():
    """The system opens a file by its kind: a `.command` would run."""
    shown = []
    saved = app.open_with_system
    app.open_with_system = shown.append
    try:
        bridge = app.Bridge()
        for name, data in (("run.command", b"#!/bin/sh\nrm -rf ~"), ("x.pdf", b"<html>")):
            try:
                bridge.open_file(name, _b64(data))
            except ValueError:
                continue
            raise AssertionError(f"opened {name}")
        path = Path(bridge.open_file("run.command", _b64(b"%PDF-1.7")))
        assert path.name == "run.pdf" and shown == [path]
        bridge.forget()
    finally:
        app.open_with_system = saved


def test_the_page_calls_the_bridge_by_name_and_nothing_else():
    opened = []
    saved = app.webbrowser.open
    # lambda: stands in for the browser, recording instead of opening.
    app.webbrowser.open = lambda url: opened.append(url)
    try:
        bridge = app.Bridge()
        assert bridge.call("open_url", ["https://example.com/"]) is True
        assert opened == ["https://example.com/"]
        for name, args in (("forget", []), ("_decode", ["x"]), ("__init__", []),
                           ("open_url", "https://example.com/"), ("open_url", [])):
            try:
                bridge.call(name, args)
            except ValueError:
                continue
            raise AssertionError(f"called {name}({args!r})")
    finally:
        app.webbrowser.open = saved


def test_the_page_asks_for_every_call_it_makes_without_eval():
    """The page's DESK lists what it may ask the app; it must cover every
    desk() call and name only Bridge.CALLS. The page's policy refuses eval,
    so neither the page nor the fix may need it."""
    import re

    from jobdork.web import serve
    page = (Path(app.__file__).resolve().parent.parent / "data" / "dashboard.html").read_text()
    desk = re.search(r"const DESK = \{(.*?)\n\};", page, re.S)
    assert desk, "DESK is gone from dashboard.html"
    names = set(re.findall(r"^\s*(\w+):", desk.group(1), re.M))
    used = set(re.findall(r"desk\(\)\.(\w+)\(", page))
    assert names == set(app.Bridge.CALLS), names
    assert used <= names, used - names
    assert not re.search(r"new Function\(|\beval\(", page)
    assert "unsafe-eval" not in Path(serve.__file__).read_text()


def test_a_pdf_opens_from_a_copy_that_is_deleted_afterwards():
    shown = []
    saved = app.open_with_system
    app.open_with_system = shown.append
    try:
        bridge = app.Bridge()
        path = Path(bridge.open_file("Jo_Doe_Resume.pdf", _b64(b"%PDF-1.7")))
        assert shown == [path] and path.name == "Jo_Doe_Resume.pdf"
        assert path.read_bytes() == b"%PDF-1.7"
        bridge.forget()
        assert not path.exists() and not path.parent.exists()
    finally:
        app.open_with_system = saved


def test_a_whole_run_opens_setup_from_the_apps_folder_and_stops():
    from jobdork.ai.llm import VAULT
    from jobdork.core import telemetry

    pages = {}

    def visit(url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            pages["status"] = resp.status
            pages["body"] = resp.read()

    cwd = os.getcwd()
    saved_out, saved_err = sys.stdout, sys.stderr
    printed = io.StringIO()
    sys.stdout = printed
    with tempfile.TemporaryDirectory() as tmp, \
            _env(JOBDORK_CONFIG=None, PATH=os.environ.get("PATH")), \
            _fake_webview(visit) as webview:
        home = Path(tmp) / "home"
        try:
            assert app.run(port=8799, home=home) == 0
        finally:
            os.chdir(cwd)
            sys.stdout, sys.stderr = saved_out, saved_err
            telemetry._calls_db = None
            logging.getLogger("jobdork").removeHandler(telemetry._handler)
            VAULT.wipe()
        made = webview.made
        assert made["title"] == "jobdork" and "?t=" in made["url"], made
        assert "js_api" not in made, "the page reaches the Bridge through the server"
        assert made["text_select"] is True        # logs and letters can be copied
        assert len(made["closing"]) == 1          # asks before closing mid-scan
        assert made["start"] == {"private_mode": False,
                                 "storage_path": str(home / "window"),
                                 "debug": False}
        assert webview.settings["ALLOW_DOWNLOADS"] is True
        assert pages["status"] == 200 and b"jobdork" in pages["body"]
        assert home.is_dir()
        # What is printed may go to logs/app.log, so it never holds the token.
        token = made["url"].split("?t=")[1]
        out = printed.getvalue()
        assert "jobdork dashboard: http://127.0.0.1:8799/" in out, out
        assert token not in out
        # Not set up yet: nothing is written until setup's first answer.
        assert not (home / "config.yaml").exists()


def test_closing_mid_scan_asks_first_and_otherwise_does_not():
    job = {"now": "scan"}
    # lambda: what is running, read when the window closes, as serve passes it.
    closing = app.ask_before_closing(lambda: job["now"])
    window = types.SimpleNamespace(confirm_close=False,
                                   localization={"global.quitConfirmation": "Quit?"})
    closing(window)
    assert window.confirm_close is True
    assert window.localization["global.quitConfirmation"].startswith("Scan is still running")
    assert window.localization["global.quit"] == "Close anyway"
    job["now"] = ""
    closing(window)
    assert window.confirm_close is False


def test_the_users_own_tools_are_found_from_an_app():
    with tempfile.TemporaryDirectory() as tmp, _env(PATH="/usr/bin:/bin"), \
            _platform("darwin"):
        tools = Path(tmp) / "bin"
        tools.mkdir()
        saved = app.USER_TOOL_DIRS
        app.USER_TOOL_DIRS = (str(tools), str(Path(tmp) / "missing"), "/usr/bin")
        try:
            app.widen_path()
            assert os.environ["PATH"] == f"/usr/bin:/bin:{tools}"
            app.widen_path()                 # twice adds nothing
            assert os.environ["PATH"] == f"/usr/bin:/bin:{tools}"
        finally:
            app.USER_TOOL_DIRS = saved


def test_an_app_with_no_terminal_logs_to_a_file():
    saved_out, frozen = sys.stdout, getattr(sys, "frozen", None)
    try:
        sys.stdout = None
        assert app.no_terminal()             # Windows, no console
        # lambda: a stdout that is not a terminal (a pipe, or nowhere).
        sys.stdout = types.SimpleNamespace(isatty=lambda: False)
        assert not app.no_terminal()         # from source, output piped
        sys.frozen = True
        assert app.no_terminal()             # macOS app opened from Finder
        # lambda: a stdout that is a terminal.
        sys.stdout = types.SimpleNamespace(isatty=lambda: True)
        assert not app.no_terminal()         # the app run in a terminal, --debug
    finally:
        sys.stdout = saved_out
        if frozen is None:
            del sys.frozen
        else:
            sys.frozen = frozen


def test_without_pywebview_it_says_what_to_install():
    saved = sys.modules.get("webview")
    sys.modules["webview"] = None            # makes `import webview` fail
    try:
        assert app.run(port=8799, home=Path(tempfile.gettempdir())) == 1
    finally:
        if saved is None:
            sys.modules.pop("webview", None)
        else:
            sys.modules["webview"] = saved


def test_self_test_passes_with_everything_present():
    backend = app.WINDOW_BACKENDS.get(sys.platform)
    saved = sys.modules.get(backend) if backend else None
    with _fake_webview():
        if backend:
            sys.modules[backend] = types.ModuleType(backend)
        try:
            assert app.self_test() == []
        finally:
            if backend and saved is None:
                sys.modules.pop(backend, None)
            elif backend:
                sys.modules[backend] = saved


def test_self_test_names_what_a_build_is_missing():
    saved_modules, saved_files = app.SELF_TEST_MODULES, app.SELF_TEST_FILES
    app.SELF_TEST_MODULES = ("jobdork_no_such_module",)
    app.SELF_TEST_FILES = ("dashboard.html", "no-such-file.csv")
    try:
        with _platform("linux"):               # no window backend to import
            problems = app.self_test()
    finally:
        app.SELF_TEST_MODULES, app.SELF_TEST_FILES = saved_modules, saved_files
    assert len(problems) == 2, problems
    assert problems[0].startswith("cannot import jobdork_no_such_module: ModuleNotFoundError")
    assert problems[1] == "missing data file no-such-file.csv"


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
