#!/usr/bin/env python3
"""
Google Dork Job Search Generator
=================================
Builds targeted Google dork queries to surface job postings on LinkedIn,
Indeed, Glassdoor, 20+ ATS portals, the hidden job market, and more.

Usage:
    python main.py                           # interactive mode
    python main.py --help                    # show all flags
    ./run.sh --help                          # run via shell wrapper (recommended)

    python main.py \\
        --title "software engineer | developer | SWE" \\
        --location "Chicago, IL" \\
        --level "mid | senior" \\
        --arrangement "remote | hybrid" \\
        --since 1w \\
        --sites linkedin indeed greenhouse lever \\
        --csv \\
        --email you@example.com \\
        --open

Pipe-separated OR values
------------------------
--title, --level, and --arrangement all accept tokens separated by |.
Each group is expanded into a Google boolean OR clause in every query.

  --title "data engineer | analytics engineer"
  -> ("data engineer" OR "analytics engineer")

  --level "mid | senior"
  -> ("mid" OR "mid-level" OR "intermediate" OR "senior" OR "sr" OR "lead" OR "staff")

  --arrangement "remote | hybrid"
  -> ("remote" OR "work from home" OR "wfh" OR "hybrid")

Advanced options
----------------
  --after YYYY-MM-DD   Add after: operator to show only results since that date
  --benefits "..."     Pipe-separated benefit phrases added as quoted terms
                       e.g. "visa sponsorship | relocation assistance"

Special site strategies (opt-in via --sites)
--------------------------------------------
  google_docs       Public Google Docs with job lists (hidden market)
  google_sheets     Public Google Sheets with job lists (hidden market)
  linkedin_posts    Recruiter posts on LinkedIn before listings go live
  hiring_manager    intitle: search to find hiring managers directly
  pdf_resumes       filetype:pdf to study how peers format their resumes

---------------------------------------------------------
EMAIL SETUP (Resend)
---------------------------------------------------------
Run  python main.py --setup-email  or set these in .env:

    RESEND_API_KEY    API key starting with re_
    RESEND_FROM       Verified sender e.g. "Job Dork <jobs@yourdomain.com>"

Docs:  https://resend.com/api-keys  |  https://resend.com/domains
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

from config import (
    GOOGLE_BASE,
    DEFAULT_DATE_FILTER,
    DATE_FILTERS,
    CRON_SCHEDULES,
    LEVEL_KEYWORDS,
    ARRANGEMENT_TERMS,
    SITE_DORKS,
    DEFAULT_SITES,
    ALL_SITES,
)


# ── Runtime constants ──────────────────────────────────────────────────────────
SCRIPT_NAME      = Path(__file__).name
RUN_SCRIPT_NAME  = "run.sh"
LOG_DIR          = Path(__file__).parent / "logs"
DEFAULT_LOG_FILE = LOG_DIR / "job_dork.log"
LOGGER           = logging.getLogger("job_dork")

# ── .env loader ────────────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent / ".env"


def _load_dotenv() -> None:
    """Load key=value pairs from .env into os.environ (no external deps)."""
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
    """Write .env with owner-only permissions where the OS supports it."""
    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(_ENV_FILE, 0o600)
    except OSError:
        pass


def _looks_like_email(addr: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", addr.strip()))


# ── Logging ────────────────────────────────────────────────────────────────────

def setup_logging(log_file: str = "") -> Path:
    """Set up file + stderr logging. Returns the resolved log path."""
    log_path = Path(log_file).expanduser() if log_file else DEFAULT_LOG_FILE
    if not log_path.is_absolute():
        log_path = Path(__file__).parent / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    for handler in (
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ):
        handler.setFormatter(fmt)
        LOGGER.addHandler(handler)

    LOGGER.info("Logging initialized — %s", log_path.resolve())
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


# ══════════════════════════════════════════════════════════════════════════════
# Pipe-separated token parsers
# ══════════════════════════════════════════════════════════════════════════════

def _split_pipe(raw: str) -> list[str]:
    """Return stripped, non-empty tokens from a pipe-separated string."""
    return [t.strip() for t in raw.split("|") if t.strip()]


def _build_title_clause(raw_title: str) -> str:
    """
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


