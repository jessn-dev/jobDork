"""
config.py — Static configuration for Google Dork Job Search Generator.

Import from here instead of defining constants inline in main.py.
"""

from pathlib import Path

# ─────────────────────────────────────────────
# Script / path constants
# ─────────────────────────────────────────────
SCRIPT_NAME     = "main.py"
RUN_SCRIPT_NAME = "run.sh"
LOG_DIR         = Path(__file__).parent / "logs"
DEFAULT_LOG_FILE = LOG_DIR / "job_dork.log"

GOOGLE_BASE = "https://www.google.com/search?q="

# ─────────────────────────────────────────────
# Date filter -> Google tbs parameter
# Google's tbs=qdr:<unit><n> means "past N units"
#   d = days | w = weeks | m = months
# ─────────────────────────────────────────────
DATE_FILTERS: dict[str, dict] = {
    "any": {"tbs": None,      "label": "No date filter"},
    "1d":  {"tbs": "qdr:d",   "label": "Past 24 hours"},
    "3d":  {"tbs": "qdr:d3",  "label": "Past 3 days"},
    "1w":  {"tbs": "qdr:w",   "label": "Past week"},
    "1m":  {"tbs": "qdr:m",   "label": "Past month"},
}

# ─────────────────────────────────────────────
# Cron schedule expressions
# ─────────────────────────────────────────────
CRON_SCHEDULES: dict[str, dict] = {
    "daily": {"expr": "0 8 * * *",   "label": "Every day at 8:00 AM"},
    "3d":    {"expr": "0 8 */3 * *", "label": "Every 3 days at 8:00 AM"},
    "1w":    {"expr": "0 8 * * 1",   "label": "Every Monday at 8:00 AM"},
}

# ─────────────────────────────────────────────
# Seniority keyword mappings
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
# Site-specific dork templates
# Each value is a (site_operator, path_hint) tuple.
# ─────────────────────────────────────────────
SITE_DORKS: dict[str, tuple[str, str]] = {
    "linkedin":     ("site:linkedin.com",          "/jobs/view OR /jobs/search"),
    "indeed":       ("site:indeed.com",            "/viewjob OR /jobs"),
    "glassdoor":    ("site:glassdoor.com",         "/job-listing OR /Jobs"),
    "lever":        ("site:jobs.lever.co",         ""),
    "greenhouse":   ("site:boards.greenhouse.io",  ""),
    "workday":      ("site:myworkdayjobs.com",     ""),
    "ashby":        ("site:jobs.ashbyhq.com",      ""),
    "builtin":      ("site:builtin.com",           "/jobs"),
    "dice":         ("site:dice.com",              "/jobs/detail"),
    "simplyhired":  ("site:simplyhired.com",       "/job"),
    "ziprecruiter": ("site:ziprecruiter.com",      "/jobs"),
    "careers":      ("",                           'careers OR "job openings" OR "we\'re hiring"'),
}
