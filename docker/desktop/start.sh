#!/bin/sh
# Starts a virtual screen, a window manager, and noVNC to show it at
# http://localhost:6080, then the jobdork desktop app in that screen.
#
#   start-desktop app          the desktop window (default)
#   start-desktop self-test    the installed-app check, no window: exit 1 if
#                              anything the window needs is missing
set -eu

if [ "${1:-app}" = "self-test" ]; then
    python /src/packaging/jobdork_app.py --self-test /tmp/self-test.txt || status=$?
    cat /tmp/self-test.txt
    exit "${status:-0}"
fi

Xvfb :1 -screen 0 1440x900x24 -nolisten tcp &
# The screen must be up before anything draws on it.
for _ in 1 2 3 4 5 6 7 8 9 10; do
    [ -e /tmp/.X11-unix/X1 ] && break
    sleep 0.5
done
fluxbox >/dev/null 2>&1 &
# VNC only inside the container (-localhost); noVNC is what the port shows.
x11vnc -display :1 -localhost -nopw -forever -shared -quiet >/dev/null 2>&1 &
websockify --web /usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &
echo "jobdork's window: open http://localhost:6080/vnc.html and press Connect"

# The window closes when you close it; the container stops with it.
exec python /src/packaging/jobdork_app.py
