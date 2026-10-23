# PyInstaller spec for the desktop app. Run through packaging/build.py, which
# sets JOBDORK_VERSION and turns the result into a .dmg or a Windows installer.
#
# One folder, not one file: a one-file build unpacks itself to a temporary
# folder on every start, which is slow and is what antivirus tools flag.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = Path(SPECPATH).parent
VERSION = os.environ.get("JOBDORK_VERSION", "0.0.0")
ICON = str(ROOT / "packaging" / "icon.png")       # converted per platform (Pillow)

a = Analysis(
    [str(ROOT / "packaging" / "jobdork_app.py")],
    pathex=[str(ROOT)],
    # The dashboard page, the board list, the gazetteer, the humanizer rules;
    # and the package's metadata, which `jobdork.__version__` is read from.
    datas=collect_data_files("jobdork") + copy_metadata("jobdork"),
    # Imported only inside functions or behind a try, so named here: the
    # Claude provider and the PDF reader are extras a pip install may skip,
    # and an app user cannot add them afterwards.
    hiddenimports=["anthropic", "pypdf"],
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
