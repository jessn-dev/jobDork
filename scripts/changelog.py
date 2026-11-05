#!/usr/bin/env python3
"""
changelog.py
============
Changelog entries that wait in files of their own until a release.

Every pull request used to add its entry at the top of docs/CHANGELOG.md,
so any two open at once changed the same lines and the second to merge was
blocked by a conflict. Now each one adds a file to docs/changes/ instead,
holding exactly one entry, and the release pull request moves them all into
the changelog at once. Two pull requests never touch the same file.

    python scripts/changelog.py check      # every waiting entry is well formed
    python scripts/changelog.py collect    # move them into docs/CHANGELOG.md (release PR)
    python scripts/changelog.py list       # what is waiting, newest first

An entry file is named for its work (`docs/changes/master-resume.md`) and
holds one heading and its text, as an entry in the changelog does:

    ## Added — 2026-11-05 — A master resume, told apart from the one you send

    What was missing, what changed, and why.

`collect` puts them above the newest entry, newest first by the heading's
date, then by when the file was added to git, and deletes the files.
release_notes.py then reads them from the changelog as before. tag_release.py
refuses to tag while any are left waiting. Standard library and git only.
"""

from __future__ import annotations

import datetime
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"
WAITING = ROOT / "docs" / "changes"
KINDS = ("Added", "Changed", "Fixed", "Security", "Removed", "Checked")
_HEADING = re.compile(r"^## (?P<kind>\w+) — (?P<date>\d{4}-\d{2}-\d{2}) — (?P<title>\S.*)$")
_FIRST_ENTRY = re.compile(r"^## (?!Still outstanding)", re.MULTILINE)


@dataclass
class Entry:
    path: Path
    text: str          # heading first, no separator around it
    date: str
    added: int = 0     # when git first saw the file, seconds; 0 when it has not


def files(folder: Path = WAITING) -> list[Path]:
    """The entry files waiting, by name. The folder's README is not one."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.md") if p.name.lower() != "readme.md")


def problems(path: Path) -> list[str]:
    """What is wrong with one entry file; empty when it is well formed."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return [f"{path.name}: empty"]
    lines = text.splitlines()
    found = []
    m = _HEADING.match(lines[0])
    if not m:
        found.append(f"{path.name}: the first line must be "
                     "`## <Kind> — <YYYY-MM-DD> — <title>`, not: " + lines[0][:80])
    else:
        if m["kind"] not in KINDS:
            found.append(f"{path.name}: kind {m['kind']!r} is not one of {', '.join(KINDS)}")
        try:
            datetime.date.fromisoformat(m["date"])
        except ValueError:
            found.append(f"{path.name}: {m['date']} is not a date")
    if sum(1 for line in lines if line.startswith("## ")) > 1:
        found.append(f"{path.name}: holds more than one entry; give each its own file")
    if len(lines) < 3 or not any(line.strip() for line in lines[1:]):
        found.append(f"{path.name}: has a heading but no text")
    if lines[-1].strip() == "---" or lines[1:2] == ["---"]:
        found.append(f"{path.name}: leave out the `---` lines; collect adds them")
    return found


def _added(path: Path) -> int:
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%ct", "--", str(path)],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return 0
    return int(out[-1]) if out else 0


def waiting(folder: Path = WAITING, added=_added) -> list[Entry]:
    """The waiting entries, newest first. Raises ValueError if one is malformed."""
    bad = [p for path in files(folder) for p in problems(path)]
    if bad:
        raise ValueError("\n".join(bad))
    out = []
    for path in files(folder):
        text = path.read_text(encoding="utf-8").strip()
        out.append(Entry(path, text, _HEADING.match(text.splitlines()[0])["date"], added(path)))
    # Newest first: by the heading's date, then by when the file came in.
    # lambda: a sort key of three fields, used only here
    return sorted(out, key=lambda e: (e.date, e.added, e.path.name), reverse=True)


def collect(changelog: Path = CHANGELOG, folder: Path = WAITING, added=_added) -> list[Path]:
    """Move every waiting entry into the changelog, above the newest entry,
    and delete its file. Returns the files moved."""
    entries = waiting(folder, added)
    if not entries:
        return []
    text = changelog.read_text(encoding="utf-8")
    m = _FIRST_ENTRY.search(text)
    at = m.start() if m else len(text)
    block = "".join(f"{e.text}\n\n---\n\n" for e in entries)
    changelog.write_text(text[:at] + block + text[at:], encoding="utf-8")
    for e in entries:
        e.path.unlink()
    return [e.path for e in entries]


def main(argv: list[str]) -> int:
    what = argv[0] if argv else "check"
    try:
        if what == "check":
            n = len(waiting())
            print(f"{n} waiting entr{'y' if n == 1 else 'ies'}, all well formed.")
        elif what == "list":
            for e in waiting():
                print(f"{e.path.relative_to(ROOT)}: {e.text.splitlines()[0]}")
        elif what == "collect":
            moved = collect()
            print(f"moved {len(moved)} into {CHANGELOG.relative_to(ROOT)}"
                  + "".join(f"\n  {p.name}" for p in moved))
        else:
            print(__doc__)
            return 2
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