def _build_level_clause(raw_level: str) -> tuple[str, list[str]]:
    """
    Expand pipe-separated role levels into a boolean OR keyword clause.

    "mid | senior"
      -> clause: ("mid" OR "mid-level" OR "intermediate" OR "senior" OR "sr" ...)
      -> valid_levels: ["mid", "senior"]

    Returns (clause_string, list_of_valid_level_names).
    """
    tokens = _split_pipe(raw_level.lower())
    valid: list[str] = []
    invalid: list[str] = []
    for t in tokens:
        (valid if t in LEVEL_KEYWORDS else invalid).append(t)

    if invalid:
        print(f"[WARN] Unknown role levels ignored: {invalid}")
        print(f"       Valid levels: {', '.join(LEVEL_KEYWORDS)}")
    if not valid:
        valid = ["any"]

    # Collect all keywords across every listed level, preserving insertion order
    terms: list[str] = []
    seen: set[str] = set()
    for lvl in valid:
        for word in LEVEL_KEYWORDS.get(lvl, []):
            if word and word not in seen:
                terms.append(word)
                seen.add(word)

    if not terms:  # "any" or only levels with empty keyword lists
        return "", valid

    clause = (
        f'"{terms[0]}"'
        if len(terms) == 1
        else "(" + " OR ".join(f'"{t}"' for t in terms) + ")"
    )
    return clause, valid


