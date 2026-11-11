"""
Build the desktop app for the machine this runs on.

    pip install -e '.[pdf,ai,app,package]'
    python packaging/build.py

macOS: dist/jobdork.app, then dist/jobdork-<version>-macos-arm64.dmg, the app
beside a link to Applications so it installs by dragging.

Windows: dist/jobdork/, then dist/jobdork-<version>-windows-x64-setup.exe from
packaging/jobdork.iss. Needs Inno Setup 6 (`iscc` on PATH, or where its
installer puts it).

Linux (x86-64): dist/jobdork/, then dist/jobdork-<version>-linux-x86_64.AppImage
and dist/jobdork_<version>_amd64.deb, the same build in each. The AppImage
needs appimagetool and the AppImage runtime it puts in front, both given as
files (APPIMAGETOOL, APPIMAGE_RUNTIME; desktop.yml fetches pinned ones), so
nothing is downloaded while building; the .deb needs dpkg-deb.

Before either, the built app checks itself (`--self-test`): a build missing
a module or a data file fails here rather than on a user's machine.

None is signed yet (docs/DECISIONS.md, 2026-10-21). CI builds them all:
.github/workflows/desktop.yml.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
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


# GitHub's macOS machines now and then answer "hdiutil: create failed -
# Resource busy" (#71 and #77, 2026-10-28): the folder or the new image is
# held a moment by Spotlight or the malware scan. The same command a little
# later works, so it is tried again; anything else fails at once.
BUSY = "Resource busy"
BUSY_WAITS = (5, 15, 30)            # seconds before the second, third and fourth try
_sleep = time.sleep


def run_retrying_busy(*cmd: str | Path) -> None:
    """`run`, asked again after a pause when macOS says the disk is busy."""
    for wait in (*BUSY_WAITS, None):
        print("$", " ".join(str(c) for c in cmd), flush=True)
        done = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True)
        sys.stdout.write(done.stdout)
        sys.stderr.write(done.stderr)
        if done.returncode == 0:
            return
        if wait is None or BUSY not in done.stdout + done.stderr:
            raise subprocess.CalledProcessError(done.returncode, done.args,
                                                done.stdout, done.stderr)
        print(f"{BUSY}: trying again in {wait}s", flush=True)
        _sleep(wait)


def pyinstaller(ver: str) -> None:
    os.environ["JOBDORK_VERSION"] = ver
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", WORK, PACKAGING / "jobdork.spec")


def built_app() -> Path:
    """The executable PyInstaller made, inside the .app on macOS."""
    if sys.platform == "darwin":
        return DIST / "jobdork.app" / "Contents" / "MacOS" / "jobdork"
    return DIST / "jobdork" / ("jobdork.exe" if sys.platform == "win32" else "jobdork")


def agent_app() -> Path:
    """What a coding agent starts: on Windows the console program beside the
    app (jobdork.spec), elsewhere the app itself."""
    if sys.platform == "win32":
        return DIST / "jobdork" / "jobdork-agent.exe"
    return built_app()


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
    mcp_test()


def mcp_test() -> None:
    """The built app answers a coding agent over stdio (`--mcp`): a Windows
    build has no console, and this is where that would show. In a folder of
    its own, so it reads no one's data."""
    import json
    import tempfile

    hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "build", "version": "1"}}}
    with tempfile.TemporaryDirectory() as home:
        done = subprocess.run([str(agent_app()), "--mcp"], input=json.dumps(hello) + "\n",
                              capture_output=True, text=True, timeout=120,
                              env={**os.environ, "JOBDORK_HOME": home})
    try:
        answer = json.loads(done.stdout.splitlines()[0])
    except (IndexError, json.JSONDecodeError):
        raise SystemExit(f"the built app did not answer as an MCP server (exit "
                         f"{done.returncode}): {done.stdout[:300]!r} {done.stderr[-500:]}") from None
    if answer.get("result", {}).get("serverInfo", {}).get("name") != "jobdork":
        raise SystemExit(f"the built app answered MCP wrongly: {answer}")
    print("mcp: ok", flush=True)


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
    if _diskutil_image():
        # macOS 27 warns that `hdiutil create -volname -format` is deprecated
        # for this. The image is APFS (it takes no filesystem), which every
        # macOS the app runs on (12 and later) reads.
        run_retrying_busy("diskutil", "image", "create", "from", "--format", "UDZO",
                          "--volumeName", "jobdork", stage, out)
    else:
        run_retrying_busy("hdiutil", "create", "-volname", "jobdork", "-srcfolder", stage,
                          "-fs", "HFS+", "-format", "UDZO", "-ov", out)
    return out


