## Security — 2026-11-13 — opentelemetry-api updated to 1.45.2

CVE-2026-126360 in opentelemetry-api 1.45.1, a package the desktop
installers and CI pull in through other tools, is fixed in 1.45.2. The
desktop and CI lock files now pin 1.45.2; nothing else changed in them. The
dashboard, the CLI and the Docker image never installed it
(`requirements.lock` does not list it).
