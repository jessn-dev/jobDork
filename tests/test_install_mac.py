"""The Mac install command (packaging/install-mac.sh), run for real with
stand-ins for the network, the disk image and the Mac's own commands: nothing
is downloaded, nothing goes into /Applications, nothing is opened."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.core import updates  # noqa: E402

SCRIPT = ROOT / "packaging" / "install-mac.sh"
VERSION = "9.8.7"
DMG = f"jobdork-{VERSION}-macos-arm64.dmg"

# Each stand-in is a small shell script on PATH ahead of the real commands.
_STANDINS = {
    "uname": 'case "$1" in -s) echo Darwin;; -m) echo "${FAKE_ARCH:-arm64}";; esac',
    "sw_vers": "echo 15.4",
    # Serves the release answer and its files from $FAKE_NET, by URL.
    "curl": """out=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift;; -H|--proto) shift;; -*) ;; *) url="$1";; esac
  shift
done
echo "$url" >> "$FAKE_NET/asked"
src="$FAKE_NET/$(basename "$url")"
[ -f "$src" ] || exit 22
cp "$src" "$out\"""",
    # "Mounts" the image by copying the app it would hold.
    "hdiutil": """if [ "$1" = attach ]; then
  while [ $# -gt 0 ]; do [ "$1" = -mountpoint ] && mnt="$2"; shift; done
  cp -R "$FAKE_NET/jobdork.app" "$mnt/"
fi""",
    "pgrep": "exit 1",
    "osascript": "exit 0",
    "open": 'echo "$@" >> "$FAKE_NET/opened"',
}


def _release(net: Path, uploader: str = updates.CI_UPLOADER, body: bytes = b"disk image") -> None:
    intel = DMG.replace("arm64", "x86_64")
    for name in (DMG, intel):
        (net / name).write_bytes(body)
    digest = hashlib.sha256(b"disk image").hexdigest()
    (net / updates.SUMS_FILE).write_text(f"{digest}  {DMG}\n{digest}  {intel}\n")
    assets = [{"name": name, "uploader": {"login": uploader},
               "browser_download_url": f"https://github.test/dl/{name}"}
              for name in (DMG, intel, updates.SUMS_FILE)]
    (net / "latest").write_text(json.dumps({"tag_name": f"v{VERSION}", "assets": assets}))
    app = net / "jobdork.app" / "Contents" / "MacOS"
    app.mkdir(parents=True)
    (app / "jobdork").write_text(f"new {VERSION}")


def _run(tmp: Path, net: Path, apps: Path, arch: str = "arm64") -> subprocess.CompletedProcess:
    bin_ = tmp / "bin"
    bin_.mkdir(exist_ok=True)
    for name, body in _STANDINS.items():
        (bin_ / name).write_text("#!/bin/bash\n" + body + "\n")
        (bin_ / name).chmod(0o755)
    env = {"PATH": f"{bin_}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp),
           "FAKE_NET": str(net), "JOBDORK_INSTALL_DIR": str(apps), "TMPDIR": str(tmp),
           "FAKE_ARCH": arch}
    return subprocess.run(["/bin/bash", str(SCRIPT)], env=env, capture_output=True,
                          text=True, timeout=60)


def _mac_only() -> bool:
    return sys.platform == "darwin"


def test_the_script_is_valid_bash_and_names_what_the_updater_trusts():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    text = SCRIPT.read_text(encoding="utf-8")
    assert f'REPO="{updates.REPO}"' in text
    assert f'CI_UPLOADER="{updates.CI_UPLOADER}"' in text
    assert f'SUMS="{updates.SUMS_FILE}"' in text
    # The name the release gives the Mac installer, as the updater asks for it.
    assert 'dmg="jobdork-$version-macos-$arch.dmg"' in text
    assert "arm64) arch=arm64" in text and "x86_64) arch=x86_64" in text
    # It installs; it never raises privileges or changes how macOS checks apps.
    for never in ("sudo", "xattr", "spctl", "--no-quarantine"):
        assert never not in text, never


def test_installs_the_checked_app_in_place_of_the_old_one():
    if not _mac_only():
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        net, apps = tmp / "net", tmp / "Applications"
        net.mkdir()
        _release(net)
        old = apps / "jobdork.app" / "Contents" / "MacOS"
        old.mkdir(parents=True)
        (old / "jobdork").write_text("old")
        done = _run(tmp, net, apps)
        assert done.returncode == 0, done.stderr
        assert (apps / "jobdork.app/Contents/MacOS/jobdork").read_text() == f"new {VERSION}"
        assert f"jobdork {VERSION} is installed" in done.stdout
        assert (net / "opened").read_text().strip() == str(apps / "jobdork.app")
        asked = (net / "asked").read_text().split()
        assert asked[0] == f"https://api.github.com/repos/{updates.REPO}/releases/latest"


def test_an_intel_mac_gets_the_intel_app():
    if not _mac_only():
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        net, apps = tmp / "net", tmp / "Applications"
        net.mkdir()
        _release(net)
        done = _run(tmp, net, apps, arch="x86_64")
        assert done.returncode == 0, done.stderr
        asked = (net / "asked").read_text()
        assert DMG.replace("arm64", "x86_64") in asked and DMG not in asked


def test_a_download_that_does_not_match_its_checksum_is_not_installed():
    if not _mac_only():
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        net, apps = tmp / "net", tmp / "Applications"
        net.mkdir()
        _release(net, body=b"something else")
        old = apps / "jobdork.app"
        old.mkdir(parents=True)
        done = _run(tmp, net, apps)
        assert done.returncode == 1
        assert "does not match SHA256SUMS.txt" in done.stderr
        assert old.is_dir() and not any(old.iterdir())       # the old app left as it was
        assert not (net / "opened").exists()


def test_a_file_github_actions_did_not_upload_is_refused():
    if not _mac_only():
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        net, apps = tmp / "net", tmp / "Applications"
        net.mkdir()
        _release(net, uploader="someone-else")
        done = _run(tmp, net, apps)
        assert done.returncode == 1 and "not GitHub Actions" in done.stderr
        assert not (apps / "jobdork.app").exists()
        assert DMG not in (net / "asked").read_text()         # never downloaded


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
