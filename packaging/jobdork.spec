# PyInstaller spec for the desktop app. Run through packaging/build.py, which
# sets JOBDORK_VERSION and turns the result into a .dmg or a Windows installer.
#
# One folder, not one file: a one-file build unpacks itself to a temporary
# folder on every start, which is slow and is what antivirus tools flag.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
VERSION = os.environ.get("JOBDORK_VERSION", "0.0.0")
ICON = str(ROOT / "packaging" / "icon.png")       # converted per platform (Pillow)

a = Analysis(
    [str(ROOT / "packaging" / "jobdork_app.py")],
    pathex=[str(ROOT)],
    # The dashboard page, the board list, the gazetteer, the humanizer rules;
    # the package's metadata, which `jobdork.__version__` is read from; and
    # the GPL's text, which must travel with every built copy. CI installs
    # editable, whose metadata does not carry LICENSE itself.
    datas=collect_data_files("jobdork") + copy_metadata("jobdork")
    + [(str(ROOT / "LICENSE"), ".")]
    # Sigstore's trust roots (sigstore/_store/*.json), which an update's
    # build attestation is verified against when the network cannot refresh
    # them; the self-test verifies one offline to prove they came along.
    + collect_data_files("sigstore") + copy_metadata("sigstore")
    # keyring finds the keychain it talks to (macOS Keychain, Windows
    # Credential Manager) through its package metadata's entry points.
    + copy_metadata("keyring"),
    # Imported only inside functions or behind a try, so named here: the
    # Claude provider and the PDF reader are extras a pip install may skip,
    # and an app user cannot add them afterwards. The command line runs the
    # scan schedule's `--scan`, reached only from inside a function.
    hiddenimports=["anthropic", "pypdf", "jobdork.cli",
                   # Imported inside a function: an update's attestation check.
                   *collect_submodules("sigstore"),
                   # Keys you choose to keep (core/keystore.py): every backend,
                   # each loaded by name from its entry point.
                   *collect_submodules("keyring.backends"),
                   # Imported inside a function, for notifications on macOS.
                   *(["UserNotifications"] if sys.platform == "darwin" else [])],
    # The dork generator is a terminal tool; the app never runs it.
    excludes=["tkinter", "jobdork.dork"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="jobdork",
    console=False,                   # a window, no terminal behind it
    icon=ICON,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="jobdork", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="jobdork.app",
        icon=ICON,
        bundle_identifier="io.github.jessn-dev.jobdork",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "jobdork",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
