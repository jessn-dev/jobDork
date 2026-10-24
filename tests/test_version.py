"""
The version the pages name (scripts/set_version.py): every page that tells
a reader which release to copy names the one in pyproject.toml, so a pull
request that sets a new version without the pages fails here, and so does
its release tag.

    python tests/test_version.py

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _script():
    spec = importlib.util.spec_from_file_location("set_version",
                                                  ROOT / "scripts" / "set_version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_page_names_the_version_in_pyproject():
    sv = _script()
    version = sv.project_version()
    stale = sv.stale(version)
    assert not stale, ("pages name another release than pyproject.toml; run "
                       f"python scripts/set_version.py {version}:\n" + "\n".join(stale))


def test_the_pages_include_new_ones_and_leave_out_the_changelog():
    names = {p.relative_to(ROOT).as_posix() for p in _script().pages()}
    assert {"README.md", "SECURITY.md", "compose.yaml", "docs/run/docker.md",
            "docs/run/nas.md", "docs/run/desktop.md"} <= names
    assert "docs/CHANGELOG.md" not in names and "docs/HISTORY.md" not in names


def test_setting_a_version_changes_what_to_copy_and_not_what_is_a_fact():
    sv = _script()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs" / "run").mkdir(parents=True)
        (root / "pyproject.toml").write_text('[project]\nname = "jobdork"\n'
                                             'version = "0.14.4"\n', encoding="utf-8")
        page = root / "docs" / "run" / "new.md"
        page.write_text("docker run jessengolab/jobdork:0.14.4\n"
                        "Download jobdork-0.14.4-macos-arm64.dmg or "
                        "jobdork-0.14.4-windows-x64-setup.exe.\n"
                        "`git tag v0.14.4 && git push origin v0.14.4`\n"
                        "Use 0.14.4 or newer; 0.14.3 and older need a config.\n",
                        encoding="utf-8")
        history = root / "docs" / "CHANGELOG.md"
        history.write_text("Published jessengolab/jobdork:0.14.2.\n", encoding="utf-8")

        assert sv.stale("0.14.4", root) == []
        changed = sv.set_version("0.15.0", root)
        assert changed == ["pyproject.toml", "docs/run/new.md"]
        assert 'version = "0.15.0"' in (root / "pyproject.toml").read_text(encoding="utf-8")
        text = page.read_text(encoding="utf-8")
        assert text.count("0.15.0") == 5
        assert "Use 0.14.4 or newer; 0.14.3 and older" in text
        assert "0.14.2" in history.read_text(encoding="utf-8")
        assert sv.stale("0.15.0", root) == []
        assert len(sv.stale("0.15.1", root)) == 5


def test_a_version_that_is_not_one_is_refused():
    sv = _script()
    for bad in ("0.15", "v0.15.0", "0.15.0-rc1"):
        try:
            sv.set_version(bad, Path(tempfile.gettempdir()) / "no-such-jobdork")
        except SystemExit:
            continue
        raise AssertionError(f"accepted {bad}")


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
