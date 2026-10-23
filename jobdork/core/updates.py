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
Settings page's Updates section writes, turns it off for one install.

Asked by the page, never at start: a dashboard opened offline costs one
failed request and no wait, and a check that fails is simply not shown.
"""

from __future__ import annotations

import json
import os
import platform
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


# Only files from this repository's own release downloads are fetched.
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
SUMS_FILE = "SHA256SUMS.txt"
MAX_INSTALLER_BYTES = 600 * 1024 * 1024


def _read_cache(path: Path) -> dict:
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
        return kept if isinstance(kept, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(path: Path, kept: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(kept), encoding="utf-8")
    except OSError:
        pass


def latest(cache_dir: str | Path, fetch=_fetch, now=time.time,
           force: bool = False) -> dict | None:
    """The newest release, {"version", "url", "assets"}, from the cache when
    it is younger than a day (unless `force`, the Settings page's Check now).
    None when off or when GitHub cannot be asked."""
    if off():
        return None
    path = Path(cache_dir) / CACHE_FILE
    kept = _read_cache(path)
    if (not force and "checked_at" in kept
            and now() - float(kept["checked_at"] or 0) < CHECK_SECONDS):
        return kept.get("release")
    try:
        answer = fetch(LATEST_URL)
    except Exception:                        # offline, rate-limited, GitHub down
        return None
    version = str(answer.get("tag_name") or "").lstrip("v")
    url = str(answer.get("html_url") or "")
    assets = {str(a.get("name") or ""): str(a.get("browser_download_url") or "")
              for a in answer.get("assets") or [] if isinstance(a, dict)}
    release = ({"version": version,
                "url": url if url.startswith("https://github.com/") else RELEASES_PAGE,
                "assets": {n: u for n, u in assets.items()
                           if n and u.startswith(DOWNLOAD_PREFIX)}}
               if parse(version) and not answer.get("prerelease") else None)
    _write_cache(path, {**kept, "checked_at": now(), "release": release})
    return release


def installer_name(version: str) -> str:
    """The installer this computer takes from a release, or "" when there is
    none for it (Linux, an Intel Mac, a copy that is not the desktop app)."""
    if not getattr(sys, "frozen", False):
        return ""
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return f"jobdork-{version}-macos-arm64.dmg"
    if sys.platform == "win32":
        return f"jobdork-{version}-windows-x64-setup.exe"
    return ""


def check(cache_dir: str | Path, current: str = __version__, fetch=_fetch,
          now=time.time, enabled: bool = True, force: bool = False) -> dict:
    """What the page shows: {"newer": False} or the release to move to.
    `enabled` is the config's `update_check`; False asks nothing."""
    mine = parse(current)
    if mine is None or off() or not enabled:
        return {"newer": False, "current": current}
    release = latest(cache_dir, fetch=fetch, now=now, force=force)
    if not release or (parse(release["version"]) or (0, 0, 0)) <= mine:
        return {"newer": False, "current": current}
    name = installer_name(release["version"])
    return {"newer": True, "current": current, "latest": release["version"],
            "url": release["url"], "how": how_to_update(release["version"]),
            "installer": name if name in (release.get("assets") or {}) else ""}


def first_notice(cache_dir: str | Path, version: str) -> bool:
    """True the first time this version is seen, so a notification about it
    is shown once, not every time the Dashboard opens."""
    path = Path(cache_dir) / CACHE_FILE
    kept = _read_cache(path)
    if kept.get("notified") == version:
        return False
    _write_cache(path, {**kept, "notified": version})
    return True


class UpdateError(Exception):
    pass


def _download(url: str, dest: Path, progress=None, opener=urllib.request.urlopen) -> None:
    if not url.startswith(DOWNLOAD_PREFIX):
        raise UpdateError("not one of this project's release downloads")
    request = urllib.request.Request(url, headers={
        "User-Agent": f"jobdork/{__version__} (update)"})
    part = dest.with_name(dest.name + ".part")
    done = 0
    with opener(request, timeout=60) as answer, open(part, "wb") as out:  # nosec B310
        total = int(answer.headers.get("Content-Length") or 0)
        while True:
            chunk = answer.read(1024 * 1024)
            if not chunk:
                break
            done += len(chunk)
            if done > MAX_INSTALLER_BYTES:
                raise UpdateError("the download is far larger than an installer")
            out.write(chunk)
            if progress and total:
                progress(f"downloaded {done * 100 // total}%")
    part.replace(dest)


def download_installer(cache_dir: str | Path, folder: Path, progress=None,
                       opener=urllib.request.urlopen) -> Path:
    """Download this computer's installer from the latest release into
    `folder`, check it against the release's SHA256SUMS.txt, and return its
    path. Raises UpdateError; a file that does not match is deleted."""
    import hashlib

    kept = _read_cache(Path(cache_dir) / CACHE_FILE)
    release = kept.get("release") or {}
    name = installer_name(str(release.get("version") or ""))
    assets = release.get("assets") or {}
    if not name or name not in assets:
        raise UpdateError("this release has no installer for this computer; "
                          "download it from the release page")
    if SUMS_FILE not in assets:
        raise UpdateError("this release has no checksums to check the installer against")
    folder.mkdir(parents=True, exist_ok=True)
    sums = folder / f".jobdork-{release['version']}-{SUMS_FILE}"
    dest = folder / name
    if progress:
        progress(f"downloading {name}")
    _download(assets[SUMS_FILE], sums, opener=opener)
    _download(assets[name], dest, progress=progress, opener=opener)
    wanted = ""
    for line in sums.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name:
            wanted = parts[0].lower()
    sums.unlink(missing_ok=True)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if not wanted or digest != wanted:
        dest.unlink(missing_ok=True)
        raise UpdateError("the downloaded installer does not match the release's "
                          "checksum, so it was deleted; try again, or download it "
                          "from the release page")
    if progress:
        progress("checksum matches the release's SHA256SUMS.txt")
    return dest
