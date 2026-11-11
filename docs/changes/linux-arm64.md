## Added — 2026-11-11 — The Linux app for ARM64

The `.deb` failed to install on an ARM computer (a Linux VM on an Apple
Silicon Mac, here) with every dependency, `libc6` included, "not
installable": jobdork's Linux packages were built for x86-64 alone, and
apt matches a package to the computer's architecture.

Each release now also has `jobdork-<version>-linux-aarch64.AppImage` and
`jobdork_<version>_arm64.deb`, built on GitHub's ARM machines
(`ubuntu-24.04-arm`) by the same `packaging/build.py`, with appimagetool
and the AppImage runtime for ARM pinned by SHA-256 like the x86-64 ones.
PyQt6's ARM wheels need glibc 2.39, so the ARM packages run on systems from
2024 on (Ubuntu 24.04, Debian 13, Raspberry Pi OS from Debian 13); the
`.deb` asks for `libc6 (>= 2.39)`, and Ubuntu 22.04 or Debian 12 on ARM
still use Docker or the source. desktop.yml installs the ARM `.deb` in bare
Ubuntu 24.04 and Debian 13, runs its self-test, opens its window and runs
the AppImage's self-test, as for x86-64.

The ARM Qt wheels load from the system what the x86-64 ones carry
inside (the web engine's Opus, Snappy, WebP, minizip and LittleCMS, and
the window plugin's ICE and SM): the ARM `.deb` depends on them
(`DEB_DEPENDS_ARM64`), and two plugins only the ARM wheels have and
jobdork never loads (text-to-speech by flite, GStreamer media) are left
out of the build.

The in-app update takes the ARM installer on an ARM computer
(`updates.installer_name`), the release page lists both, and
`docs/run/desktop.md`, the README and the guide's Getting started say which
to download (`dpkg --print-architecture`). tests/test_build.py,
tests/test_notify.py and tests/test_release_notes.py cover the names,
architecture and glibc. The ARM build has not run yet: its first run is
this change's CI.
