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
failed request and no wait. A check that fails is not shown as news, but
Check now says it failed and why: 0.14.4 answered "you have 0.14.4, the
newest" when it could not reach GitHub at all, with 0.15.0 out.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import ssl
import sys
import time
import urllib.error
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

log = logging.getLogger(__name__)

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


def _tls() -> ssl.SSLContext:
    """Certificates to check GitHub's with: certifi's, the bundle requests
    already uses for every other call. urllib alone asks the Python it runs
    in, and the desktop app's own Python may look for them where the build
    machine kept them, which on someone else's computer can be nowhere."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


def _open(request, timeout):
    # Safe: callers pass only api.github.com or this repository's downloads.
    return urllib.request.urlopen(request, timeout=timeout, context=_tls())  # nosec B310


def _fetch(url: str) -> dict:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"jobdork/{__version__} (update check)",
    })
    # Safe: LATEST_URL or ATTEST_URL, fixed https addresses on api.github.com.
    with _open(request, timeout=TIMEOUT) as answer:
        return json.loads(answer.read(256 * 1024).decode("utf-8"))


def why_not(exc: BaseException) -> str:
    """Why GitHub could not be asked, in words for the Settings page."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (403, 429):
            return "GitHub is limiting requests from this network for now; try again in an hour"
        return f"GitHub answered HTTP {exc.code}"
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "this computer could not verify GitHub's certificate"
    if isinstance(exc, (urllib.error.URLError, OSError)):
        return "could not reach GitHub; is this computer online?"
    if isinstance(exc, ValueError):
        return "GitHub's answer could not be read"
    return f"the check failed ({type(exc).__name__})"


# Only files from this repository's own release downloads are fetched.
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
SUMS_FILE = "SHA256SUMS.txt"
MAX_INSTALLER_BYTES = 600 * 1024 * 1024

# Who may have put a file on a release: the release workflow, and nobody
# else. A file uploaded by hand, with a stolen login or token, names that
# person instead, and is not offered.
CI_UPLOADER = "github-actions[bot]"

# Proof of where an installer came from. The release workflow attests each
# installer (desktop.yml, actions/attest-build-provenance): a statement naming
# the file and its SHA-256, signed through Sigstore with a certificate GitHub
# issues to that workflow run. A checksum from the same release page only
# proves the download arrived whole; whoever could replace the installer
# could replace SHA256SUMS.txt too. The attestation cannot be made outside
# this repository's workflow, at that version's tag.
ATTEST_URL = f"https://api.github.com/repos/{REPO}/attestations/sha256:{{digest}}"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
IN_TOTO = "application/vnd.in-toto+json"


def build_identity(version: str) -> str:
    """The signing certificate's identity for an installer of `version`:
    this repository's desktop workflow, run for that version's tag."""
    return f"https://github.com/{REPO}/.github/workflows/desktop.yml@refs/tags/v{version}"


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
    return _latest(cache_dir, fetch, now, force)[0]


def _latest(cache_dir, fetch, now, force) -> tuple[dict | None, str]:
    """latest(), and why GitHub could not be asked ("" when it was)."""
    if off():
        return None, ""
    path = Path(cache_dir) / CACHE_FILE
    kept = _read_cache(path)
    if (not force and "checked_at" in kept
            and now() - float(kept["checked_at"] or 0) < CHECK_SECONDS):
        return kept.get("release"), ""
    try:
        answer = fetch(LATEST_URL)
    except Exception as exc:                 # offline, rate-limited, GitHub down
        why = why_not(exc)
        log.warning("update check: %s (%s: %s)", why, type(exc).__name__, exc)
        return None, why
    release = _release_from(answer)
    _write_cache(path, {**kept, "checked_at": now(), "release": release})
    return release, ""


