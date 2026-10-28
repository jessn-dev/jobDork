# In the terminal

Every command, with no dashboard: for a server with no screen, a cron job,
or anyone who would rather type. Install as in [source.md](source.md#install);
the terminal and the dashboard read and write the same `config.yaml` and
database, so you can use both. Other ways in: [README.md](README.md).

Inside the venv (`source .venv/bin/activate`, or `.venv\Scripts\activate` on
Windows) the command is `jobdork`; without it, `.venv/bin/python -m jobdork`,
or `./run.sh <command>`.

## First run

```bash
jobdork setup        # the same questions as the dashboard's setup, then a first scan
```

Or copy `config.example.yaml` to `config.yaml` and edit it
([../CONFIG.md](../CONFIG.md); the [minimal config](../CONFIG.md#minimal-working-config)
is three lines).

**Keys come from the environment here**, since there is no AI page to type
them into: put `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY` or `GROQ_API_KEY` in
`.env` for an AI reader, and `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` or
`USAJOBS_API_KEY`/`USAJOBS_EMAIL` for those sources. The full list:
[../CONFIG.md](../CONFIG.md#environment). Ollama needs no key.

## Commands

| Command | Does |
|---|---|
| `jobdork scan` | Read the sources, screen, store. `--limit N` for a quick look, `--email you@x` to mail what is new, `--fresh` to start over (previews unless `--yes`) |
| `jobdork list` | Print stored job posts. `--new` for what the last scan added, `--flags` for why each was flagged |
| `jobdork show <uid>` | One job post in full, with the advert |
| `jobdork applied <url\|company\|uid> -s <status>` | Record what you did: `interested`, `applied`, `interviewing`, `offer`, `rejected`… `--note` adds a note |
| `jobdork add <url>` | Fetch a posting by its address into the database: any board jobdork reads, Taleo Enterprise, or any page with schema.org job markup |
| `jobdork rescreen` | Apply the current config to what is stored; `--remove` deletes what no longer matches, never a post you acted on |
| `jobdork check` | Close the postings that are gone |
| `jobdork enrich` | Fetch the full advert for posts stored as a summary |
| `jobdork prune --older-than 30` | Delete old or settled posts; previews unless `--yes` |
| `jobdork digest --email you@x` | Mail the last scan's new posts again; `--all --csv` for everything open |
| `jobdork discover <domain>` | Find an employer's job board from their own site; `--add` writes it to your config |
| `jobdork sources` | What will run, and what is dormant for want of a key |
| `jobdork judge` | AI reads the best job posts against your resume |
| `jobdork letter <uid>` | AI cover letter, checked against your resume and the advert |
| `jobdork review [<uid>]` | AI resume review, or against one post |
| `jobdork tailor <uid>` | AI resume rewritten for one post, as a PDF |
| `jobdork generate <uid> -k screen\|cv\|cover_letter` | Drafts through the `claude` CLI, which must be on your PATH |
| `jobdork serve` / `jobdork app` | The dashboard, in a browser or a window ([source.md](source.md)) |
| `jobdork dork` | The original Google search builder ([../DORK.md](../DORK.md)) |

`jobdork <command> --help` lists every option. Any setting can be overridden
for one run, checked exactly as the file is:

```bash
jobdork scan --anchor "Berlin, Germany" --country DE   # one city, in place of your list
jobdork list --title "penetration tester" --work-mode remote --salary-floor 150000
```

What each part of a scan does, and why: [ARCHITECTURE.md](../ARCHITECTURE.md#the-pipeline).

## Scheduling scans yourself

The dashboard's **Settings → Schedule a run** does this for you. By hand,
use `scan --scheduled`: it prints nothing, writes to
`logs/scheduled-scan.log` beside the config, and steps aside if another scan
is already running.

**macOS and Linux (crontab -e)**, every day at 08:00:

```cron
0 8 * * * cd /path/to/jobDork && .venv/bin/python -m jobdork scan --scheduled
```

Add `--email you@example.com` to have new posts mailed (needs
`RESEND_API_KEY` and `RESEND_FROM` in `.env`; free key at
[resend.com](https://resend.com/api-keys)). An empty digest is not sent.

**Windows (Task Scheduler):**

```bat
schtasks /Create /SC DAILY /ST 08:00 /TN jobdork-scan ^
  /TR "cmd /c cd /d C:\path\to\jobDork && .venv\Scripts\python.exe -m jobdork scan --scheduled"
```

**In Docker**, from the host: `docker exec jobdork jobdork scan --scheduled`
([docker.md](docker.md#scans-that-run-by-themselves)).
