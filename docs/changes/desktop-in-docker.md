## Added — 2026-11-13 — The Linux desktop app in Docker, for testing

Asked for: a way to try the desktop app locally, not only the browser
version, the terminal and the server image. `docker/desktop/` runs the Linux
desktop app, its own window with the Qt web engine the AppImage and the .deb
carry, in a container, and shows it in your browser through noVNC at
http://localhost:6080, built from the checkout so a change shows in the real
window. `docker compose -f docker/desktop/compose.yaml up --build` starts it,
and `... run --rm desktop self-test` runs the app's own check without a window
(it printed `ok` on an Apple Silicon Mac, in the ARM64 build). The screen is
published on this computer only, as it has no password. The Windows and Mac
apps cannot run this way on a Mac (macOS only on Apple's hardware; a Windows
virtual machine needs virtualisation Docker on a Mac does not offer):
docs/run/desktop-in-docker.md says what to use instead.
