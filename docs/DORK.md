# The dork generator

`jobdork dork` is the original tool: it builds Google searches you open and
read yourself. It reaches anything Google has indexed, including what no
job board's API exposes (role lists in public Docs, recruiter posts, hiring
managers to approach directly) and the sites jobdork does not read, such as
LinkedIn and Indeed. It needs no config and keeps nothing in the database.

It runs wherever jobdork is installed ([run/README.md](run/README.md)), from a
terminal: `jobdork dork`, or `python -m jobdork.dork`, with its own flags.

Its code is in `jobdork/dork/`, moved there rather than rewritten. Results are always saved to a plain-text file. Optionally export a named CSV, email it, open every query in your browser, or schedule the whole thing to run automatically.

---

## How it works

The tool constructs a Google search URL for every job board you select. Each URL combines Google operators to zero in on real listings:

```
site:boards.greenhouse.io
  ("mid" OR "mid-level" OR "intermediate" OR "senior" OR "sr" OR "lead" OR "staff")
  ("data engineer" OR "analytics engineer")
  ("remote" OR "work from home" OR "wfh" OR "hybrid")
  "Chicago, IL"
  after:2026-03-01
  &tbs=qdr:w
```

| Operator | Purpose |
|---|---|
| `site:` | Restrict to a specific domain / ATS portal |
| `"quoted phrase"` | Require an exact match |
| `(A OR B OR C)` | Expand search with boolean OR |
| `after:YYYY-MM-DD` | Only show results published after this date |
| `tbs=qdr:w` | Google's built-in recency filter (past week by default) |
| `filetype:pdf` | Restrict to PDF files (resume intel mode) |
| `intitle:` | Require a phrase in the page title |
| `-"phrase"` | Exclude results containing this phrase |

---

## Quick start

### Interactive mode

Run with no arguments to step through a guided prompt:

```bash
jobdork dork
```

Every prompt defaults to a sensible value — just press Enter to accept it.
Blank answers for export, email, and recurring search always mean **no**.

### CLI mode

```bash
jobdork dork \
  --title "software engineer | developer | SWE" \
  --location "Austin, TX" \
  --level "mid | senior" \
  --arrangement "remote | hybrid" \
  --since 1w \
  --csv \
  --open
```

---

## Pipe-separated OR values

`--title`, `--level`, and `--arrangement` all accept tokens separated by `|`.  
Each group is expanded into a Google boolean OR clause in every query.

```bash
# Multiple role aliases
--title "data engineer | analytics engineer | ETL developer"
# -> ("data engineer" OR "analytics engineer" OR "ETL developer")

# Multiple role levels — keywords for each level are merged
--level "mid | senior"
# -> ("mid" OR "mid-level" OR "intermediate" OR "senior" OR "sr" OR "lead" OR "staff")

# Multiple work arrangements — each token expands to its search terms
--arrangement "remote | hybrid"
# -> ("remote" OR "work from home" OR "wfh" OR "hybrid")
```

---

## All flags

### Search parameters

| Flag | Default | Description |
|---|---|---|
| `--title` | *(none)* | Role title; pipe-separate aliases for OR |
| `--location` | *(none)* | City/state — omit for location-agnostic results |
| `--level` | `any` | Role level; pipe-separate for OR: `"mid \| senior"` |
| `--arrangement` | *(none)* | Work type; pipe-separate for OR: `"remote \| hybrid \| on-site"` |
| `--benefits` | *(none)* | Benefit phrases; pipe-separate: `"visa sponsorship \| relocation"` |
| `--sites` | *(default boards)* | Space-separated board keys — or `all` for every site |
| `--since` | `1w` | Recency via Google `tbs=`: `any` `1d` `3d` `1w` `1m` |
| `--after` | *(none)* | `after:YYYY-MM-DD` operator for precise date cutoff |

### Output options

