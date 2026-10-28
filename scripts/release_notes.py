#!/usr/bin/env python3
"""
release_notes.py
================
A release's GitHub Release page: the downloads first, then how to check
them, then what changed (the docs/CHANGELOG.md entries written since the
release before it, in full).

    python scripts/release_notes.py --page v0.14.5 <image> <digest>  # the whole page
    python scripts/release_notes.py v0.14.5              # what changed, since the tag before it
    python scripts/release_notes.py v0.14.5 v0.14.3      # since a tag you name

GitHub lists a release's files (assets) after its text, always, and that
order cannot be changed. So the page opens with a Download table linking
each file directly, and the changelog, which is long, is folded under a
"What changed" line you click to open: the files are found first either way.

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
    # Folded: GitHub shows the files after the text, and this is long.
    out, used, left = ["## What changed", "",
                       f"<details><summary><b>{len(new)} change{'' if len(new) == 1 else 's'} in this release</b>, "
                       "newest first (click to read)</summary>", ""], 0, []
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
    out += ["</details>", ""]
    return "\n".join(out)


def page(tag: str, image: str, digest: str, previous: str = "") -> str:
    """The whole release page: downloads, first opening, checking, changes."""
    version = tag.removeprefix("v")
    files = f"{REPO}/releases/download/{tag}"
    mac = f"jobdork-{version}-macos-arm64.dmg"
    intel = f"jobdork-{version}-macos-x86_64.dmg"
    win = f"jobdork-{version}-windows-x64-setup.exe"
    return "\n".join([
        "## Download", "",
        "| For | Download |",
        "|---|---|",
        f"| **Mac** with Apple Silicon (M1 or later) | [{mac}]({files}/{mac}) |",
        f"| **Mac** with an Intel processor | [{intel}]({files}/{intel}) |",
        f"| **Windows** 10 or 11, 64-bit | [{win}]({files}/{win}) |",
        f"| **Docker** (a NAS or a server) | `docker pull {image}:{version}` |",
        f"| Checksums of the installers | [SHA256SUMS.txt]({files}/SHA256SUMS.txt) |",
        "",
        "**Mac:** open the `.dmg` and drag jobdork into Applications. "
        "**Windows:** run the setup; it installs for you alone, no administrator needed. "
        "Not sure which Mac you have? Apple menu → **About This Mac**: \"Chip\" is "
        "Apple Silicon, \"Processor … Intel\" is Intel. "
        "Linux, or from source: "
        f"[the ways to run it]({REPO}/blob/{tag}/docs/run/README.md). "
        "New to jobdork? The [user guide](https://jessn-dev.github.io/jobDork/overview/) "
        "shows every page of the app.", "",
        "### The first time you open it", "",
        "The installers are not signed yet, so each system warns once:", "",
        "- **macOS** says it cannot check jobdork for malicious software. Click **Done**,",
        "  open **System Settings → Privacy & Security**, scroll down to the line about",
        "  jobdork and click **Open Anyway**, then **Open Anyway** again.",
        "- **Windows** shows \"Windows protected your PC\". Click **More info**, then "
        "**Run anyway**.", "",
        "## Verify Build Package", "",
        "An installer: compare its SHA-256 with `SHA256SUMS.txt`, or with the "
        "[GitHub CLI](https://cli.github.com/):", "",
        "```bash",
        f"gh attestation verify {mac} --repo {REPO.removeprefix('https://github.com/')}",
        "```", "",
        "Each installer's signed attestation is here too, as `<installer>.sigstore.json`, "
        "to check it without asking GitHub:", "",
        "```bash",
        f"gh attestation verify {mac} --bundle {mac}.sigstore.json "
        f"--repo {REPO.removeprefix('https://github.com/')}",
        "```", "",
        f"The image `{image}:{version}` is exactly:", "",
        "```", f"{image}@{digest}", "```", "",
        "Built, scanned, checked and signed by this repository's workflow after approval.",
        "Verify it before you run it, then pull it by that digest:", "",
        "```bash",
        f"cosign verify {image}@{digest} \\",
        f"  --certificate-identity-regexp '^{REPO}/\\.github/workflows/docker\\.yml@' \\",
        "  --certificate-oidc-issuer https://token.actions.githubusercontent.com",
        "```", "",
        f"The installers are unsigned: [how to open them]({REPO}/blob/{tag}/docs/run/desktop.md#the-first-open-warning). "
        f"Privacy: [PRIVACY.md]({REPO}/blob/{tag}/PRIVACY.md).", "",
        notes(tag, previous if previous else previous_tag(tag)),
    ])


def main(argv: list[str]) -> int:
    if argv[:1] == ["--page"] and len(argv) == 4:
        sys.stdout.write(page(*argv[1:]))
        return 0
    if not 1 <= len(argv) <= 2 or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[1])
        return 2
    tag = argv[0]
    previous = argv[1] if len(argv) == 2 else previous_tag(tag)
    sys.stdout.write(notes(tag, previous))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
