"""
jobdork.output.render
=====================
Writes the scan out as a file you can open.

This is the read-only dashboard: one self-contained HTML page, no server, no
JavaScript framework, no external request. It works from a cron job's output
and it works as an email attachment, which a localhost server does not.

`jobdork serve` is the same list with buttons. Both read the same database, so
they cannot disagree.
"""

from __future__ import annotations

import contextlib
import csv
import html
import json
import sqlite3
import time
from pathlib import Path

from ..core.textutil import cap, platform_name
from ..search.geo import distance_label
from ..search.resume import flag_label

# Written by to_csv, in this order. Stable on purpose: a spreadsheet or a
# script pointed at yesterday's export should still work against today's.
CSV_COLUMNS = (
    "uid", "score", "status", "title", "company", "location", "distance_mi",
    "work_mode", "salary_stated", "salary_min", "salary_max", "salary_currency",
    "salary_period", "platform", "posted_at", "first_seen", "url", "flags",
    "fit",
)

STATUS_COLOURS = {
    "new": "#6b7280", "viewed": "#0891b2", "interested": "#2563eb", "applied": "#7c3aed",
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
        # dict(row), not `{k: row[k] for k in row}`: iterating an sqlite3.Row
        # yields its values, and a lint "simplification" of `.keys()` to that
        # broke roles.json, and with it every scan that wrote one.
        item = dict(row)
        item["flags"] = _flags(row)
        # Stored as JSON text; written out as JSON, not as strings inside it.
        for key in ("reasons", "score_parts", "llm_judgement"):
            if isinstance(item.get(key), str):
                with contextlib.suppress(json.JSONDecodeError):
                    item[key] = json.loads(item[key])
        judgement = item.get("llm_judgement")
        if isinstance(judgement, dict) and isinstance(judgement.get("score"), (int, float)):
            from ..ai.llm import verdict_for
            judgement["verdict"] = verdict_for(judgement["score"])
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
                "" if row["fit"] is None else f"{row['fit']:.1f}",
            ])
    return path


def to_markdown(rows: list[sqlite3.Row], path: Path, cfg=None,
                report=None) -> Path:
    """The same list as text, for pasting into a note or an email."""
    units = getattr(getattr(cfg, "locations", None), "units", "mi") or "mi"
    lines = [
        "# jobdork",
        "",
        f"{time.strftime('%A %d %B %Y, %H:%M')}: {len(rows)} job posts, "
        "settled ones hidden.",
        "",
    ]

    if cfg:
        floor = (f"{cfg.salary.floor:,.0f} {cfg.salary.currency}"
                 if cfg.salary.floor else "none")
        radius = (cfg.locations.radius if cfg.locations.radius == "exact"
                  else f"{cfg.locations.radius} {units}")
        lines += [
            f"- Anchor: {cfg.locations.anchor or 'anywhere'}",
            f"- Radius: {radius}",
            f"- Countries: {', '.join(cfg.locations.countries) or 'any'}",
            f"- Work modes: {', '.join(cfg.locations.work_modes) or 'all'}",
            f"- Salary floor: {floor}",
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
        meta = _meta(row, units)
        score = "-" if row["score"] is None else f"{row['score']:.0f}"
        title = (row["title"] or "").replace("[", "").replace("]", "")
        fit = "–" if row["fit"] is None else f"{row['fit']:.0f}"
        lines.append(f"### Match {score} · fit {fit}/25 · [{title}]({row['url']})")
        lines.append("")
        lines.append(" · ".join(str(m) for m in meta if m))
        lines.append("")
        lines.append(f"`{row['uid']}` · **{cap(row['status'] or 'new')}**")
        flags = _flags(row)
        if flags:
            lines.append("")
            lines += [f"- {flag_label(flag)}" for flag in flags]
        lines.append("")

    notes = []
    if report:
        for result in report.per_source:
            if result.skipped:
                notes.append(f"`{result.source}` skipped: {result.skipped}")
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


def _meta(row: sqlite3.Row, units: str) -> list[str]:
    """Company, place, distance, arrangement, pay and source, as shown.

    The distance is stored in miles and converted to the reader's units: it
    was printed as miles with "km" after it, or always as "mi".
    """
    return [
        row["company"], row["location_raw"],
        distance_label(row["distance_mi"], units),
        cap(row["work_mode"] or "arrangement not stated"),
        cap(_salary(row)), platform_name(row["platform"]),
    ]


def to_html(rows: list[sqlite3.Row], path: Path, cfg=None,
            report=None) -> Path:
    units = getattr(getattr(cfg, "locations", None), "units", "mi") or "mi"
    parts: list[str] = []
    for row in rows:
        status = row["status"] or "new"
        colour = STATUS_COLOURS.get(status, "#6b7280")
        meta = [*_meta(row, units),
                f"First seen {row['first_seen'][:10]}" if row["first_seen"] else ""]
        flags = "".join(
            f'<span class="flag">{_e(flag_label(f))}</span>' for f in _flags(row)
        )
        parts.append(f"""
      <div class="role">
        <div class="role-head">
          <span class="score" title="Title, arrangement, distance, salary and resume fit, added up">Match {'-' if row['score'] is None else f"{row['score']:.0f}"}</span>
          <span class="uid" title="Resume fit, out of 25">Fit {'–' if row['fit'] is None else f"{row['fit']:.0f}"}/25</span>
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
        stats.append(f"Anchor <b>{_e(cfg.locations.anchor or 'anywhere')}</b>")
        # The reader's units: this said "mi" to a reader in kilometres.
        stats.append(f"Radius <b>{_e(cfg.locations.radius)}</b>"
                     + (f" {_e(units)}" if cfg.locations.radius != "exact" else ""))
        stats.append("Work modes <b>"
                     + _e(", ".join(cfg.locations.work_modes) or "all") + "</b>")
        floor = (f"{cfg.salary.floor:,.0f} {cfg.salary.currency}"
                 if cfg.salary.floor else "none")
        stats.append(f"Salary floor <b>{_e(floor)}</b>")
    if report:
        stats.append(f"Fetched <b>{report.fetched}</b>")
        stats.append(f"New <b>{report.newly_seen}</b>")
    stats.append(f"Showing <b>{len(rows)}</b>")

    notes = []
    if report:
        for result in report.per_source:
            if result.skipped:
                notes.append(f"{result.source}: skipped ({result.skipped})")
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
<title>jobdork: {len(rows)} job posts</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>jobdork</h1>
<p class="sub">{time.strftime('%A %d %B %Y, %H:%M')}. Settled job posts are hidden.
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


def write_all(rows: list[sqlite3.Row], cfg, report=None) -> list[Path]:
    """Every format in `output.formats`, to `output.dir`. Returns the paths.

    One function for the terminal and the dashboard: the dashboard's scan
    wrote only html and json, so md and csv went stale when you scanned from
    the page.
    """
    out = Path(cfg.output.dir)
    writers = {
        "html": lambda: to_html(rows, out / "index.html", cfg, report),
        "json": lambda: to_json(rows, out / "roles.json"),
        "md":   lambda: to_markdown(rows, out / "roles.md", cfg, report),
        "csv":  lambda: to_csv(rows, out / "roles.csv"),
    }
    written = []
    for fmt in cfg.output.formats:
        write = writers.get(fmt)
        if write is None:
            # Unreachable: the config validator rejects unknown formats. Kept
            # so a format added there and not here fails loudly.
            raise ValueError(f"no writer for output format {fmt!r}")
        written.append(Path(write()))
    return written
