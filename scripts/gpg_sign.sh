#!/bin/sh
# Sign each Linux installer in a folder with jobdork's GPG key, a detached,
# ASCII-armoured signature beside it (<file>.asc), then check every one the
# way a user would: against the public key in the repository alone, so a
# release never carries a signature its users cannot check.
#
#   scripts/gpg_sign.sh <folder> [public key, default packaging/jobdork-signing-key.asc]
#
# The secret key (armoured) comes from $JOBDORK_GPG_KEY and its passphrase,
# if it has one, from $JOBDORK_GPG_PASSPHRASE: the release run passes them
# from the `release` environment (docker.yml, sign-linux). Neither is written
# to disk outside a temporary keyring, which is removed on the way out.
set -eu
export LC_ALL=C
dir=$1
public=${2:-packaging/jobdork-signing-key.asc}
[ -n "${JOBDORK_GPG_KEY:-}" ] || { echo "no GPG key given (JOBDORK_GPG_KEY)"; exit 2; }
[ -f "$public" ] || { echo "$public is missing: commit the public key first"; exit 2; }
home=$(mktemp -d)
trap 'rm -rf "$home"' EXIT

export GNUPGHOME="$home/sign"
mkdir -m 700 "$GNUPGHOME"
printf '%s\n' "$JOBDORK_GPG_KEY" | gpg --batch --quiet --import
n=0
for f in "$dir"/*.AppImage "$dir"/*.deb; do
  [ -f "$f" ] || continue
  # The passphrase on a pipe, not the command line, which others can read.
  printf '%s' "${JOBDORK_GPG_PASSPHRASE:-}" | gpg --batch --yes --quiet \
    --pinentry-mode loopback --passphrase-fd 0 \
    --armor --detach-sign --output "$f.asc" "$f"
  n=$((n + 1))
done
[ "$n" -gt 0 ] || { echo "no Linux installers in $dir"; exit 1; }

export GNUPGHOME="$home/check"
mkdir -m 700 "$GNUPGHOME"
gpg --batch --quiet --import "$public"
for f in "$dir"/*.AppImage "$dir"/*.deb; do
  [ -f "$f" ] || continue
  if ! gpg --batch --verify "$f.asc" "$f" 2>&1 | grep -q '^gpg: Good signature'; then
    echo "$(basename "$f"): its signature does not check against $public"
    exit 1
  fi
  echo "signed and checked: $(basename "$f")"
done
