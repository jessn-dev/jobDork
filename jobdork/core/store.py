"""
jobdork.core.store
==================
Whether this copy is the Microsoft Store's: the same program, installed as
an MSIX package (packaging/build.py, msix), which Windows gives an identity
of its own. Three things then work differently:

- **Updates** come from the Store, so jobdork does not ask GitHub or offer
  its own (core/updates.py).
- **Notifications** are shown under the package's app id, not the
  installer's (core/notify.py).
- **The scheduled scan** starts the `jobdork` command the package declares
  (its execution alias), since the package's own folder is renamed by every
  update (core/schedule.py).
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

# The manifest's Application Id (packaging/build.py, APPX_APP_ID).
APP_ENTRY = "jobdork"
# What GetCurrentPackageFamilyName answers in a program that has no package.
_NO_PACKAGE = 15700


@functools.lru_cache(maxsize=1)
def package_family() -> str:
    """The package family name ("12345Name.jobdork_abc123") when this copy
    runs as the Store's package; "" otherwise, and on every other system."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        length = ctypes.c_uint32(0)
        if kernel.GetCurrentPackageFamilyName(ctypes.byref(length), None) == _NO_PACKAGE:
            return ""
        name = ctypes.create_unicode_buffer(length.value)
        if kernel.GetCurrentPackageFamilyName(ctypes.byref(length), name) != 0:
            return ""
        return name.value
    except (AttributeError, OSError):          # an older Windows: no packages
        return ""


def packaged() -> bool:
    return bool(package_family())


def aumid() -> str:
    """The app id Windows shows the package's notifications under, or ""."""
    family = package_family()
    return f"{family}!{APP_ENTRY}" if family else ""


def alias() -> str:
    """The `jobdork` command the package declares, as a path that stays the
    same through updates."""
    base = os.environ.get("LOCALAPPDATA", "").strip() or str(Path.home() / "AppData" / "Local")
    return str(Path(base) / "Microsoft" / "WindowsApps" / "jobdork.exe")
