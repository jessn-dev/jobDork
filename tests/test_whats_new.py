"""
What's new, once after an update: the bundled list matches the release
(scripts/whats_new.py), and the app shows it when, and only when, it runs a
newer version than it last showed (web/api.py, whats_new). Also the update
fixes of 2026-11-12: a .deb's version read from its name, and Windows'
installer started after jobdork has quit. No network.

    python tests/test_whats_new.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork import __version__  # noqa: E402
from jobdork.core import updates  # noqa: E402
from jobdork.core.config import Config  # noqa: E402
from jobdork.db.store import Role, Store  # noqa: E402
from jobdork.web import api  # noqa: E402


def _script():
    spec = importlib.util.spec_from_file_location("whats_new", ROOT / "scripts" / "whats_new.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_bundled_list_is_this_releases():
    assert _script().main(["--check"]) == 0, "run python scripts/whats_new.py"
    data = json.loads(api.WHATS_NEW.read_text(encoding="utf-8"))
    assert data["items"] and all(isinstance(i, str) and i for i in data["items"])


def test_the_list_is_read_from_the_release_entry():
    text = ("# Changelog\n\n## Changed — 2026-01-02 — version 9.8.7\n\n9.8.7 carries...\n"
            "For you:\n\n- **One.** first line\n  goes on.\n- **Two** with [a link](x.md).\n\n"
            "Updating from 9.8.6: ...\n\n---\n\n## Added — 2026-01-01 — Old\n\n- not this\n")
    found = _script().newest(text)
    assert found == {"version": "9.8.7", "items": ["**One.** first line goes on.",
                                                    "**Two** with a link."]}


def _cfg(tmp: str, posts: bool) -> Config:
    cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"))
    with Store(cfg.db_path) as store:
        if posts:
            store.upsert(Role(platform="x", title="Nurse", url="https://x.test/1"))
    return cfg


def _with_news(version: str):
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "news.json"
    path.write_text(json.dumps({"version": version, "items": ["**A** thing"]}), encoding="utf-8")
    return path


def test_shown_once_after_an_update_and_never_to_a_new_copy():
    was = api.WHATS_NEW
    api.WHATS_NEW = _with_news(__version__)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp, posts=False)                  # a new copy
            assert api.whats_new(cfg) is None
            assert api.whats_new(cfg) is None
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp, posts=True)                   # an update from before this existed
            assert api.whats_new(cfg)["items"] == ["**A** thing"]
            api.whats_new_seen(cfg)
            assert api.whats_new(cfg) is None
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp, posts=True)
            with Store(cfg.db_path) as store:
                store.set_meta(api.SEEN_KEY, "0.0.1")      # last ran an older version
            assert api.whats_new(cfg)["version"] == __version__
        api.WHATS_NEW = _with_news("0.0.1")                # a list for another version
        with tempfile.TemporaryDirectory() as tmp:
            assert api.whats_new(_cfg(tmp, posts=True)) is None
    finally:
        api.WHATS_NEW = was


def test_a_deb_and_the_windows_installer_are_handled():
    import re
    pattern = r"jobdork[-_](\d+\.\d+\.\d+)[-_]"
    for name in ("jobdork_0.16.5_amd64.deb", "jobdork_0.16.5_arm64.deb",
                 "jobdork-0.16.5-linux-x86_64.AppImage", "jobdork-0.16.5-windows-x64-setup.exe"):
        assert re.search(pattern, name).group(1) == "0.16.5", name
    source = (ROOT / "jobdork" / "web" / "api.py").read_text(encoding="utf-8")
    assert pattern in source.replace("\\\\", "\\")
    spawned = []

    def spawn(argv, **kw):
        spawned.append((argv, kw))
    updates.run_windows_installer_after_quit(Path("C:/D/setup.exe"), Path(tempfile.mkdtemp()) / "u.log",
                                             pid=4321, spawn=spawn)
    (argv, kw), = spawned
    assert argv[0] == "powershell" and "Wait-Process" in argv[-1] and "Start-Process" in argv[-1]
    assert kw["env"]["JOBDORK_UPDATE_PID"] == "4321"
    args = json.loads(kw["env"]["JOBDORK_UPDATE_ARGS"])
    assert args[0].endswith("setup.exe") and "/restart=yes" in args and "/FORCECLOSEAPPLICATIONS" in args
    assert any(a.startswith("/LOG=") for a in args)
    iss = (ROOT / "packaging" / "jobdork.iss").read_text(encoding="utf-8")
    assert "CloseApplications=force" in iss and "function PrepareToInstall" in iss


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