def _build_arrangement_clause(raw_arrangement: str) -> str:
    """
    "remote | hybrid"
      -> ("remote" OR "work from home" OR "wfh" OR "hybrid")
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


def _build_benefits_clause(raw_benefits: str) -> list[str]:
    """
    "visa sponsorship | relocation assistance | 4-day work week"
      -> ['"visa sponsorship"', '"relocation assistance"', '"4-day work week"']

    Each benefit becomes its own quoted phrase added to the query.
    """
    return [f'"{b}"' for b in _split_pipe(raw_benefits) if b]


# ══════════════════════════════════════════════════════════════════════════════
# CSV filename helper
# ══════════════════════════════════════════════════════════════════════════════

def _csv_filename(title: str, date_filter: str) -> str:
    """
    Build a descriptive CSV filename:
        <role_slug>_<date_filter>_<YYYYMMDD_HHMM>.csv

    Example: data_engineer_analytics_engineer_1w_20260327_1430.csv
    """
    roles = _split_pipe(title)
    slugs = [
        re.sub(r"[^\w]+", "_", r.lower()).strip("_")
        for r in roles[:3]  # cap at 3 roles to keep filename sane
    ]
    role_part = "_".join(s for s in slugs if s) or "search"
    # Trim very long slugs
    if len(role_part) > 50:
        role_part = role_part[:50].rstrip("_")
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"{role_part}_{date_filter}_{ts}.csv"


# ══════════════════════════════════════════════════════════════════════════════
# Query builder
# ══════════════════════════════════════════════════════════════════════════════

def build_query(
    title: str,
    location: str,
    level_clause: str,
    site_key: str,
    date_filter: str = DEFAULT_DATE_FILTER,
    arrangement: str = "",
    benefits: str = "",
    after_date: str = "",
) -> tuple[str, str]:
    """
    Construct a single Google dork query string.
    Returns (raw_query, full_url).
    """
    parts: list[str] = []
    site_op, path_hint = SITE_DORKS.get(site_key, ("", ""))

    # 1. Site / file-type / intitle operator
    if site_op:
        parts.append(site_op)

    # 2. Role level keywords (pre-built OR clause)
    if level_clause:
        parts.append(level_clause)

    # 3. Job title — boolean OR when pipe-separated
    title_clause = _build_title_clause(title)
    if title_clause:
        parts.append(title_clause)

    # 4. Work arrangement — boolean OR when pipe-separated
    arr_clause = _build_arrangement_clause(arrangement)
    if arr_clause:
        parts.append(arr_clause)

    # 5. Location
    if location:
        parts.append(f'"{location}"')

    # 6. Site-specific path hint / extra terms
    if path_hint:
        parts.append(path_hint)

    # 7. Benefit phrases (each individually quoted)
    for phrase in _build_benefits_clause(benefits):
        parts.append(phrase)

    # 8. after: date operator (Google restricts results to after this date)
    if after_date:
        parts.append(f"after:{after_date}")

    raw_query = " ".join(parts)

    # 9. Build URL with optional tbs recency param
    tbs_value = DATE_FILTERS.get(date_filter, {}).get("tbs")
    url = f"{GOOGLE_BASE}{urllib.parse.quote_plus(raw_query)}"
    if tbs_value:
        url += f"&tbs={tbs_value}"

    return raw_query, url


# ══════════════════════════════════════════════════════════════════════════════
# CSV export
# ══════════════════════════════════════════════════════════════════════════════

def export_to_csv(rows: list[dict], filename: str) -> Path:
    """Write result rows to a CSV file. Returns the Path written."""
    out_path = Path(filename)
    fieldnames = [
        "site", "title", "location", "level", "arrangement",
        "benefits", "date_filter", "query", "url", "generated_at",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"  CSV exported  -> {out_path.resolve()}")
    return out_path


# ══════════════════════════════════════════════════════════════════════════════
# Email delivery (Resend)
# ══════════════════════════════════════════════════════════════════════════════

def _resend_api_key() -> str:
    return (os.environ.get("RESEND_API_KEY") or "").strip()


def _resend_from_address() -> str:
    return (
        os.environ.get("RESEND_FROM")
        or os.environ.get("JOB_DORK_EMAIL_FROM")
        or ""
    ).strip()


def send_email(to_addr: str, csv_path: Path, job_config: dict) -> None:
    """Send the CSV as an email attachment via Resend."""
    api_key   = _resend_api_key()
    from_addr = _resend_from_address()
    to_addr   = to_addr.strip()
    LOGGER.info("Preparing email to %s", to_addr)

    # Guard-clause validation
    if not _looks_like_email(to_addr):
        print(f"[ERROR] Invalid recipient email: {to_addr!r}")
        sys.exit(1)
    if not api_key:
        print("\n[ERROR] RESEND_API_KEY is missing.")
        print(f"  Run:  python {SCRIPT_NAME} --setup-email")
        print("  Docs: https://resend.com/api-keys")
        sys.exit(1)
    if not from_addr:
        print("\n[ERROR] RESEND_FROM is missing — set it in .env.")
        print('  Example: RESEND_FROM="Job Dork <jobs@yourdomain.com>"')
        print("  Docs: https://resend.com/domains")
        sys.exit(1)
    if not csv_path.exists():
        print(f"[ERROR] CSV not found: {csv_path}")
        sys.exit(1)

    raw_bytes = csv_path.read_bytes()
    if len(raw_bytes) > 30 * 1024 * 1024:
        print("[ERROR] CSV exceeds 30 MB — too large to attach. Send manually.")
        sys.exit(1)

    resend.api_key = api_key
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = (
        f"Job Dork | {job_config.get('title', 'Search')} "
        f"[{job_config.get('level', 'any')}] | {ts}"
    )
    body_lines = [
        f"Job dork search completed at {ts}.",
        "",
        "Parameters:",
        f"  Title       : {job_config.get('title') or '(any)'}",
        f"  Location    : {job_config.get('location') or '(any)'}",
        f"  Role level  : {job_config.get('level', 'any')}",
        f"  Arrangement : {job_config.get('arrangement') or '(any)'}",
        f"  Benefits    : {job_config.get('benefits') or '(none)'}",
        f"  Posted      : {DATE_FILTERS.get(job_config.get('date_filter', DEFAULT_DATE_FILTER), {}).get('label', 'N/A')}",
        "",
        f"Results attached as: {csv_path.name}",
        f"-- {SCRIPT_NAME}",
    ]

    params: resend.Emails.SendParams = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "text": "\n".join(body_lines),
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
        LOGGER.exception("Unexpected email error")
        print(f"[ERROR] Failed to send email: {exc}")
        sys.exit(1)


def setup_email_wizard() -> None:
    """Interactive wizard to save Resend credentials to .env."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   ✉   Resend email setup                 ║")
    print("╚══════════════════════════════════════════╝\n")
    print("Create an API key : https://resend.com/api-keys")
    print("Verify a domain   : https://resend.com/domains\n")
    print(f"Credentials saved to: {_ENV_FILE}")
    print("Add .env to .gitignore so credentials are never committed.\n")

    api_key = input("Resend API key (re_...) : ").strip()
    if not api_key:
        print("[ERROR] RESEND_API_KEY is required.")
        sys.exit(1)
    if not api_key.startswith("re_"):
        print("  [WARN] Keys usually start with re_ — double-check.\n")

    frm = input("From address (e.g. Job Dork <jobs@yourdomain.com>) : ").strip()
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
            tmp_path: Path | None = None
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