def _diskutil_image() -> bool:
    """`diskutil image create from` is there and names the volume (macOS 27).

    Asked by its help, not by whether it runs: CI's macOS 15 has the command
    but no `--volumeName`, and refused it (exit 64); there `hdiutil` is used,
    and does not warn.
    """
    help_ = subprocess.run(["diskutil", "image", "create", "from", "--help"],
                           capture_output=True, text=True)
    return help_.returncode == 0 and "--volumeName" in help_.stdout + help_.stderr


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


# ── Microsoft Store ───────────────────────────────────────────────────────────
# The same build as an MSIX package for the Store, which signs it when it
# publishes it: no code-signing certificate of jobdork's own is needed, as
# one is for the installer above (docs/DECISIONS.md). The identity comes
# from Partner Center (packaging/store.toml); without one, a stand-in that
# only CI installs. core/store.py is what the app does differently in it.

APPX_APP_ID = "jobdork"                 # core/store.py, APP_ENTRY
TEST_IDENTITY = {"name": "jobdork.test", "publisher": "CN=jobdork test",
                 "publisher_display_name": "jobdork"}
# Logos the manifest names, by their pixel size.
APPX_LOGOS = {"StoreLogo.png": 50, "Square44x44Logo.png": 44, "Square150x150Logo.png": 150,
              "Square44x44Logo.targetsize-256_altform-unplated.png": 256}


def store_identity() -> tuple[dict, bool]:
    """(identity, real): packaging/store.toml's, or TEST_IDENTITY when it
    is not filled in."""
    with open(PACKAGING / "store.toml", "rb") as fh:
        given = tomllib.load(fh)
    real = all(str(given.get(k) or "").strip() for k in TEST_IDENTITY)
    return ({k: str(given[k]).strip() for k in TEST_IDENTITY} if real else dict(TEST_IDENTITY),
            real)


def appx_version(ver: str) -> str:
    """The Store's four-part version; its last part must be 0."""
    parts = [*ver.split("+")[0].split("-")[0].split("."), "0", "0", "0"][:3]
    return ".".join(str(int(p)) for p in parts) + ".0"