def _release_from(answer: dict) -> dict | None:
    """The release in GitHub's answer, with only the files the release
    workflow uploaded to this repository's downloads; None for a
    pre-release or a tag that is not a version."""
    version = str(answer.get("tag_name") or "").lstrip("v")
    url = str(answer.get("html_url") or "")
    assets = {str(a.get("name") or ""): str(a.get("browser_download_url") or "")
              for a in answer.get("assets") or []
              if isinstance(a, dict) and _uploader(a) == CI_UPLOADER}
    if not parse(version) or answer.get("prerelease"):
        return None
    return {"version": version,
            "url": url if url.startswith("https://github.com/") else RELEASES_PAGE,
            "assets": {n: u for n, u in assets.items() if n and u.startswith(DOWNLOAD_PREFIX)}}


def _uploader(asset: dict) -> str:
    uploader = asset.get("uploader")
    return str(uploader.get("login") or "") if isinstance(uploader, dict) else ""


def installer_name(version: str) -> str:
    """The installer this computer takes from a release, or "" when there is
    none for it (Linux, a copy that is not the desktop app). Macs have one
    for Apple silicon and one for Intel (from 0.15.3)."""
    if not getattr(sys, "frozen", False):
        return ""
    if sys.platform == "darwin":
        arch = "arm64" if platform.machine() == "arm64" else "x86_64"
        return f"jobdork-{version}-macos-{arch}.dmg"
    if sys.platform == "win32":
        return f"jobdork-{version}-windows-x64-setup.exe"
    return ""


def check(cache_dir: str | Path, current: str = __version__, fetch=_fetch,
          now=time.time, enabled: bool = True, force: bool = False) -> dict:
    """What the page shows: {"newer": False} or the release to move to;
    with "failed" saying why when GitHub could not be asked, so the page
    does not call this copy the newest. `enabled` is the config's
    `update_check`; False asks nothing."""
    mine = parse(current)
    if mine is None or off() or not enabled:
        return {"newer": False, "current": current}
    release, why = _latest(cache_dir, fetch, now, force)
    if why:
        return {"newer": False, "current": current, "failed": why, "url": RELEASES_PAGE}
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


def _download(url: str, dest: Path, progress=None, opener=_open, on_bytes=None) -> None:
    if not url.startswith(DOWNLOAD_PREFIX):
        raise UpdateError("not one of this project's release downloads")
    request = urllib.request.Request(url, headers={
        "User-Agent": f"jobdork/{__version__} (update)"})
    part = dest.with_name(dest.name + ".part")
    done = 0
    with opener(request, timeout=60) as answer, open(part, "wb") as out:
        total = int(answer.headers.get("Content-Length") or 0)
        while True:
            chunk = answer.read(1024 * 1024)
            if not chunk:
                break
            done += len(chunk)
            if done > MAX_INSTALLER_BYTES:
                raise UpdateError("the download is far larger than an installer")
            out.write(chunk)
            if on_bytes:
                on_bytes(done, total)
            if progress and total:
                progress(f"downloaded {done * 100 // total}% "
                         f"({done / 1e6:.0f} of {total / 1e6:.0f} MB)")
    part.replace(dest)


def download_installer(folder: Path, progress=None, opener=_open,
                       fetch=_fetch, verify=None, step=None) -> Path:
    """Download this computer's installer from the latest release into
    `folder`, check it against the release's SHA256SUMS.txt and its build
    attestation, and return its path. Raises UpdateError; a file that fails
    either check is deleted, and nothing is opened.

    The release is asked for again, not read from the day-old cache: the
    files offered are the ones the release workflow uploaded now.

    `step(stage, **facts)` follows it for the page's update window: "asking",
    "downloading" (file, version), "bytes" (done, total), "checksum",
    "attestation". `progress` gets the same as lines for the activity log.
    """
    import hashlib

    def at(stage, **facts):
        if step:
            step(stage, **facts)

    at("asking")
    try:
        release = _release_from(fetch(LATEST_URL)) or {}
    except Exception as exc:                # offline, rate-limited, GitHub down
        raise UpdateError(f"could not ask GitHub for the release ({why_not(exc)}); "
                          "try again, or download it from the release page") from None
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
    at("downloading", file=name, version=str(release["version"]))
    try:
        _download(assets[SUMS_FILE], sums, opener=opener)
        # lambda: an adapter, the byte counts to the step the page follows.
        _download(assets[name], dest, progress=progress, opener=opener,
                  on_bytes=lambda done, total: at("bytes", done=done, total=total))
    except UpdateError:
        raise
    except Exception as exc:                 # the connection dropped part way
        sums.unlink(missing_ok=True)
        raise UpdateError(f"the download stopped ({why_not(exc)}); try again, "
                          "or download it from the release page") from None
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
        progress("checksum matches the release's SHA256SUMS.txt; checking who built it")
    at("checksum")
    try:
        verify_attestation(name, digest, str(release["version"]), fetch=fetch, verify=verify)
    except UpdateError:
        dest.unlink(missing_ok=True)
        raise
    if progress:
        progress("built by this project's release workflow, at its version tag")
    at("attestation")
    return dest


