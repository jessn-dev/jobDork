#!/usr/bin/env python3
"""
Google Dork Job Search Generator
=================================
Builds targeted Google dork queries to surface job postings on LinkedIn,
Indeed, Glassdoor, ATS portals, and company career pages.

Usage:
    python main.py                          # interactive mode
    python main.py --help                   # show all flags
    ./run.sh --help                         # run via shell wrapper (recommended)

    python main.py \\
        --title "software engineer | developer | SWE" \\
        --location "Chicago, IL" \\
        --level senior \\
        --arrangement "remote | hybrid" \\
        --since 3d \\
        --sites linkedin indeed greenhouse \\
        --csv \\
        --email you@example.com \\
        --open

Pipe-separated OR values
------------------------
Both --title and --arrangement accept pipe-separated tokens that are
expanded into Google boolean OR groups in every query.

  --title "data engineer | analytics engineer | ETL developer"
  -> ("data engineer" OR "analytics engineer" OR "ETL developer")

  --arrangement "remote | hybrid"
  -> ("remote" OR "work from home" OR "wfh" OR "hybrid")

Arrangement tokens: remote | hybrid | on-site  (leave blank for any)

Date filter options (--since):
    any  -> no date filter
    1d   -> past 24 hours
    3d   -> past 3 days
    1w   -> past week  <- DEFAULT
    1m   -> past month

---------------------------------------------------------
EMAIL SETUP (Resend)
---------------------------------------------------------
Create an API key and verify a sending domain, then either run
--setup-email or set these env vars / .env entries:

    RESEND_API_KEY    API key starting with re_
    RESEND_FROM       Verified sender e.g. "Job Dork <jobs@yourdomain.com>"

Docs:
  * https://resend.com/api-keys
  * https://resend.com/domains
---------------------------------------------------------
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


SCRIPT_NAME     = Path(__file__).name
RUN_SCRIPT_NAME = "run.sh"
LOG_DIR         = Path(__file__).parent / "logs"
DEFAULT_LOG_FILE = LOG_DIR / "job_dork.log"
LOGGER          = logging.getLogger("job_dork")

# ─────────────────────────────────────────────
# Optional .env loader (no dotenv dependency)
# ─────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent / ".env"


def _load_dotenv() -> None:
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
                os.environ.setdefault(
                    key.strip(), val.strip().strip('"').strip("'")
                )
    except OSError as exc:
        print(f"[WARN] Failed to read {_ENV_FILE}: {exc}")


def _write_private_env(lines: list[str]) -> None:
    """Write .env and restrict permissions to owner-only where supported."""
    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(_ENV_FILE, 0o600)
    except OSError:
        pass  # best-effort only


def _looks_like_email(addr: str) -> bool:
    """Basic email address sanity check."""
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", addr.strip()))


def setup_logging(log_file: str = "") -> Path:
    """Configure logging to file + stderr. Returns the resolved log path."""
    log_path = Path(log_file).expanduser() if log_file else DEFAULT_LOG_FILE
    if not log_path.is_absolute():
        log_path = Path(__file__).parent / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    LOGGER.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    LOGGER.addHandler(sh)

    LOGGER.info("Logging initialized — log: %s", log_path.resolve())
    return log_path.resolve()


def _log_unhandled_exception(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    LOGGER.critical(
        "Unhandled exception:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    )
    sys.__excepthook__(exc_type, exc_value, exc_tb)


_load_dotenv()


# ═══════════════════════════════════════════════
# Configuration tables
# ═══════════════════════════════════════════════

DEFAULT_DATE_FILTER = "1w"

DATE_FILTERS: dict[str, dict] = {
    "any": {"tbs": None,       "label": "No date filter"},
    "1d":  {"tbs": "qdr:d",    "label": "Past 24 hours"},
    "3d":  {"tbs": "qdr:d3",   "label": "Past 3 days"},
    "1w":  {"tbs": "qdr:w",    "label": "Past week"},
    "1m":  {"tbs": "qdr:m",    "label": "Past month"},
}

CRON_SCHEDULES: dict[str, dict] = {
    "daily": {"expr": "0 8 * * *",   "label": "Every day at 8:00 AM"},
    "3d":    {"expr": "0 8 */3 * *", "label": "Every 3 days at 8:00 AM"},
    "1w":    {"expr": "0 8 * * 1",   "label": "Every Monday at 8:00 AM"},
}

SENIORITY_KEYWORDS: dict[str, list[str]] = {
    "intern":    ["intern", "internship", "co-op", "student"],
    "junior":    ["junior", "jr", "entry level", "entry-level", "associate", "new grad"],
    "mid":       ["mid", "mid-level", "intermediate"],
    "senior":    ["senior", "sr", "lead", "staff"],
    "principal": ["principal", "staff", "distinguished"],
    "manager":   ["manager", "engineering manager", "em", "team lead"],
    "director":  ["director", "head of", "vp of"],
    "executive": ["vp", "vice president", "cto", "cpo", "c-level"],
    "any":       [],
}

# Work-arrangement token -> search terms used in the Google query
ARRANGEMENT_TERMS: dict[str, list[str]] = {
    "remote":   ["remote", "work from home", "wfh"],
    "hybrid":   ["hybrid"],
    "on-site":  ["on-site", "onsite", "in-office", "in office"],
    "onsite":   ["on-site", "onsite", "in-office", "in office"],   # alias
    "in-office":["on-site", "onsite", "in-office", "in office"],   # alias
}

# All known job boards + ATS portals; searched by default when --sites is omitted
SITE_DORKS: dict[str, tuple[str, str]] = {
    # ── Major aggregators ────────────────────
    "linkedin":        ("site:linkedin.com",              "/jobs/view OR /jobs/search"),
    "indeed":          ("site:indeed.com",                "/viewjob OR /jobs"),
    "glassdoor":       ("site:glassdoor.com",             "/job-listing OR /Jobs"),
    "builtin":         ("site:builtin.com",               "/jobs"),
    "dice":            ("site:dice.com",                  "/jobs/detail"),
    "simplyhired":     ("site:simplyhired.com",           "/job"),
    "ziprecruiter":    ("site:ziprecruiter.com",          "/jobs"),
    "monster":         ("site:monster.com",               "/job-openings"),
    "careerbuilder":   ("site:careerbuilder.com",         "/job"),
    "flexjobs":        ("site:flexjobs.com",              "/jobs"),
    "wellfound":       ("site:wellfound.com",             "/jobs"),
    "ycombinator":     ("site:workatastartup.com",        ""),
    # ── ATS / company career portals ─────────
    "lever":           ("site:jobs.lever.co",             ""),
    "greenhouse":      ("site:boards.greenhouse.io",      ""),
    "workday":         ("site:myworkdayjobs.com",         ""),
    "ashby":           ("site:jobs.ashbyhq.com",          ""),
    "smartrecruiters": ("site:jobs.smartrecruiters.com",  ""),
    "icims":           ("site:careers.icims.com",         ""),
    "breezy":          ("site:app.breezy.hr",             ""),
    "rippling":        ("site:ats.rippling.com",          ""),
    # ── Open company career pages ─────────────
    "careers":         ("",                               'careers OR "job openings" OR "we\'re hiring"'),
}

ALL_SITES = list(SITE_DORKS.keys())

GOOGLE_BASE = "https://www.google.com/search?q="


# ═══════════════════════════════════════════════
# Pipe-separated token parsers
# ═══════════════════════════════════════════════

def _split_pipe(raw: str) -> list[str]:
    """Split a pipe-separated string into stripped, non-empty tokens."""
    return [t.strip() for t in raw.split("|") if t.strip()]


def _build_title_clause(raw_title: str) -> str:
    """
    Build a Google boolean OR clause from a pipe-separated title string.

    "software engineer | developer | SWE"
      -> ("software engineer" OR "developer" OR "SWE")
    "data engineer"
      -> "data engineer"
    """
    roles = _split_pipe(raw_title)
    if not roles:
        return ""
    if len(roles) == 1:
        return f'"{roles[0]}"'
    return "(" + " OR ".join(f'"{r}"' for r in roles) + ")"


def _build_arrangement_clause(raw_arrangement: str) -> str:
    """
    Build a Google boolean OR clause for work arrangement.

    Tokens (remote, hybrid, on-site) are expanded to their search-term
    equivalents then flattened into a single OR group.

    "remote | hybrid"
      -> ("remote" OR "work from home" OR "wfh" OR "hybrid")
    "on-site"
      -> ("on-site" OR "onsite" OR "in-office" OR "in office")
    """
    tokens = _split_pipe(raw_arrangement.lower())
    if not tokens:
        return ""

    terms: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for term in ARRANGEMENT_TERMS.get(token, [token]):
            if term not in seen:
                terms.append(term)
                seen.add(term)

    if not terms:
        return ""
    if len(terms) == 1:
        return f'"{terms[0]}"'
    return "(" + " OR ".join(f'"{t}"' for t in terms) + ")"


# ═══════════════════════════════════════════════
# Query builder
# ═══════════════════════════════════════════════

def build_query(
    title: str,
    location: str,
    level: str,
    site_key: str,
    date_filter: str = DEFAULT_DATE_FILTER,
    arrangement: str = "",
) -> tuple[str, str]:
    """
    Construct a single Google dork query string.
    Returns (raw_query, full_url).
    """
    parts: list[str] = []
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

    # 3. Job title (boolean OR when pipe-separated)
    title_clause = _build_title_clause(title)
    if title_clause:
        parts.append(title_clause)

    # 4. Work arrangement (boolean OR when pipe-separated)
    arrangement_clause = _build_arrangement_clause(arrangement)
    if arrangement_clause:
        parts.append(arrangement_clause)

    # 5. Location
    if location:
        parts.append(f'"{location}"')

    # 6. Path hint
    if path_hint:
        parts.append(path_hint)

    raw_query = " ".join(parts)

    # 7. Build URL + optional tbs date param
    tbs_value = DATE_FILTERS.get(date_filter, {}).get("tbs")
    encoded_q = urllib.parse.quote_plus(raw_query)
    url = f"{GOOGLE_BASE}{encoded_q}"
    if tbs_value:
        url += f"&tbs={tbs_value}"

    return raw_query, url


# ═══════════════════════════════════════════════
# CSV export
# ═══════════════════════════════════════════════

def export_to_csv(rows: list[dict], filename: str = "") -> Path:
    """Write result rows to a timestamped CSV file. Returns the Path written."""
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dork_results_{ts}.csv"

    out_path = Path(filename)
    fieldnames = [
        "site", "title", "location", "level", "arrangement",
        "date_filter", "query", "url", "generated_at",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  CSV exported  -> {out_path.resolve()}")
    return out_path


# ═══════════════════════════════════════════════
# Email delivery (Resend)
# ═══════════════════════════════════════════════

def _resend_api_key() -> str:
    return (os.environ.get("RESEND_API_KEY") or "").strip()


def _resend_from_address() -> str:
    return (
        os.environ.get("RESEND_FROM")
        or os.environ.get("JOB_DORK_EMAIL_FROM")
        or ""
    ).strip()


def send_email(to_addr: str, csv_path: Path, job_config: dict) -> None:
    """Send the CSV results file as an email attachment via Resend."""
    api_key   = _resend_api_key()
    from_addr = _resend_from_address()
    to_addr   = to_addr.strip()
    LOGGER.info("Preparing to send email to %s", to_addr)

    if not _looks_like_email(to_addr):
        LOGGER.error("Invalid recipient address: %r", to_addr)
        print(f"[ERROR] Invalid recipient email address: {to_addr!r}")
        sys.exit(1)

    if not api_key:
        LOGGER.error("Missing RESEND_API_KEY")
        print("\n[ERROR] Resend is not configured — RESEND_API_KEY is missing.")
        print(f"  Run:  python {SCRIPT_NAME} --setup-email")
        print("  Docs: https://resend.com/api-keys")
        sys.exit(1)

    if not from_addr:
        LOGGER.error("Missing RESEND_FROM")
        print("\n[ERROR] Missing sender — set RESEND_FROM in .env.")
        print('  Example: RESEND_FROM="Job Dork <jobs@yourdomain.com>"')
        print("  Docs: https://resend.com/domains")
        sys.exit(1)

    if not csv_path.exists():
        LOGGER.error("CSV not found: %s", csv_path)
        print(f"[ERROR] CSV attachment not found: {csv_path}")
        sys.exit(1)

    raw_bytes = csv_path.read_bytes()
    if len(raw_bytes) > 30 * 1024 * 1024:
        LOGGER.error("CSV too large: %d bytes", len(raw_bytes))
        print("[ERROR] CSV exceeds 30 MB — too large to attach. Send manually.")
        sys.exit(1)

    resend.api_key = api_key
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = (
        f"Job Dork Results | {job_config.get('title', 'Search')} "
        f"[{job_config.get('level', 'any')}] | {ts}"
    )
    body = "\n".join([
        f"Your job dork search completed at {ts}.",
        "",
        "Search parameters:",
        f"  Title       : {job_config.get('title') or '(any)'}",
        f"  Location    : {job_config.get('location') or '(any)'}",
        f"  Level       : {job_config.get('level', 'any')}",
        f"  Arrangement : {job_config.get('arrangement') or '(any)'}",
        f"  Posted      : {DATE_FILTERS.get(job_config.get('date_filter', DEFAULT_DATE_FILTER), {}).get('label', 'N/A')}",
        "",
        f"Results attached as: {csv_path.name}",
        "",
        f"-- {SCRIPT_NAME}",
    ])

    params: resend.Emails.SendParams = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": body,
        "attachments": [{
            "filename":     csv_path.name,
            "content":      base64.standard_b64encode(raw_bytes).decode("ascii"),
            "content_type": "text/csv",
        }],
    }

    print("  Sending via Resend ...")
    try:
        result = resend.Emails.send(params)
        eid = result.get("id", "?")
        LOGGER.info("Email sent to %s (id: %s)", to_addr, eid)
        print(f"  Email sent    -> {to_addr}  (id: {eid})")
    except ResendError as exc:
        LOGGER.error("Resend error (%s): %s", exc.error_type, exc.message)
        print(f"[ERROR] Resend API error ({exc.error_type}): {exc.message}")
        if exc.suggested_action:
            print(f"  {exc.suggested_action.strip()}")
        sys.exit(1)
    except Exception as exc:
        LOGGER.exception("Unexpected error sending email")
        print(f"[ERROR] Failed to send email: {exc}")
        sys.exit(1)


def setup_email_wizard() -> None:
    """Interactive wizard to write Resend credentials to .env."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   ✉   Resend email setup                 ║")
    print("╚══════════════════════════════════════════╝\n")
    print("Create an API key : https://resend.com/api-keys")
    print("Verify a domain   : https://resend.com/domains\n")
    print(f"Settings saved to : {_ENV_FILE}")
    print("Add .env to .gitignore to keep credentials private.\n")

    api_key = input("Resend API key (re_...) : ").strip()
    if not api_key:
        print("[ERROR] RESEND_API_KEY is required.")
        sys.exit(1)
    if not api_key.startswith("re_"):
        print("  [WARN] Keys usually start with re_ — double-check.\n")

    frm = input('From address (e.g. Job Dork <jobs@yourdomain.com>) : ').strip()
    if not frm:
        print("[ERROR] RESEND_FROM is required.")
        sys.exit(1)

    _write_private_env([
        f"# {SCRIPT_NAME} — Resend credentials (keep private)",
        f'RESEND_API_KEY="{api_key}"',
        f'RESEND_FROM="{frm}"',
    ])
    print(f"\n  Saved -> {_ENV_FILE}")

    if input("\nSend a test email now? [y/N]: ").strip().lower() == "y":
        to = input("Recipient email: ").strip()
        if not to:
            print("  Skipped — no recipient entered.")
        elif not _looks_like_email(to):
            print(f"  Skipped — invalid address: {to!r}")
        else:
            _load_dotenv()
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".csv", delete=False, encoding="utf-8"
                ) as tf:
                    tf.write("site,query,url\ntest,test query,https://google.com\n")
                    tmp_path = Path(tf.name)
                send_email(to, tmp_path, {"title": "TEST", "level": "any"})
            finally:
                if tmp_path:
                    tmp_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════