def appx_manifest(ver: str, identity: dict) -> str:
    def esc(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap5="http://schemas.microsoft.com/appx/manifest/uap/windows10/5"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap5 rescap">
  <Identity Name="{esc(identity['name'])}" Publisher="{esc(identity['publisher'])}"
    Version="{appx_version(ver)}" ProcessorArchitecture="x64"/>
  <Properties>
    <DisplayName>jobdork</DisplayName>
    <PublisherDisplayName>{esc(identity['publisher_display_name'])}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0"/>
  </Dependencies>
  <Resources><Resource Language="en-us"/></Resources>
  <Applications>
    <Application Id="{APPX_APP_ID}" Executable="jobdork\\jobdork.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="jobdork" Description="{esc(SUMMARY)}"
        BackgroundColor="transparent" Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png"/>
      <Extensions>
        <uap:Extension Category="windows.protocol">
          <uap:Protocol Name="jobdork" Parameters="&quot;%1&quot;">
            <uap:DisplayName>jobdork</uap:DisplayName>
          </uap:Protocol>
        </uap:Extension>
        <uap5:Extension Category="windows.appExecutionAlias" Executable="jobdork\\jobdork.exe"
          EntryPoint="Windows.FullTrustApplication">
          <uap5:AppExecutionAlias><uap5:ExecutionAlias Alias="jobdork.exe"/></uap5:AppExecutionAlias>
        </uap5:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <Capability Name="internetClient"/>
    <rescap:Capability Name="runFullTrust"/>
  </Capabilities>
</Package>
"""


def _makeappx() -> str:
    """The Windows SDK's makeappx.exe, newest first."""
    found = shutil.which("makeappx")
    if found:
        return found
    kits = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin"
    tools = sorted(kits.glob("10.*/x64/makeappx.exe"), reverse=True)
    if not tools:
        raise SystemExit("the Windows SDK's makeappx.exe was not found")
    return str(tools[0])


def msix(ver: str) -> Path:
    """The build as an MSIX package, unsigned: the Store signs what it publishes."""
    from PIL import Image

    identity, real = store_identity()
    root = WORK / "msix"
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(DIST / "jobdork", root / "jobdork")
    (root / "Assets").mkdir(parents=True)
    for name, size in APPX_LOGOS.items():
        Image.open(PACKAGING / "icon.png").resize((size, size)).save(root / "Assets" / name)
    (root / "AppxManifest.xml").write_text(appx_manifest(ver, identity), encoding="utf-8")
    out = DIST / f"jobdork-{ver}-windows-x64.msix"
    out.unlink(missing_ok=True)
    run(_makeappx(), "pack", "/o", "/d", root, "/p", out)
    if not real:
        print("packaging/store.toml has no identity: this MSIX is for testing, "
              "and the Store refuses it", flush=True)
    return out


# ── Linux ─────────────────────────────────────────────────────────────────────

SUMMARY = "Find job posts that fit your resume"
HOMEPAGE = "https://github.com/jessn-dev/jobDork"
MAINTAINER = "jessn-dev <jessengolab.dev@gmail.com>"
# What the .deb asks the system for: what Qt and its web engine load from the
# system rather than carry (graphics, fonts, X and Wayland, sound, NSS for
# certificates). desktop.yml's Linux check installs the .deb on bare Ubuntu
# 22.04, 24.04 and Debian 12 and fails on any library still missing (ldd).
# Where a package was renamed, the build machine (Ubuntu 22.04) installs the
# name without "t64" (build_packages). Names that Ubuntu 24.04 renamed take either. glibc 2.35: the build
# runs on Ubuntu 22.04.
DEB_DEPENDS = (
    "libc6 (>= 2.35)", "libegl1", "libgl1", "libopengl0", "libfontconfig1", "libfreetype6",
    "libdbus-1-3", "libxkbcommon0", "libxkbcommon-x11-0", "libx11-6", "libx11-xcb1",
    "libxcb1", "libxcb-cursor0", "libxcb-glx0", "libxcb-icccm4", "libxcb-image0",
    "libxcb-keysyms1", "libxcb-randr0", "libxcb-render-util0", "libxcb-shape0",
    "libxcb-shm0", "libxcb-sync1", "libxcb-xfixes0", "libxcb-xinerama0", "libxcb-xkb1",
    "libxcomposite1", "libxdamage1", "libxext6", "libxfixes3", "libxrandr2", "libxrender1",
    "libxtst6", "libxkbfile1", "libxshmfence1", "libgbm1", "libdrm2", "libnss3",
    "libnspr4", "libwayland-client0", "libwayland-cursor0", "libwayland-egl1",
    "libwayland-server0", "libxcb-util1", "libgssapi-krb5-2", "libexpat1", "zlib1g",
    "libstdc++6", "libgcc-s1",
    # Ubuntu 24.04's names first: there "libasound2" is also answered by a
    # stand-in (liboss4-salsa-asound2) that lacks what the web engine calls.
    "libasound2t64 | libasound2", "libglib2.0-0t64 | libglib2.0-0",
)


# Libraries PyInstaller copies from the build machine that belong to the
# system it runs on: X11 and xcb, OpenGL and its drivers' helpers, fonts,
# glib, D-Bus, sound, Kerberos, NSS (the web engine's certificate store), the
# C++ runtime. A copy from Ubuntu 22.04 beside a newer system's own graphics
# drivers kept Qt from finding an OpenGL configuration, and NSS's pieces must
# match each other and the system's settings. Every Linux desktop has them,
# and the .deb depends on them (DEB_DEPENDS). Named exactly: a wheel's own
# copies carry a hash in their name (libxcb-9065bb12.so...) and stay, and so
# does libxcb-cursor, which the build carries on purpose (jobdork.spec).
SYSTEM_LIBRARIES = re.compile(
    r"^lib(X11|X11-xcb|Xau|Xdmcp|Xext|Xfixes|Xrender|Xrandr|Xcomposite|Xdamage|Xtst|Xi"
    r"|xcb|xcb-(glx|icccm|image|keysyms|randr|render|render-util|shape|shm|sync|util"
    r"|xfixes|xkb|xinerama|dri2|dri3|present|xinput)"
    r"|xkbcommon|xkbcommon-x11|xkbfile|gbm|drm|GL|GLX|GLdispatch|EGL|OpenGL|wayland-[a-z]+"
    r"|fontconfig|freetype|harfbuzz|png16|brotlicommon|brotlidec|expat|dbus-1|systemd|udev"
    r"|asound|glib-2\.0|gio-2\.0|gobject-2\.0|gmodule-2\.0|gthread-2\.0|pcre|pcre2-8|mount"
    r"|blkid|selinux|cap|gcrypt|gpg-error|lz4|zstd|lzma|bsd|md|uuid|com_err|keyutils|krb5"
    r"|krb5support|k5crypto|gssapi_krb5|z|gcc_s|stdc\+\+|nss3|nssutil3|smime3|ssl3|nspr4"
    r"|plc4|plds4|softokn3|freebl3|freeblpriv3"
    # What the two Qt plugins the build leaves out (jobdork.spec) needed, when
    # the build machine has it: GTK and its drawing and accessibility, and
    # CUPS with its network printing and TLS. Taken from GitHub's Ubuntu
    # 22.04 runner on 2026-11-05; each needs libraries a bare system lacks.
    r"|gtk-3|gdk-3|gdk_pixbuf-2\.0|pango-1\.0|pangocairo-1\.0|pangoft2-1\.0|cairo"
    r"|cairo-gobject|atk-1\.0|atk-bridge-2\.0|atspi|epoxy|fribidi|thai|datrie|pixman-1"
    r"|graphite2|Xcursor|Xinerama|cups|avahi-client|avahi-common|gnutls|hogweed|nettle"
    r"|gmp|p11-kit|tasn1|idn2|unistring)\.(so|chk)")


def prune_linux(bundle: Path) -> list[str]:
    """Take the system's own libraries out of the build (SYSTEM_LIBRARIES),
    and NSS's folder, then every link left pointing at nothing. Returns what
    was removed, for the build log."""
    internal = bundle / "_internal"
    gone = []
    for path in sorted(internal.iterdir()):
        if SYSTEM_LIBRARIES.match(path.name) or (path.name == "nss" and path.is_dir()):
            gone.append(path.name)
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    for path in sorted(internal.rglob("*")):
        if path.is_symlink() and not path.exists():
            path.unlink()
            gone.append(str(path.relative_to(internal)))
    return gone


def build_packages() -> list[str]:
    """DEB_DEPENDS as the build machine (Ubuntu 22.04) names them, for apt:
    the alternative from before Ubuntu 24.04's renaming."""
    names = []
    for dep in DEB_DEPENDS:
        alts = [a.split(" (")[0] for a in dep.split(" | ")]
        names.append(next((a for a in alts if not a.endswith("t64")), alts[0]))
    return names


def desktop_entry(command: str) -> str:
    """The menu entry: what the desktop lists jobdork under, and starts."""
    return (f"[Desktop Entry]\nType=Application\nName=jobdork\nComment={SUMMARY}\n"
            f"Exec={command}\nIcon=jobdork\nTerminal=false\nCategories=Office;\n"
            f"StartupWMClass=jobdork\n")


# The AppStream id: what software centres (GNOME Software, KDE Discover)
# know jobdork by. Without its metainfo file they showed a package opened
# from a file with a generic gear for its icon and "No Screenshots" (2026-11-11).
APP_ID = "io.github.jessn_dev.jobdork"
ICON_SIZES = (64, 128, 256, 512)
# Guide pictures shown as screenshots, from the release's own tag so they
# match the version installed: (picture, caption).
SCREENSHOTS = (("dashboard", "The Dashboard: scans, job posts found and the AI's numbers"),
               ("job-posts", "Job posts, scored against your resume"),
               ("job-window", "One job post: its scores, advert and what to do next"),
               ("resume", "Your resume, the ones tailored from it, and its checks"))


def _xml(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def metainfo(ver: str, date: str = "") -> str:
    """The AppStream metainfo: name, description, icon, screenshots and the
    release, for software centres."""
    date = date or time.strftime("%Y-%m-%d")
    raw = f"https://raw.githubusercontent.com/jessn-dev/jobDork/v{ver}"
    default = ' type="default"'
    shots = "\n".join(
        f'    <screenshot{default if i == 0 else ""}>\n'
        f"      <caption>{_xml(caption)}</caption>\n"
        f'      <image type="source">{raw}/guide/docs/images/{name}.png</image>\n'
        "    </screenshot>"
        for i, (name, caption) in enumerate(SCREENSHOTS))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>{APP_ID}</id>
  <name>jobdork</name>
  <summary>{_xml(SUMMARY)}</summary>
  <developer id="io.github.jessn_dev"><name>jessn-dev</name></developer>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>GPL-3.0-or-later</project_license>
  <description>
    <p>jobdork searches job sites and employers' own boards for the jobs you want,
    scores each post against your resume, and keeps what you applied to.</p>
    <p>An AI model of your choice, local or with your own key, can judge posts,
    draft cover letters, tailored resumes and interview prep, and every claim it
    makes is checked against your resume and the advert. It never applies for you.</p>
    <p>Your search, resume and job posts stay on this computer.</p>
  </description>
  <launchable type="desktop-id">jobdork.desktop</launchable>
  <icon type="stock">jobdork</icon>
  <icon type="remote" width="512" height="512">{raw}/packaging/icon.png</icon>
  <url type="homepage">{HOMEPAGE}</url>
  <url type="bugtracker">{HOMEPAGE}/issues</url>
  <url type="help">https://jessn-dev.github.io/jobDork/</url>
  <categories><category>Office</category></categories>
  <provides><binary>jobdork</binary></provides>
  <screenshots>
{shots}
  </screenshots>
  <releases>
    <release version="{ver}" date="{date}">
      <url type="details">{HOMEPAGE}/releases/tag/v{ver}</url>
    </release>
  </releases>
  <content_rating type="oars-1.1"/>
</component>
"""


def _linux_files(root: Path, command: str, ver: str = "") -> None:
    """The menu entry, the icon in each size the desktop looks for, and the
    AppStream metainfo software centres read."""
    from PIL import Image

    apps = root / "usr" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / "jobdork.desktop").write_text(desktop_entry(command), encoding="utf-8")
    hicolor = root / "usr" / "share" / "icons" / "hicolor"
    for size in ICON_SIZES:
        icons = hicolor / f"{size}x{size}" / "apps"
        icons.mkdir(parents=True, exist_ok=True)
        Image.open(PACKAGING / "icon.png").resize((size, size)).save(icons / "jobdork.png")
    scalable = hicolor / "scalable" / "apps"
    scalable.mkdir(parents=True, exist_ok=True)
    shutil.copy(PACKAGING / "icon.svg", scalable / "jobdork.svg")
    if ver:
        meta = root / "usr" / "share" / "metainfo"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / f"{APP_ID}.metainfo.xml").write_text(metainfo(ver), encoding="utf-8")


APPRUN = """#!/bin/sh
# What the AppImage starts: the app inside it, with what it was given.
here="$(dirname "$(readlink -f "$0")")"
exec "$here/usr/lib/jobdork/jobdork" "$@"
"""


def appimage(ver: str) -> Path:
    """The build in an AppImage: one file that runs where it is put."""
    tool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool") or ""
    runtime = os.environ.get("APPIMAGE_RUNTIME", "")
    if not tool or not Path(runtime).is_file():
        raise SystemExit("an AppImage needs APPIMAGETOOL and APPIMAGE_RUNTIME, both files "
                         "(see .github/workflows/desktop.yml for the pinned ones)")
    appdir = WORK / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(DIST / "jobdork", appdir / "usr" / "lib" / "jobdork", symlinks=True)
    _linux_files(appdir, "jobdork", ver)
    (appdir / "AppRun").write_text(APPRUN, encoding="utf-8")
    (appdir / "AppRun").chmod(0o755)
    # The AppImage's own entry and icon, at its top, as the format asks.
    shutil.copy(appdir / "usr" / "share" / "applications" / "jobdork.desktop", appdir)
    shutil.copy(appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
                / "jobdork.png", appdir)
    (appdir / ".DirIcon").symlink_to("jobdork.png")
    out = DIST / f"jobdork-{ver}-linux-x86_64.AppImage"
    out.unlink(missing_ok=True)
    # appimagetool is itself an AppImage: unpacked to run, so the build
    # machine needs no FUSE.
    os.environ.update(ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    run(tool, "--no-appstream", "--runtime-file", runtime, appdir, out)
    return out


def deb_control(ver: str, installed_kb: int) -> str:
    return (f"Package: jobdork\nVersion: {ver}\nArchitecture: amd64\n"
            f"Maintainer: {MAINTAINER}\nInstalled-Size: {installed_kb}\n"
            f"Depends: {', '.join(DEB_DEPENDS)}\n"
            # notify-send, for notifications (core/notify.py); without it
            # jobdork runs and shows none.
            "Recommends: libnotify-bin\nSection: utils\nPriority: optional\n"
            f"Homepage: {HOMEPAGE}\n"
            f"Description: {SUMMARY}\n"
            " jobdork searches job sites and employers' own boards for the jobs you\n"
            " want, scores each post against your resume, and keeps what you applied\n"
            " to. Your search, resume and job posts stay on this computer.\n")


def deb(ver: str) -> Path:
    """The build in a .deb, installed to /opt/jobdork with `jobdork` on the
    PATH and a menu entry."""
    root = WORK / "deb"
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(DIST / "jobdork", root / "opt" / "jobdork", symlinks=True)
    (root / "usr" / "bin").mkdir(parents=True)
    (root / "usr" / "bin" / "jobdork").symlink_to("/opt/jobdork/jobdork")
    _linux_files(root, "/opt/jobdork/jobdork", ver)
    docs = root / "usr" / "share" / "doc" / "jobdork"
    docs.mkdir(parents=True)
    shutil.copy(ROOT / "LICENSE", docs / "copyright")
    size = sum(p.lstat().st_size for p in root.rglob("*") if not p.is_dir())
    (root / "DEBIAN").mkdir()
    (root / "DEBIAN" / "control").write_text(deb_control(ver, size // 1024 + 1),
                                             encoding="utf-8")
    out = DIST / f"jobdork_{ver}_amd64.deb"
    out.unlink(missing_ok=True)
    run("dpkg-deb", "--root-owner-group", "-Zxz", "--build", root, out)
    return out


def main() -> int:
    ver = version()
    pyinstaller(ver)
    if sys.platform.startswith("linux"):
        gone = prune_linux(DIST / "jobdork")
        print(f"left to the system: {len(gone)} libraries and links", flush=True)
    self_test()
    if sys.platform == "darwin":
        built = [dmg(ver)]
    elif sys.platform == "win32":
        built = [windows_installer(ver)]
    elif platform.machine() == "x86_64":
        built = [appimage(ver), deb(ver)]
    else:
        print(f"Linux on {platform.machine()} is not packaged; the build is in dist/jobdork/.")
        return 0
    if sys.platform == "win32":
        built.append(msix(ver))                 # the Microsoft Store's package
    for out in built:
        print(f"built {out} ({out.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
