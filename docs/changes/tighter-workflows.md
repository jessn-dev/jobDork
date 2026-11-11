## Changed — 2026-11-11 — Tighter CI: no needless installer builds, no hung or piled-up runs

Asked for on 2026-11-11: fewer and shorter runs, still catching what
breaks. A healthy run already takes about eight minutes, the installers
built in parallel; the long waits that day were GitHub's outage. What
changed:

- **Installers are not rebuilt for a change to `docker.yml`** (its image,
  test or release steps change no installer, and a tag builds them all
  anyway). They still are for anything that can change one: `packaging/`,
  `desktop.yml`, the locked desktop dependencies, the version, the CI
  scripts the installer jobs run (`gpg_sign.sh`, `ci_apt_mirror.sh`), and
  the code only the installed app runs, now including `core/store.py` and
  `core/schedule.py`.
- **A pull request's newer push cancels its older run** (the CI and the
  dependency review), instead of both running to the end. A push to main
  and a release tag are never cancelled.
- **Every job has a time limit** (5 to 30 minutes, by what it does), so one
  that hangs fails and says so, rather than holding a runner for GitHub's
  default six hours.
