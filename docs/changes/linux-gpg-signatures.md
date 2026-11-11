## Security — 2026-11-11 — The Linux installers are signed with GPG

Asked for on 2026-11-11. The AppImage and `.deb` carried a build
attestation (Sigstore) and a checksum, but no GPG signature, which is what
Linux users and tools usually check.

Each release now puts a detached, ASCII-armoured signature beside every
Linux installer on its page, `<file>.asc`, made with jobdork's GPG key
(`scripts/gpg_sign.sh`):

- **Signed in the `release` environment**, by a new `sign-linux` job that
  waits for the same approval as the image, so the secret key
  (`LINUX_GPG_KEY`, `LINUX_GPG_PASSPHRASE`) is only handed to a run you
  approved, and is imported into a temporary keyring removed afterwards.
- **Checked before it is published**: every signature is verified against
  the public key in the repository alone
  (`packaging/jobdork-signing-key.asc`), as a user would; one that does not
  check stops the release.
- **Tried on every change** that builds the installers: a `gpg-check` job
  runs the same script with a key made and thrown away in CI.
- Without the key set, the release says so and goes out with no `.asc`
  files, rather than not at all.

Checking one: `gpg --import` the public key, then `gpg --verify
<file>.asc <file>` (docs/run/desktop.md, the release page, SECURITY.md).
The key itself is made and kept by the maintainer; its public half is
committed with the first release that is signed.
