## Security — 2026-11-13 — dnspython updated to 2.9.2

CVE-2026-128089 in dnspython 2.9.0, which the desktop installer builds and CI
pull in (through pydantic's email-validator), is fixed in 2.9.2. The desktop
and CI lock files now pin 2.9.2; nothing else changed in them. The dashboard,
the CLI and the Docker image never installed it (`requirements.lock` does not
list it). CI's Python 3.10 test job keeps dnspython 2.8.0, the last release
for Python 3.10, which has this and an earlier advisory: it only runs the
tests, and nothing there looks up names through it.
