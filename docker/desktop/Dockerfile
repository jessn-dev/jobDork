# syntax=docker/dockerfile:1

# The Linux desktop app (its own window, the Qt web engine the .deb and
# AppImage carry), run in a container and shown in your browser through
# noVNC: http://localhost:6080. For trying a change in the real window on a
# Mac or Windows machine without a Linux one. Not the server image (the
# Dockerfile at the top), which has no window.
#
#   docker compose -f docker/desktop/compose.yaml up --build
#
# Debian 13 (trixie), not 12: PyQt6's ARM64 wheels need glibc 2.39, and an
# Apple Silicon Mac runs ARM64 containers. Pinned by digest, as the server
# image is; Python 3.13, as requirements-desktop.lock is resolved for.
FROM python:3.13-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# What Qt and its web engine load from the system (packaging/build.py,
# DEB_DEPENDS, with Debian 13's names, and DEB_DEPENDS_ARM64, which the ARM
# wheels need and which do no harm on x86), then the screen: a virtual
# display, a small window manager, a VNC server and noVNC in a browser.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
        libegl1 libgl1 libopengl0 libfontconfig1 libfreetype6 libdbus-1-3 \
        libxkbcommon0 libxkbcommon-x11-0 libx11-6 libx11-xcb1 libxcb1 libxcb-cursor0 \
        libxcb-glx0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
        libxcb-render-util0 libxcb-shape0 libxcb-shm0 libxcb-sync1 libxcb-xfixes0 \
        libxcb-xinerama0 libxcb-xkb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
        libxrandr2 libxrender1 libxtst6 libxkbfile1 libxshmfence1 libgbm1 libdrm2 \
        libnss3 libnspr4 libasound2t64 libglib2.0-0t64 libgssapi-krb5-2 \
        libopus0 libsnappy1v5 libwebp7 libwebpdemux2 libwebpmux3 libminizip1t64 \
        liblcms2-2 libbz2-1.0 libice6 libsm6 \
        fonts-dejavu-core \
        xvfb fluxbox x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*

# Every package at the exact version and checksum the desktop installers use.
WORKDIR /src
COPY requirements-desktop.lock pyproject.toml README.md ./
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --require-hashes -r requirements-desktop.lock

# jobdork itself, from this checkout: rebuild to try a change.
COPY jobdork/ ./jobdork/
COPY packaging/jobdork_app.py ./packaging/
RUN pip install --no-deps --no-build-isolation .

# A user of its own: the web engine refuses to run its sandbox as root.
# The X server's socket folder, made here: as that user it cannot make it.
RUN useradd --create-home --uid 1000 app && mkdir -p /data /tmp/.X11-unix \
    && chown app /data && chmod 1777 /tmp/.X11-unix
COPY docker/desktop/start.sh /usr/local/bin/start-desktop
USER 1000:1000
WORKDIR /data

# The app's folder (settings, database, documents) is a volume, so a rebuild
# keeps them. Qt as pywebview's engine, as the installed Linux app uses.
ENV JOBDORK_HOME=/data PYWEBVIEW_GUI=qt QT_API=pyqt6 QT_QPA_PLATFORM=xcb \
    DISPLAY=:1 LIBGL_ALWAYS_SOFTWARE=1 \
    QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"
EXPOSE 6080
ENTRYPOINT ["start-desktop"]
CMD ["app"]