# ══════════════════════════════════════════════════════════════════════════════
# Cron / Task Scheduler installer
# ══════════════════════════════════════════════════════════════════════════════

def _rebuild_argv_without_cron() -> list[str]:
    """Strip --cron <val> from sys.argv and ensure --csv is present."""
    cleaned: list[str] = []
    skip = False
    for tok in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if tok == "--cron":
            skip = True
            continue
        if tok.startswith("--cron="):
            continue
        cleaned.append(tok)
    if "--csv" not in cleaned:
        cleaned.append("--csv")
    return cleaned


def install_cron(schedule_key: str) -> None:
    """Install or replace a crontab / Task Scheduler entry."""
    LOGGER.info("Installing scheduler: %s", schedule_key)
    if platform.system() == "Windows":
        _install_windows_task(schedule_key)
        return

    if schedule_key not in CRON_SCHEDULES:
        print(f"[ERROR] Unknown schedule '{schedule_key}'. "
              f"Valid options: {', '.join(CRON_SCHEDULES)}")
        sys.exit(1)

    sched     = CRON_SCHEDULES[schedule_key]
    cron_expr = sched["expr"]
    label     = sched["label"]
    marker    = "# job_dork_auto"
    argv_tail = _rebuild_argv_without_cron()

    run_script = Path(__file__).resolve().parent / RUN_SCRIPT_NAME
    cmd = (
        shlex.join(["bash", str(run_script)] + argv_tail)
        if run_script.exists()
        else shlex.join([str(sys.executable), str(Path(__file__).resolve())] + argv_tail)
    )
    if not run_script.exists():
        print(f"[WARN] {RUN_SCRIPT_NAME} not found; cron will invoke Python directly.")

    print(f"  Schedule : {label}  ({cron_expr})")
    print(f"  Command  : {cmd}\n")

    if input("Install this cron job? [y/N]: ").strip().lower() != "y":
        print("Aborted.")
        return

    try:
        existing = subprocess.check_output(
            ["crontab", "-l"], stderr=subprocess.DEVNULL
        ).decode()
    except subprocess.CalledProcessError:
        existing = ""

    lines = [l for l in existing.splitlines() if marker not in l]
    lines.append(f"{cron_expr}  {cmd}  {marker}")
    proc = subprocess.run(
        ["crontab", "-"],
        input=("\n".join(lines) + "\n").encode(),
        capture_output=True,
    )
    if proc.returncode != 0:
        print(f"[ERROR] crontab write failed:\n{proc.stderr.decode()}")
        sys.exit(1)

    LOGGER.info("Cron installed: %s", schedule_key)
    print(f"\n  Cron job installed -> {label.lower()}")
    print(f"  View   : crontab -l")
    print(f"  Remove : crontab -e  (delete the line containing '{marker}')")


def _install_windows_task(schedule_key: str) -> None:
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

    argv_tail = _rebuild_argv_without_cron()
    tr_cmd    = subprocess.list2cmdline(
        [str(sys.executable), str(Path(__file__).resolve())] + argv_tail
    )
    task_name = "JobDorkSearch"
    print(f"  Schedule : {label_map[schedule_key]}")
    print(f"  Command  : {tr_cmd}\n")

    if input("Install this scheduled task? [y/N]: ").strip().lower() != "y":
        print("Aborted.")
        return

    result = subprocess.run(
        ["schtasks", "/Create", "/F", "/TN", task_name, "/TR", tr_cmd,
         *trigger_map[schedule_key]],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] schtasks failed:\n{(result.stderr or result.stdout).strip()}")
        sys.exit(1)

    LOGGER.info("Windows task installed: %s", schedule_key)
    print(f'\n  Task "{task_name}" scheduled -> {label_map[schedule_key]}')
    print(f'  View   : schtasks /Query /TN "{task_name}"')
    print(f'  Remove : schtasks /Delete /TN "{task_name}" /F')


