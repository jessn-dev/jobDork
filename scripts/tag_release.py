#!/usr/bin/env python3
"""
tag_release.py
==============
Tags a release once its pull request is merged and its checks passed, then
opens the run that waits for your approval.

    python scripts/tag_release.py              # asks: major, minor or patch?
    python scripts/tag_release.py patch        # or say it here
    python scripts/tag_release.py patch --yes  # and skip typing the version

What it does, stopping at the first thing that is not right:

1. Brings main up to date (`git checkout main`, `git pull --ff-only`). A
   working copy with changes is refused, so nothing of yours is lost.
2. The next version: the last release tag (the highest `vX.Y.Z`) moved on by
   the kind you chose. From v0.16.1, patch is 0.16.2, minor 0.17.0, major
   1.0.0.
3. That version must be the one the release pull request set: pyproject.toml
   says it, every page names it (scripts/set_version.py --check), and main's
   last commit is the merge of `release/<version>`. The release run refuses
   a tag that differs from pyproject.toml, and a release tag can never be
   moved or deleted, so a mismatch stops here instead.
4. The merge passed: the release pull request is merged, and every check on
   main's last commit finished and passed (skipped ones are fine). One still
   running stops it: run it again when they are done.
5. The tag exists neither here nor on GitHub. Then you type the version to
   confirm, and it is tagged and pushed.
6. It finds the release run and opens it in the browser, where you approve
   the `release` environment yourself: the approval is the sign-off
   (SECURITY.md) and is not done for you.

Needs git and the GitHub CLI (`gh`, signed in). Standard library only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "jessn-dev/jobDork"
KINDS = ("major", "minor", "patch")
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# A check that finished without failing: passed, skipped, or nothing to do.
FINE = {"success", "skipped", "neutral"}


def stop(why: str) -> None:
    print(f"Not tagged: {why}", file=sys.stderr)
    raise SystemExit(1)


def run(*cmd: str, check: bool = True) -> str:
    try:
        done = subprocess.run(list(cmd), cwd=ROOT, capture_output=True, text=True)
    except OSError:
        stop(f"`{cmd[0]}` is not installed")
    if check and done.returncode:
        stop(f"{' '.join(cmd)} failed:\n{(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()


def git(*args: str) -> str:
    return run("git", *args)


def gh(*args: str) -> str:
    return run("gh", *args)


def last_release(tags: list[str]) -> tuple[int, int, int]:
    """The highest vX.Y.Z among the tags (by number, not by text)."""
    found = [tuple(int(n) for n in m.groups()) for t in tags if (m := TAG.match(t.strip()))]
    if not found:
        stop("no vX.Y.Z tag yet to count from")
    return max(found)


def bump(last: tuple[int, int, int], kind: str) -> str:
    major, minor, patch = last
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(kind)


def project_version() -> str:
    match = re.search(r'^version = "(\d+\.\d+\.\d+)"$',
                      (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        stop('no `version = "x.y.z"` line in pyproject.toml')
    return match.group(1)


def is_release_merge(subject: str, body: str, ver: str) -> bool:
    """Whether a commit is the merge of release/<ver>: GitHub's merge commit
    ("Merge pull request #N from owner/release/X.Y.Z"), or a squash of the
    release commit ("chore: release X.Y.Z ...")."""
    branch = re.escape(f"release/{ver}")
    return bool(re.search(rf"^Merge pull request #\d+ from [\w.-]+/{branch}$", subject)
                or re.search(rf"\brelease {re.escape(ver)}\b", subject + "\n" + body))


def failing(runs: list[dict]) -> tuple[list[str], list[str]]:
    """From a commit's check runs: the names still running, and those that
    finished without passing."""
    waiting = [r["name"] for r in runs if r.get("status") != "completed"]
    bad = [f"{r['name']} ({r.get('conclusion')})" for r in runs
           if r.get("status") == "completed" and r.get("conclusion") not in FINE]
    return waiting, bad


def ask_kind(argv: list[str]) -> str:
    given = [a for a in argv if a in KINDS]
    if given:
        return given[0]
    answer = input("Which release is this: major, minor or patch? ").strip().lower()
    if answer not in KINDS:
        stop(f"{answer!r} is not major, minor or patch")
    return answer


def open_run(tag: str) -> None:
    for _ in range(20):                          # the run shows up a few seconds after the push
        url = run("gh", "run", "list", "--branch", tag, "--event", "push", "--limit", "1",
                  "--json", "url", "--jq", ".[0].url", check=False)
        if url:
            print(f"The release run: {url}\n"
                  "When it waits at publish: Review deployments, tick release, "
                  "Approve and deploy.")
            run("gh", "run", "view", "--web", url.rsplit("/", 1)[-1], check=False)
            return
        time.sleep(3)
    print(f"The run has not shown up yet: see https://github.com/{REPO}/actions.")


def main(argv: list[str]) -> int:
    kind = ask_kind(argv)
    gh("auth", "status")                         # signed in, before anything changes

    if git("status", "--porcelain"):
        stop("the working copy has changes; commit or stash them first")
    git("checkout", "main")
    git("pull", "--ff-only")
    git("fetch", "--tags", "origin")

    last = last_release(git("tag", "--list", "v*").splitlines())
    ver = bump(last, kind)
    tag = f"v{ver}"
    print(f"Last release v{'.'.join(map(str, last))}; a {kind} release is {tag}.")

    have = project_version()
    if have == ".".join(map(str, last)):
        stop(f"pyproject.toml still says {have}, released as v{have} already. Set "
             f"{ver} in a release pull request first (scripts/set_version.py {ver}).")
    if have != ver:
        stop(f"pyproject.toml says {have}, not {ver}. Set the version in a release "
             f"pull request first (scripts/set_version.py {ver}), or choose the kind "
             f"that gives {have}.")
    left = sorted(p.name for p in (ROOT / "docs" / "changes").glob("*.md")
                  if p.name.lower() != "readme.md")
    if left:
        stop("changelog entries are still waiting in docs/changes/ ("
             + ", ".join(left) + "): the release page would leave them out. Run "
             "scripts/changelog.py collect in a release pull request first.")
    pages = subprocess.run([sys.executable, str(ROOT / "scripts" / "set_version.py"), "--check"],
                           cwd=ROOT, capture_output=True, text=True)
    if pages.returncode:
        stop(f"a page is not on {ver}:\n{pages.stdout.strip()}")

    sha = git("rev-parse", "HEAD")
    subject, body = git("log", "-1", "--format=%s"), git("log", "-1", "--format=%b")
    if not is_release_merge(subject, body, ver):
        stop(f"main's last commit is not the merge of release/{ver}:\n  {subject}\n"
             "Merge the release pull request first.")
    merged = json.loads(gh("pr", "list", "--repo", REPO, "--head", f"release/{ver}",
                           "--state", "merged", "--json", "number,mergeCommit"))
    if not any((p.get("mergeCommit") or {}).get("oid") == sha for p in merged):
        stop(f"no merged pull request from release/{ver} made main's last commit")
    runs = json.loads(gh("api", f"repos/{REPO}/commits/{sha}/check-runs?per_page=100",
                         "--jq", ".check_runs"))
    if not runs:
        stop("no checks have run on main's last commit yet; try again in a minute")
    waiting, bad = failing(runs)
    if bad:
        stop("checks on the merge did not pass:\n  " + "\n  ".join(bad))
    if waiting:
        stop("checks on the merge are still running:\n  " + "\n  ".join(waiting)
             + "\nRun this again when they are done.")
    print(f"The merge of release/{ver} passed its {len(runs)} checks.")

    if git("tag", "--list", tag):
        stop(f"{tag} already exists here")
    if git("ls-remote", "--tags", "origin", f"refs/tags/{tag}"):
        stop(f"{tag} already exists on GitHub")

    print(f"About to tag {tag} on {sha[:7]} {subject}\n"
          "A release tag can never be moved or deleted.")
    if "--yes" not in argv and input(f"Type {ver} to tag it: ").strip() != ver:
        stop("not confirmed")
    git("tag", tag)
    git("push", "origin", tag)
    print(f"Tagged and pushed {tag}.")
    open_run(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
