"""
The Microsoft Store's copy (an MSIX package, packaging/build.py msix): its
manifest, its version, and what the app does differently in it
(core/store.py). No network; Windows' package calls are stood in for.

    python tests/test_store_package.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packaging"))

from jobdork.core import schedule, store, updates  # noqa: E402

BUILDS_HERE = sys.version_info >= (3, 11)          # build.py reads TOML with tomllib
NS = {"m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
      "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
      "uap3": "http://schemas.microsoft.com/appx/manifest/uap/windows10/3",
      "uap5": "http://schemas.microsoft.com/appx/manifest/uap/windows10/5",
      "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"}


def test_the_manifest_declares_what_the_app_needs():
    if not BUILDS_HERE:
        return
    import build
    identity = {"name": "123Me.jobdork", "publisher": "CN=ABC", "publisher_display_name": "Me & co"}
    m = ET.fromstring(build.appx_manifest("0.16.4", identity))
    ident = m.find("m:Identity", NS)
    assert ident.get("Name") == "123Me.jobdork" and ident.get("Publisher") == "CN=ABC"
    assert ident.get("Version") == "0.16.4.0" and ident.get("ProcessorArchitecture") == "x64"
    assert m.find("m:Properties/m:PublisherDisplayName", NS).text == "Me & co"
    app = m.find("m:Applications/m:Application", NS)
    assert app.get("Id") == store.APP_ENTRY == build.APPX_APP_ID
    assert app.get("EntryPoint") == "Windows.FullTrustApplication"
    protocol = app.find(".//uap3:Protocol", NS)                           # notification clicks
    assert protocol.get("Name") == "jobdork" and protocol.get("Parameters") == '"%1"'
    assert app.find(".//uap:Protocol", NS) is None, "makeappx refuses Parameters on uap:Protocol"
    assert app.find(".//uap5:ExecutionAlias", NS).get("Alias") == "jobdork.exe"
    assert m.find("m:Capabilities/rescap:Capability", NS).get("Name") == "runFullTrust"
    for logo in build.APPX_LOGOS:
        assert logo.endswith(".png")


def test_the_store_version_has_four_parts_ending_in_zero():
    if not BUILDS_HERE:
        return
    import build
    assert build.appx_version("0.16.4") == "0.16.4.0"
    assert build.appx_version("1.2") == "1.2.0.0"
    assert build.appx_version("2.0.1-rc1") == "2.0.1.0"


def test_without_an_identity_the_package_is_for_testing():
    if not BUILDS_HERE:
        return
    import build
    identity, real = build.store_identity()
    if not real:
        assert identity == build.TEST_IDENTITY


def test_outside_the_store_nothing_changes():
    assert (store.package_family() == "") or sys.platform == "win32"
    assert store.alias().endswith(str(Path("Microsoft") / "WindowsApps" / "jobdork.exe"))


def test_in_the_store_package_updates_toasts_and_schedules_follow_it():
    was = store.package_family
    # lambda: the answer Windows gives a program running in the Store's package.
    store.package_family = lambda: "123Me.jobdork_abc"
    frozen = getattr(sys, "frozen", None)
    try:
        assert store.packaged() and store.aumid() == "123Me.jobdork_abc!jobdork"
        found = updates.check(Path("."), current="0.16.4")
        assert found == {"newer": False, "current": "0.16.4", "store": True}
        sys.frozen = True
        assert schedule.program() == store.alias()
    finally:
        store.package_family = was
        if frozen is None:
            del sys.frozen
        else:
            sys.frozen = frozen


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
