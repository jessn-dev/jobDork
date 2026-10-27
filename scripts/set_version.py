#!/usr/bin/env python3
"""
set_version.py
==============
Sets jobdork's version in `pyproject.toml` and everywhere the documentation
names the current release, in one step, so no page is left on the old one.

    python scripts/set_version.py 0.14.5     # the release you are preparing
    python scripts/set_version.py --check    # exit 1 if any page is stale

`pyproject.toml` is the one source of the version (jobdork/__init__.py reads
it from the package metadata). The pages name it where a reader copies it:
the image tag in a `docker run`, the installer's file name, the tag command
in SECURITY.md. Those are found by their shape (CURRENT), in every page
(PAGES), so a new page that names the image is kept up to date without being
listed here.

A version stated as a fact is left alone: "0.14.4 or newer", "0.14.3 and
older", "from 0.14.4 on" are true whatever the newest release is, and none
of them has one of these shapes. Write it that way on purpose, and write a
version the reader should copy in one of these shapes.

The tests run `--check` (tests/test_version.py), so a pull request that sets
a new version without the pages fails, and so does the release tag.
Standard library only, Python 3.10 and newer.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"

VERSION = r"\d+\.\d+\.\d+"
_PROJECT_VERSION = re.compile(r'^(version = ")(' + VERSION + r')(")$', re.MULTILINE)

# The shapes a current-release version takes in the pages: the part before
# the version, and the part after it. Each is (prefix, suffix) of one regex.
CURRENT = (
    (r"jessengolab/jobdork:", r""),                       # the image tag
    (r"jobdork-", r"-(?:macos-(?:arm64|x86_64)\.dmg|windows-x64-setup\.exe)"),  # installers
    (r"git tag v", r" && git push origin v"),               # SECURITY.md, step 2
    (r"git push origin v", r"\b"),
)
_SHAPES = [re.compile(f"({prefix})({VERSION})({suffix})") for prefix, suffix in CURRENT]

# The pages. The changelog and the history name past versions on purpose.
PAGES = ("README.md", "SECURITY.md", "PRIVACY.md", "compose.yaml", "docs/**/*.md")
NOT_PAGES = {"docs/CHANGELOG.md", "docs/HISTORY.md"}


def project_version() -> str:
    match = _PROJECT_VERSION.search(PYPROJECT.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("no `version = \"x.y.z\"` line in pyproject.toml")
    return match.group(2)


def pages(root: Path = ROOT) -> list[Path]:
    found = {p for pattern in PAGES for p in root.glob(pattern) if p.is_file()}
    return sorted(p for p in found
                  if p.relative_to(root).as_posix() not in NOT_PAGES)


def stale(version: str, root: Path = ROOT) -> list[str]:
    """Every place a page names a current release other than `version`."""
    out = []
    for page in pages(root):
        for n, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            for shape in _SHAPES:
                for m in shape.finditer(line):
                    if m.group(2) != version:
                        out.append(f"{page.relative_to(root).as_posix()}:{n}: "
                                   f"{m.group(0)} (expected {version})")
    return out


def set_version(version: str, root: Path = ROOT) -> list[str]:
    """Write `version` into pyproject.toml and every page; the files changed."""
    if not re.fullmatch(VERSION, version):
        raise SystemExit(f"{version!r} is not a version like 0.14.5")
    changed = []
    project = root / "pyproject.toml"
    text = project.read_text(encoding="utf-8")
    # lambda: keeps the quotes around the version and replaces only the number.
    new = _PROJECT_VERSION.sub(lambda m: m.group(1) + version + m.group(3), text, count=1)
    if new != text:
        project.write_text(new, encoding="utf-8")
        changed.append("pyproject.toml")
    for page in pages(root):
        text = page.read_text(encoding="utf-8")
        new = text
        for shape in _SHAPES:
            # lambda: keeps what surrounds the version and replaces only the number.
            new = shape.sub(lambda m: m.group(1) + version + m.group(3), new)
        if new != text:
            page.write_text(new, encoding="utf-8")
            changed.append(page.relative_to(root).as_posix())
    return changed


def main(argv: list[str]) -> int:
    if argv == ["--check"]:
        version = project_version()
        problems = stale(version)
        for p in problems:
            print(p)
        print(f"{len(problems)} page(s) not on {version}" if problems
              else f"every page names {version}")
        return 1 if problems else 0
    if len(argv) != 1 or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[1])
        return 2
    changed = set_version(argv[0].removeprefix("v"))
    print("\n".join(changed) if changed else "nothing to change")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
