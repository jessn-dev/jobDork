# Google Dork Job Search Generator

Builds targeted Google search queries ("dorks") that surface job postings
across LinkedIn, Indeed, Glassdoor, 20+ ATS portals, and company career
pages — all from the command line.

Results are saved to a plain-text file automatically. Optionally export to
CSV, email the CSV, open every query in your browser, and schedule recurring
searches via cron (macOS/Linux) or Task Scheduler (Windows).

---

## How it works

The tool constructs a Google search URL for every job board you select.
Each URL uses Google operators to zero in on real job listings:

```
site:boards.greenhouse.io ("senior" OR "lead" OR "staff") ("data engineer" OR "analytics engineer") ("remote" OR "work from home" OR "wfh") &tbs=qdr:w
```

- **`site:`** restricts results to a specific job board or ATS portal
- **Quoted phrases** require exact matches
- **`OR` groups** in parentheses expand your search to role aliases and work arrangements
- **`tbs=qdr:w`** filters Google results to the past week (default)

---

## Requirements

- Python 3.10+
- [`resend`](https://pypi.org/project/resend/) Python package (email delivery only)

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Quick start

### Interactive mode

Run with no arguments to step through a guided prompt:

```bash
./run.sh
# or
python main.py
```

You'll be asked for:

| Prompt | Example input |
|---|---|
| Job title / role(s) | `data engineer \| analytics engineer` |
| Location | `Chicago, IL` |
| Seniority level | `senior` |
| Work arrangement | `remote \| hybrid` |
| Sites to search | *(blank = all boards)* |
| Posted within | *(blank = past week)* |
| Export to CSV? | `y` / *(blank = no)* |
| Email CSV to | *(blank = skip)* |
| Open in browser? | `y` / *(blank = no)* |
| Recurring search | `1w` / *(blank = skip)* |

### CLI mode

```bash
python main.py \
  --title "software engineer | developer | SWE" \
  --location "Austin, TX" \
  --level senior \
  --arrangement "remote | hybrid" \
  --since 1w \
  --sites linkedin indeed greenhouse lever \
  --csv \
  --open
```

All options are described below. Run `python main.py --help` for a full reference.

---

## Pipe-separated OR values

Both `--title` and `--arrangement` accept tokens separated by `|`.
Each token group is wrapped in a Google boolean OR clause.

```bash
# Title OR group
--title "data engineer | analytics engineer | ETL developer"
# -> ("data engineer" OR "analytics engineer" OR "ETL developer")

# Arrangement OR group
--arrangement "remote | hybrid"
# -> ("remote" OR "work from home" OR "wfh" OR "hybrid")
```

Valid arrangement tokens:

| Token | Expands to |
|---|---|
| `remote` | `"remote" OR "work from home" OR "wfh"` |
| `hybrid` | `"hybrid"` |
| `on-site` | `"on-site" OR "onsite" OR "in-office" OR "in office"` |

Leave `--arrangement` blank to skip the filter and return all posting types.

---

## All flags

### Search parameters

| Flag | Default | Description |
|---|---|---|
| `--title` | *(none)* | Job title or pipe-separated role aliases |
| `--location` | *(none)* | City/state — omit for location-agnostic results |
| `--level` | `any` | Seniority: `intern` `junior` `mid` `senior` `principal` `manager` `director` `executive` `any` |
| `--arrangement` | *(none)* | Work type: `remote \| hybrid \| on-site` (pipe-separated) |
| `--sites` | *(all)* | Space-separated board keys (see `--list-sites`) |
| `--since` | `1w` | Recency: `any` `1d` `3d` `1w` `1m` |

### Output options

| Flag | Description |
|---|---|
| `--open` | Auto-open every query URL in browser tabs |
| `--csv` | Export results to a timestamped `dork_results_<ts>.csv` |
| `--email ADDRESS` | Email the CSV via Resend (implies `--csv`) |
| `--log-file PATH` | Custom log path (default: `./logs/job_dork.log`) |

### Automation

| Flag | Description |
|---|---|
| `--cron daily\|3d\|1w` | Install a recurring cron job (macOS/Linux) or Task Scheduler task (Windows) |
| `--setup-email` | Interactive wizard to save Resend credentials to `.env` |

### Info flags

```bash
python main.py --list-sites    # all supported job boards
python main.py --list-levels   # seniority levels and their keywords
python main.py --list-dates    # date filter options
python main.py --list-cron     # cron schedule options
```

---

## Output files

Every run produces:

| File | Description |
|---|---|
| `dork_results.txt` | Plain-text list of every query and URL |
| `dork_results_<timestamp>.csv` | Structured export (with `--csv` or `--email`) |
| `logs/job_dork.log` | Timestamped run log |

---

## Supported job boards

Run `python main.py --list-sites` for the full list. Includes:

**Aggregators** — LinkedIn, Indeed, Glassdoor, Builtin, Dice, ZipRecruiter,
Monster, CareerBuilder, FlexJobs, Wellfound, YC's Work at a Startup

**ATS portals** — Lever, Greenhouse, Workday, Ashby, SmartRecruiters,
iCIMS, Breezy, Rippling

**Open web** — Company career pages via a broad keyword match

Omit `--sites` to search all boards in a single run.

---

## Scheduling recurring searches

### macOS / Linux (cron)

```bash
# Install a weekly cron job that re-runs your current search
python main.py --title "backend engineer" --level senior --arrangement remote \
               --csv --cron 1w
```

Available schedules: `daily`, `3d`, `1w`

To remove: run `crontab -e` and delete the line containing `# job_dork_auto`.

### Windows (Task Scheduler)

Same flags — the tool uses `schtasks.exe` automatically when run on Windows.

To remove: `schtasks /Delete /TN "JobDorkSearch" /F`

---

## Email delivery (Resend)

The tool uses [Resend](https://resend.com) to email CSV results.

### 1. Create a free Resend account

- Get an API key: <https://resend.com/api-keys>
- Verify a sending domain: <https://resend.com/domains>

### 2. Configure credentials

Run the interactive wizard:

```bash
python main.py --setup-email
```

Or create a `.env` file manually:

```env
RESEND_API_KEY="re_xxxxxxxxxxxx"
RESEND_FROM="Job Dork <jobs@yourdomain.com>"
```

> **Security:** add `.env` to `.gitignore` so credentials are never committed.

### 3. Send results

```bash
python main.py --title "product manager" --csv --email you@example.com
```

---

## Examples

```bash
# All senior remote Python roles posted in the last 3 days
python main.py \
  --title "python engineer | backend engineer | software engineer" \
  --level senior --arrangement remote --since 3d --open

# Data roles in NYC, export to CSV
python main.py \
  --title "data engineer | analytics engineer" \
  --location "New York, NY" --since 1w --csv

# Search only Greenhouse and Lever for product managers
python main.py \
  --title "product manager | PM | product lead" \
  --level mid --sites greenhouse lever --csv

# Weekly email digest of remote senior engineering roles
python main.py \
  --title "software engineer | SWE | backend engineer" \
  --level senior --arrangement remote \
  --since 1w --csv --email you@example.com --cron 1w
```

---

## Project structure

```
.
├── main.py          # main script
├── run.sh           # shell wrapper (auto-detects venv)
├── requirements.txt # Python dependencies
├── .env             # Resend credentials (create via --setup-email)
├── logs/
│   └── job_dork.log
├── dork_results.txt          # latest plain-text results
└── dork_results_<ts>.csv     # CSV exports
```

---

## License

MIT