| Flag | Description |
|---|---|
| `--open` | Auto-open every query URL in browser tabs |
| `--csv` | Export to `<role>_<since>_<YYYYMMDD_HHMM>.csv` |
| `--email ADDRESS` | Email the CSV via Resend (implies `--csv`) |
| `--log-file PATH` | Custom log path (default: `./logs/job_dork.log`) |

### Automation

| Flag | Description |
|---|---|
| `--cron daily\|3d\|1w` | Install a recurring cron / Task Scheduler job |
| `--setup-email` | Interactive wizard to save Resend credentials to `.env` |

### Info flags

```bash
jobdork dork --list-sites    # all boards (standard + opt-in)
jobdork dork --list-levels   # role levels and their keyword expansions
jobdork dork --list-dates    # date filter options
jobdork dork --list-cron     # cron schedule options
```

---

## Role levels

Pass a single level or pipe-separate multiple levels.

| Level | Keywords added to query |
|---|---|
| `intern` | intern, internship, co-op, student |
| `junior` | junior, jr, entry level, associate, new grad |
| `mid` | mid, mid-level, intermediate |
| `senior` | senior, sr, lead, staff |
| `principal` | principal, staff, distinguished |
| `manager` | manager, engineering manager, team lead |
| `director` | director, head of, vp of |
| `executive` | vp, vice president, cto, cpo, c-level |
| `any` | *(no keyword filter)* |

Example — mid and senior combined:

```bash
--level "mid | senior"
# -> ("mid" OR "mid-level" OR "intermediate" OR "senior" OR "sr" OR "lead" OR "staff")
```

---

## Work arrangement tokens

| Token | Expands to |
|---|---|
| `remote` | `"remote"`, `"work from home"`, `"wfh"` |
| `hybrid` | `"hybrid"` |
| `on-site` | `"on-site"`, `"onsite"`, `"in-office"`, `"in office"` |

---

## CSV filename format

CSV files are named automatically:

```
<role_slug>_<since>_<YYYYMMDD_HHMM>.csv
```

Examples:

```
data_engineer_analytics_engineer_1w_20260327_1430.csv
software_engineer_developer_SWE_3d_20260327_0900.csv
search_1w_20260327_1800.csv          # when no title is provided
```

---

## Site strategies

### Standard boards (searched by default)

Run `jobdork dork --list-sites` for the full list. Covers:

- **Aggregators** — LinkedIn, Indeed, Glassdoor, Builtin, Dice, ZipRecruiter, Monster, CareerBuilder, FlexJobs, Wellfound, YC's Work at a Startup
- **ATS portals** — Lever, Greenhouse, Workday, Ashby, Workable, SmartRecruiters, iCIMS, Breezy, Rippling
- **Open web** — company career pages via keyword match

### Opt-in strategies

Pass these via `--sites` to unlock additional search modes:

| Key | Operator | What it finds |
|---|---|---|
| `google_docs` | `site:docs.google.com` | Startups often drop job lists in public Docs before hitting formal boards |
| `google_sheets` | `site:docs.google.com/spreadsheets` | Same pattern in spreadsheet form |
| `linkedin_posts` | `site:linkedin.com/posts` | Recruiter posts that go live before the official listing |
| `hiring_manager` | `intitle:"hiring manager"` | Pages to surface hiring managers for direct outreach |
| `pdf_resumes` | `filetype:pdf` | Publicly uploaded resumes — useful for studying formatting in your field |

```bash
# Search hidden market alongside standard boards
jobdork dork --title "product manager" \
  --sites linkedin greenhouse lever google_docs google_sheets

# Surface hiring managers for direct outreach
jobdork dork --title "machine learning engineer" \
  --sites hiring_manager linkedin_posts --open

# Study how others in your field format their resumes
jobdork dork --title "data scientist" --sites pdf_resumes --open

# Everything at once
jobdork dork --title "backend engineer" --sites all
```

---

## Advanced search techniques