# ══════════════════════════════════════════════════════════════════════════════
# Interactive mode
# ══════════════════════════════════════════════════════════════════════════════

def run_interactive() -> dict:
    """Step-by-step prompt. Returns a config dict ready for run()."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   🔍  Google Dork Job Search Tool        ║")
    print("╚══════════════════════════════════════════╝\n")
    print("Use  |  to OR multiple values together in any field.")
    print('Example title: "data engineer | analytics engineer"\n')

    title    = input("Job title / role(s)   : ").strip()
    location = input("Location              : ").strip()

    print(f"\nRole levels: {', '.join(LEVEL_KEYWORDS)}")
    level = input("Role level            (leave blank = any): ").strip() or "any"

    print("\nArrangement tokens: remote | hybrid | on-site")
    arrangement = input("Work arrangement      (leave blank = any): ").strip()

    print("\nBenefit phrases (pipe-separated):")
    print('  e.g. "visa sponsorship | relocation assistance | 4-day work week"')
    benefits = input("Benefits filter       (leave blank = none): ").strip()

    print(f"\nAvailable sites: {', '.join(SITE_DORKS)}")
    print("Special opt-in: google_docs google_sheets linkedin_posts hiring_manager pdf_resumes")
    print("(leave blank = all standard job boards; type 'all' for every site)")
    sites_raw = input("Sites                 (space-separated, blank = default): ").strip()
    if sites_raw.lower() == "all":
        sites = ALL_SITES
    elif sites_raw:
        sites = sites_raw.split()
    else:
        sites = DEFAULT_SITES

    print(f"\nDate filters: {', '.join(DATE_FILTERS)}")
    since = input(f"Posted within         (leave blank = {DEFAULT_DATE_FILTER}): ").strip() or DEFAULT_DATE_FILTER
    if since not in DATE_FILTERS:
        print(f"[WARN] Unknown filter '{since}', using '{DEFAULT_DATE_FILTER}'.")
        since = DEFAULT_DATE_FILTER

    after = input("Show results after    (YYYY-MM-DD, leave blank = none): ").strip()

    # Export / delivery — blank = no
    print()
    do_csv = input("Export to CSV?        [y/N]: ").strip().lower() == "y"
    email  = input("Email CSV to          (leave blank = skip): ").strip() if do_csv else ""
    open_b = input("Open in browser?      [y/N]: ").strip().lower() == "y"

    # Recurring — blank = no
    print(f"\nSchedule options: {', '.join(CRON_SCHEDULES)} — or leave blank")
    cron_in = input("Recurring search      (leave blank = skip): ").strip().lower()
    cron = cron_in if cron_in in CRON_SCHEDULES else ""

    return dict(
        title=title, location=location, level=level,
        arrangement=arrangement, benefits=benefits,
        sites=sites, date_filter=since, after_date=after,
        do_csv=do_csv, email=email,
        open_browser=open_b, cron=cron,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main runner
# ══════════════════════════════════════════════════════════════════════════════

def run(
    title: str,
    location: str,
    level: str,
    sites: list[str],
    open_browser: bool,
    date_filter: str = DEFAULT_DATE_FILTER,
    arrangement: str = "",
    benefits: str = "",
    after_date: str = "",
    do_csv: bool = False,
    email: str = "",
    cron: str = "",
) -> None:
    LOGGER.info(
        "Run | title=%r location=%r level=%r arrangement=%r benefits=%r "
        "sites=%d since=%s after=%s csv=%s email=%s cron=%s",
        title, location, level, arrangement, benefits,
        len(sites), date_filter, after_date or "(none)",
        do_csv, bool(email), bool(cron),
    )

    # ── Validate date filter ───────────────────────────────────────────────────
    if date_filter not in DATE_FILTERS:
        print(f"[WARN] Unknown date filter '{date_filter}', using '{DEFAULT_DATE_FILTER}'.")
        date_filter = DEFAULT_DATE_FILTER

    # ── Validate sites ─────────────────────────────────────────────────────────
    unknown = [s for s in sites if s not in SITE_DORKS]
    if unknown:
        print(f"[WARN] Unknown sites ignored: {unknown}")
        LOGGER.warning("Unknown sites: %s", unknown)
        sites = [s for s in sites if s in SITE_DORKS]
    if not sites:
        print("[ERROR] No valid sites specified.")
        sys.exit(1)

    # ── Build level clause (validates levels internally) ───────────────────────
    level_clause, valid_levels = _build_level_clause(level)
    level_display = " | ".join(valid_levels)

    # ── Display labels ─────────────────────────────────────────────────────────
    title_roles   = _split_pipe(title)
    title_display = " | ".join(title_roles) if title_roles else "(any)"
    arr_tokens    = _split_pipe(arrangement)
    arr_display   = " | ".join(arr_tokens) if arr_tokens else "(any)"
    ben_tokens    = _split_pipe(benefits)
    ben_display   = " | ".join(ben_tokens) if ben_tokens else "(none)"
    date_label    = DATE_FILTERS[date_filter]["label"]
    ts            = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'─'*66}")
    print(f"  Title       : {title_display}")
    print(f"  Location    : {location or '(any)'}")
    print(f"  Role level  : {level_display}")
    print(f"  Arrangement : {arr_display}")
    print(f"  Benefits    : {ben_display}")
    print(f"  Posted      : {date_label}" + (f"  (after {after_date})" if after_date else ""))
    print(f"  Sites       : {len(sites)} boards")
    print(f"{'─'*66}\n")

    # ── Build queries ──────────────────────────────────────────────────────────
    rows: list[dict] = []
    for site_key in sites:
        raw, url = build_query(
            title, location, level_clause, site_key,
            date_filter, arrangement, benefits, after_date,
        )
        rows.append({
            "site":         site_key,
            "title":        title_display,
            "location":     location,
            "level":        level_display,
            "arrangement":  arr_display,
            "benefits":     ben_display,
            "date_filter":  date_label,
            "query":        raw,
            "url":          url,
            "generated_at": ts,
        })
        print(f"[{site_key.upper():18s}]  {raw}")
        print(f"  -> {url}\n")

    # ── Open browser ───────────────────────────────────────────────────────────
    if open_browser:
        LOGGER.info("Opening %d browser tabs", len(rows))
        print(f"Opening {len(rows)} tab(s) in browser ...")
        for row in rows:
            webbrowser.open_new_tab(row["url"])

    # ── Plain-text output (always written) ────────────────────────────────────
    txt_path = Path("dork_results.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("Google Dork Job Search Results\n")
        f.write(
            f"Title: {title_display} | Location: {location} | "
            f"Level: {level_display} | Arrangement: {arr_display} | "
            f"Benefits: {ben_display} | Posted: {date_label}"
            + (f" | After: {after_date}" if after_date else "") + "\n"
        )
        f.write("=" * 70 + "\n\n")
        for row in rows:
            f.write(f"[{row['site'].upper()}]\n")
            f.write(f"Query : {row['query']}\n")
            f.write(f"URL   : {row['url']}\n\n")
    print(f"  Text saved    -> {txt_path.resolve()}")
    LOGGER.info("Text results saved: %s", txt_path)

    # ── CSV export ─────────────────────────────────────────────────────────────
    csv_path: Path | None = None
    if do_csv or email:
        csv_name = _csv_filename(title or "search", date_filter)
        csv_path = export_to_csv(rows, csv_name)
        LOGGER.info("CSV saved: %s", csv_path)

    # ── Email delivery ─────────────────────────────────────────────────────────
    if email:
        job_config = {
            "title": title_display, "location": location,
            "level": level_display, "arrangement": arr_display,
            "benefits": ben_display, "date_filter": date_filter,
        }
        print(f"\nSending results to {email} ...")
        send_email(email, csv_path, job_config)

    # ── Cron install ───────────────────────────────────────────────────────────
    if cron:
        print()
        install_cron(cron)

    print("\nDone.")
    LOGGER.info("Run completed successfully")


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

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
                   help="City/state (omit for location-agnostic results)")
    g.add_argument("--level", default="any",
                   help='Role level; pipe-separate for OR: "mid | senior" (default: any)')
    g.add_argument("--arrangement", default="",
                   help='Work arrangement; pipe-separate for OR: "remote | hybrid | on-site"')
    g.add_argument("--benefits", default="",
                   help='Benefit phrases; pipe-separate: "visa sponsorship | relocation assistance"')
    g.add_argument("--sites", nargs="+",
                   help='Boards to search (default: all standard). Pass "all" for every site. '
                        "See --list-sites.")
    g.add_argument("--since", default=DEFAULT_DATE_FILTER,
                   choices=list(DATE_FILTERS),
                   metavar="|".join(DATE_FILTERS),
                   help=f"Recency filter via tbs= (default: {DEFAULT_DATE_FILTER})")
    g.add_argument("--after", default="", metavar="YYYY-MM-DD",
                   help="Add after: operator — restrict results to after this date")

    o = parser.add_argument_group("Output options")
    o.add_argument("--open",     action="store_true", help="Open query URLs in browser tabs")
    o.add_argument("--csv",      action="store_true", help="Export results to a CSV file")
    o.add_argument("--email",    default="", metavar="ADDRESS",
                   help="Email the CSV via Resend (implies --csv); requires RESEND_API_KEY")
    o.add_argument("--log-file", default="", metavar="PATH",
                   help="Log file path (default: ./logs/job_dork.log)")

    a = parser.add_argument_group("Automation")
    a.add_argument("--cron", default="", choices=list(CRON_SCHEDULES),
                   metavar="|".join(CRON_SCHEDULES),
                   help="Install a recurring cron/Task Scheduler job: daily | 3d | 1w")
    a.add_argument("--setup-email", action="store_true",
                   help="Interactive wizard to configure Resend in .env")

    i = parser.add_argument_group("Info flags")
    i.add_argument("--list-sites",  action="store_true",
                   help="Print all site keys (standard + opt-in) and exit")
    i.add_argument("--list-levels", action="store_true",
                   help="Print role level keywords and exit")
    i.add_argument("--list-dates",  action="store_true",
                   help="Print date filter options and exit")
    i.add_argument("--list-cron",   action="store_true",
                   help="Print cron schedule options and exit")

    args = parser.parse_args()

    log_path = setup_logging(args.log_file)
    sys.excepthook = _log_unhandled_exception
    LOGGER.info("CLI args: %s", sys.argv[1:])
    print(f"Logging to: {log_path}")

    # ── Info exits ─────────────────────────────────────────────────────────────
    if args.list_sites:
        print(f"\nStandard boards ({len(DEFAULT_SITES)}):")
        for k in DEFAULT_SITES:
            op = SITE_DORKS[k][0]
            print(f"  {k:20s}  {op or '(open web)'}")
        opt_in = [k for k in ALL_SITES if k not in DEFAULT_SITES]
        print(f"\nOpt-in strategies ({len(opt_in)}) — pass via --sites:")
        for k in opt_in:
            op = SITE_DORKS[k][0]
            print(f"  {k:20s}  {op}")
        sys.exit(0)

    if args.list_levels:
        print("Role levels (pipe-separate for OR: --level \"mid | senior\"):")
        for k, v in LEVEL_KEYWORDS.items():
            kws = ", ".join(f'"{w}"' for w in v) or "(no keyword filter)"
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

    # ── Resolve sites ──────────────────────────────────────────────────────────
    if args.sites is None:
        sites = DEFAULT_SITES
    elif len(args.sites) == 1 and args.sites[0].lower() == "all":
        sites = ALL_SITES
    else:
        sites = args.sites

    # ── Interactive mode when called bare ──────────────────────────────────────
    if not any([args.title, args.location, args.arrangement, args.benefits]) \
            and len(sys.argv) == 1:
        cfg = run_interactive()
        run(**cfg)
        return

    run(
        title        = args.title or "",
        location     = args.location or "",
        level        = args.level,
        sites        = sites,
        date_filter  = args.since,
        arrangement  = args.arrangement,
        benefits     = args.benefits,
        after_date   = args.after,
        do_csv       = args.csv,
        email        = args.email,
        open_browser = args.open,
        cron         = args.cron,
    )


if __name__ == "__main__":
    main()
