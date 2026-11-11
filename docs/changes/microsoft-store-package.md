## Added — 2026-11-11 — A Microsoft Store package

The Windows build is now also made as an MSIX package,
`jobdork-<version>-windows-x64.msix`, for the Microsoft Store. The Store
signs what it publishes, so this needs no code-signing certificate of
jobdork's own (the installer still has none; docs/DECISIONS.md).

- **The package** (`packaging/build.py`, `msix`): the same PyInstaller
  build, its manifest declaring jobdork as a full-trust desktop app, the
  `jobdork://` link (so a click on a notification still opens the
  Notifications page) and a `jobdork` command, and its logos made from the
  icon. Its identity comes from Partner Center, in `packaging/store.toml`;
  until that is filled in, the build makes a stand-in that only CI
  installs.
- **In the Store's copy** (`core/store.py`): the Store updates it, so
  jobdork neither asks GitHub nor offers its own update, and Settings says
  the Store keeps it up to date; notifications are shown under the
  package's app id; the scheduled scan starts the `jobdork` command, whose
  path stays the same when an update renames the package's folder.
- **CI**: the Windows build keeps the package as its own artifact
  (`store-Windows-X64`), never on the release page; a new job signs a copy
  with a certificate made for the test, installs it, runs its self-test
  through the `jobdork` command, and removes it.

Windows keeps a Store app's own data apart: the Store copy's settings and
job posts are not the installer's, and go when it is uninstalled.
tests/test_store_package.py covers the manifest, the version, and the
update check, notification id and scheduled scan in the package.