# Cron / Task Scheduler installer
# ═══════════════════════════════════════════════

def _rebuild_argv_without_cron() -> list[str]:
    """Strip --cron <val> from sys.argv and ensure --csv is present."""
    cleaned: list[str] = []
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
    """Install (or replace) a crontab / Task Scheduler entry."""
    LOGGER.info("Installing scheduler: %s", schedule_key)
    if platform.system() == "Windows":
        _install_windows_task(schedule_key)
        return

    if schedule_key not in CRON_SCHEDULES:
        print(f"[ERROR] Unknown schedule '{schedule_key}'. Choose: {', '.join(CRON_SCHEDULES)}")
        sys.exit(1)

    sched     = CRON_SCHEDULES[schedule_key]
    cron_expr = sched["expr"]
    label     = sched["label"]
    marker    = "# job_dork_auto"

    project_dir = Path(__file__).resolve().parent
    run_script  = project_dir / RUN_SCRIPT_NAME
    argv_tail   = _rebuild_argv_without_cron()

    if run_script.exists():
        cmd = shlex.join(["bash", str(run_script)] + argv_tail)
    else:
        cmd = shlex.join([str(sys.executable), str(Path(__file__).resolve())] + argv_tail)
        print(f"[WARN] {RUN_SCRIPT_NAME} not found; cron will invoke Python directly.")

    cron_line = f"{cron_expr}  {cmd}  {marker}"
    print(f"  Schedule : {label}  ({cron_expr})")
    print(f"  Command  : {cmd}\n")

    if input("Install this cron job? [y/N]: ").strip().lower() != "y":
        print("Aborted — no changes made.")
        return

    try:
        existing = subprocess.check_output(
            ["crontab", "-l"], stderr=subprocess.DEVNULL
        ).decode()
    except subprocess.CalledProcessError:
        existing = ""

    lines = [l for l in existing.splitlines() if marker not in l]
    lines.append(cron_line)
    proc = subprocess.run(
        ["crontab", "-"], input=("\n".join(lines) + "\n").encode(), capture_output=True
    )
    if proc.returncode != 0:
        print(f"[ERROR] crontab write failed:\n{proc.stderr.decode()}")
        sys.exit(1)

    LOGGER.info("Cron installed: %s", schedule_key)
    print(f"\n  Cron job installed -> {label.lower()}")
    print(f"  View   : crontab -l")
    print(f"  Remove : crontab -e  (delete line containing '{marker}')")


