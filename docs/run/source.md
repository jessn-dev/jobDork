# Running from source

The dashboard in your browser (or in its own window), from a clone of this
repository. Works on macOS, Windows and Linux, and is the way to run it on
Linux. For the terminal commands without a dashboard, see
[cli.md](cli.md); for the other ways in, [README.md](README.md).

## What you need

- **Python 3.10 or newer** (`python3 --version`).
- **git**, or the repository's ZIP from GitHub.
- Optional: [Ollama](https://ollama.com) for a free local AI model, or a key
  for Anthropic, Gemini, OpenAI or Groq. jobdork scans without any.

## Install

```bash
git clone https://github.com/jessn-dev/jobDork.git
cd jobDork
python3 -m venv .venv
.venv/bin/pip install -e '.[pdf]'
```

On Windows the venv's programs are in `.venv\Scripts\` rather than
`.venv/bin/`.

**The extras** add what only some people need; combine them, as in `'.[pdf,ai]'`:

| Extra | Adds | Needed for |
|---|---|---|
| `pdf` | `pypdf` | Reading a PDF resume (`.docx`, `.md` and `.txt` need nothing) |
| `ai` | `anthropic` | Anthropic as an AI reader or checker. Ollama, Gemini, OpenAI and Groq need nothing extra |
| `app` | `pywebview` (and macOS notifications) | The desktop window, `jobdork app` |
| `package` | PyInstaller, Pillow | Building the installers ([desktop.md](desktop.md#building-the-installers-yourself)) |
| `dev` | pytest, ruff | Running the tests ([Development](../../README.md#development)) |

**The place list ships with jobdork** (`jobdork/data/cities.csv`: 70,026
places with 5,000 people or more, in 245 countries, from GeoNames), so
distances work in every country from the first run. `scripts/build_gazetteer.py all`
refreshes it from GeoNames; run with no country it rebuilds the list for
your config's countries only, replacing the full one.

## Start the dashboard

```bash
.venv/bin/python -m jobdork serve      # or: jobdork serve, inside the venv
./run.sh                               # the same, finding the venv for you (macOS, Linux)
```

It opens your browser at `http://127.0.0.1:8765/?t=…`. The `t=` token is required on every request and is new each
run; copy the whole address if you open it in another browser. `--no-open`
prints the address without opening it, and `--port` picks another port when
8765 is taken.

With no config the dashboard opens on setup. Answers are saved as you go to
`config.yaml` in the folder you started from. Stop it with **Ctrl-C**: any
API key it held is forgotten.

**It is reachable from your own machine only.** It binds to loopback and has
no `--host`. To open it from another device, run it in Docker on a server
instead ([nas.md](nas.md)).

## The desktop window, from source

```bash
.venv/bin/pip install -e '.[pdf,app]'
.venv/bin/python -m jobdork app
```

The same dashboard in a window of its own, behaving as the installed app does
([desktop.md](desktop.md#using-it)), including where it keeps its files: its
own folder (`~/.local/share/jobdork` on Linux, `$XDG_DATA_HOME/jobdork` when
that is set), not the folder you start it from. `--home <folder>` or
`$JOBDORK_HOME` chooses another.

On Linux, pywebview draws the window with GTK or Qt, which come from your
distribution rather than pip; its
[installation guide](https://pywebview.flowrl.com/guide/installation.html#linux)
lists the packages. Notifications use `notify-send`.

## Your settings and data

Everything is in the folder you start from:

| | |
|---|---|
| `config.yaml` | Your settings. `config.local.yaml` wins when both exist; `-c <file>` or `JOBDORK_CONFIG` names another |
| `.env` | Keys for the terminal and job sources, one `NAME=value` per line ([../CONFIG.md](../CONFIG.md#environment)) |
| `data/` | The database, the uploaded resume, source keys, backups, logs |
| `out/` | The static page and JSON each scan writes |
| `~/Documents/job-applications/` | Cover letters, CVs and drafts, one folder per job |

None of these is in the repository: `config.yaml`, `.env`, `data/` and `out/`
are gitignored, so a `git pull` never touches them. To start again from setup,
`./run.sh clean` deletes them from this folder (it lists what it will delete
and asks first; `.env` is kept).

Prefer writing the config by hand? Copy `config.example.yaml` to
`config.yaml`; a config you write yourself skips setup.

## Updating

```bash
git pull
.venv/bin/pip install -e '.[pdf]'      # the same extras as before
```

The database is brought up to date on the next start. The dashboard's
"newer version" banner links to the release; from source, `git pull` is the
update.

## Scans that run by themselves

**Settings → Schedule a run** works from source too: it adds an entry to
launchd (macOS), Task Scheduler (Windows) or crontab (Linux) that runs
`jobdork scan --scheduled` in this folder. Or schedule it yourself:
[cli.md](cli.md#scheduling-scans-yourself).
