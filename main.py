#!/usr/bin/env python3
"""
Google Dork Job Search Generator
================================
Builds targeted Google dork queries to surface job postings on LinkedIn,
Indeed, Glassdoor, company career pages, and more.

Usage:
    python main.py                                 # interactive mode
    python main.py --help                          # show all flags
    ./run.sh --help                                # run via wrapper (recommended)

    python main.py \
        --title "software engineer" \
        --location "Chicago, IL" \
        --level senior \
        --since 3d \
        --remote \
        --sites linkedin indeed glassdoor \
        --csv \
        --email you@gmail.com \
        --open

    # Schedule to run automatically every week:
    python main.py --title "data engineer" --level senior --since 1w --csv --cron 1w

Flags:
    --remote          Add "remote" keyword to every query
    --csv             Export results to a timestamped CSV file
    --email ADDR      Send the CSV to this address after generation
                      (requires Resend — see EMAIL SETUP below)
    --cron SCHEDULE   Install a cron job: daily | 3d | 1w
    --setup-email     Interactive wizard to configure Resend (.env)

Date filter options (--since):
    any   -> no date filter (default)
    1d    -> past 24 hours
    3d    -> past 3 days
    1w    -> past week
    1m    -> past month

─────────────────────────────────────────────────────
EMAIL SETUP (Resend)
─────────────────────────────────────────────────────
Create an API key and verify a sending domain, then set (or use --setup-email):

    RESEND_API_KEY       API key (starts with re_)
    RESEND_FROM          Verified sender, e.g. "Job Dork <jobs@yourdomain.com>"

Docs:
  • https://resend.com/api-keys
  • https://resend.com/domains
  • https://resend.com/docs/send-with-fastapi
─────────────────────────────────────────────────────
"""

import argparse
import base64
import csv
import logging
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import traceback
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path

import resend
from resend.exceptions import ResendError


SCRIPT_NAME = Path(__file__).name
RUN_SCRIPT_NAME = "run.sh"
LOG_DIR = Path(__file__).parent / "logs"
DEFAULT_LOG_FILE = LOG_DIR / "job_dork.log"
LOGGER = logging.getLogger("job_dork")

# ─────────────────────────────────────────────
# Optional .env loader (no dotenv dependency)
# ─────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent / ".env"


