"""
jobdork.render
==============
Writes the scan out as a file you can open.

This is the read-only dashboard: one self-contained HTML page, no server, no
JavaScript framework, no external request. It works from a cron job's output
and it works as an email attachment, which a localhost server does not.

`jobdork serve` is the same list with buttons. Both read the same database, so
they cannot disagree.
"""

from __future__ import annotations

import csv
import html
import json
import sqlite3
import time
from pathlib import Path

# Written by to_csv, in this order. Stable on purpose: a spreadsheet or a
# script pointed at yesterday's export should still work against today's.
CSV_COLUMNS = (
    "uid", "score", "status", "title", "company", "location", "distance_mi",
    "work_mode", "salary_stated", "salary_min", "salary_max", "salary_currency",
    "salary_period", "platform", "posted_at", "first_seen", "url", "flags",
)

STATUS_COLOURS = {
    "new": "#6b7280", "interested": "#2563eb", "applied": "#7c3aed",
    "submitted": "#7c3aed", "interviewing": "#c2410c", "offer": "#15803d",
    "rejected": "#991b1b", "withdrawn": "#991b1b", "skipped": "#4b5563",
    "closed": "#4b5563",
}

CSS = """
:root { color-scheme: light dark;
  --bg:#ffffff; --fg:#18181b; --muted:#71717a; --line:#e4e4e7;
  --card:#fafafa; --accent:#1d4ed8; --flag:#92400e; --flagbg:#fef3c7; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0b0b0d; --fg:#e7e7ea; --muted:#a1a1aa; --line:#27272a;
          --card:#141417; --accent:#93b4ff; --flag:#fde68a; --flagbg:#3f2d0a; }
}
* { box-sizing: border-box; }
body { margin:0; padding:2rem 1.25rem; background:var(--bg); color:var(--fg);
  font:15px/1.55 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif; }
.wrap { max-width: 1100px; margin: 0 auto; }
h1 { font-size:1.5rem; margin:0 0 .25rem; }
.sub { color:var(--muted); margin:0 0 1.5rem; font-size:.9rem; }
.stats { display:flex; flex-wrap:wrap; gap:.5rem 1.5rem; margin-bottom:1.5rem;
  padding:.85rem 1rem; background:var(--card); border:1px solid var(--line);
  border-radius:8px; font-size:.85rem; }
.stats b { font-variant-numeric: tabular-nums; }
.role { border:1px solid var(--line); border-radius:8px; padding:.9rem 1rem;
  margin-bottom:.6rem; background:var(--card); }
.role-head { display:flex; gap:.75rem; align-items:baseline; flex-wrap:wrap; }
.score { font-variant-numeric:tabular-nums; font-weight:600; color:var(--accent);
  min-width:3ch; }
.title { font-weight:600; }
.title a { color:inherit; text-decoration:none; }
.title a:hover { text-decoration:underline; }
.company { color:var(--muted); }
.meta { color:var(--muted); font-size:.85rem; margin-top:.35rem;
  display:flex; gap:.4rem 1rem; flex-wrap:wrap; }
.pill { display:inline-block; padding:.1rem .5rem; border-radius:999px;
  font-size:.72rem; font-weight:600; color:#fff; text-transform:uppercase;
  letter-spacing:.02em; }
.flags { margin-top:.45rem; display:flex; gap:.35rem; flex-wrap:wrap; }
.flag { background:var(--flagbg); color:var(--flag); font-size:.75rem;
  padding:.1rem .45rem; border-radius:4px; }
.uid { font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:.75rem; color:var(--muted); }
.empty { color:var(--muted); padding:2rem 0; }
footer { margin-top:2rem; color:var(--muted); font-size:.8rem;
  border-top:1px solid var(--line); padding-top:1rem; }
"""


def _e(text) -> str:
    return html.escape(str(text or ""))


