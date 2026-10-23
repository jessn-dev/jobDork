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


def pyinstaller(ver: str) -> None:
    os.environ["JOBDORK_VERSION"] = ver
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", WORK, PACKAGING / "jobdork.spec")


def built_app() -> Path:
    """The executable PyInstaller made, inside the .app on macOS."""
    if sys.platform == "darwin":
        return DIST / "jobdork.app" / "Contents" / "MacOS" / "jobdork"
    return DIST / "jobdork" / ("jobdork.exe" if sys.platform == "win32" else "jobdork")


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
    run("hdiutil", "create", "-volname", "jobdork", "-srcfolder", stage,
        "-fs", "HFS+", "-format", "UDZO", "-ov", out)
    return out


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
