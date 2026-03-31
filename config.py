"""
config.py
=========
All configuration tables for the Google Dork Job Search Generator.

Edit this file to:
  - Add or remove job boards / ATS platforms  (SITE_DORKS, DEFAULT_SITES)
  - Adjust role-level keyword mappings        (LEVEL_KEYWORDS)
  - Change work-arrangement expansions        (ARRANGEMENT_TERMS)
  - Add cron schedule presets                 (CRON_SCHEDULES)
  - Change the default recency filter         (DEFAULT_DATE_FILTER)
"""

# ── Google search base URL ─────────────────────────────────────────────────────
GOOGLE_BASE = "https://www.google.com/search?q="

# ── Default date recency filter ────────────────────────────────────────────────
DEFAULT_DATE_FILTER = "1w"

# ── Date filters -> Google tbs parameter ──────────────────────────────────────
# tbs=qdr:<unit><n>   d=days  w=weeks  m=months
DATE_FILTERS: dict[str, dict] = {
    "any": {"tbs": None,      "label": "No date filter"},
    "1d":  {"tbs": "qdr:d",   "label": "Past 24 hours"},
    "3d":  {"tbs": "qdr:d3",  "label": "Past 3 days"},
    "1w":  {"tbs": "qdr:w",   "label": "Past week"},
    "1m":  {"tbs": "qdr:m",   "label": "Past month"},
}

# ── Cron / Task Scheduler presets ─────────────────────────────────────────────
CRON_SCHEDULES: dict[str, dict] = {
    "daily": {"expr": "0 8 * * *",   "label": "Every day at 8:00 AM"},
    "3d":    {"expr": "0 8 */3 * *", "label": "Every 3 days at 8:00 AM"},
    "1w":    {"expr": "0 8 * * 1",   "label": "Every Monday at 8:00 AM"},
}

# ── Role level -> search keywords ─────────────────────────────────────────────
# Pipe-separate multiple levels on the CLI:  --level "mid | senior"
# All keywords from each listed level are merged into one boolean OR group.
LEVEL_KEYWORDS: dict[str, list[str]] = {
    "intern":    ["intern", "internship", "co-op", "student"],
    "junior":    ["junior", "jr", "entry level", "entry-level", "associate", "new grad"],
    "mid":       ["mid", "mid-level", "intermediate"],
    "senior":    ["senior", "sr", "lead", "staff"],
    "principal": ["principal", "staff", "distinguished"],
    "manager":   ["manager", "engineering manager", "em", "team lead"],
    "director":  ["director", "head of", "vp of"],
    "executive": ["vp", "vice president", "cto", "cpo", "c-level"],
    "any":       [],  # no keyword filter added to query
}

# ── Work arrangement -> search terms ──────────────────────────────────────────
# Pipe-separate multiple values:  --arrangement "remote | hybrid"
# Each token expands to the phrase list below before being OR'd together.
ARRANGEMENT_TERMS: dict[str, list[str]] = {
    "remote":    ["remote", "work from home", "wfh"],
    "hybrid":    ["hybrid"],
    "on-site":   ["on-site", "onsite", "in-office", "in office"],
    # Aliases normalised to the same expansion
    "onsite":    ["on-site", "onsite", "in-office", "in office"],
    "in-office": ["on-site", "onsite", "in-office", "in office"],
}

# ── Job boards, ATS portals, and special search strategies ────────────────────
# Format: "key": (site_operator, extra_terms)
#
#   site_operator  Any Google operator prefix:
#                    site:domain.com   restrict to a domain
#                    filetype:pdf      restrict to file type
#                    intitle:"phrase"  require phrase in page title
#                    ""                no restriction (open web)
#
#   extra_terms    Appended verbatim after the level/title/arrangement/location
#                  clauses. Use OR groups, quoted phrases, minus signs freely.
#
# ─────────────────────────────────────────────────────────────────────────────
SITE_DORKS: dict[str, tuple[str, str]] = {

    # ── Standard aggregators ──────────────────────────────────────────────────
    "linkedin":          ("site:linkedin.com",               "/jobs/view OR /jobs/search"),
    "indeed":            ("site:indeed.com",                 "/viewjob OR /jobs"),
    "glassdoor":         ("site:glassdoor.com",              "/job-listing OR /Jobs"),
    "builtin":           ("site:builtin.com",                "/jobs"),
    "dice":              ("site:dice.com",                   "/jobs/detail"),
    "simplyhired":       ("site:simplyhired.com",            "/job"),
    "ziprecruiter":      ("site:ziprecruiter.com",           "/jobs"),
    "monster":           ("site:monster.com",                "/job-openings"),
    "careerbuilder":     ("site:careerbuilder.com",          "/job"),
    "flexjobs":          ("site:flexjobs.com",               "/jobs"),
    "wellfound":         ("site:wellfound.com",              "/jobs"),
    "ycombinator":       ("site:workatastartup.com",         ""),

    # ── ATS / company career portals ──────────────────────────────────────────
    "lever":             ("site:jobs.lever.co",              ""),
    "greenhouse":        ("site:boards.greenhouse.io",       ""),
    "workday":           ("site:myworkdayjobs.com",          ""),
    "ashby":             ("site:jobs.ashbyhq.com",           ""),
    "workable":          ("site:apply.workable.com",         ""),
    "smartrecruiters":   ("site:jobs.smartrecruiters.com",   ""),
    "icims":             ("site:careers.icims.com",          ""),
    "breezy":            ("site:app.breezy.hr",              ""),
    "rippling":          ("site:ats.rippling.com",           ""),

    # ── Company career pages (open web) ───────────────────────────────────────
    "careers":           ("", 'careers OR "job openings" OR "we\'re hiring"'),

    # ── Hidden job market: Google Docs / Sheets ───────────────────────────────
    # Startups often share role lists in public Docs/Sheets before hitting boards.
    "google_docs":       ("site:docs.google.com",
                          '"we\'re hiring" OR "open roles" OR "now hiring" OR "job openings"'),
    "google_sheets":     ("site:docs.google.com/spreadsheets",
                          '"hiring" OR "open roles" OR "job openings"'),

    # ── Social / direct recruiter posts ───────────────────────────────────────
    # Recruiters post on LinkedIn before listings go live on job boards.
    "linkedin_posts":    ("site:linkedin.com/posts",
                          '"we are hiring" OR "we\'re hiring" OR "now hiring" OR "join our team"'),
    # Surface hiring managers to reach out to directly.
    "hiring_manager":    ('intitle:"hiring manager" OR intitle:"we are hiring"', ""),

    # ── Resume / portfolio intel ───────────────────────────────────────────────
    # Surface publicly uploaded resumes to study how others in the field present.
    "pdf_resumes":       ("filetype:pdf",
                          '"resume" -job -template -apply -"job description"'),
}

# ── Default site set (used when --sites is omitted) ───────────────────────────
# Covers standard aggregators and ATS portals.
# Hidden market, social, and resume intel are opt-in: pass them via --sites.
# Pass --sites all to include every registered key.
DEFAULT_SITES: list[str] = [
    "linkedin", "indeed", "glassdoor", "builtin", "dice", "simplyhired",
    "ziprecruiter", "monster", "careerbuilder", "flexjobs", "wellfound",
    "ycombinator", "lever", "greenhouse", "workday", "ashby", "workable",
    "smartrecruiters", "icims", "breezy", "rippling", "careers",
]

# All registered site keys (including opt-in strategies)
ALL_SITES: list[str] = list(SITE_DORKS.keys())
