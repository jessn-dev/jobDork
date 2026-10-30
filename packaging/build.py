"""
Build the desktop app for the machine this runs on.

    pip install -e '.[pdf,ai,app,package]'
    python packaging/build.py

macOS: dist/jobdork.app, then dist/jobdork-<version>-macos-arm64.dmg, the app
beside a link to Applications so it installs by dragging.

Windows: dist/jobdork/, then dist/jobdork-<version>-windows-x64-setup.exe from
packaging/jobdork.iss. Needs Inno Setup 6 (`iscc` on PATH, or where its
installer puts it).

Before either, the built app checks itself (`--self-test`): a build missing
a module or a data file fails here rather than on a user's machine.

Neither is signed yet (docs/DECISIONS.md, 2026-10-21). CI builds both:
.github/workflows/desktop.yml.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
WORK = ROOT / "build"
INNO = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")


def version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def run(*cmd: str | Path) -> None:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


# GitHub's macOS machines now and then answer "hdiutil: create failed -
# Resource busy" (#71 and #77, 2026-10-28): the folder or the new image is
# held a moment by Spotlight or the malware scan. The same command a little
# later works, so it is tried again; anything else fails at once.
BUSY = "Resource busy"
BUSY_WAITS = (5, 15, 30)            # seconds before the second, third and fourth try
_sleep = time.sleep


def run_retrying_busy(*cmd: str | Path) -> None:
    """`run`, asked again after a pause when macOS says the disk is busy."""
    for wait in (*BUSY_WAITS, None):
        print("$", " ".join(str(c) for c in cmd), flush=True)
        done = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True)
        sys.stdout.write(done.stdout)
        sys.stderr.write(done.stderr)
        if done.returncode == 0:
            return
        if wait is None or BUSY not in done.stdout + done.stderr:
            raise subprocess.CalledProcessError(done.returncode, done.args,
                                                done.stdout, done.stderr)
        print(f"{BUSY}: trying again in {wait}s", flush=True)
        _sleep(wait)


def pyinstaller(ver: str) -> None:
    os.environ["JOBDORK_VERSION"] = ver
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", WORK, PACKAGING / "jobdork.spec")


def built_app() -> Path:
    """The executable PyInstaller made, inside the .app on macOS."""
    if sys.platform == "darwin":
        return DIST / "jobdork.app" / "Contents" / "MacOS" / "jobdork"
    return DIST / "jobdork" / ("jobdork.exe" if sys.platform == "win32" else "jobdork")


def agent_app() -> Path:
    """What a coding agent starts: on Windows the console program beside the
    app (jobdork.spec), elsewhere the app itself."""
    if sys.platform == "win32":
        return DIST / "jobdork" / "jobdork-agent.exe"
    return built_app()


def self_test() -> None:
    """Run the built app's own check; stop the build if anything is missing."""
    report = WORK / "self-test.txt"
    report.unlink(missing_ok=True)
    print("$", built_app(), "--self-test", report, flush=True)
    code = subprocess.run([str(built_app()), "--self-test", str(report)],
                          cwd=ROOT, timeout=120).returncode
    found = report.read_text(encoding="utf-8").strip() if report.is_file() else ""
    if code or found != "ok":
        raise SystemExit(f"the built app failed its self-test (exit {code}):\n"
                         f"{found or 'it wrote no report'}")
    print("self-test: ok", flush=True)
    mcp_test()


def mcp_test() -> None:
    """The built app answers a coding agent over stdio (`--mcp`): a Windows
    build has no console, and this is where that would show. In a folder of
    its own, so it reads no one's data."""
    import json
    import tempfile

    hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "build", "version": "1"}}}
    with tempfile.TemporaryDirectory() as home:
        done = subprocess.run([str(agent_app()), "--mcp"], input=json.dumps(hello) + "\n",
                              capture_output=True, text=True, timeout=120,
                              env={**os.environ, "JOBDORK_HOME": home})
    try:
        answer = json.loads(done.stdout.splitlines()[0])
    except (IndexError, json.JSONDecodeError):
        raise SystemExit(f"the built app did not answer as an MCP server (exit "
                         f"{done.returncode}): {done.stdout[:300]!r} {done.stderr[-500:]}") from None
    if answer.get("result", {}).get("serverInfo", {}).get("name") != "jobdork":
        raise SystemExit(f"the built app answered MCP wrongly: {answer}")
    print("mcp: ok", flush=True)


def dmg(ver: str) -> Path:
    """The app and a link to Applications, in a compressed disk image."""
    stage = WORK / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    # symlinks=True: the app's frameworks are full of them, and copying
    # through them doubles the size and breaks the code signature.
    shutil.copytree(DIST / "jobdork.app", stage / "jobdork.app", symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    arch = "arm64" if platform.machine() == "arm64" else "x86_64"
    out = DIST / f"jobdork-{ver}-macos-{arch}.dmg"
    out.unlink(missing_ok=True)
    if _diskutil_image():
        # macOS 27 warns that `hdiutil create -volname -format` is deprecated
        # for this. The image is APFS (it takes no filesystem), which every
        # macOS the app runs on (12 and later) reads.
        run_retrying_busy("diskutil", "image", "create", "from", "--format", "UDZO",
                          "--volumeName", "jobdork", stage, out)
    else:
        run_retrying_busy("hdiutil", "create", "-volname", "jobdork", "-srcfolder", stage,
                          "-fs", "HFS+", "-format", "UDZO", "-ov", out)
    return out


def _diskutil_image() -> bool:
    """`diskutil image create from` is there and names the volume (macOS 27).

    Asked by its help, not by whether it runs: CI's macOS 15 has the command
    but no `--volumeName`, and refused it (exit 64); there `hdiutil` is used,
    and does not warn.
    """
    help_ = subprocess.run(["diskutil", "image", "create", "from", "--help"],
                           capture_output=True, text=True)
    return help_.returncode == 0 and "--volumeName" in help_.stdout + help_.stderr


def windows_installer(ver: str) -> Path:
    """An installer for one user (no administrator needed), from jobdork.iss."""
    from PIL import Image

    icon = WORK / "jobdork.ico"
    icon.parent.mkdir(parents=True, exist_ok=True)
    Image.open(PACKAGING / "icon.png").save(
        icon, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                     (256, 256)])
    iscc = shutil.which("iscc") or (str(INNO) if INNO.is_file() else "")
    if not iscc:
        raise SystemExit("Inno Setup 6 is not installed: https://jrsoftware.org/isdl.php")
    run(iscc, f"/DVersion={ver}", f"/DSource={DIST / 'jobdork'}",
        f"/DIcon={icon}", f"/DOutput={DIST}", PACKAGING / "jobdork.iss")
    return DIST / f"jobdork-{ver}-windows-x64-setup.exe"


def main() -> int:
    ver = version()
    pyinstaller(ver)
    self_test()
    if sys.platform == "darwin":
        out = dmg(ver)
    elif sys.platform == "win32":
        out = windows_installer(ver)
    else:
        print("Linux is not packaged yet; the build is in dist/jobdork/.")
        return 0
    print(f"built {out} ({out.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
