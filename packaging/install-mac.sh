#!/bin/bash
# Install or update jobdork on a Mac, from Terminal:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/jessn-dev/jobDork/main/packaging/install-mac.sh)"
#
# Downloads the newest jobdork for Apple silicon from GitHub's Releases page,
# checks it is the file this repository's GitHub Actions built (who uploaded
# it, its SHA-256 in the release's SHA256SUMS.txt, and its build attestation
# when the GitHub CLI `gh` is installed), and copies jobdork.app into
# /Applications, or ~/Applications when /Applications cannot be written.
# Then it opens jobdork.
#
# It asks for no password and changes no setting. Your settings, job posts
# and keys are not touched: they live in ~/Library/Application Support/jobdork
# and the keychain, not in the app. Run it again to update.
#
# macOS 12 or newer, on Apple silicon or Intel. Bash 3.2, as macOS ships.
# JOBDORK_INSTALL_DIR puts the app in another folder; JOBDORK_INSTALL_NO_OPEN=1
# leaves it closed.

set -euo pipefail

REPO="jessn-dev/jobDork"
API="https://api.github.com/repos/$REPO/releases/latest"
# The account GitHub Actions uploads release files as (core/updates.py).
CI_UPLOADER="github-actions[bot]"
SUMS="SHA256SUMS.txt"
GUIDE="https://github.com/$REPO/blob/main/docs/run/desktop.md"

say() { printf '%s\n' "$*"; }
die() {
    printf 'jobdork install: %s\n' "$*" >&2
    exit 1
}

[ "$(uname -s)" = Darwin ] || die "this command is for macOS. Windows and Linux: $GUIDE"
case "$(uname -m)" in
    arm64) arch=arm64 ;;
    x86_64) arch=x86_64 ;;
    *) die "no Mac app for a $(uname -m) processor" ;;
esac
major=$(sw_vers -productVersion | cut -d. -f1)
[ "$major" -ge 12 ] || die "jobdork needs macOS 12 or newer; this Mac has $(sw_vers -productVersion)"

work=$(mktemp -d -t jobdork-install)
mounted=""
old=""
cleanup() {
    if [ -n "$mounted" ]; then
        hdiutil detach -quiet "$mounted" 2>/dev/null || hdiutil detach -quiet -force "$mounted" 2>/dev/null || true
    fi
    rm -rf "$work"
}
trap cleanup EXIT

# One value from GitHub's answer; plutil reads JSON, so nothing else is needed.
field() { plutil -extract "$1" raw -o - "$work/release.json" 2>/dev/null; }

say "Asking GitHub for the newest jobdork..."
curl -fsSL --proto '=https' --tlsv1.2 -H "Accept: application/vnd.github+json" \
    -o "$work/release.json" "$API" || die "could not reach GitHub ($API)"
tag=$(field tag_name) || die "GitHub's answer named no release"
version=${tag#v}
dmg="jobdork-$version-macos-$arch.dmg"

# The two files this needs, each uploaded by GitHub Actions and nobody else.
dmg_url=""
sums_url=""
i=0
while name=$(field "assets.$i.name"); do
    url=$(field "assets.$i.browser_download_url")
    by=$(field "assets.$i.uploader.login" || true)
    if [ "$name" = "$dmg" ] || [ "$name" = "$SUMS" ]; then
        [ "$by" = "$CI_UPLOADER" ] || die "$name in $tag was uploaded by '$by', not GitHub Actions; not installing it"
        if [ "$name" = "$dmg" ]; then dmg_url=$url; else sums_url=$url; fi
    fi
    i=$((i + 1))
done
[ -n "$dmg_url" ] || die "$tag has no $dmg"
[ -n "$sums_url" ] || die "$tag has no $SUMS to check the download against"

say "Downloading jobdork $version..."
curl -fL --proto '=https' --tlsv1.2 --progress-bar -o "$work/$dmg" "$dmg_url" || die "the download failed"
curl -fsSL --proto '=https' --tlsv1.2 -o "$work/$SUMS" "$sums_url" || die "could not download $SUMS"

expected=$(awk -v n="$dmg" '$2 == n || $2 == "*" n { print $1 }' "$work/$SUMS")
actual=$(shasum -a 256 "$work/$dmg" | awk '{ print $1 }')
[ -n "$expected" ] || die "$SUMS does not list $dmg"
[ "$expected" = "$actual" ] || die "the download does not match $SUMS; not installing it"
say "Checked: the file matches the release's $SUMS."

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh attestation verify "$work/$dmg" --repo "$REPO" >/dev/null 2>&1 \
        || die "GitHub could not confirm this repository built $dmg; not installing it"
    say "Checked: GitHub confirms this repository's GitHub Actions built it."
fi

dest=${JOBDORK_INSTALL_DIR:-/Applications}
if [ -z "${JOBDORK_INSTALL_DIR:-}" ] && [ ! -w /Applications ]; then
    dest="$HOME/Applications"
fi
mkdir -p "$dest"
app="$dest/jobdork.app"

# An open jobdork is asked to quit, as the Update button's installer does.
if pgrep -f "jobdork.app/Contents/MacOS/jobdork" >/dev/null 2>&1; then
    say "Closing jobdork..."
    osascript -e 'quit app "jobdork"' >/dev/null 2>&1 || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        pgrep -f "jobdork.app/Contents/MacOS/jobdork" >/dev/null 2>&1 || break
        sleep 1
    done
    ! pgrep -f "jobdork.app/Contents/MacOS/jobdork" >/dev/null 2>&1 \
        || die "jobdork is still open; close it and run this again"
fi

mounted="$work/disk"
mkdir -p "$mounted"
hdiutil attach -quiet -nobrowse -readonly -noautoopen -mountpoint "$mounted" "$work/$dmg" \
    || { mounted=""; die "could not open $dmg"; }
[ -d "$mounted/jobdork.app" ] || die "$dmg holds no jobdork.app"

# The old app is set aside, not deleted, until the new one is in place.
if [ -e "$app" ]; then
    old="$work/previous.app"
    mv "$app" "$old" || die "could not move the old jobdork aside in $dest"
fi
if ! ditto "$mounted/jobdork.app" "$app"; then
    rm -rf "$app"
    [ -z "$old" ] || mv "$old" "$app"
    die "could not copy jobdork into $dest"
fi

say "jobdork $version is installed in $dest."
if [ -z "${JOBDORK_INSTALL_NO_OPEN:-}" ]; then
    open "$app"
fi
