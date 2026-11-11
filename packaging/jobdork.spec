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
LINUX = sys.platform.startswith("linux")


def linux_libraries():
    """System libraries the Linux build carries: libxcb-cursor, which Qt 6.5
    and later needs to draw on X11 and many desktops do not install. The
    build machine's copy goes beside the app's own, which the program finds
    first. The .deb asks for the system's too (packaging/build.py)."""
    import ctypes.util
    import glob

    name = ctypes.util.find_library("xcb-cursor")
    found = sorted(glob.glob(f"/usr/lib/*/{name}*")) if name else []
    if not found:
        raise SystemExit("libxcb-cursor is not installed on the build machine "
                         "(apt install libxcb-cursor0)")
    return [(found[0], ".")]


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
    + copy_metadata("keyring")
    # Windows has no time zone database, nor a bare Linux: the tzdata package's travels with
    # the app (ai/limits.py), checked by the self-test.
    + (collect_data_files("tzdata") if sys.platform == "win32" or LINUX else []),
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
                   *(collect_submodules("tzdata") if sys.platform == "win32" or LINUX else []),
                   # Imported inside a function, for notifications on macOS.
                   *(["UserNotifications"] if sys.platform == "darwin" else []),
                   # The Linux window: pywebview loads its Qt engine by name.
                   *(["webview.platforms.qt", "qtpy", "PyQt6.QtWebEngineWidgets",
                      "PyQt6.QtWebEngineCore", "PyQt6.QtWebChannel", "PyQt6.QtNetwork"]
                     if LINUX else [])],
    binaries=linux_libraries() if LINUX else [],
    # The dork generator is a terminal tool; the app never runs it.
    excludes=["tkinter", "jobdork.dork"],
    noarchive=False,
)
# The Linux build carries Qt, and PyInstaller takes every part of it a part it
# found might load: QML modules, 3D, multimedia, speech, SQL drivers, sensors.
# The window is a widget with a web page in it and uses none of them, so they
# are left out (about a third of the build). Qt's web engine, its widgets and
# what they load stay; the self-test imports them and desktop.yml opens the
# window, so a part cut that was needed fails the build, not someone's start.
if LINUX:
    import re

    UNUSED_QT = re.compile(
        r"PyQt6/Qt6/(qml/"
        r"|lib/libQt6(Quick3D|Multimedia|SpatialAudio|TextToSpeech|Charts|DataVisualization"
        r"|Graphs|Sensors|Bluetooth|Nfc|SerialPort|SerialBus|Location|RemoteObjects|Scxml"
        r"|StateMachine|Designer|Help|Sql|VirtualKeyboard|3D|QuickControls2|QuickDialogs2"
        r"|QuickTemplates2|QuickParticles|QuickTimeline|QuickEffects|QuickVectorImage"
        r"|LabsAnimation|Lottie|ShaderTools)"
        r"|plugins/(multimedia|sqldrivers|sensors|position|geoservices|texttospeech|canbus"
        r"|designer|qmltooling|renderers|sceneparsers|assetimporters|geometryloaders"
        r"|renderplugins|qmllint)/"
        # The GTK theme and CUPS printing: each pulls the build machine's
        # GTK or CUPS in after it (packaging/build.py, SYSTEM_LIBRARIES), Qt draws
        # its own look without the first, and jobdork prints through neither.
        r"|plugins/platformthemes/libqgtk3\.so|plugins/printsupport/libcupsprintersupport\.so)")
    # The system's own libraries PyInstaller also took are removed after the
    # build instead (packaging/build.py, prune_linux).
    a.binaries = [x for x in a.binaries if not UNUSED_QT.search(x[0].replace("\\", "/"))]
    a.datas = [x for x in a.datas if not UNUSED_QT.search(x[0].replace("\\", "/"))]

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

# Windows only: the same program with a console, for a coding agent to start
# (`jobdork-agent.exe --mcp`, web/mcp.py). A program built without one gets
# no standard input or output, and an MCP server is nothing else; the window
# keeps jobdork.exe. A Mac app has its streams either way.
agent = (EXE(pyz, a.scripts, [], exclude_binaries=True, name="jobdork-agent",
             console=True, icon=ICON, upx=False),) if sys.platform == "win32" else ()

coll = COLLECT(exe, *agent, a.binaries, a.datas, name="jobdork", upx=False)

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
            # Notifications as Alerts, which stay until closed, rather than
            # banners, which go in seconds (asked 2026-11-11). The default
            # only: System Settings, Notifications, jobdork can change it.
            "NSUserNotificationAlertStyle": "alert",
        },
    )
