# Ways to run jobdork

jobdork is one program with four ways in. Each keeps its own settings and
database, so pick one and stay with it; moving later means copying one
folder (see [Moving between them](#moving-between-them)).

| | You get | You need | Guide |
|---|---|---|---|
| **The desktop app** | The dashboard in a window of its own, from an installer. Scheduled scans, notifications, an Update button | A Mac with Apple Silicon, or Windows 10/11 (64-bit) | [desktop.md](desktop.md) |
| **From source, in your browser** | The same dashboard, in a browser tab, started from a terminal | Python 3.10 or newer, on macOS, Windows or Linux | [source.md](source.md) |
| **From source, in the terminal** | Every command (`scan`, `list`, `applied`, `judge`…) with no dashboard at all; good for cron and scripts | The same install as above | [cli.md](cli.md) |
| **Docker, on your computer** | The dashboard from the published image, nothing installed but Docker | Docker | [docker.md](docker.md) |
| **Docker, on a NAS or home server** | jobdork always on, opened from your laptop or phone anywhere, the AI on another computer | A NAS with Docker; Tailscale | [nas.md](nas.md) |

**The AI on another computer.** Whichever way you run it, the AI models can
run on another computer of yours, one model on each when one computer cannot
hold both: [ai-on-two-computers.md](ai-on-two-computers.md).

**Not sure?** Take the desktop app on a Mac (Apple Silicon or Intel) or a
Windows PC. On Linux there is no installer: run it [from source](source.md), which
also gives you the desktop window (`jobdork app`). Use the NAS guide only if
you want it running while your computer is off.

`jobdork dork`, the original Google search builder, works in every one of
them from a terminal; its flags are in [../DORK.md](../DORK.md).

---

## What is the same everywhere

Once it is open, the app is the same whichever way you run it: the
[user guide](https://jessn-dev.github.io/jobDork/overview/) shows every page.

- **The first start opens setup**, one question per screen: your resume, an
  AI model (or skip it), the job titles, where you are, pay, and what will
  be searched. It ends with a first scan. Answers are saved as you go, so
  stopping and starting again comes back to the same step.
- **Every setting** is in one `config.yaml`, written by setup and the
  dashboard, or by hand: [../CONFIG.md](../CONFIG.md).
- **Keys are never written to a file.** AI keys and job-source keys (Adzuna,
  USAJOBS) are held in memory and asked for again after jobdork closes, or,
  if you choose, kept in your computer's keychain (macOS Keychain, Windows
  Credential Manager, Secret Service on Linux). In Docker, which has no
  keychain, give them in the environment or `.env`, which always win.
- **Feedback's Send works out of the box.** It goes to the maintainers'
  relay, whose address is built into jobdork itself, in every way of
  running it: nothing to set up, and no key in the app (the relay holds
  them; [relay/feedback](../../relay/feedback/README.md)).
  `JOBDORK_FEEDBACK_URL=off` turns Send off, or names another relay.
- **The dashboard needs its token.** The address it prints or opens carries
  `?t=…`; the token is new each time it starts.

## Where each one keeps your files

| | Settings and database | Resume, letters, CVs |
|---|---|---|
| Desktop app | `~/Library/Application Support/jobdork` (macOS), `%LOCALAPPDATA%\jobdork` (Windows), `~/.local/share/jobdork` (Linux, from source) | `~/Documents/job-applications` |
| From source | The folder you start it in: `config.yaml` (or `config.local.yaml`, which wins), `data/`, `out/` | Resume in `data/`, documents in `~/Documents/job-applications` |
| Docker | The folder mapped to `/app/data` | `data/documents` in the same folder |

In the dashboard, **Settings → Where your files are** opens them.

## Moving between them

Copy the settings and database folder from one to the other while neither is
running: `config.yaml` and `data/` (the desktop app keeps `config.yaml` and
`data/` inside its folder too). In Docker, `config.yaml` goes inside the
mapped data folder. The resume path in `config.yaml` may need changing to
where the resume now is; the Resume page can upload it again instead.
