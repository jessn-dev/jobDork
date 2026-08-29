"""
jobdork.digest
==============
Mails what a scan found, so the roles come to you instead of you going to a
dashboard.

This is the piece that makes a scheduled scan worth scheduling. A dashboard is
something you have to remember to open; a digest arrives, and the roles that
arrived with it are the ones that were not there yesterday.

Two rules it inherits from the rest of the tool:

  **An empty digest is not sent by default.** A mail that says "nothing new"
  every morning trains you to ignore the mail that says something. Use
  `--even-if-empty` if you would rather have the heartbeat.

  **New means new.** The digest reports roles first seen on the most recent
  scan date, not everything still open. A digest that resends the same three
  hundred rows every day is a digest you stop reading.

Credentials come from `.env`, the same two the dork generator already uses:

    RESEND_API_KEY="re_..."
    RESEND_FROM="Job Dork <jobs@yourdomain.com>"
"""

from __future__ import annotations

import base64
import html as html_mod
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("jobdork.digest")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Resend rejects anything larger; the CSV would have to be enormous to reach
# this, but a scan with no filters could.
MAX_ATTACHMENT_BYTES = 30 * 1024 * 1024


class DigestError(Exception):
    """Raised when the digest cannot be built or sent. Always reported, never
    swallowed — a digest that silently fails is a scan you think you read."""


def resend_api_key() -> str:
    return (os.environ.get("RESEND_API_KEY") or "").strip()


def resend_from_address() -> str:
    """Matches the dork generator's resolution order, including its old name."""
    return (
        os.environ.get("RESEND_FROM")
        or os.environ.get("JOB_DORK_EMAIL_FROM")
        or ""
    ).strip()


def looks_like_email(address: str) -> bool:
    return bool(_EMAIL.match((address or "").strip()))


# ── building it ────────────────────────────────────────────────────────────────


@dataclass
class Digest:
    rows: list[sqlite3.Row] = field(default_factory=list)
    subject: str = ""
    text: str = ""
    html: str = ""
    csv_bytes: bytes = b""
    csv_name: str = ""

    @property
    def empty(self) -> bool:
        return not self.rows


