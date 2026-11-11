"""
The desktop build script's one retry (packaging/build.py): macOS's disk image
tools, refused with "Resource busy" on GitHub's machines, are asked again;
any other failure stops the build at once. Nothing here runs a real command.

    python tests/test_build.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# The build script reads pyproject.toml with tomllib (3.11 and later); the
# desktop build runs on 3.14, the tests also on 3.10, where these are skipped.
BUILDS_HERE = sys.version_info >= (3, 11)


def _build():
    spec = importlib.util.spec_from_file_location("build_script", ROOT / "packaging" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _answers(build, *results):
    """The script's commands answered in turn, its waits recorded. Only the
    script's own view of `subprocess` is replaced: patching the module itself
    reached every later test that runs a real command."""
    calls, waits = [], []
    answers = list(results)

    def run(cmd, **_):
        calls.append(cmd)
        code, err = answers.pop(0)
        return subprocess.CompletedProcess(cmd, code, "", err)

    build.subprocess = type("Subprocess", (), {
        "run": staticmethod(run), "CalledProcessError": subprocess.CalledProcessError})
    build._sleep = waits.append
    return calls, waits


def test_a_busy_disk_is_asked_again_and_the_image_is_made():
    if not BUILDS_HERE:
        return
    build = _build()
    calls, waits = _answers(build, (1, "hdiutil: create failed - Resource busy\n"),
                            (1, "hdiutil: create failed - Resource busy\n"), (0, ""))
    build.run_retrying_busy("hdiutil", "create", "out.dmg")
    assert len(calls) == 3 and waits == list(build.BUSY_WAITS[:2])


def test_another_failure_stops_the_build_without_waiting():
    if not BUILDS_HERE:
        return
    build = _build()
    calls, waits = _answers(build, (64, "diskutil: unrecognized option --volumeName\n"))
    try:
        build.run_retrying_busy("diskutil", "image", "create")
    except subprocess.CalledProcessError as exc:
        assert exc.returncode == 64
    else:
        raise AssertionError("a failure that is not 'busy' must stop the build")
    assert len(calls) == 1 and waits == []


def test_still_busy_after_every_try_stops_the_build():
    if not BUILDS_HERE:
        return
    build = _build()
    busy = (1, "hdiutil: create failed - Resource busy\n")
    calls, waits = _answers(build, *[busy] * (len(build.BUSY_WAITS) + 1))
    try:
        build.run_retrying_busy("hdiutil", "create", "out.dmg")
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("busy on every try must still fail")
    assert len(calls) == len(build.BUSY_WAITS) + 1 and waits == list(build.BUSY_WAITS)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"\n{len(tests)}/{len(tests)} passed")


def test_the_linux_packages_say_what_they_are_and_what_they_need():
    if not BUILDS_HERE:
        return
    build = _build()
    entry = build.desktop_entry("/opt/jobdork/jobdork")
    assert entry.startswith("[Desktop Entry]\n") and "Exec=/opt/jobdork/jobdork\n" in entry
    assert "Icon=jobdork\n" in entry and "Terminal=false\n" in entry
    control = build.deb_control("1.2.3", 400000)
    fields = dict(line.split(": ", 1) for line in control.splitlines() if not line.startswith(" "))
    assert fields["Package"] == "jobdork" and fields["Version"] == "1.2.3"
    assert fields["Architecture"] == "amd64" and fields["Installed-Size"] == "400000"
    # Every dependency a plain package name, a version bound, or alternatives
    # (Ubuntu 24.04 renamed some); desktop.yml installs the first of each.
    for dep in fields["Depends"].split(", "):
        for alt in dep.split(" | "):
            name = alt.split(" (")[0]
            assert name and name == name.strip() and " " not in name, dep
    assert "libxcb-cursor0" in fields["Depends"] and "libnss3" in fields["Depends"]
    assert fields["Depends"].startswith("libc6 (>= 2.35)")
    # ARM64 (from 0.16.4): its own architecture and the glibc its Qt needs.
    arm = dict(line.split(": ", 1) for line in build.deb_control("1.2.3", 1, "arm64").splitlines()
               if not line.startswith(" "))
    assert arm["Architecture"] == "arm64" and arm["Depends"].startswith("libc6 (>= 2.39)")
    # What the ARM wheels load from the system that the x86 ones carry.
    assert "libopus0" in arm["Depends"] and "libsm6" in arm["Depends"]
    assert "libopus0" not in fields["Depends"]
    assert build.linux_arch("aarch64")[:2] == ("aarch64", "arm64")
    assert build.linux_arch("x86_64")[:2] == ("x86_64", "amd64")
    assert "libasound2t64" in build.build_packages(t64=True)
    assert "libasound2" in build.build_packages(t64=False)
    assert build.APPRUN.startswith("#!/bin/sh") and "usr/lib/jobdork/jobdork" in build.APPRUN
    # What software centres show: icon and screenshots (2026-11-11: a generic
    # gear and "No Screenshots" without it).
    import xml.etree.ElementTree as ET
    meta = ET.fromstring(build.metainfo("1.2.3", "2026-11-11"))
    assert meta.get("type") == "desktop-application" and meta.findtext("id") == build.APP_ID
    assert meta.find("launchable").text == "jobdork.desktop"
    assert {i.get("type") for i in meta.findall("icon")} == {"stock", "remote"}
    shots = [s.find("image").text for s in meta.find("screenshots")]
    assert len(shots) == len(build.SCREENSHOTS) and all("/v1.2.3/guide/docs/images/" in s for s in shots)
    for name, _ in build.SCREENSHOTS:
        assert (ROOT / "guide" / "docs" / "images" / f"{name}.png").is_file(), name
    assert meta.find("releases/release").get("version") == "1.2.3"
    # Ubuntu 24.04's real ALSA first: its "libasound2" is also a stand-in's.
    assert "libasound2t64 | libasound2" in fields["Depends"]
    # The x86-64 build machine's names (Ubuntu 22.04); named, since the
    # machine running this test may be 24.04.
    pkgs = build.build_packages(t64=False)
    assert "libasound2" in pkgs and "libglib2.0-0" in pkgs and not any(p.endswith("t64") for p in pkgs)


def test_the_linux_build_leaves_the_systems_own_libraries_to_the_system():
    if not BUILDS_HERE:
        return
    import tempfile

    build = _build()
    with tempfile.TemporaryDirectory() as tmp:
        internal = Path(tmp) / "jobdork" / "_internal"
        (internal / "nss").mkdir(parents=True)
        (internal / "nss" / "libsoftokn3.so").write_text("x")
        (internal / "PyQt6" / "Qt6" / "lib").mkdir(parents=True)
        for name in ("libX11.so.6", "libxcb-glx.so.0", "libglib-2.0.so.0", "libstdc++.so.6",
                     "libnss3.so", "libfreeblpriv3.chk", "libpython3.13.so.1.0", "libssl.so.3",
                     "libxcb-cursor.so.0", "libxcb-9065bb12.so.1.1.0", "libicudata.so.73",
                     # GitHub's runner has GTK and CUPS, which two Qt plugins pulled in
                     "libgtk-3.so.0", "libpangocairo-1.0.so.0", "libcairo.so.2", "libcups.so.2",
                     "libgnutls.so.30", "libharfbuzz-fb49c9fc.so.0.61450.0"):
            (internal / name).write_text("x")
        (internal / "PyQt6" / "Qt6" / "lib" / "libQt6Core.so.6").write_text("x")
        (internal / "libQt6Core.so.6").symlink_to("PyQt6/Qt6/lib/libQt6Core.so.6")
        (internal / "libQt6Quick3D.so.6").symlink_to("PyQt6/Qt6/lib/libQt6Quick3D.so.6")
        gone = build.prune_linux(internal.parent)
        left = sorted(p.name for p in internal.iterdir())
        assert left == ["PyQt6", "libQt6Core.so.6", "libharfbuzz-fb49c9fc.so.0.61450.0",
                        "libicudata.so.73", "libpython3.13.so.1.0", "libssl.so.3",
                        "libxcb-9065bb12.so.1.1.0", "libxcb-cursor.so.0"], left
        assert "nss" in gone and "libQt6Quick3D.so.6" in gone, "NSS, and links to nothing"