def _load_dotenv():
    """Load key=value pairs from .env into os.environ (if file exists)."""
    if not _ENV_FILE.exists():
        return
    try:
        with open(_ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    except OSError as e:
        print(f"[WARN] Failed to read {_ENV_FILE}: {e}")


def _write_private_env(lines: list[str]) -> None:
    """
    Write .env and lock permissions to user-read/write where supported.
    """
    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(_ENV_FILE, 0o600)
    except OSError:
        # Best-effort only (not all platforms/filesystems honor chmod).
        pass


def _looks_like_email(addr: str) -> bool:
    """Reasonable email sanity check for user-provided recipients."""
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", addr.strip()))


def setup_logging(log_file: str = "") -> Path:
    """
    Configure app logging to file + console.
    Returns the resolved log path.
    """
    if log_file:
        log_path = Path(log_file).expanduser()
    else:
        log_path = DEFAULT_LOG_FILE
    if not log_path.is_absolute():
        log_path = Path(__file__).parent / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    LOGGER.addHandler(stream_handler)

    LOGGER.info("Logging initialized")
    LOGGER.info("Log file: %s", log_path.resolve())
    return log_path.resolve()


def _log_unhandled_exception(exc_type, exc_value, exc_tb) -> None:
    """Write uncaught exceptions to log with traceback."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    LOGGER.critical(
        "Unhandled exception:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    )
    sys.__excepthook__(exc_type, exc_value, exc_tb)


_load_dotenv()


# ─────────────────────────────────────────────
# Config: date filter -> Google tbs parameter
# Google's tbs=qdr:<unit><n> means "past N units"
#   d  = days  |  w = weeks  |  m = months
# ─────────────────────────────────────────────
DATE_FILTERS = {
    "any": {"tbs": None,      "label": "No date filter"},
    "1d":  {"tbs": "qdr:d",   "label": "Past 24 hours"},
    "3d":  {"tbs": "qdr:d3",  "label": "Past 3 days"},
    "1w":  {"tbs": "qdr:w",   "label": "Past week"},
    "1m":  {"tbs": "qdr:m",   "label": "Past month"},
}

# ─────────────────────────────────────────────
# Config: cron schedule expressions
# ─────────────────────────────────────────────
CRON_SCHEDULES = {
    "daily": {"expr": "0 8 * * *",   "label": "Every day at 8:00 AM"},
    "3d":    {"expr": "0 8 */3 * *", "label": "Every 3 days at 8:00 AM"},
    "1w":    {"expr": "0 8 * * 1",   "label": "Every Monday at 8:00 AM"},
}

# ─────────────────────────────────────────────
# Config: seniority keyword mappings
# ─────────────────────────────────────────────
SENIORITY_KEYWORDS = {
    "intern":     ["intern", "internship", "co-op", "student"],
    "junior":     ["junior", "jr", "entry level", "entry-level", "associate", "new grad"],
    "mid":        ["mid", "mid-level", "intermediate"],
    "senior":     ["senior", "sr", "lead", "staff"],
    "principal":  ["principal", "staff", "distinguished"],
    "manager":    ["manager", "engineering manager", "em", "team lead"],
    "director":   ["director", "head of", "vp of"],
    "executive":  ["vp", "vice president", "cto", "cpo", "c-level"],
    "any":        [],
}

# ─────────────────────────────────────────────
# Config: site-specific dork templates
# Each value is a (site_operator, path_hint) tuple.
# ─────────────────────────────────────────────
SITE_DORKS = {
    "linkedin":    ("site:linkedin.com",          "/jobs/view OR /jobs/search"),
    "indeed":      ("site:indeed.com",            "/viewjob OR /jobs"),
    "glassdoor":   ("site:glassdoor.com",         "/job-listing OR /Jobs"),
    "lever":       ("site:jobs.lever.co",         ""),
    "greenhouse":  ("site:boards.greenhouse.io",  ""),
    "workday":     ("site:myworkdayjobs.com",     ""),
    "ashby":       ("site:jobs.ashbyhq.com",      ""),
    "builtin":     ("site:builtin.com",           "/jobs"),
    "dice":        ("site:dice.com",              "/jobs/detail"),
    "simplyhired": ("site:simplyhired.com",       "/job"),
    "ziprecruiter":("site:ziprecruiter.com",      "/jobs"),
    "careers":     ("",                           'careers OR "job openings" OR "we\'re hiring"'),
}

GOOGLE_BASE = "https://www.google.com/search?q="


# ══════════════════════════════════════════════
# Query builder
# ══════════════════════════════════════════════

def build_query(
    title: str,
    location: str,
    level: str,
    site_key: str,
    extra_keywords: list = None,
    date_filter: str = "any",
    remote: bool = False,
) -> tuple:
    """
    Construct a single Google dork query string.
    Returns (raw_query, full_url).
    """
    parts = []
    site_op, path_hint = SITE_DORKS.get(site_key, ("", ""))

    # 1. Site operator
    if site_op:
        parts.append(site_op)

    # 2. Seniority keywords
    level_words = [w for w in SENIORITY_KEYWORDS.get(level.lower(), []) if w]
    if level_words:
        if len(level_words) == 1:
            parts.append(f'"{level_words[0]}"')
        else:
            parts.append("(" + " OR ".join(f'"{w}"' for w in level_words) + ")")

    # 3. Job title
    if title:
        parts.append(f'"{title}"')

    # 4. Remote keyword — inserted before location so it groups naturally
    if remote:
        parts.append('("remote" OR "work from home" OR "wfh")')

    # 5. Location
    if location:
        parts.append(f'"{location}"')

    # 6. Path hint
    if path_hint:
        parts.append(path_hint)

    # 7. Extra keywords
    if extra_keywords:
        for kw in extra_keywords:
            parts.append(f'"{kw}"' if " " in kw else kw)

    raw_query = " ".join(parts)

    # 8. Build URL + optional tbs date param
    tbs_value = DATE_FILTERS.get(date_filter, {}).get("tbs")
    encoded_q = urllib.parse.quote_plus(raw_query)
    url = f"{GOOGLE_BASE}{encoded_q}"
    if tbs_value:
        url += f"&tbs={tbs_value}"

    return raw_query, url


# ══════════════════════════════════════════════
# CSV export
# ══════════════════════════════════════════════

def export_to_csv(rows: list, filename: str = None) -> Path:
    """Write result rows to a CSV file. Returns the Path written."""
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dork_results_{ts}.csv"

    out_path = Path(filename)
    fieldnames = [
        "site", "title", "location", "level", "remote",
        "date_filter", "query", "url", "generated_at",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  CSV exported  -> {out_path.resolve()}")
    return out_path


# ══════════════════════════════════════════════
# Email delivery (Resend)
# ══════════════════════════════════════════════


def _resend_api_key() -> str:
    """API key from environment / .env (after _load_dotenv)."""
    return (os.environ.get("RESEND_API_KEY") or "").strip()


def _resend_from_address() -> str:
    """Verified sender: RESEND_FROM or JOB_DORK_EMAIL_FROM."""
    return (
        os.environ.get("RESEND_FROM")
        or os.environ.get("JOB_DORK_EMAIL_FROM")
        or ""
    ).strip()


def send_email(to_addr: str, csv_path: Path, job_config: dict) -> None:
    """Send the CSV results file as an email attachment via Resend."""
    api_key = _resend_api_key()
    from_addr = _resend_from_address()
    to_addr = to_addr.strip()
    LOGGER.info("Preparing to send email to %s", to_addr)

    if not _looks_like_email(to_addr):
        LOGGER.error("Invalid recipient email address: %r", to_addr)
        print(f"[ERROR] Invalid recipient email address: {to_addr!r}")
        sys.exit(1)

    if not api_key:
        LOGGER.error("Missing RESEND_API_KEY")
        print("\n[ERROR] Resend is not configured: missing RESEND_API_KEY.")
        print(f"  Run:  python {SCRIPT_NAME} --setup-email")
        print("  Or set RESEND_API_KEY (see EMAIL SETUP in --help).")
        print("  -> https://resend.com/api-keys")
        sys.exit(1)

    if not from_addr:
        LOGGER.error("Missing RESEND_FROM / JOB_DORK_EMAIL_FROM")
        print("\n[ERROR] Missing sender address: set RESEND_FROM in .env or environment.")
        print('  Example: RESEND_FROM="Job Dork <jobs@yourdomain.com>"')
        print("  The domain must be verified in Resend.")
        print("  -> https://resend.com/domains")
        sys.exit(1)

    if not csv_path.exists():
        LOGGER.error("CSV attachment not found: %s", csv_path)
        print(f"[ERROR] CSV attachment not found: {csv_path}")
        sys.exit(1)

    # Resend limits total payload to ~40MB after base64 encoding.
    # 30MB raw is a conservative cap to avoid request rejection.
    raw_bytes = csv_path.read_bytes()
    if len(raw_bytes) > 30 * 1024 * 1024:
        LOGGER.error("CSV too large for attachment: %s bytes", len(raw_bytes))
        print("[ERROR] CSV is too large for email attachment (>30MB raw).")
        print("  Regenerate with fewer sites/keywords or send manually.")
        sys.exit(1)

    resend.api_key = api_key
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = (
        f"Job Dork Results | {job_config.get('title', 'Search')} "
        f"[{job_config.get('level', 'any')}] | {ts}"
    )

    body = "\n".join([
        f"Your job dork search completed at {ts}.",
        "",
        "Search parameters:",
        f"  Title    : {job_config.get('title') or '(any)'}",
        f"  Location : {job_config.get('location') or '(any)'}",
        f"  Level    : {job_config.get('level', 'any')}",
        f"  Remote   : {'Yes' if job_config.get('remote') else 'No'}",
        f"  Posted   : {DATE_FILTERS.get(job_config.get('date_filter', 'any'), {}).get('label', 'N/A')}",
        "",
        f"Results are attached as: {csv_path.name}",
        "",
        f"-- {SCRIPT_NAME}",
    ])

    attach_b64 = base64.standard_b64encode(raw_bytes).decode("ascii")
    params: resend.Emails.SendParams = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
        "attachments": [
            {
                "filename": csv_path.name,
                "content": attach_b64,
                "content_type": "text/csv",
            }
        ],
    }

    print("  Sending via Resend ...")
    try:
        result = resend.Emails.send(params)
        eid = result.get("id", "?")
        LOGGER.info("Email sent to %s with id %s", to_addr, eid)
        print(f"  Email sent    -> {to_addr}  (id: {eid})")
    except ResendError as e:
        LOGGER.error("Resend API error (%s): %s", e.error_type, e.message)
        print(f"[ERROR] Resend API error ({e.error_type}): {e.message}")
        if e.suggested_action:
            print(f"  {e.suggested_action.strip()}")
        sys.exit(1)
    except Exception as e:
        LOGGER.exception("Unexpected error while sending email")
        print(f"[ERROR] Failed to send email: {e}")
        sys.exit(1)


def setup_email_wizard() -> None:
    """Interactive wizard to write Resend settings to .env file."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   ✉   Resend email setup                 ║")
    print("╚══════════════════════════════════════════╝\n")
    print("Create an API key: https://resend.com/api-keys")
    print("Verify a domain:  https://resend.com/domains\n")
    print(f"Values will be saved to: {_ENV_FILE}")
    print("Add .env to your .gitignore to keep your API key private.\n")

    api_key = input("Resend API key (re_...) : ").strip()
    if not api_key:
        print("[ERROR] RESEND_API_KEY is required.")
        sys.exit(1)
    if not api_key.startswith("re_"):
        print("  [WARN] Keys usually start with re_ — double-check you pasted the API key.\n")

    frm = input(
        'From (verified sender), e.g. Job Dork <jobs@yourdomain.com> : '
    ).strip()
    if not frm:
        print("[ERROR] RESEND_FROM is required.")
        sys.exit(1)

    lines = [
        f"# {SCRIPT_NAME} — Resend (keep private). Docs: https://resend.com/docs/send-with-fastapi",
        f'RESEND_API_KEY="{api_key}"',
        f'RESEND_FROM="{frm}"',
    ]
    _write_private_env(lines)

    print(f"\n  Saved -> {_ENV_FILE}")

    # Quick send test
    test = input("\nSend a test email now? [y/N]: ").strip().lower()
    if test == "y":
        to = input("Send test to (recipient email): ").strip()
        if not to:
            print("  Skipped — no recipient.")
        elif not _looks_like_email(to):
            print(f"  Skipped — invalid email address: {to!r}")
        else:
            _load_dotenv()
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".csv", delete=False, encoding="utf-8"
                ) as tf:
                    tf.write(
                        "site,query,url\ntest,test query,https://google.com\n"
                    )
                    tmp_path = Path(tf.name)
                send_email(to, tmp_path, {"title": "TEST", "level": "any"})
            finally:
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)