def _flags(row: sqlite3.Row) -> list[str]:
    try:
        return json.loads(row["flags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


def _salary(row: sqlite3.Row) -> str:
    if not row["salary_stated"]:
        return "unconfirmed salary"
    lo, hi, cur = row["salary_min"], row["salary_max"], row["salary_currency"] or ""
    if lo and hi:
        return f"{cur} {lo:,.0f}–{hi:,.0f}"
    value = hi or lo
    return f"{cur} {value:,.0f}" if value else "unconfirmed salary"


def _meta(row: sqlite3.Row, units: str) -> list[str]:
    distance = (f"{row['distance_mi']:.0f} {units}"
                if row["distance_mi"] is not None else "")
    return [str(part) for part in (
        row["company"], row["location_raw"], distance,
        row["work_mode"] or "arrangement not stated",
        _salary(row), row["platform"],
    ) if part]


def build(rows: list[sqlite3.Row], cfg, new_only: bool = True) -> Digest:
    """Render the mail. Does not send, and does not need a credential."""
    units = getattr(getattr(cfg, "locations", None), "units", "mi") or "mi"
    stamp = time.strftime("%a %d %b %Y")
    scope = "new roles" if new_only else "open roles"

    digest = Digest(rows=list(rows))
    digest.subject = (
        f"jobdork — {len(rows)} {scope}, {stamp}" if rows
        else f"jobdork — nothing new, {stamp}"
    )

    # ── plain text: the version that always renders ────────────────────────────
    lines = [digest.subject, ""]
    if cfg:
        radius = (cfg.locations.radius if cfg.locations.radius == "exact"
                  else f"{cfg.locations.radius} {units}")
        lines += [
            f"{cfg.locations.anchor or 'anywhere'} · within {radius} · "
            f"{', '.join(cfg.locations.countries) or 'any country'}",
            "",
        ]
    if not rows:
        lines.append("Nothing appeared since the last scan.")
    for row in rows:
        score = "-" if row["score"] is None else f"{row['score']:.0f}"
        lines += [
            f"[{score}] {row['title']} — {row['company']}",
            f"       {' · '.join(_meta(row, units))}",
        ]
        for flag in _flags(row):
            lines.append(f"       · {flag}")
        lines += [f"       {row['url']}", ""]
    lines += [
        "---",
        "Salary reads 'unconfirmed' where the employer published no figure,",
        "which is most of them. Only a published number can hide a role.",
        "",
        "jobdork applied <uid> -s applied    to record what you did",
    ]
    digest.text = "\n".join(lines)

    # ── html ───────────────────────────────────────────────────────────────────
    def esc(value) -> str:
        return html_mod.escape(str(value or ""))

    parts = [
        '<div style="font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;'
        'max-width:680px;margin:0 auto;color:#18181b">',
        f"<h2 style='margin:0 0 4px'>{esc(digest.subject)}</h2>",
    ]
    if cfg:
        radius = (cfg.locations.radius if cfg.locations.radius == "exact"
                  else f"{cfg.locations.radius} {units}")
        parts.append(
            f"<p style='color:#71717a;margin:0 0 20px;font-size:13px'>"
            f"{esc(cfg.locations.anchor or 'anywhere')} · within {esc(radius)} · "
            f"{esc(', '.join(cfg.locations.countries) or 'any country')}</p>"
        )
    if not rows:
        parts.append("<p>Nothing appeared since the last scan.</p>")
    for row in rows:
        score = "-" if row["score"] is None else f"{row['score']:.0f}"
        flags = "".join(
            f"<span style='background:#fef3c7;color:#92400e;font-size:12px;"
            f"padding:1px 6px;border-radius:4px;margin-right:4px'>{esc(f)}</span>"
            for f in _flags(row)
        )
        parts.append(
            "<div style='border:1px solid #e4e4e7;border-radius:8px;"
            "padding:12px 14px;margin-bottom:8px'>"
            f"<div><b style='color:#1d4ed8'>{esc(score)}</b> "
            f"<a href='{esc(row['url'])}' style='color:#18181b;font-weight:600;"
            f"text-decoration:none'>{esc(row['title'])}</a></div>"
            f"<div style='color:#71717a;font-size:13px;margin-top:4px'>"
            f"{esc(' · '.join(_meta(row, units)))}</div>"
            + (f"<div style='margin-top:6px'>{flags}</div>" if flags else "")
            + "</div>"
        )
    parts.append(
        "<p style='color:#71717a;font-size:12px;border-top:1px solid #e4e4e7;"
        "padding-top:12px;margin-top:20px'>Salary reads &ldquo;unconfirmed&rdquo; "
        "where the employer published no figure, which is most of them. Only a "
        "published number can hide a role.</p></div>"
    )
    digest.html = "\n".join(parts)
    return digest


def attach_csv(digest: Digest, rows: list[sqlite3.Row]) -> Digest:
    """Attach the same roles as a CSV, using the normal writer.

    Written through `render.to_csv` rather than a second implementation, so the
    columns in your inbox and the columns in `out/roles.csv` cannot drift.
    """
    import tempfile

    from . import render

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"jobdork_{time.strftime('%Y%m%d_%H%M')}.csv"
        render.to_csv(rows, path)
        payload = path.read_bytes()
        if len(payload) > MAX_ATTACHMENT_BYTES:
            raise DigestError(
                f"CSV is {len(payload) / 1e6:.0f}MB, over the 30MB attachment "
                "limit. Narrow the search or send without --csv."
            )
        digest.csv_bytes = payload
        digest.csv_name = path.name
    return digest


# ── sending it ─────────────────────────────────────────────────────────────────

def send(digest: Digest, to_address: str) -> str:
    """Send via Resend. Returns the message id.

    Every failure raises DigestError with the reason, rather than exiting: a
    scheduled scan should log why the mail failed and still have stored its
    roles.
    """
    import resend
    from resend.exceptions import ResendError

    to_address = (to_address or "").strip()
    if not looks_like_email(to_address):
        raise DigestError(f"{to_address!r} is not an email address")

    api_key = resend_api_key()
    if not api_key:
        raise DigestError(
            "RESEND_API_KEY is missing from .env. Get one at "
            "https://resend.com/api-keys, or run `python main.py --setup-email`."
        )
    from_address = resend_from_address()
    if not from_address:
        raise DigestError(
            'RESEND_FROM is missing from .env. Example: '
            'RESEND_FROM="Job Dork <jobs@yourdomain.com>". '
            "The domain has to be verified at https://resend.com/domains."
        )

    resend.api_key = api_key
    params = {
        "from": from_address,
        "to": [to_address],
        "subject": digest.subject,
        "text": digest.text,
        "html": digest.html,
    }
    if digest.csv_bytes:
        params["attachments"] = [{
            "filename": digest.csv_name,
            "content": base64.standard_b64encode(digest.csv_bytes).decode("ascii"),
            "content_type": "text/csv",
        }]

    try:
        result = resend.Emails.send(params)
    except ResendError as exc:
        detail = f"{exc.error_type}: {exc.message}"
        if exc.suggested_action:
            detail += f" — {exc.suggested_action.strip()}"
        raise DigestError(f"Resend refused the message ({detail})") from exc
    except Exception as exc:
        raise DigestError(f"could not send: {exc}") from exc

    message_id = result.get("id", "?")
    log.info("digest sent to %s (id %s)", to_address, message_id)
    return message_id
