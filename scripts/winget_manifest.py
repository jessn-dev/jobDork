#!/usr/bin/env python3
"""
winget_manifest.py
==================
Writes the WinGet manifest for one jobdork release: the three files a pull
request to microsoft/winget-pkgs adds, so `winget install jessn-dev.jobdork`
installs that release from its GitHub Release page.

    python scripts/winget_manifest.py 0.15.2
    python scripts/winget_manifest.py 0.15.2 --out /tmp/winget

CI tries it before a release does: on every pull request the desktop
workflow writes one for the installer it just built, with the address of a
server on the runner, and installs and uninstalls it with winget:

    python scripts/winget_manifest.py 0.15.2 --installer dist/jobdork-0.15.2-windows-x64-setup.exe \
        --url http://127.0.0.1:8765/jobdork-0.15.2-windows-x64-setup.exe --iss packaging/jobdork.iss

It writes them under `<out>/manifests/j/jessn-dev/jobdork/<version>/`, the
same path they take in winget-pkgs, so that folder can be checked on Windows
(`winget validate --manifest <folder>`, `winget install --manifest <folder>`)
and copied into a fork of winget-pkgs as it is.

What it reads, all from the release itself:

- The installer's SHA-256, from the release's SHA256SUMS.txt (one request to
  GitHub; `--sums FILE` reads a local copy instead). WinGet refuses a
  download whose hash differs, and releases cannot be changed once published,
  so the address and hash stay right for good.
- The release date, from GitHub's answer for the tag (`--date` instead).
- The name Windows lists the app under, from packaging/jobdork.iss as it
  was at the release's tag: WinGet matches an installed app to its package by
  that name, so the manifest says it when it is not plain "jobdork".

The rules followed (winget-pkgs doc/Authoring.md, its pull request template):
a multi-file manifest in the 1.12 schema; `inno`, so WinGet runs the
installer with Inno Setup's silent switches; `user` scope, since the
installer installs for one person and asks for no administrator; one version
per pull request.

Standard library only, Python 3.10 and newer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REPO = "jessn-dev/jobDork"
PUBLISHER = "jessn-dev"
NAME = "jobdork"
IDENTIFIER = f"{PUBLISHER}.{NAME}"
SCHEMA = "1.12.0"
# Inno Setup's uninstall key: the AppId in packaging/jobdork.iss, with "_is1".
PRODUCT_CODE = "{89BA0AFD-43DD-4F5C-ADC2-221D5F8E1EA6}_is1"
SHORT = ("Finds job posts on employers' own boards and job sites, screens them "
         "against your search and resume, and runs on your own computer")
DESCRIPTION = """\
jobdork reads the job boards employers post to and job sites, keeps the
posts that match what you search for, and
scores each against your resume. It can draft cover letters and tailored
resumes with an AI model you choose, a local one through Ollama included, and
checks what the AI writes against your resume. Your resume, job posts and
settings stay on your computer."""
TAGS = ["job-search", "jobs", "resume", "ats", "career", "privacy",
        "local-first", "self-hosted", "ollama", "cover-letter"]

_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def installer_name(version: str) -> str:
    return f"jobdork-{version}-windows-x64-setup.exe"


def download_url(version: str, name: str) -> str:
    return f"https://github.com/{REPO}/releases/download/v{version}/{name}"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "jobdork-winget-manifest"})
    with urllib.request.urlopen(request, timeout=30) as answer:  # nosec B310 - fixed https URLs
        return answer.read()


def sha256_from_sums(text: str, name: str) -> str:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            digest = parts[0].upper()
            if re.fullmatch(r"[0-9A-F]{64}", digest):
                return digest
    raise SystemExit(f"SHA256SUMS.txt does not list {name}")


def release_date(version: str) -> str:
    answer = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/tags/v{version}"))
    return str(answer["published_at"])[:10]


def display_name(version: str, iss: str | None = None) -> str:
    """The name the installer at this release writes under Installed apps.
    Inno Setup's default, with no UninstallDisplayName, is "<AppName>
    version <AppVersion>"."""
    if iss is None:
        shown = subprocess.run(["git", "show", f"v{version}:packaging/jobdork.iss"],
                               cwd=ROOT, capture_output=True, text=True)
        if shown.returncode != 0:
            raise SystemExit(f"no tag v{version} here to read packaging/jobdork.iss "
                             "from; run `git fetch --tags` first")
        iss = shown.stdout
    match = re.search(r"^UninstallDisplayName=(.+)$", iss, re.MULTILINE)
    return match.group(1).strip() if match else f"{NAME} version {version}"


def _header(kind: str) -> str:
    return (f"# Written by scripts/winget_manifest.py in {REPO}\n"
            f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}.{SCHEMA}.schema.json\n\n")


def _quote(text: str) -> str:
    """A YAML string in single quotes: nothing in it is read as YAML."""
    return "'" + text.replace("'", "''") + "'"


