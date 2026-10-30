# The desktop app

The dashboard in a window of its own, installed like any other program.
Nothing to type, no Python to install. Other ways to run it:
[README.md](README.md).

| System | Download |
|---|---|
| Mac with Apple Silicon (M1 or later), macOS 12 or newer | `jobdork-0.16.1-macos-arm64.dmg` |
| Mac with an Intel processor, macOS 12 or newer | `jobdork-0.16.1-macos-x86_64.dmg` (from 0.15.3) |
| Windows 10 or 11, 64-bit | `jobdork-0.16.1-windows-x64-setup.exe` |
| Linux | No installer: run the same window [from source](source.md#the-desktop-window-from-source) |

**Which Mac do I have?** Apple menu → **About This Mac**. "Chip: Apple M…"
is Apple Silicon; "Processor: … Intel" is Intel.

The Intel app keeps one library, `cryptography`, at 48.0.1: 49 and later
are no longer built for Intel Macs. The three advisories fixed since are in
code jobdork does not use that way, and the reasons are written beside the
exception in `.github/workflows/docker.yml`.

Installers are attached to the
[Releases](https://github.com/jessn-dev/jobDork/releases) page from 0.14.4
on. Until a release has them, a pull request's CI run builds both; they are
under that run's **Artifacts** for a week.

---

## Installing

**macOS.** Open the `.dmg` and drag jobdork into Applications.

**macOS, with one command.** Paste this into Terminal (in Applications →
Utilities):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jessn-dev/jobDork/main/packaging/install-mac.sh)"
```

It downloads the newest jobdork from the Releases page, checks it is the
file this repository's release workflow built (who uploaded it, its SHA-256
in `SHA256SUMS.txt`, and its build attestation when the
[GitHub CLI](https://cli.github.com/) is installed), copies it into
Applications and opens it. It asks for no password and changes no setting,
and macOS does not show the first-open warning below: that warning is for
files a browser downloaded. Run it again to update; your settings, job posts
and keys are not in the app and are not touched.
[Read the script](../../packaging/install-mac.sh) before you run it.

**Windows.** Run the setup. It installs for you alone, so it asks for no
administrator password, and it shows what jobdork keeps and sends before
installing ([PRIVACY.md](../../PRIVACY.md) in full).

### The first-open warning

The installers are not code-signed (see
[why](../DECISIONS.md#a-desktop-app-a-pywebview-window-unsigned-at-first--2026-10-21)),
so each system warns once (on a Mac, not when installed with the command
above):

- **macOS** says it cannot check jobdork for malicious software. Click
  **Done**, open **System Settings → Privacy & Security**, scroll down to the
  line about jobdork and click **Open Anyway**, then **Open Anyway** again.
- **Windows** shows "Windows protected your PC". Click **More info**, then
  **Run anyway**.

**Check a download is the one this repository built**, with the
[GitHub CLI](https://cli.github.com/):

```bash
gh attestation verify jobdork-0.16.1-macos-arm64.dmg --repo jessn-dev/jobDork
```

or compare its SHA-256 with `SHA256SUMS.txt` on the same release.

---

## Using it

The first start opens setup ([what it asks](README.md#what-is-the-same-everywhere)).
After that it opens on the Dashboard.

- **Job posts open in your own browser**, and a file you download is saved
  where you choose.
- **Closing the window stops jobdork**, and any API key it held is
  forgotten. While a scan is running it asks first.
- **Scans that run by themselves:** **Settings → Schedule a run** puts a
  daily, weekday or weekly scan in your computer's own scheduler (launchd on
  macOS, Task Scheduler on Windows), so it runs whether or not the window is
  open. **Run a scan now** sits beside it.
- **Notifications:** new job posts, a failed scan and a newer jobdork show in
  Notification Center (macOS) or as a toast (Windows). **Settings →
  Notifications** turns them, or their sound, off.
- **Updates:** once a day the app asks GitHub whether a newer release is
  out, and a banner says so. Its **Update**, or **Settings → Updates →
  Update**, downloads the installer and, only once it is shown to be this
  project's, puts it in place and restarts jobdork as the new version: on a
  Mac the new app replaces this one once it has quit and opens by itself; on
  Windows the installer runs on its own and opens the new version. The
  checks: uploaded
  by the release workflow, matching the release's checksums, and carrying a
  build attestation from this repository's workflow at that version's tag
  ([how](../../SECURITY.md#how-the-app-checks-an-update-before-opening-it)).
  Anything else is deleted unopened. The daily check can be switched off
  there, and nothing else is sent
  ([PRIVACY.md](../../PRIVACY.md#the-version-check)).

- **A coding agent** (Claude Code, Codex, Gemini CLI, Cursor, Claude
  Desktop) can do the AI work with no key: **AI → Coding agent** shows the
  line to connect each one, filled in for your computer
  ([how](https://jessn-dev.github.io/jobDork/ai/#coding-agent)). On Windows
  it starts `jobdork-agent.exe`, installed beside `jobdork.exe`: the same
  program with a console, which an agent needs to talk to it; nothing opens
  a window.

## Where your files are

| | Settings, database, resume | Letters and CVs |
|---|---|---|
| macOS | `~/Library/Application Support/jobdork` | `~/Documents/job-applications` |
| Windows | `%LOCALAPPDATA%\jobdork` | `Documents\job-applications` |

**Settings → Where your files are** opens them. To keep them somewhere else,
start the program with `--home <folder>` or set `JOBDORK_HOME`.

## Uninstalling

macOS: drag jobdork from Applications to the Bin. Windows: **Settings →
Apps → jobdork → Uninstall**. Either way your settings, job posts and resume
stay where they are, so a reinstall finds them; delete the folder above to
remove them too. Turn a schedule off first (**Settings → Schedule a run → Never by
itself**, then **Save**), or the system keeps trying to start a program that
is gone.

## When something goes wrong

The app writes what a terminal would show to `logs/app.log` in its folder
(never the access token). For a problem that shows only in the app, start it
with `--debug`, which adds the window's developer tools (right-click,
**Inspect**):

```bash
/Applications/jobdork.app/Contents/MacOS/jobdork --debug     # macOS
"%LOCALAPPDATA%\Programs\jobdork\jobdork.exe" --debug        # Windows, default install
```

[Report it](../../SECURITY.md#reporting-a-problem) if it is a security
problem, or through the dashboard's Feedback page otherwise.

## Building the installers yourself

```bash
pip install --require-hashes -r requirements-desktop.lock
pip install --no-deps --no-build-isolation -e .
python packaging/build.py   # macOS: dist/jobdork-0.16.1-macos-arm64.dmg
                            # Windows: dist/jobdork-0.16.1-windows-x64-setup.exe
```

The lock pins every package by version and hash, as the release builds do;
`pip install -e '.[pdf,ai,app,package]'` also works, with whatever versions
PyPI has that day. It builds for the machine it runs on; Windows also needs
[Inno Setup 6](https://jrsoftware.org/isdl.php). Before packaging, the built
app runs its own `--self-test`, and the build stops if a module or data file
is missing from it or it cannot verify a build attestation (the check its
Update button relies on). CI builds both in
[desktop.yml](../../.github/workflows/desktop.yml), after the tests and
security scans pass.
