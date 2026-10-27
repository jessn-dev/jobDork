"""The WinGet manifest for a release (scripts/winget_manifest.py): the files,
the folder and the fields winget-pkgs checks. Nothing is fetched: the
checksums, the date and the installer script are given."""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import winget_manifest as wm  # noqa: E402

from jobdork.core import updates  # noqa: E402

DIGEST = hashlib.sha256(b"setup").hexdigest()


def _files(version="1.2.3", shown_as="jobdork") -> dict[str, dict]:
    sha = wm.sha256_from_sums(f"{DIGEST}  {wm.installer_name(version)}\n", wm.installer_name(version))
    texts = wm.manifests(version, sha, "2026-10-27", shown_as)
    for text in texts.values():
        assert text.splitlines()[1].startswith("# yaml-language-server: $schema=https://aka.ms/")
    return {name: yaml.safe_load(text) for name, text in texts.items()}


def test_three_files_in_the_folder_winget_pkgs_keeps_them_in():
    files = _files()
    assert set(files) == {"jessn-dev.jobdork.yaml", "jessn-dev.jobdork.installer.yaml",
                          "jessn-dev.jobdork.locale.en-US.yaml"}
    kinds = {f["ManifestType"] for f in files.values()}
    assert kinds == {"version", "installer", "defaultLocale"}
    for f in files.values():
        assert f["PackageIdentifier"] == "jessn-dev.jobdork" and f["PackageVersion"] == "1.2.3"
        assert f["ManifestVersion"] == "1.12.0"
    where = wm.folder(Path("out"), "1.2.3")
    assert where.as_posix() == "out/manifests/j/jessn-dev/jobdork/1.2.3"


def test_the_installer_is_the_release_file_the_updater_also_takes():
    inst = _files()["jessn-dev.jobdork.installer.yaml"]
    assert inst["InstallerType"] == "inno" and inst["Scope"] == "user"
    (one,) = inst["Installers"]
    assert one["Architecture"] == "x64"
    assert one["InstallerSha256"] == DIGEST.upper()
    assert one["InstallerUrl"] == (f"https://github.com/{updates.REPO}/releases/download/"
                                   "v1.2.3/jobdork-1.2.3-windows-x64-setup.exe")
    # The name the release workflow gives the Windows installer.
    iss = (ROOT / "packaging" / "jobdork.iss").read_text(encoding="utf-8")
    assert "OutputBaseFilename=jobdork-{#Version}-windows-x64-setup" in iss
    app_id = re.search(r"^AppId=\{(\{[0-9A-F-]+\})$", iss, re.MULTILINE).group(1)
    assert inst["ProductCode"] == app_id + "_is1"


def test_the_name_windows_lists_is_said_when_it_is_not_plain_jobdork():
    assert "AppsAndFeaturesEntries" not in _files()["jessn-dev.jobdork.installer.yaml"]
    old = _files(shown_as="jobdork version 1.2.3")["jessn-dev.jobdork.installer.yaml"]
    (entry,) = old["AppsAndFeaturesEntries"]
    assert entry["DisplayName"] == "jobdork version 1.2.3" and entry["DisplayVersion"] == "1.2.3"
    # Inno Setup's default when the script names none, and the script's own.
    assert wm.display_name("0.15.2", iss="AppName=jobdork\n") == "jobdork version 0.15.2"
    iss = (ROOT / "packaging" / "jobdork.iss").read_text(encoding="utf-8")
    assert wm.display_name("9.9.9", iss=iss) == "jobdork"


def test_the_listing_keeps_within_winget_pkgs_limits():
    loc = _files()["jessn-dev.jobdork.locale.en-US.yaml"]
    assert 3 <= len(loc["ShortDescription"]) <= 256
    assert len(loc["Tags"]) <= 16
    assert all(re.fullmatch(r"[a-z0-9-]+", t) for t in loc["Tags"])
    assert loc["Publisher"] == "jessn-dev"                     # AppPublisher in jobdork.iss
    assert loc["PackageName"] == "jobdork" and loc["License"] == "GPL-3.0-or-later"
    assert loc["LicenseUrl"].endswith("/blob/v1.2.3/LICENSE")


def test_writes_the_folder_from_a_local_checksum_file():
    with tempfile.TemporaryDirectory() as tmp:
        sums = Path(tmp) / "SHA256SUMS.txt"
        sums.write_text(f"{DIGEST}  jobdork-1.2.3-windows-x64-setup.exe\n"
                        f"{DIGEST}  jobdork-1.2.3-macos-arm64.dmg\n")
        saved = wm.display_name
        try:
            # lambda: the name without asking git for a tag this checkout may not have.
            wm.display_name = lambda version: "jobdork"
            assert wm.main(["1.2.3", "--out", tmp, "--sums", str(sums), "--date", "2026-10-27"]) == 0
        finally:
            wm.display_name = saved
        where = wm.folder(Path(tmp), "1.2.3")
        assert sorted(p.name for p in where.iterdir()) == sorted(_files())
        try:
            wm.main(["1.2.4", "--out", tmp, "--sums", str(sums), "--date", "2026-10-27"])
        except SystemExit as exc:
            assert "does not list" in str(exc)
        else:
            raise AssertionError("a release missing from SHA256SUMS.txt must stop it")


def test_a_build_on_this_computer_is_written_with_its_own_address():
    """What CI installs with winget on every pull request."""
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "jobdork-1.2.3-windows-x64-setup.exe"
        exe.write_bytes(b"setup")
        url = "http://127.0.0.1:8765/" + exe.name
        assert wm.main(["1.2.3", "--out", tmp, "--installer", str(exe), "--url", url,
                        "--iss", str(ROOT / "packaging" / "jobdork.iss"),
                        "--date", "2026-10-27"]) == 0
        inst = yaml.safe_load((wm.folder(Path(tmp), "1.2.3")
                               / "jessn-dev.jobdork.installer.yaml").read_text())
        (one,) = inst["Installers"]
        assert one["InstallerUrl"] == url and one["InstallerSha256"] == DIGEST.upper()
        assert "AppsAndFeaturesEntries" not in inst              # this script says "jobdork"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