def manifests(version: str, sha256: str, date: str, shown_as: str,
              url: str | None = None) -> dict[str, str]:
    """The three files, by file name."""
    tag = f"v{version}"
    common = f"PackageIdentifier: {IDENTIFIER}\nPackageVersion: {version}\n"
    version_file = (_header("version") + common
                    + f"DefaultLocale: en-US\nManifestType: version\nManifestVersion: {SCHEMA}\n")

    apps = ""
    if shown_as != NAME:
        apps = (f"AppsAndFeaturesEntries:\n- DisplayName: {_quote(shown_as)}\n"
                f"  Publisher: {PUBLISHER}\n  DisplayVersion: {version}\n"
                f"  ProductCode: {_quote(PRODUCT_CODE)}\n")
    installer_file = (_header("installer") + common
                      + "InstallerType: inno\nScope: user\nUpgradeBehavior: install\n"
                      + f"ProductCode: {_quote(PRODUCT_CODE)}\nReleaseDate: {date}\n" + apps
                      + "Installers:\n- Architecture: x64\n"
                      + f"  InstallerUrl: {url or download_url(version, installer_name(version))}\n"
                      + f"  InstallerSha256: {sha256}\n"
                      + f"ManifestType: installer\nManifestVersion: {SCHEMA}\n")

    description = "".join(f"  {line}\n" for line in DESCRIPTION.splitlines())
    tags = "".join(f"- {t}\n" for t in TAGS)
    locale_file = (_header("defaultLocale") + common
                   + "PackageLocale: en-US\n"
                   + f"Publisher: {PUBLISHER}\n"
                   + f"PublisherUrl: https://github.com/{PUBLISHER}\n"
                   + f"PublisherSupportUrl: https://github.com/{REPO}/issues\n"
                   + f"PrivacyUrl: https://github.com/{REPO}/blob/{tag}/PRIVACY.md\n"
                   + f"Author: {PUBLISHER}\n"
                   + f"PackageName: {NAME}\n"
                   + f"PackageUrl: https://github.com/{REPO}\n"
                   + "License: GPL-3.0-or-later\n"
                   + f"LicenseUrl: https://github.com/{REPO}/blob/{tag}/LICENSE\n"
                   + f"ShortDescription: {_quote(SHORT)}\n"
                   + "Description: |-\n" + description
                   + f"Moniker: {NAME}\n"
                   + "Tags:\n" + tags
                   + f"ReleaseNotesUrl: https://github.com/{REPO}/releases/tag/{tag}\n"
                   + "Documentations:\n- DocumentLabel: User guide\n"
                   + "  DocumentUrl: https://jessn-dev.github.io/jobDork/\n"
                   + f"ManifestType: defaultLocale\nManifestVersion: {SCHEMA}\n")

    return {f"{IDENTIFIER}.yaml": version_file,
            f"{IDENTIFIER}.installer.yaml": installer_file,
            f"{IDENTIFIER}.locale.en-US.yaml": locale_file}


def folder(out: Path, version: str) -> Path:
    """Where winget-pkgs keeps this version: manifests/<p>/<Publisher>/<Package>/<version>."""
    return out / "manifests" / PUBLISHER[0].lower() / PUBLISHER / NAME / version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the WinGet manifest for one release.")
    parser.add_argument("version", help="the release, as 0.15.2")
    parser.add_argument("--out", default="winget", help="folder to write under (default: ./winget)")
    parser.add_argument("--sums", help="a local SHA256SUMS.txt instead of the release's")
    parser.add_argument("--date", help="the release date, YYYY-MM-DD, instead of GitHub's")
    parser.add_argument("--installer", help="hash this installer file instead (a build, not a release)")
    parser.add_argument("--url", help="the installer's address, instead of the release's")
    parser.add_argument("--iss", help="read the installer's name from this script, not the tag's")
    args = parser.parse_args(argv)

    version = args.version.removeprefix("v")
    if not _VERSION.match(version):
        parser.error(f"{args.version!r} is not a version like 0.15.2")
    name = installer_name(version)
    if args.installer:
        sha256 = hashlib.sha256(Path(args.installer).read_bytes()).hexdigest().upper()
    else:
        sums = (Path(args.sums).read_text(encoding="utf-8") if args.sums
                else _get(download_url(version, "SHA256SUMS.txt")).decode("utf-8"))
        sha256 = sha256_from_sums(sums, name)
    shown_as = (display_name(version, Path(args.iss).read_text(encoding="utf-8"))
                if args.iss else display_name(version))
    files = manifests(version, sha256, args.date or release_date(version), shown_as, args.url)
    where = folder(Path(args.out), version)
    where.mkdir(parents=True, exist_ok=True)
    for file_name, text in files.items():
        (where / file_name).write_text(text, encoding="utf-8", newline="\n")
    print(where)
    return 0


if __name__ == "__main__":
    sys.exit(main())
