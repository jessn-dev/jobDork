#!/usr/bin/env python3
"""
guide_screenshots.py
====================
Refreshes the user guide's pictures (guide/docs/images/*.png) from the real
dashboard, run on a made-up person's data.

    python scripts/guide_screenshots.py

Builds the demo (scripts/guide_demo.py) in a temporary folder, starts
`jobdork serve` on it, and has scripts/guide_shots.mjs photograph every page
in headless Chrome. A second dashboard, on an empty folder, gives the first
page of setup. Needs Chrome and Node; touches nothing of yours: no config,
database or resume outside the temporary folder, no network, notifications
and the version check off.

Run it after any change to what a page shows, and commit the pictures with
the change, so the guide shows the app as it is (guide/README.md).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "guide" / "docs" / "images"
TOKEN = "guide-screenshots"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(folder: Path, port: int, config: Path | None) -> subprocess.Popen:
    env = {**os.environ,
           "JOBDORK_FEEDBACK_URL": "https://feedback.invalid/", "JOBDORK_HOME": str(folder)}
    # Settings in the demo shows both as people see them: its version check
    # is already answered (guide_demo.py), so nothing asks GitHub, and the
    # pictures start no scan, so nothing notifies. The empty folder has no
    # answered check, so both are switched off there.
    if config is None:
        env |= {"JOBDORK_NOTIFY": "off", "JOBDORK_UPDATE_CHECK": "off"}
    cmd = [sys.executable, "-m", "jobdork", *(["-c", str(config)] if config else []),
           "serve", "--port", str(port), "--no-open", "--token", TOKEN]
    proc = subprocess.Popen(cmd, cwd=folder, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return proc
        except OSError:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit(f"the dashboard did not start on port {port}")


def main() -> int:
    if not shutil.which("node"):
        raise SystemExit("needs Node (https://nodejs.org) to drive Chrome")
    sys.path.insert(0, str(ROOT / "scripts"))
    import guide_demo

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jobdork-guide-") as tmp:
        demo, empty = Path(tmp) / "demo", Path(tmp) / "new"
        empty.mkdir()
        config = guide_demo.build(demo)
        port, setup_port = _free_port(), _free_port()
        servers = [_serve(demo, port, config), _serve(empty, setup_port, None)]
        try:
            code = subprocess.call(
                ["node", str(ROOT / "scripts" / "guide_shots.mjs"),
                 f"http://127.0.0.1:{port}/?t={TOKEN}", str(OUT),
                 f"http://127.0.0.1:{setup_port}/?t={TOKEN}"])
        finally:
            for server in servers:
                server.terminate()
                server.wait(timeout=10)
    print(f"pictures in {OUT.relative_to(ROOT)}" if code == 0 else "failed")
    return code


if __name__ == "__main__":
    sys.exit(main())