def _install_windows_task(schedule_key: str) -> None:
    """Install a Windows Task Scheduler task via schtasks.exe."""
    trigger_map = {
        "daily": ["/SC", "DAILY",  "/ST", "08:00"],
        "3d":    ["/SC", "DAILY",  "/MO", "3", "/ST", "08:00"],
        "1w":    ["/SC", "WEEKLY", "/D",  "MON", "/ST", "08:00"],
    }
    label_map = {
        "daily": "every day at 08:00",
        "3d":    "every 3 days at 08:00",
        "1w":    "every Monday at 08:00",
    }
    if schedule_key not in trigger_map:
        print(f"[ERROR] Unknown schedule '{schedule_key}'.")
        sys.exit(1)

    label     = label_map[schedule_key]
    argv_tail = _rebuild_argv_without_cron()
    tr_cmd    = subprocess.list2cmdline(
        [str(sys.executable), str(Path(__file__).resolve())] + argv_tail
    )
    task_name = "JobDorkSearch"
    print(f"  Schedule : {label}")
    print(f"  Command  : {tr_cmd}\n")

    if input("Install this scheduled task? [y/N]: ").strip().lower() != "y":
        print("Aborted — no changes made.")
        return

    result = subprocess.run(
        ["schtasks", "/Create", "/F", "/TN", task_name, "/TR", tr_cmd,
         *trigger_map[schedule_key]],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "(no output)").strip()
        print(f"[ERROR] schtasks failed:\n{err}")
        sys.exit(1)

    LOGGER.info("Windows task installed: %s", schedule_key)
    print(f"\n  Task '{task_name}' scheduled -> {label}")
    print(f'  View   : schtasks /Query /TN "{task_name}"')
    print(f'  Remove : schtasks /Delete /TN "{task_name}" /F')


