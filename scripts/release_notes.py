#!/usr/bin/env python3
"""
release_notes.py
================
What changed in a release, for its GitHub Release page: the docs/CHANGELOG.md
entries written since the release before it, in full.

    python scripts/release_notes.py v0.14.5              # since the tag before it
    python scripts/release_notes.py v0.14.5 v0.14.3      # since a tag you name

GitHub's own release notes list pull request titles ("chore: release 0.14.1
(see docs/CHANGELOG.md) by @jessn-dev in #11"), which say nothing. The
changelog says what changed and why, so the page carries that instead.

The entries are the ones above the newest entry the previous release's
changelog had: each finished piece of work is its own dated entry at the top
(docs/CHANGELOG.md, first lines), so what a release added is exactly what was
written above where the last one stopped. With no earlier release, every
entry counts.

A release page holds at most 125,000 characters. Entries are given in full,
newest first, while they fit in BUDGET; any left over are listed by title,
each linked to its place in the changelog. Standard library and git only.
"""

from __future__ import annotations

import re
import subprocess
import sys

CHANGELOG = "docs/CHANGELOG.md"
BUDGET = 105_000
LIMIT = 115_000          # what this writes; the page adds ~3,000 and GitHub caps it at 125,000
REPO = "https://github.com/jessn-dev/jobDork"
_ENTRY = re.compile(r"^## (?!Still outstanding)", re.MULTILINE)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def previous_tag(tag: str) -> str:
    """The release tag before `tag`, or "" for the first release."""
    try:
        return _git("describe", "--tags", "--abbrev=0", "--match", "v*.*.*",
                    f"{tag}^").strip()
    except subprocess.CalledProcessError:
        return ""


def entries(text: str) -> list[str]:
    """Each entry of a changelog, heading first, newest first."""
    end = text.find("\n## Still outstanding")
    body = text if end < 0 else text[:end]
    starts = [m.start() for m in _ENTRY.finditer(body)]
    if not starts:
        return []
    return [body[a:b].strip().rstrip("-").strip()
            for a, b in zip(starts, [*starts[1:], len(body)], strict=True)]


def since(current: str, before: str) -> list[str]:
    """The entries in `current` above the newest one `before` had."""
    now = entries(current)
    old = entries(before)
    if not old:
        return now
    first = old[0].splitlines()[0]
    for i, entry in enumerate(now):
        if entry.splitlines()[0] == first:
            return now[:i]
    return now


def anchor(heading: str) -> str:
    """GitHub's link to a heading: lower case, punctuation gone, spaces to hyphens."""
    text = heading.lstrip("#").strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def notes(tag: str, previous: str = "") -> str:
    from pathlib import Path

    current = (_git("show", f"{tag}:{CHANGELOG}") if tag
               else Path(CHANGELOG).read_text(encoding="utf-8"))
    before = _git("show", f"{previous}:{CHANGELOG}") if previous else ""
    new = since(current, before)
    if not new:
        return "## What changed\n\nNo changelog entries since the last release.\n"
    out, used, left = ["## What changed", ""], 0, []
    for entry in new:
        heading, _, rest = entry.partition("\n")
        block = f"### {heading[3:]}\n{rest}\n"
        if left or used + len(block) > BUDGET:
            left.append(heading)
            continue
        out.append(block)
        used += len(block)
    if left:
        ref = tag or "main"
        out += [f"### And {len(left)} more", "",
                "Too long for this page; each is in full in the changelog:", ""]
        links = [f"- [{h[3:]}]({REPO}/blob/{ref}/{CHANGELOG}#{anchor(h)})" for h in left]
        while links and len("\n".join(out + links)) > LIMIT:
            links.pop()
        out += links
        if len(links) < len(left):
            out.append(f"- …and the older ones in [the changelog]({REPO}/blob/{ref}/{CHANGELOG})")
        out.append("")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 2 or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[1])
        return 2
    tag = argv[0]
    previous = argv[1] if len(argv) == 2 else previous_tag(tag)
    sys.stdout.write(notes(tag, previous))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