def _salary(row: sqlite3.Row) -> str:
    if not row["salary_stated"]:
        return "unconfirmed salary"
    lo, hi = row["salary_min"], row["salary_max"]
    cur = row["salary_currency"] or ""
    if lo and hi:
        return f"{cur} {lo:,.0f}–{hi:,.0f}"
    value = hi or lo
    return f"{cur} {value:,.0f}" if value else "unconfirmed salary"


def _flags(row: sqlite3.Row) -> list[str]:
    try:
        return json.loads(row["flags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    out = []
    for row in rows:
        item = {k: row[k] for k in row}
        item["flags"] = _flags(row)
        # The advert is large and nobody reads it out of a JSON dump.
        item.pop("description", None)
        out.append(item)
    return out


def to_json(rows: list[sqlite3.Row], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
             "count": len(rows), "roles": rows_to_dicts(rows)},
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def to_csv(rows: list[sqlite3.Row], path: Path) -> Path:
    """One row per role, for a spreadsheet or another script.

    The advert is left out deliberately: a 5,000-character description in a
    CSV cell breaks every viewer that opens it, and `jobdork show` is where
    the advert belongs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            distance = row["distance_mi"]
            writer.writerow([
                row["uid"],
                "" if row["score"] is None else f"{row['score']:.1f}",
                row["status"] or "new",
                row["title"] or "",
                row["company"] or "",
                row["location_raw"] or "",
                "" if distance is None else f"{distance:.1f}",
                row["work_mode"] or "",
                # The distinction the whole salary rule turns on: a blank pay
                # range because nobody published one is not a zero.
                "yes" if row["salary_stated"] else "no",
                "" if row["salary_min"] is None else f"{row['salary_min']:.0f}",
                "" if row["salary_max"] is None else f"{row['salary_max']:.0f}",
                row["salary_currency"] or "",
                row["salary_period"] or "",
                row["platform"] or "",
                row["posted_at"] or "",
                (row["first_seen"] or "")[:10],
                row["url"] or "",
                "; ".join(_flags(row)),
            ])
    return path


def to_markdown(rows: list[sqlite3.Row], path: Path, cfg=None,
                report=None) -> Path:
    """The same list as text, for pasting into a note or an email."""
    units = getattr(getattr(cfg, "locations", None), "units", "mi") or "mi"
    lines = [
        "# jobdork",
        "",
        f"{time.strftime('%A %d %B %Y, %H:%M')} — {len(rows)} roles, "
        "settled ones hidden.",
        "",
    ]

    if cfg:
        floor = (f"{cfg.salary.floor:,.0f} {cfg.salary.currency}"
                 if cfg.salary.floor else "none")
        radius = (cfg.locations.radius if cfg.locations.radius == "exact"
                  else f"{cfg.locations.radius} {units}")
        lines += [
            f"- **anchor** {cfg.locations.anchor or 'anywhere'}",
            f"- **radius** {radius}",
            f"- **countries** {', '.join(cfg.locations.countries) or 'any'}",
            f"- **modes** {', '.join(cfg.locations.work_modes) or 'all'}",
            f"- **salary floor** {floor}",
            "",
        ]

    lines += [
        "Salary reads *unconfirmed* where the employer published no figure, "
        "which is most of them.",
        "",
        "---",
        "",
    ]

    if not rows:
        lines.append("_Nothing matched. Widen the radius, or add a title._")
    for row in rows:
        distance = (f"{row['distance_mi']:.0f} {units}"
                    if row["distance_mi"] is not None else "")
        meta = [
            row["company"], row["location_raw"], distance,
            row["work_mode"] or "arrangement not stated",
            _salary(row), row["platform"],
        ]
        score = "-" if row["score"] is None else f"{row['score']:.0f}"
        title = (row["title"] or "").replace("[", "").replace("]", "")
        lines.append(f"### {score} · [{title}]({row['url']})")
        lines.append("")
        lines.append(" · ".join(str(m) for m in meta if m))
        lines.append("")
        lines.append(f"`{row['uid']}` · **{row['status'] or 'new'}**")
        flags = _flags(row)
        if flags:
            lines.append("")
            lines += [f"- {flag}" for flag in flags]
        lines.append("")

    notes = []
    if report:
        for result in report.per_source:
            if result.skipped:
                notes.append(f"`{result.source}` skipped — {result.skipped}")
            elif result.suspect:
                notes.append(
                    f"`{result.source}` answered empty. These APIs return 200 "
                    "with nothing both for a dead board and for a throttle, so "
                    "this is *unknown*, not *not hiring*."
                )
        for host in report.blocked_hosts:
            notes.append(f"`{host}` blocked after repeated 429s, left alone.")
    if notes:
        lines += ["---", "", "## Notes", ""] + [f"- {n}" for n in notes]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def to_html(rows: list[sqlite3.Row], path: Path, cfg=None,
            report=None) -> Path:
    parts: list[str] = []
    for row in rows:
        status = row["status"] or "new"
        colour = STATUS_COLOURS.get(status, "#6b7280")
        distance = (f"{row['distance_mi']:.0f} mi"
                    if row["distance_mi"] is not None else "")
        meta = [
            row["company"], row["location_raw"], distance,
            row["work_mode"] or "arrangement not stated",
            _salary(row), row["platform"],
            f"first seen {row['first_seen'][:10]}" if row["first_seen"] else "",
        ]
        flags = "".join(
            f'<span class="flag">{_e(f)}</span>' for f in _flags(row)
        )
        parts.append(f"""
      <div class="role">
        <div class="role-head">
          <span class="score">{row['score'] if row['score'] is not None else '-'}</span>
          <span class="title"><a href="{_e(row['url'])}" rel="noopener noreferrer"
            target="_blank">{_e(row['title'])}</a></span>
          <span class="pill" style="background:{colour}">{_e(status)}</span>
          <span class="uid">{_e(row['uid'])}</span>
        </div>
        <div class="meta">{''.join(f'<span>{_e(m)}</span>' for m in meta if m)}</div>
        {f'<div class="flags">{flags}</div>' if flags else ''}
      </div>""")

    body = "\n".join(parts) or '<p class="empty">Nothing matched. Widen the radius, or add a title.</p>'

    stats = []
    if cfg:
        stats.append(f"anchor <b>{_e(cfg.locations.anchor or 'anywhere')}</b>")
        stats.append(f"radius <b>{_e(cfg.locations.radius)}</b>"
                     + (" mi" if cfg.locations.radius != "exact" else ""))
        stats.append("modes <b>"
                     + _e(", ".join(cfg.locations.work_modes) or "all") + "</b>")
        floor = (f"{cfg.salary.floor:,.0f} {cfg.salary.currency}"
                 if cfg.salary.floor else "none")
        stats.append(f"floor <b>{_e(floor)}</b>")
    if report:
        stats.append(f"fetched <b>{report.fetched}</b>")
        stats.append(f"new <b>{report.newly_seen}</b>")
    stats.append(f"showing <b>{len(rows)}</b>")

    notes = []
    if report:
        for result in report.per_source:
            if result.skipped:
                notes.append(f"{result.source}: skipped — {result.skipped}")
            elif result.suspect:
                notes.append(
                    f"{result.source}: answered empty. Several of these APIs "
                    "return 200 with nothing both for a dead board and for a "
                    "throttle, so this is 'unknown', not 'not hiring'."
                )
        for host in report.blocked_hosts:
            notes.append(f"{host}: blocked after repeated 429s, left alone.")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>jobdork — {len(rows)} roles</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>jobdork</h1>
<p class="sub">{time.strftime('%A %d %B %Y, %H:%M')} — settled roles are hidden.
Salary reads &ldquo;unconfirmed&rdquo; where the employer published no figure,
which is most of them.</p>
<div class="stats">{''.join(f'<span>{s}</span>' for s in stats)}</div>
{body}
<footer>{'<br>'.join(_e(n) for n in notes) if notes else 'All sources answered.'}
<br>Generated by jobdork. Nothing here was fetched from an aggregator.</footer>
</div></body></html>"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
