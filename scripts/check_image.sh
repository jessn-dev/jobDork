#!/usr/bin/env bash
# Checks a built jobdork image before it is published. CI runs it on every
# build; run it yourself with:  scripts/check_image.sh jobdork:local
#
# Fails (exit 1) if the image runs as root, carries an installer, contains a
# secret or personal file, lets the app rewrite its own code, or does not
# start and guard the dashboard as it should.
set -uo pipefail

IMAGE=${1:?usage: check_image.sh <image>}
PORT=${CHECK_PORT:-18765}
TOKEN=checkimagetoken0123456789
FAILED=0
pass() { echo "ok    $1"; }
fail() { echo "FAIL  $1"; FAILED=1; }

user=$(docker inspect -f '{{.Config.User}}' "$IMAGE")
[ "$user" = "1000:1000" ] && pass "runs as 1000:1000, not root" || fail "runs as '$user'"

inside() { docker run --rm --entrypoint sh "$IMAGE" -c "$1"; }

inside 'command -v pip pip3 >/dev/null || python -m pip --version >/dev/null 2>&1' \
  && fail "pip is present" || pass "no pip in the image"

for f in /app/.env /app/config.yaml /app/config.local.yaml /app/data/jobdork.db /root/.ssh; do
  inside "test -e $f" && fail "$f is in the image" || pass "no $f"
done

inside 'touch /opt/venv/probe 2>/dev/null' \
  && fail "the app can write to its own code" || pass "code is read-only to the app"
inside 'touch /app/data/probe' && pass "data/ is writable" || fail "data/ is not writable"

# Start it as a user would, and check the guards from outside.
work=$(mktemp -d)
cp config.example.yaml "$work/config.yaml"
mkdir "$work/data" && chmod 777 "$work/data"
name=jobdork-check-$$
docker run -d --name "$name" -p "127.0.0.1:$PORT:8765" \
  -e JOBDORK_ALLOW_HOSTS=nas.test \
  -v "$work/config.yaml:/app/config.yaml" -v "$work/data:/app/data" \
  "$IMAGE" serve --no-open --token "$TOKEN" >/dev/null
trap 'docker rm -f "$name" >/dev/null 2>&1; rm -rf "$work"' EXIT

for _ in $(seq 1 30); do
  docker logs "$name" 2>&1 | grep -q "jobdork dashboard: http" && break
  sleep 1
done
docker logs "$name" 2>&1 | grep -q "jobdork dashboard: http" \
  && pass "the log shows the dashboard's address" || { fail "no address in the log"; docker logs "$name"; }

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
url="http://127.0.0.1:$PORT"
[ "$(code -H 'Host: 127.0.0.1:8765' "$url/?t=$TOKEN")" = 200 ] && pass "opens with the token" || fail "does not open with the token"
[ "$(code -H 'Host: nas.test' -H "X-Jobdork-Token: $TOKEN" "$url/api/roles")" = 200 ] && pass "opens by a named address" || fail "a named address is refused"
[ "$(code -H 'Host: nas.test' "$url/api/roles")" = 401 ] && pass "refuses without the token" || fail "answers without the token"
[ "$(code -H 'Host: evil.example' -H "X-Jobdork-Token: $TOKEN" "$url/api/roles")" = 421 ] && pass "refuses an address not named" || fail "answers an address not named"
[ "$(code -X POST -H 'Host: nas.test' "$url/api/scan?t=$TOKEN")" = 401 ] && pass "a token in the URL cannot change anything" || fail "a POST with the token in the URL was accepted"

[ "$FAILED" = 0 ] && echo "all image checks passed" || echo "image checks FAILED"
exit "$FAILED"
