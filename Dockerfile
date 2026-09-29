# syntax=docker/dockerfile:1

# The base image, pinned by digest: a tag like 3.14-alpine can be re-pointed at
# different contents, a digest cannot. Dependabot proposes updates to both
# FROM lines below.
# Python 3.14 is the newest stable release, supported until October 2030.
# Alpine, not Debian slim: scanned on 2026-09-29, the slim image carried 44
# high-severity findings in system packages with no fix released (util-linux,
# ncurses, perl), none of which jobdork uses; Alpine carried none, and is
# 159 MB against 278 MB. The full test suite passes on it.

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.14-alpine@sha256:9e9fde4d32eedce0b661d9ab91e826b62dddf28e928c230ec55f1866cac66b01 AS builder

WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Every dependency is installed at an exact version and refused unless its
# checksum matches requirements.lock, so a tampered release on PyPI cannot get
# in. Regenerate the lock after changing pyproject.toml; the command is at the
# top of requirements.lock, run inside this same base image.
COPY requirements.lock pyproject.toml README.md ./
COPY jobdork/ ./jobdork/

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --require-hashes -r requirements.lock \
    && pip install --no-deps --no-build-isolation . \
    # The running app never installs anything: no pip in the final image.
    && pip uninstall -y pip


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# The same base as the build stage; keep the two digests equal.
FROM python:3.14-alpine@sha256:9e9fde4d32eedce0b661d9ab91e826b62dddf28e928c230ec55f1866cac66b01

LABEL org.opencontainers.image.title="jobdork" \
      org.opencontainers.image.source="https://github.com/jessn-dev/jobDork" \
      org.opencontainers.image.licenses="MIT"

# A non-root user with a fixed id, 1000: the folders mounted from a NAS or a
# server (config.yaml, data/) must be writable by it, and a known id makes
# that one command on any system: chown -R 1000:1000 <the folder>. 1000 is
# also the first user on most Linux systems and NAS, often the owner already.
RUN addgroup -S -g 1000 appgroup && adduser -S -D -H -u 1000 -G appgroup appuser \
    # The base image's own pip, which nothing here needs: an installer left in
    # an image is a way to add code to it.
    && python -m pip uninstall -y --root-user-action=ignore pip

WORKDIR /app

# The app's code is owned by root and read-only to the user it runs as, so
# nothing running as that user can rewrite jobdork itself.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 127.0.0.1 inside the container is unreachable through a published port, so
# `serve` binds 0.0.0.0 here (and only where a container marker file exists).
# Publish it to the host's loopback only, on the same port on both sides:
# the Host check compares the port.
#   docker run --rm -p 127.0.0.1:8765:8765 \
#     -v "$PWD/config.yaml:/app/config.yaml" \
#     -v "$PWD/.env:/app/.env:ro" \
#     -v "$PWD/data:/app/data" -v "$PWD/out:/app/out" jobdork
# The dashboard edits config.yaml, so that mount is not read-only.
# To open it from another computer (a NAS opened from a laptop), publish the
# port to the network instead and name the address it is opened by:
#   -p 8765:8765 -e JOBDORK_ALLOW_HOSTS=192.168.1.50
# The access token is still required; see docs/DEPLOY.md.
ENV JOBDORK_IN_CONTAINER=1

# Print as it happens. Without this Python holds output back when it is not
# writing to a terminal, and the startup line with the access token never
# reaches the container's log, which is the only place to read it.
ENV PYTHONUNBUFFERED=1

# The uploaded resume and every generated document (cover letters, CVs,
# reviews) go to a temporary folder inside the container, emptied when the
# dashboard starts and when it stops, so nothing personal outlives a run.
ENV JOBDORK_TEMP_DOCS=/tmp/jobdork

# Directories the app writes to. No config.yaml or .env is baked in: an empty
# config.yaml does not load, so `serve` would exit at once. Mount your own;
# the example is here to copy from.
COPY config.example.yaml ./
RUN mkdir -p data out logs /tmp/jobdork \
    && chown appuser:appgroup data out logs /tmp/jobdork \
    && chmod 700 /tmp/jobdork

USER 1000:1000
EXPOSE 8765

ENTRYPOINT ["jobdork"]
# There is no browser in the container to open.
CMD ["serve", "--no-open"]
