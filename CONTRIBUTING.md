# Contributing

Pull requests are welcome: a fix, a new job source, a clearer sentence in the
guide. So are issues: the app's **Feedback** page files one for you
([how](https://jessn-dev.github.io/jobDork/feedback/)), or open one on
[GitHub](https://github.com/jessn-dev/jobDork/issues/new/choose) from one of
its three forms: a problem, an idea or a question. For a security problem,
follow [SECURITY.md](SECURITY.md) instead of opening an issue.

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md): be
kind, keep to the work, and keep private things out of public issues.

## Set up

```bash
git clone https://github.com/jessn-dev/jobDork.git && cd jobDork
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,pdf,ai]'
.venv/bin/pytest            # the whole suite; none of it goes online
.venv/bin/ruff check .      # lint (the code style)
```

Running the app from your clone: [docs/run/source.md](docs/run/source.md).
How it fits together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What a pull request needs

The pull request template has the checklist. In short:

- **Tests pass and ruff is clean.** CI runs both, on Python 3.10 and 3.14,
  with the security scans; `main` takes nothing that fails. Ruff is pinned
  in `pyproject.toml`, so the same version passes here and in CI; after a
  Dependabot update, `pip install -e '.[dev]'` again.
- **An entry in [docs/CHANGELOG.md](docs/CHANGELOG.md)**, at the top: what
  was wrong or missing, and what changed. Release pages are built from these
  entries, so write for the person reading the release.
- **The user guide**, when the change shows in the app: a new button,
  setting, page or status is explained in `guide/docs/`, and the pictures
  are retaken with `python scripts/guide_screenshots.py`. `tests/test_guide.py`
  fails for a button or heading the guide never names.
  [guide/README.md](guide/README.md) has the details.
- **The other docs** where they cover it: `README.md`, `docs/CONFIG.md`,
  `docs/run/`.
- **No real data in a test or a picture.** Tests use their own database and
  never go online; screenshots come from the made-up demo.
- **A dependency change updates every lock file.** `requirements.lock` (the
  Docker image), `requirements-desktop.lock` (the installers) and
  `requirements-ci.lock` (what CI installs, with the tools in
  `packaging/ci.in`) pin every package by hash; the command that regenerates
  each is at its top. A build or CI run with a package missing from its lock
  stops.

## House style

- Comments say why, not what. A Python `lambda` gets a `# lambda: <why>`
  comment above it.
- Write for someone who is not a programmer wherever a user will read it:
  the app's own text, the guide, error messages.

By contributing, you agree that your contribution is licensed under the
project's [GNU GPL v3 or later](LICENSE).