# ══════════════════════════════════════════════
# Cron / Task Scheduler installer
# ══════════════════════════════════════════════

def _rebuild_argv_without_cron() -> list:
    """Return sys.argv[1:] with --cron and its value stripped, --csv added."""
    cleaned = []
    skip_next = False
    for tok in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if tok == "--cron":
            skip_next = True
            continue
        if tok.startswith("--cron="):
            continue
        cleaned.append(tok)
    if "--csv" not in cleaned:
        cleaned.append("--csv")
    return cleaned


def install_cron(schedule_key: str) -> None:
    """Install (or update) a crontab / Task Scheduler entry for this script."""
    LOGGER.info("Installing scheduler entry: %s", schedule_key)
    if platform.system() == "Windows":
        _install_windows_task(schedule_key)
        return

    if schedule_key not in CRON_SCHEDULES:
        LOGGER.error("Unknown cron schedule: %s", schedule_key)
        print(f"[ERROR] Unknown cron schedule '{schedule_key}'. "
              f"Choose: {', '.join(CRON_SCHEDULES)}")
        sys.exit(1)

    sched     = CRON_SCHEDULES[schedule_key]
    cron_expr = sched["expr"]
    label     = sched["label"]
    marker    = "# job_dork_auto"

    project_dir = Path(__file__).resolve().parent
    run_script = project_dir / RUN_SCRIPT_NAME
    argv_tail = _rebuild_argv_without_cron()
    if run_script.exists():
        cmd = shlex.join(["bash", str(run_script)] + argv_tail)
    else:
        python = sys.executable
        script = Path(__file__).resolve()
        cmd = shlex.join([str(python), str(script)] + argv_tail)
        print(f"[WARN] {RUN_SCRIPT_NAME} not found; cron will call Python directly.")
    cron_line = f"{cron_expr}  {cmd}  {marker}"

    print(f"  Schedule  : {label}  ({cron_expr})")
    print(f"  Command   : {cmd}\n")

    confirm = input("Install this cron job? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted — no changes made.")
        return

    # Read existing crontab, strip old job_dork entry, append new one
    try:
        existing = subprocess.check_output(
            ["crontab", "-l"], stderr=subprocess.DEVNULL
        ).decode()
    except subprocess.CalledProcessError:
        existing = ""

    lines = [l for l in existing.splitlines() if marker not in l]
    lines.append(cron_line)
    new_crontab = "\n".join(lines) + "\n"

    proc = subprocess.run(
        ["crontab", "-"], input=new_crontab.encode(), capture_output=True
    )
    if proc.returncode != 0:
        LOGGER.error("crontab write failed: %s", proc.stderr.decode().strip())
        print(f"[ERROR] crontab write failed:\n{proc.stderr.decode()}")
        sys.exit(1)
    LOGGER.info("Cron installed successfully with schedule %s", schedule_key)

    print(f"\n  Cron job installed -> runs {label.lower()}")
    print(f"  View all jobs  :  crontab -l")
    print(f"  Edit/remove    :  crontab -e   (delete line containing '{marker}')")