def verify_attestation(name: str, digest: str, version: str, fetch=_fetch,
                       verify=None) -> None:
    """Raise UpdateError unless GitHub holds an attestation, signed for this
    repository's desktop workflow at tag v`version`, that names `name` with
    this SHA-256. `verify` (bundle, identity) -> statement replaces the
    Sigstore check in tests."""
    try:
        answer = fetch(ATTEST_URL.format(digest=digest))
    except Exception as exc:                # offline, rate-limited: cannot vouch
        raise UpdateError("could not ask GitHub who built this installer "
                          f"({type(exc).__name__}), so it was deleted; try again, "
                          "or download it from the release page") from None
    bundles = [a.get("bundle") for a in (answer.get("attestations") or [])
               if isinstance(a, dict) and isinstance(a.get("bundle"), dict)]
    check = verify or signed_statement
    for bundle in bundles:
        try:
            statement = check(bundle, build_identity(version))
        except Exception:                   # a bundle that does not verify vouches for nothing
            continue
        if any(isinstance(s, dict) and s.get("name") == name
               and (s.get("digest") or {}).get("sha256") == digest
               for s in statement.get("subject") or []):
            return
    raise UpdateError("this installer could not be shown to come from this "
                      "project's release workflow, so it was deleted and not "
                      "opened; download it from the release page and report it")


def signed_statement(bundle: dict, identity: str, offline: bool = False) -> dict:
    """The in-toto statement in a Sigstore bundle, once its signature, its
    certificate (issued to `identity` by GitHub Actions) and its transparency
    log entry all check out. Raises otherwise.

    Sigstore's trust root is refreshed online; offline, or when that fails,
    the one bundled with the app is used. Both came with this signed copy.
    """
    from sigstore.models import Bundle
    from sigstore.verify import Verifier
    from sigstore.verify.policy import Identity

    parsed = Bundle.from_json(json.dumps(bundle))
    policy = Identity(identity=identity, issuer=OIDC_ISSUER)
    try:
        verifier = Verifier.production(offline=offline)
    except Exception:
        if offline:
            raise
        verifier = Verifier.production(offline=True)
    payload_type, payload = verifier.verify_dsse(parsed, policy)
    if payload_type != IN_TOTO:
        raise UpdateError(f"not an in-toto statement ({payload_type})")
    statement = json.loads(payload)
    if not isinstance(statement, dict):
        raise UpdateError("not an in-toto statement")
    return statement


def check_bundled_attestation() -> str:
    """For the app's self-test: verify, offline, the attestation of 0.14.4's
    macOS installer kept in the package. "" when it verifies, else why not."""
    from importlib import resources

    try:
        kept = json.loads(resources.files("jobdork").joinpath(
            "data/attestation-check.json").read_text(encoding="utf-8"))
        statement = signed_statement(kept["bundle"], build_identity(kept["version"]),
                                     offline=True)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    named = [(s.get("name"), (s.get("digest") or {}).get("sha256"))
             for s in statement.get("subject") or []]
    return "" if (kept["name"], kept["sha256"]) in named else "the statement names another file"
