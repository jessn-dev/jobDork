"""
jobdork.core.updates
====================
Whether a newer jobdork has been released, for the Dashboard to say so.

One request to GitHub's releases API, for the latest release of this
repository, at most once a day: the answer is kept in `version-check.json`
beside the database. What is sent is what any request to GitHub sends (this
machine's address and a User-Agent naming jobdork and its version); nothing
about you or your search. `JOBDORK_UPDATE_CHECK=off` turns it off, and the
tests turn it off for every run. `update_check: false` in config.yaml, which the
Dashboard's Updates card writes, turns it off for one install.

Asked by the page, never at start: a dashboard opened offline costs one
failed request and no wait, and a check that fails is simply not shown.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from .. import __version__
from .config import CONTAINER_ENV

ENV = "JOBDORK_UPDATE_CHECK"
REPO = "jessn-dev/jobDork"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CACHE_FILE = "version-check.json"
CHECK_SECONDS = 24 * 3600
TIMEOUT = 6

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse(text: str) -> tuple[int, int, int] | None:
    """(0, 14, 4) from "v0.14.4" or "0.14.4"; None for anything else,
    including a pre-release or a build from a clone ("0.0.0+source")."""
    match = _VERSION.match(str(text or "").strip())
    return tuple(int(x) for x in match.groups()) if match else None


def off() -> bool:
    return os.environ.get(ENV, "").strip().lower() in ("off", "0", "no", "false")


def how_to_update(latest: str) -> str:
    """What to do about it, for the way this copy was installed."""
    if getattr(sys, "frozen", False):
        return ("Download the installer for your computer from the release page "
                "and install it over this one; your settings and job posts are kept.")
    if os.environ.get(CONTAINER_ENV):
        return (f"Change the image to jessengolab/jobdork:{latest} and restart "
                "the container; the data folder is kept.")
    return ("In the folder jobdork was installed from: git pull, then "
            "pip install -e . again.")


def _fetch(url: str) -> dict:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"jobdork/{__version__} (update check)",
    })
    # Safe: always LATEST_URL, a fixed https address.
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # nosec B310
        return json.loads(answer.read(256 * 1024).decode("utf-8"))


def latest(cache_dir: str | Path, fetch=_fetch, now=time.time) -> dict | None:
    """The newest release, {"version", "url"}, from the cache when it is
    younger than a day. None when off or when GitHub cannot be asked."""
    if off():
        return None
    path = Path(cache_dir) / CACHE_FILE
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
        if now() - float(kept.get("checked_at", 0)) < CHECK_SECONDS:
            return kept.get("release")
    except (OSError, ValueError, AttributeError):
        pass
    try:
        answer = fetch(LATEST_URL)
    except Exception:                        # offline, rate-limited, GitHub down
        return None
    version = str(answer.get("tag_name") or "").lstrip("v")
    url = str(answer.get("html_url") or "")
    release = ({"version": version,
                "url": url if url.startswith("https://github.com/") else RELEASES_PAGE}
               if parse(version) and not answer.get("prerelease") else None)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"checked_at": now(), "release": release}),
                        encoding="utf-8")
    except OSError:
        pass
    return release


def check(cache_dir: str | Path, current: str = __version__, fetch=_fetch,
          now=time.time, enabled: bool = True) -> dict:
    """What the page shows: {"newer": False} or the release to move to.
    `enabled` is the config's `update_check`; False asks nothing."""
    mine = parse(current)
    if mine is None or off() or not enabled:
        return {"newer": False, "current": current}
    release = latest(cache_dir, fetch=fetch, now=now)
    if not release or (parse(release["version"]) or (0, 0, 0)) <= mine:
        return {"newer": False, "current": current}
    return {"newer": True, "current": current, "latest": release["version"],
            "url": release["url"], "how": how_to_update(release["version"])}