### Force a precise date cutoff

Combine `--since` (Google's `tbs` param) with `--after` (the `after:` operator) for maximum precision:

```bash
jobdork dork --title "frontend engineer" --since 1m --after 2026-03-01
```

### Filter by benefits

Add quoted benefit phrases to every query:

```bash
jobdork dork --title "software engineer" \
  --benefits "visa sponsorship | relocation assistance | 4-day work week"
```

### Exclude seniority levels you're not targeting

Add minus-sign phrases directly to `--title` or add them manually to a query. For example, if you want mid-level only and want to suppress senior results, you can add them as extra quoted terms in the query after generating, or contribute an `--exclude-levels` PR.

---

## Scheduling recurring searches

### macOS / Linux (cron)

```bash
jobdork dork \
  --title "backend engineer | platform engineer" \
  --level "senior" --arrangement remote \
  --since 1w --csv --cron 1w
```

Schedules: `daily`, `3d`, `1w`

Remove: `crontab -e` → delete the line containing `# job_dork_auto`

### Windows (Task Scheduler)

Same flags — the tool detects Windows and uses `schtasks.exe` automatically.

Remove: `schtasks /Delete /TN "JobDorkSearch" /F`

---

## Email delivery (Resend)

### 1. Create a free account

- API key: <https://resend.com/api-keys>
- Verified domain: <https://resend.com/domains>

### 2. Configure credentials

```bash
jobdork dork --setup-email
```

Or create `.env` manually:

```env
RESEND_API_KEY="re_xxxxxxxxxxxx"
RESEND_FROM="Job Dork <jobs@yourdomain.com>"
```

> Add `.env` to `.gitignore` — never commit credentials.

### 3. Send results

```bash
jobdork dork --title "data engineer" --csv --email you@example.com
```

---

## Customising the tool

All of its configuration lives in **`jobdork/dork/boards.py`** — no need to
touch `generator.py`:

| Table | What to edit |
|---|---|
| `SITE_DORKS` | Add/remove job boards or search strategies |
| `DEFAULT_SITES` | Change which boards are searched by default |
| `LEVEL_KEYWORDS` | Add keywords to a role level |
| `ARRANGEMENT_TERMS` | Add synonyms for remote/hybrid/on-site |
| `DATE_FILTERS` | Add new recency presets |
| `CRON_SCHEDULES` | Add new recurring schedule options |
| `DEFAULT_DATE_FILTER` | Change the global default (currently `1w`) |

---

## Output files

| File | Description |
|---|---|
| `dork_results.txt` | Plain-text list of every query and URL, in the directory you ran it from (always written) |
| `<role>_<since>_<ts>.csv` | Structured export — produced with `--csv` or `--email` |
| `logs/job_dork.log` | Timestamped run log |

---

## Examples

```bash
# Senior remote Python roles posted in the last 3 days, open in browser
jobdork dork \
  --title "python engineer | backend engineer" \
  --level senior --arrangement remote --since 3d --open

# Mid or senior data roles in NYC, export CSV
jobdork dork \
  --title "data engineer | analytics engineer" \
  --level "mid | senior" --location "New York, NY" --since 1w --csv

# Product managers on ATS portals only
jobdork dork \
  --title "product manager | PM | product lead" \
  --level mid --sites greenhouse lever ashby workable --csv

# Weekly email digest — remote senior engineering roles
jobdork dork \
  --title "software engineer | SWE | backend engineer" \
  --level senior --arrangement remote \
  --since 1w --csv --email you@example.com --cron 1w

# Hidden job market — Google Docs/Sheets + social posts
jobdork dork \
  --title "growth marketer | growth manager" \
  --sites google_docs google_sheets linkedin_posts --open

# Roles with visa sponsorship posted after March 1st
jobdork dork \
  --title "software engineer" \
  --benefits "visa sponsorship" \
  --after 2026-03-01 --since 1m --csv
```
