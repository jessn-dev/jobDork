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
    """subprocess.run answering each call in turn; the waits recorded."""
    calls, waits = [], []
    answers = list(results)

    def run(cmd, **_):
        calls.append(cmd)
        code, err = answers.pop(0)
        return subprocess.CompletedProcess(cmd, code, "", err)

    build.subprocess.run, build._sleep = run, waits.append
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