def _install_windows_task(schedule_key: str) -> None:
    """Install a Windows Task Scheduler task via schtasks.exe."""
    LOGGER.info("Installing Windows task schedule: %s", schedule_key)
    trigger_map = {
        "daily": ["/SC", "DAILY", "/ST", "08:00"],
        "3d":    ["/SC", "DAILY", "/MO", "3", "/ST", "08:00"],
        "1w":    ["/SC", "WEEKLY", "/D", "MON", "/ST", "08:00"],
    }
    label_map = {
        "daily": "every day at 08:00",
        "3d":    "every 3 days at 08:00",
        "1w":    "every Monday at 08:00",
    }
    if schedule_key not in trigger_map:
        LOGGER.error("Unknown Windows schedule: %s", schedule_key)
        print(f"[ERROR] Unknown schedule '{schedule_key}'.")
        sys.exit(1)

    label     = label_map[schedule_key]
    python    = sys.executable
    script    = Path(__file__).resolve()
    argv_tail = _rebuild_argv_without_cron()
    tr_cmd    = subprocess.list2cmdline([str(python), str(script)] + argv_tail)
    task_name = "JobDorkSearch"

    print(f"  Schedule  : {label}")
    print(f"  Command   : {tr_cmd}\n")

    confirm = input("Install this scheduled task? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted — no changes made.")
        return

    schtasks_args = [
        "schtasks",
        "/Create",
        "/F",
        "/TN",
        task_name,
        "/TR",
        tr_cmd,
        *trigger_map[schedule_key],
    ]
    result = subprocess.run(schtasks_args, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip() or "(no output)"
        LOGGER.error("schtasks failed: %s", err)
        print(f"[ERROR] schtasks failed:\n{err}")
        sys.exit(1)
    LOGGER.info("Windows scheduled task installed successfully")

    print(f"\n  Task '{task_name}' scheduled -> {label}")
    print(f"  View  :  schtasks /Query /TN \"{task_name}\"")
    print(f"  Remove:  schtasks /Delete /TN \"{task_name}\" /F")


# ══════════════════════════════════════════════
# Interactive mode
# ══════════════════════════════════════════════

def run_interactive() -> dict:
    """Prompt user for all inputs, return config dict for run()."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   🔍  Google Dork Job Search Tool        ║")
    print("╚══════════════════════════════════════════╝\n")

    title    = input("Job title / role   (e.g. 'data engineer'): ").strip()
    location = input("Location           (e.g. 'Austin, TX' or leave blank): ").strip()

    print(f"\nSeniority levels: {', '.join(SENIORITY_KEYWORDS.keys())}")
    level  = input("Seniority level    (default: any): ").strip() or "any"
    remote = input("Remote only?       [y/N]: ").strip().lower() == "y"

    print(f"\nAvailable sites: {', '.join(SITE_DORKS.keys())}")
    sites_in = input("Sites to search    (space-separated, default: all): ").strip()
    sites    = sites_in.split() if sites_in else list(SITE_DORKS.keys())

    extra_in = input("\nExtra keywords     (optional, space-separated): ").strip()
    extra    = extra_in.split() if extra_in else []

    print(f"\nDate filters: {', '.join(DATE_FILTERS.keys())}")
    since = input("Posted within      (default: any): ").strip() or "any"
    if since not in DATE_FILTERS:
        print(f"[WARN] Unknown filter '{since}', defaulting to 'any'.")
        since = "any"

    do_csv = input("\nExport results to CSV? [y/N]: ").strip().lower() == "y"

    email = ""
    if do_csv:
        email = input("Email CSV to (leave blank to skip): ").strip()

    open_b = input("Auto-open in browser? [y/N]: ").strip().lower() == "y"

    cron = ""
    sched_opts = "/".join(CRON_SCHEDULES.keys())
    cron_in = input(
        f"\nSchedule recurring search? ({sched_opts}/no) [no]: "
    ).strip().lower()
    if cron_in in CRON_SCHEDULES:
        cron = cron_in

    return dict(
        title=title, location=location, level=level, remote=remote,
        sites=sites, extra=extra, date_filter=since,
        do_csv=do_csv, email=email, open_browser=open_b, cron=cron,
    )


# ══════════════════════════════════════════════
# Main runner
# ══════════════════════════════════════════════

def run(
    title: str,
    location: str,
    level: str,
    sites: list,
    extra: list,
    open_browser: bool,
    date_filter: str = "any",
    remote: bool = False,
    do_csv: bool = False,
    email: str = "",
    cron: str = "",
) -> None:
    LOGGER.info(
        "Run started | title=%r location=%r level=%r sites=%d remote=%s since=%s csv=%s email=%s cron=%s",
        title, location, level, len(sites), remote, date_filter, do_csv, bool(email), bool(cron),
    )

    # ── Validate ─────────────────────────────
    if level not in SENIORITY_KEYWORDS:
        LOGGER.warning("Unknown level provided: %s", level)
        print(f"[WARN] Unknown level '{level}', defaulting to 'any'.")
        level = "any"
    if date_filter not in DATE_FILTERS:
        LOGGER.warning("Unknown date filter provided: %s", date_filter)
        print(f"[WARN] Unknown date filter '{date_filter}', defaulting to 'any'.")
        date_filter = "any"

    unknown_sites = [s for s in sites if s not in SITE_DORKS]
    if unknown_sites:
        LOGGER.warning("Unknown sites ignored: %s", unknown_sites)
        print(f"[WARN] Unknown sites ignored: {unknown_sites}")
        sites = [s for s in sites if s in SITE_DORKS]
    if not sites:
        LOGGER.error("No valid sites specified after filtering")
        print("[ERROR] No valid sites specified.")
        sys.exit(1)

    date_label = DATE_FILTERS[date_filter]["label"]
    ts         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Summary header ────────────────────────
    print(f"\n{'─'*62}")
    print(f"  Title    : {title or '(any)'}")
    location_display = location or "(any)"
    if remote:
        location_display += "  + remote"
    print(f"  Location : {location_display}")
    print(f"  Level    : {level}")
    print(f"  Posted   : {date_label}")
    print(f"  Remote   : {'Yes' if remote else 'No'}")
    print(f"  Sites    : {', '.join(sites)}")
    print(f"{'─'*62}\n")

    # ── Build queries ─────────────────────────
    rows = []
    for site_key in sites:
        raw, url = build_query(
            title, location, level, site_key,
            extra, date_filter, remote,
        )
        rows.append({
            "site":         site_key,
            "title":        title,
            "location":     location,
            "level":        level,
            "remote":       "yes" if remote else "no",
            "date_filter":  date_label,
            "query":        raw,
            "url":          url,
            "generated_at": ts,
        })
        print(f"[{site_key.upper():12s}]  {raw}")
        print(f"  -> {url}\n")

    # ── Open browser ──────────────────────────
    if open_browser:
        LOGGER.info("Opening %d browser tabs", len(rows))
        print(f"Opening {len(rows)} tab(s) in your browser ...")
        for row in rows:
            webbrowser.open_new_tab(row["url"])

    # ── Plain-text results (always written) ───
    txt_file = "dork_results.txt"
    with open(txt_file, "w") as f:
        f.write("Google Dork Job Search Results\n")
        f.write(
            f"Title: {title} | Location: {location} | Level: {level} | "
            f"Remote: {'yes' if remote else 'no'} | Posted: {date_label}\n"
        )
        f.write("=" * 70 + "\n\n")
        for row in rows:
            f.write(f"[{row['site'].upper()}]\n")
            f.write(f"Query : {row['query']}\n")
            f.write(f"URL   : {row['url']}\n\n")
    print(f"  Text saved    -> {txt_file}")
    LOGGER.info("Text results written to %s", txt_file)

    # ── CSV export ────────────────────────────
    csv_path = None
    if do_csv or email:
        csv_path = export_to_csv(rows)
        LOGGER.info("CSV generated at %s", csv_path)

    # ── Email delivery ────────────────────────
    if email:
        job_config = {
            "title": title, "location": location, "level": level,
            "remote": remote, "date_filter": date_filter,
        }
        print(f"\nSending results to {email} ...")
        send_email(email, csv_path, job_config)

    # ── Cron install ──────────────────────────
    if cron:
        print()
        install_cron(cron)

    print("\nDone.")
    LOGGER.info("Run finished successfully")


# ══════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Generate Google dork queries to find job postings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Search params
    g = parser.add_argument_group("Search parameters")
    g.add_argument("--title",    default=None,  help="Job title or role")
    g.add_argument("--location", default=None,  help="City/state (omit for remote-only)")
    g.add_argument("--level",    default="any",
                   choices=list(SENIORITY_KEYWORDS.keys()),
                   help="Seniority level (default: any)")
    g.add_argument("--remote",   action="store_true",
                   help='Add "remote / work from home" keywords to every query')
    g.add_argument("--sites",    nargs="+", default=list(SITE_DORKS.keys()),
                   help="Sites to search (default: all)")
    g.add_argument("--keywords", nargs="+", default=[],
                   help="Extra keywords to include in queries")
    g.add_argument("--since",    default="any",
                   choices=list(DATE_FILTERS.keys()),
                   metavar="|".join(DATE_FILTERS.keys()),
                   help="Recency filter: any|1d|3d|1w|1m  (default: any)")

    # Output options
    o = parser.add_argument_group("Output options")
    o.add_argument("--open",  action="store_true",
                   help="Auto-open all results in browser tabs")
    o.add_argument("--csv",   action="store_true",
                   help="Export results to a timestamped CSV file")
    o.add_argument("--email", default="", metavar="ADDRESS",
                   help="Email CSV via Resend after generation (implies --csv); needs RESEND_API_KEY")
    o.add_argument("--log-file", default="", metavar="PATH",
                   help="Write logs to PATH (default: ./logs/job_dork.log)")

    # Automation
    a = parser.add_argument_group("Automation")
    a.add_argument("--cron", default="",
                   choices=list(CRON_SCHEDULES.keys()),
                   metavar="|".join(CRON_SCHEDULES.keys()),
                   help="Install a recurring cron job: daily|3d|1w")
    a.add_argument("--setup-email", action="store_true",
                   help="Interactive wizard: write RESEND_API_KEY / RESEND_FROM to .env")

    # Info flags
    i = parser.add_argument_group("Info / listing flags")
    i.add_argument("--list-sites",  action="store_true", help="List site keys and exit")
    i.add_argument("--list-levels", action="store_true", help="List seniority levels and exit")
    i.add_argument("--list-dates",  action="store_true", help="List date filter options and exit")
    i.add_argument("--list-cron",   action="store_true", help="List cron schedule options and exit")

    args = parser.parse_args()
    log_path = setup_logging(args.log_file)
    sys.excepthook = _log_unhandled_exception
    LOGGER.info("CLI args: %s", sys.argv[1:])
    print(f"Logging to: {log_path}")

    # Info exits
    if args.list_sites:
        print("Available sites:", ", ".join(SITE_DORKS.keys()))
        sys.exit(0)

    if args.list_levels:
        print("Available seniority levels:")
        for k, v in SENIORITY_KEYWORDS.items():
            kws = ", ".join(f'"{w}"' for w in v if w) or "(no filter)"
            print(f"  {k:12s} -> {kws}")
        sys.exit(0)

    if args.list_dates:
        print("Available date filters (--since):")
        for k, v in DATE_FILTERS.items():
            print(f"  {k:6s} -> {v['label']:22s}  tbs={v['tbs'] or '(none)'}")
        sys.exit(0)

    if args.list_cron:
        print("Available cron schedules (--cron):")
        for k, v in CRON_SCHEDULES.items():
            print(f"  {k:8s} -> {v['label']:32s}  [{v['expr']}]")
        sys.exit(0)

    if args.setup_email:
        setup_email_wizard()
        sys.exit(0)

    # Interactive mode if no args at all
    if args.title is None and len(sys.argv) == 1:
        cfg = run_interactive()
        run(**cfg)
    else:
        run(
            title        = args.title or "",
            location     = args.location or "",
            level        = args.level,
            sites        = args.sites,
            extra        = args.keywords,
            date_filter  = args.since,
            remote       = args.remote,
            do_csv       = args.csv,
            email        = args.email,
            open_browser = args.open,
            cron         = args.cron,
        )


if __name__ == "__main__":
    main()
