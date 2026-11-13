## Security — 2026-11-13 — The desktop app's Docker image installs jobdork from a built wheel

`docker/desktop/Dockerfile` (the Linux desktop app in Docker, for testing)
installed jobdork with `pip install .`, which OpenSSF Scorecard counts as an
unpinned download (code scan #36). It now builds a wheel from the checkout
and installs that file, as the main image has since #168. Every dependency
was already installed by hash from `requirements-desktop.lock`.