# ═══════════════════════════════════════════════
# Interactive mode
# ═══════════════════════════════════════════════

def run_interactive() -> dict:
    """Prompt the user for all options and return a config dict for run()."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   🔍  Google Dork Job Search Tool        ║")
    print("╚══════════════════════════════════════════╝\n")

    print("Tip: use  |  to OR multiple values together")
    print("     e.g. 'software engineer | developer | SWE'\n")

    title    = input("Job title / role(s)  : ").strip()
    location = input("Location             : ").strip()

    print(f"\nSeniority: {', '.join(SENIORITY_KEYWORDS)}")
    level = input("Seniority level      (leave blank = any): ").strip() or "any"

    print("\nArrangement tokens: remote | hybrid | on-site")
    arrangement = input("Work arrangement     (leave blank = any): ").strip()

    print(f"\nAvailable sites: {', '.join(SITE_DORKS)}")
    print("(leave blank to search ALL boards)")
    sites_raw = input("Sites                (space-separated, blank = all): ").strip()
    sites = sites_raw.split() if sites_raw else ALL_SITES

    print(f"\nDate filters: {', '.join(DATE_FILTERS)}")
    since = input(f"Posted within        (leave blank = {DEFAULT_DATE_FILTER}): ").strip() or DEFAULT_DATE_FILTER
    if since not in DATE_FILTERS:
        print(f"[WARN] Unknown filter '{since}', using '{DEFAULT_DATE_FILTER}'.")
        since = DEFAULT_DATE_FILTER

    # Export / delivery — blank always means no
    print()
    do_csv = input("Export to CSV?       [y/N]: ").strip().lower() == "y"

    email = ""
    if do_csv:
        email = input("Email CSV to         (leave blank to skip): ").strip()

    open_b = input("Open in browser?     [y/N]: ").strip().lower() == "y"

    # Recurring — blank means no
    print(f"\nSchedule options: {', '.join(CRON_SCHEDULES)} — or leave blank to skip")
    cron_in = input("Recurring search     (leave blank to skip): ").strip().lower()
    cron = cron_in if cron_in in CRON_SCHEDULES else ""

    return dict(
        title=title, location=location, level=level,
        arrangement=arrangement, sites=sites,
        date_filter=since, do_csv=do_csv, email=email,
        open_browser=open_b, cron=cron,
    )


# ═══════════════════════════════════════════════
# Main runner
# ═══════════════════════════════════════════════

def run(
    title: str,
    location: str,
    level: str,
    sites: list[str],
    open_browser: bool,
    date_filter: str = DEFAULT_DATE_FILTER,
    arrangement: str = "",
    do_csv: bool = False,
    email: str = "",
    cron: str = "",
) -> None:
    LOGGER.info(
        "Run started | title=%r location=%r level=%r arrangement=%r sites=%d since=%s csv=%s email=%s cron=%s",
        title, location, level, arrangement, len(sites),
        date_filter, do_csv, bool(email), bool(cron),
    )

    # ── Validate inputs ───────────────────────
    if level not in SENIORITY_KEYWORDS:
        LOGGER.warning("Unknown level '%s', defaulting to 'any'", level)
        print(f"[WARN] Unknown level '{level}', defaulting to 'any'.")
        level = "any"

    if date_filter not in DATE_FILTERS:
        LOGGER.warning("Unknown date filter '%s', defaulting to '%s'", date_filter, DEFAULT_DATE_FILTER)
        print(f"[WARN] Unknown date filter '{date_filter}', defaulting to '{DEFAULT_DATE_FILTER}'.")
        date_filter = DEFAULT_DATE_FILTER

    unknown = [s for s in sites if s not in SITE_DORKS]
    if unknown:
        LOGGER.warning("Unknown sites ignored: %s", unknown)
        print(f"[WARN] Unknown sites ignored: {unknown}")
        sites = [s for s in sites if s in SITE_DORKS]
    if not sites:
        print("[ERROR] No valid sites specified.")
        sys.exit(1)

    # ── Display labels ────────────────────────
    title_roles   = _split_pipe(title)
    title_display = " | ".join(title_roles) if title_roles else "(any)"
    arr_tokens    = _split_pipe(arrangement)
    arr_display   = " | ".join(arr_tokens) if arr_tokens else "(any)"
    date_label    = DATE_FILTERS[date_filter]["label"]
    ts            = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'─'*62}")
    print(f"  Title       : {title_display}")
    print(f"  Location    : {location or '(any)'}")
    print(f"  Level       : {level}")
    print(f"  Arrangement : {arr_display}")
    print(f"  Posted      : {date_label}")
    print(f"  Sites       : {len(sites)} boards")
    print(f"{'─'*62}\n")

    # ── Build queries ─────────────────────────
    rows: list[dict] = []
    for site_key in sites:
        raw, url = build_query(
            title, location, level, site_key, date_filter, arrangement
        )
        rows.append({
            "site":         site_key,
            "title":        title_display,
            "location":     location,
            "level":        level,
            "arrangement":  arr_display,
            "date_filter":  date_label,
            "query":        raw,
            "url":          url,
            "generated_at": ts,
        })
        print(f"[{site_key.upper():16s}]  {raw}")
        print(f"  -> {url}\n")

    # ── Open browser ──────────────────────────
    if open_browser:
        LOGGER.info("Opening %d browser tabs", len(rows))
        print(f"Opening {len(rows)} tab(s) in browser ...")
        for row in rows:
            webbrowser.open_new_tab(row["url"])

    # ── Plain-text output (always written) ────
    txt_path = Path("dork_results.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("Google Dork Job Search Results\n")
        f.write(
            f"Title: {title_display} | Location: {location} | Level: {level} | "
            f"Arrangement: {arr_display} | Posted: {date_label}\n"
        )
        f.write("=" * 70 + "\n\n")
        for row in rows:
            f.write(f"[{row['site'].upper()}]\n")
            f.write(f"Query : {row['query']}\n")
            f.write(f"URL   : {row['url']}\n\n")
    print(f"  Text saved    -> {txt_path.resolve()}")
    LOGGER.info("Text results saved to %s", txt_path)

    # ── CSV export ────────────────────────────
    csv_path = None
    if do_csv or email:
        csv_path = export_to_csv(rows)
        LOGGER.info("CSV saved to %s", csv_path)

    # ── Email delivery ────────────────────────
    if email:
        job_config = {
            "title": title_display, "location": location, "level": level,
            "arrangement": arr_display, "date_filter": date_filter,
        }
        print(f"\nSending results to {email} ...")
        send_email(email, csv_path, job_config)

    # ── Cron install ──────────────────────────
    if cron:
        print()
        install_cron(cron)

    print("\nDone.")
    LOGGER.info("Run finished successfully")


# ═══════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Google dork queries to find job postings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    g = parser.add_argument_group("Search parameters")
    g.add_argument("--title",
                   help='Role title; pipe-separate aliases for OR: "engineer | developer | SWE"')
    g.add_argument("--location",
                   help="City/state (omit to search without a location filter)")
    g.add_argument("--level", default="any", choices=list(SENIORITY_KEYWORDS),
                   help="Seniority level (default: any)")
    g.add_argument("--arrangement", default="",
                   help='Work arrangement; pipe-separate for OR: "remote | hybrid | on-site"')
    g.add_argument("--sites", nargs="+",
                   help="Specific boards to search (default: all). See --list-sites.")
    g.add_argument("--since", default=DEFAULT_DATE_FILTER,
                   choices=list(DATE_FILTERS),
                   metavar="|".join(DATE_FILTERS),
                   help=f"Recency filter (default: {DEFAULT_DATE_FILTER})")

    o = parser.add_argument_group("Output options")
    o.add_argument("--open",  action="store_true", help="Open results in browser tabs")
    o.add_argument("--csv",   action="store_true", help="Export results to a CSV file")
    o.add_argument("--email", default="", metavar="ADDRESS",
                   help="Email the CSV via Resend (implies --csv); requires RESEND_API_KEY")
    o.add_argument("--log-file", default="", metavar="PATH",
                   help="Log file path (default: ./logs/job_dork.log)")

    a = parser.add_argument_group("Automation")
    a.add_argument("--cron", default="", choices=list(CRON_SCHEDULES),
                   metavar="|".join(CRON_SCHEDULES),
                   help="Install a recurring cron job: daily | 3d | 1w")
    a.add_argument("--setup-email", action="store_true",
                   help="Interactive wizard to configure Resend in .env")

    i = parser.add_argument_group("Info flags")
    i.add_argument("--list-sites",  action="store_true", help="Print all site keys and exit")
    i.add_argument("--list-levels", action="store_true", help="Print seniority levels and exit")
    i.add_argument("--list-dates",  action="store_true", help="Print date filter options and exit")
    i.add_argument("--list-cron",   action="store_true", help="Print cron schedules and exit")

    args = parser.parse_args()

    log_path = setup_logging(args.log_file)
    sys.excepthook = _log_unhandled_exception
    LOGGER.info("CLI args: %s", sys.argv[1:])
    print(f"Logging to: {log_path}")

    # Info exits
    if args.list_sites:
        print(f"Available sites ({len(SITE_DORKS)} total):")
        for k, (op, hint) in SITE_DORKS.items():
            print(f"  {k:20s}  {op or '(open web)'}")
        sys.exit(0)

    if args.list_levels:
        print("Seniority levels:")
        for k, v in SENIORITY_KEYWORDS.items():
            kws = ", ".join(f'"{w}"' for w in v) or "(no filter)"
            print(f"  {k:12s} -> {kws}")
        sys.exit(0)

    if args.list_dates:
        print("Date filters (--since):")
        for k, v in DATE_FILTERS.items():
            marker = "  <- default" if k == DEFAULT_DATE_FILTER else ""
            print(f"  {k:6s} -> {v['label']:22s}  tbs={v['tbs'] or '(none)'}{marker}")
        sys.exit(0)

    if args.list_cron:
        print("Cron schedules (--cron):")
        for k, v in CRON_SCHEDULES.items():
            print(f"  {k:8s} -> {v['label']:32s}  [{v['expr']}]")
        sys.exit(0)

    if args.setup_email:
        setup_email_wizard()
        sys.exit(0)

    # Interactive mode when called with no arguments
    if not any([args.title, args.location, args.arrangement]) and len(sys.argv) == 1:
        cfg = run_interactive()
        run(**cfg)
        return

    run(
        title        = args.title or "",
        location     = args.location or "",
        level        = args.level,
        sites        = args.sites if args.sites else ALL_SITES,
        date_filter  = args.since,
        arrangement  = args.arrangement,
        do_csv       = args.csv,
        email        = args.email,
        open_browser = args.open,
        cron         = args.cron,
    )


if __name__ == "__main__":
    main()