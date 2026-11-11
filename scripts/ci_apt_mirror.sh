#!/bin/sh
# CI only: point apt at an Ubuntu mirror this runner can reach, then update.
#
# On 2026-11-11 GitHub's runners could not resolve Ubuntu's own hosts for
# hours (azure.archive.ubuntu.com first, then archive.ubuntu.com), and every
# Linux build failed in apt before building anything. When the usual host
# does not resolve, the first of these that does is used instead; x86-64 and
# ARM64 packages live on different mirrors (ARM's are "ubuntu-ports").
# Plain HTTP, as Ubuntu's own: apt checks every file against Ubuntu's
# signing key, and a bare container has no certificates for HTTPS.
# Run with sudo. desktop.yml calls it before installing anything.
set -e
if [ "$(dpkg --print-architecture)" = amd64 ]; then
  usual=azure.archive.ubuntu.com
  mirrors="http://archive.ubuntu.com/ubuntu/ http://mirrors.edge.kernel.org/ubuntu/"
else
  usual=ports.ubuntu.com
  mirrors="http://ports.ubuntu.com/ubuntu-ports/ http://mirror.us.leaseweb.net/ubuntu-ports/ http://mirrors.ocf.berkeley.edu/ubuntu-ports/"
fi
if ! getent hosts "$usual" > /dev/null; then
  chosen=""
  for url in $mirrors; do
    host=$(echo "$url" | cut -d/ -f3)
    if getent hosts "$host" > /dev/null; then chosen=$url; break; fi
  done
  if [ -n "$chosen" ]; then
    echo "$usual does not resolve: apt uses $chosen"
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do
      [ -f "$f" ] || continue
      sed -i -E \
        -e "s#mirror\+file:/etc/apt/apt-mirrors\.txt#$chosen#g" \
        -e "s#https?://(azure\.)?archive\.ubuntu\.com/ubuntu/?#$chosen#g" \
        -e "s#https?://security\.ubuntu\.com/ubuntu/?#$chosen#g" \
        -e "s#https?://ports\.ubuntu\.com/ubuntu-ports/?#$chosen#g" "$f"
    done
  else
    echo "no Ubuntu mirror resolves from this runner; apt will fail"
  fi
fi
apt-get -o Acquire::Retries=3 update -q
