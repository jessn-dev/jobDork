"""
CI installs nothing unchecked: every `pip install` in the workflows takes a
lock with hashes (or adds jobdork itself with --no-deps), each tool pinned in
packaging/ci.in is in requirements-ci.lock at that version, and the guide's
own requirements (for building it by hand) say the same versions.

    python tests/test_ci_lock.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;#\\]+)", re.M)


def _pins(path: Path) -> dict[str, str]:
    return {name.lower(): version for name, version in PIN.findall(path.read_text())}


def test_every_install_in_ci_checks_hashes():
    loose = []
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for n, line in enumerate(workflow.read_text().splitlines(), 1):
            if re.search(r"\bpip install\b", line) and not re.search(
                    r"--require-hashes|--no-deps", line):
                loose.append(f"{workflow.name}:{n}: {line.strip()}")
    assert not loose, "installs without hashes:\n" + "\n".join(loose)


def test_the_ci_tools_are_in_the_lock_at_their_versions():
    wanted = _pins(ROOT / "packaging" / "ci.in")
    locked = _pins(ROOT / "requirements-ci.lock")
    assert wanted, "expected exact pins in packaging/ci.in"
    wrong = {name: (version, locked.get(name)) for name, version in wanted.items()
             if locked.get(name) != version}
    assert not wrong, f"regenerate requirements-ci.lock (command at its top): {wrong}"


def test_the_guide_is_built_by_hand_with_the_versions_ci_uses():
    ci = _pins(ROOT / "packaging" / "ci.in")
    guide = _pins(ROOT / "guide" / "requirements.txt")
    assert guide and all(ci.get(name) == version for name, version in guide.items()), \
        f"guide/requirements.txt {guide} and packaging/ci.in disagree"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"\n{len(tests)}/{len(tests)} passed")
