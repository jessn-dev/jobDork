#!/usr/bin/env python3
"""
Runs every tests/test_*.py, with no dependency on pytest.

Discovering the files rather than naming them is the point: naming one file
means a new test file runs nowhere until somebody remembers to add it, and the
suite reports a confident pass over tests it never executed.

`BaseException` rather than `Exception` on purpose — a test that raises
SystemExit would otherwise end the run mid-file with no failure line and no
summary.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    import importlib.util

    total = failures = 0
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        tests = [(name, fn) for name, fn in sorted(vars(module).items())
                 if name.startswith("test_") and callable(fn)]
        for name, fn in tests:
            total += 1
            try:
                fn()
            except BaseException:
                failures += 1
                print(f"FAIL {path.name}::{name}")
                traceback.print_exc(limit=3)

    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
