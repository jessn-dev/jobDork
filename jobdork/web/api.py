"""
jobdork.web.api
===============
The dashboard's half of every command the CLI has.

The rule this file exists to keep: **anything you can do in the terminal, you
can do in the page, and the result of either shows up in the other.** They are
not two programs sharing a database, they are two front ends over the same
functions — `scan`, `enrich`, `discover`, `generate` and the rest are called
here exactly as `cli.py` calls them, so there is no second implementation to
drift.

The long ones run through the Runner and report over the event stream, because
a scan takes minutes and drafting a CV spends money; both are things you want
to watch rather than wait blindly for.

Two things are handled carefully because they take input from a browser:

  **The resume upload.** The filename is never trusted: the extension is
  checked against a short list and the file is written to a name this code
  chooses, in a directory this code chooses. A browser can suggest
  `../../.ssh/authorized_keys` and it will land as `resume.pdf`.

  **Reading a generated document.** Only paths recorded in the `artifacts`
  table are served. The page cannot ask for an arbitrary file, so a bug in the
  front end cannot turn the dashboard into a file browser.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from ..core.textutil import platform_name

log = logging.getLogger("jobdork.web.api")

# Formats the resume reader understands. Anything else is refused by name
# rather than accepted and silently unread.
RESUME_SUFFIXES = (".pdf", ".docx", ".md", ".markdown", ".txt")
MAX_RESUME_BYTES = 10 * 1024 * 1024

UID = re.compile(r"^[0-9a-f]{12}$")

# A pasted advert. The longest measured one is 7,341 characters; this is room
# for ten of those, and a bound on what a page can make the database hold.
MAX_ADVERT_CHARS = 80_000


class ApiError(Exception):
    """Something the page asked for that cannot be done. Carries a status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ── reading ───────────────────────────────────────────────────────────────────


def ai_fields(row) -> dict:
    """The model's verdict and the listing check, for the page."""
    try:
        judgement = json.loads(row["llm_judgement"] or "null")
    except (json.JSONDecodeError, TypeError, IndexError, KeyError):
        judgement = None
    if isinstance(judgement, dict):
        # Verdicts stored before the humanizer rules get the same fix on the
        # way out; quotes of the advert stay as written.
        from ..writing.humanize import clean
        judgement["summary"] = clean(judgement.get("summary", ""), keep_quotes=True)
        # Verdicts stored before the word followed the score (llm._clean_judgement).
        if isinstance(judgement.get("score"), (int, float)):
            from ..ai.llm import verdict_for
            judgement["verdict"] = verdict_for(judgement["score"])
        for key in ("reasons", "concerns"):
            judgement[key] = [clean(x, keep_quotes=True) for x in judgement.get(key) or []]
    return {
        "ai": judgement if isinstance(judgement, dict) else None,
        "listing": {"state": row["listing_state"] or "",
                    "note": row["listing_note"] or "",
                    "checked_at": (row["listing_checked_at"] or "")[:16]},
    }


def score_parts(row) -> list[dict]:
    """How a stored score was reached; empty for a role not screened since v4."""
    try:
        parts = json.loads(row["score_parts"] or "[]")
    except (json.JSONDecodeError, TypeError, IndexError, KeyError):
        return []
    return parts if isinstance(parts, list) else []


def role_detail(cfg, uid: str) -> dict:
    """One role in full, including the advert and anything generated for it."""
    from ..db.store import Store

    if not UID.match(uid or ""):
        raise ApiError("not a job post id")

    with Store(cfg.db_path) as store:
        row = store.get(uid)
        if row is None:
            raise ApiError("no such job post", 404)
        artifacts = [
            {
                "id": a["id"],
                "kind": a["kind"],
                "path": a["path"],
                "created_at": a["created_at"],
                "gates": _gates(a["gates_json"])[0],
                "exists": bool(a["path"] and Path(a["path"]).is_file()),
            }
            for a in store.artifacts(uid)
        ]
        copies = [
            {"uid": c["uid"], "platform": c["platform"], "url": c["url"] or "",
             "listing": c["listing_state"] or "", "note": c["listing_note"] or "",
             "advert_chars": c["advert_chars"], "last_seen": (c["last_seen"] or "")[:10]}
            for c in store.copies(uid)
        ]
        ai = ai_fields(row)
        # The verdict's rating, so the dialog shows which thumb is pressed.
        if ai["ai"] and ai["ai"].get("ai_output_id"):
            output = store.ai_output(int(ai["ai"]["ai_output_id"]))
            ai["ai"]["feedback"] = output["feedback"] if output else None

    try:
        flags = json.loads(row["flags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        flags = []

    return {
        "uid": row["uid"],
        "title": row["title"] or "",
        "company": row["company"] or "",
        "url": row["url"] or "",
        "platform": row["platform"] or "",
        "location": row["location_raw"] or "",
        "work_mode": row["work_mode"] or "",
        "status": row["status"] or "new",
        "note": row["note"] or "",
        "score": row["score"],
        "fit": row["fit"],
        "parts": score_parts(row),
        **ai,
        "posted_at": row["posted_at"] or "",
        "first_seen": row["first_seen"] or "",
        "flags": flags,
        "description": row["description"] or "",
        "advert_chars": len(row["description"] or ""),
        "artifacts": artifacts,
        "copies": copies,
    }


def _gates(raw: str) -> tuple[dict, int | None]:
    """Stored gate results, and the ai_outputs row the document is, if any."""
    try:
        gates = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}, None
    output_id = next((g.get("output_id") for g in gates.values()
                      if isinstance(g, dict) and g.get("output_id")), None)
    return {k: v for k, v in gates.items() if not k.startswith("_")}, output_id


# The files a cover letter is written as: the AI page's, and claude -p's.
LETTER_FILES = ("cover-letter-ai.md", "cover-letter.md")


def list_letters(cfg) -> dict:
    """Every cover letter recorded, newest first, with its job post."""
    from ..core import storage
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        rows = store.conn.execute(
            "SELECT a.id, a.uid, a.path, a.created_at, r.title, r.company "
            "FROM artifacts a LEFT JOIN roles r ON r.uid = a.uid "
            "WHERE a.kind = 'cover_letter' ORDER BY a.created_at DESC, a.id DESC"
        ).fetchall()
    return {"temporary": storage.temp_root() is not None,
            "letters": [{"id": r["id"], "uid": r["uid"], "title": r["title"] or "",
                         "company": r["company"] or "", "created_at": r["created_at"],
                         "exists": bool(r["path"]) and Path(r["path"]).is_file()}
                        for r in rows]}


def delete_letter(cfg, artifact_id: int) -> dict:
    """Delete a cover letter now: its file, its record, and its text.

    Only a file this tool recorded writing, under a cover letter's own name,
    is removed; the page passes an id, never a path. The AI's copy of the text
    is blanked too, so nothing of the letter is left, but its claim counts
    stay, because the hallucination chart is built from them.
    """
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        row = store.conn.execute(
            "SELECT id, path, gates_json FROM artifacts "
            "WHERE id = ? AND kind = 'cover_letter'", (int(artifact_id),)).fetchone()
        if row is None:
            raise ApiError("no such cover letter", 404)
        path = Path(row["path"] or "")
        if path.name in LETTER_FILES and path.is_file():
            path.unlink()
        _, output_id = _gates(row["gates_json"])
        if output_id:
            store.conn.execute("UPDATE ai_outputs SET text = '' WHERE id = ?",
                               (int(output_id),))
        store.conn.execute("DELETE FROM artifacts WHERE id = ?", (row["id"],))
        store.conn.commit()
    return {"deleted": True, "id": int(artifact_id)}


def forget_temporary(cfg) -> int:
    """Empty the temporary folder and forget what was in it.

    Documents whose files were there lose their record and their text, as a
    Delete would; the resume setting is cleared if it pointed there. Returns
    how many files were removed. Does nothing outside a container.
    """
    from ..core import storage
    from ..db.store import Store

    if storage.temp_root() is None:
        return 0
    removed = storage.wipe()
    with Store(cfg.db_path) as store:
        rows = store.conn.execute(
            "SELECT id, path, gates_json FROM artifacts").fetchall()
        for row in rows:
            if storage.is_temporary(row["path"] or ""):
                _, output_id = _gates(row["gates_json"])
                if output_id:
                    store.conn.execute("UPDATE ai_outputs SET text = '' WHERE id = ?",
                                       (int(output_id),))
                store.conn.execute("DELETE FROM artifacts WHERE id = ?", (row["id"],))
        store.conn.commit()
    if storage.is_temporary(cfg.resume_path):
        cfg.resume_path = ""
    return removed


def resume_view(cfg) -> dict:
    """The resume as the tools read it: its text, and the skills found in it.

    This is what a scan scores against and what a model is given, so it is
    what to check when a fit score or a draft looks wrong.
    """
    from ..search import resume as resume_mod

    if not cfg.resume_path:
        raise ApiError("no resume is set", 404)
    try:
        parsed = resume_mod.load(cfg.resume_path)
    except resume_mod.ResumeError as exc:
        raise ApiError(str(exc), 410) from exc
    # How the page shows it: a PDF as itself, a Word file or Markdown with
    # its headings and bullets, plain text as written.
    suffix = Path(cfg.resume_path).suffix.lower()
    markdown = ""
    if suffix in (".md", ".markdown"):
        markdown = parsed.text
    elif suffix == ".docx":
        try:
            markdown = resume_mod.docx_markdown(cfg.resume_path)
        except resume_mod.ResumeError:
            markdown = ""
    return {"name": Path(cfg.resume_path).name, "text": parsed.text,
            "type": suffix.lstrip("."), "markdown": markdown,
            "chars": len(parsed.text),
            "skills": [resume_mod.skill_name(s) for s in sorted(parsed.skills)],
            "years": resume_mod.years_claimed(parsed.text)}


# ── projects (Resume page) ────────────────────────────────────────────────────

MAX_PROJECT_FIELD = 2_000     # one STAR answer; a whole case study is a document


def _project(row) -> dict:
    from ..writing import resume_doc

    d = {k: row[k] for k in ("id", "name", "tools", "link", "situation", "task",
                             "action", "result", "updated_at")}
    d["tutorial"] = bool(resume_doc.tutorial_projects([row["name"]]))
    return d


def list_projects(cfg) -> dict:
    from ..db.store import Store
    from ..writing import resume_doc

    with Store(cfg.db_path) as store:
        rows = store.projects()
    return {"projects": [_project(r) for r in rows],
            "tutorial_advice": resume_doc.TUTORIAL_ADVICE,
            # One list, both sides: the page warns as you type with the same pattern.
            "tutorial_pattern": resume_doc.TUTORIAL.pattern}


def save_project(cfg, form: dict) -> dict:
    """Add or change one project. The link must be a web address, if given."""
    from ..db.store import Store

    fields = {k: str(form.get(k) or "").strip() for k in Store.PROJECT_FIELDS}
    if not fields["name"]:
        raise ApiError("give the project a name")
    for key, value in fields.items():
        if len(value) > MAX_PROJECT_FIELD:
            raise ApiError(f"{key} is over {MAX_PROJECT_FIELD} characters")
    if fields["link"] and not re.match(r"^https?://\S+$", fields["link"]):
        raise ApiError("the link must start with http:// or https://")
    raw = str(form.get("id") or "")
    with Store(cfg.db_path) as store:
        project_id = store.save_project(fields, int(raw) if raw.isdigit() else None)
        if not project_id:
            raise ApiError("no such project", 404)
        row = next(r for r in store.projects() if r["id"] == project_id)
    return {"project": _project(row)}


def delete_project(cfg, project_id: int) -> dict:
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        if not store.delete_project(project_id):
            raise ApiError("no such project", 404)
    return {"deleted": project_id}


RESUME_TYPES = {".pdf": "application/pdf", ".md": "text/markdown; charset=utf-8",
                ".markdown": "text/markdown; charset=utf-8",
                ".txt": "text/plain; charset=utf-8",
                ".docx": "application/vnd.openxmlformats-officedocument."
                         "wordprocessingml.document"}


def resume_file(cfg) -> tuple[bytes, str, str]:
    """The configured resume's own bytes, for Download. Only that one file."""
    if not cfg.resume_path:
        raise ApiError("no resume is set", 404)
    path = Path(cfg.resume_path)
    if not path.is_file():
        raise ApiError("the resume file is gone", 410)
    return (path.read_bytes(),
            RESUME_TYPES.get(path.suffix.lower(), "application/octet-stream"),
            path.name)


def delete_resume(cfg) -> dict:
    """Stop using the resume, and delete it if it was uploaded here.

    A resume you pointed the config at yourself is your file, somewhere of
    your choosing: it is only unset, never deleted.
    """
    from ..core import storage

    path = cfg.resume_path
    if not path:
        raise ApiError("no resume is set")
    uploaded = storage.is_uploaded_resume(path, cfg)
    if uploaded:
        Path(path).expanduser().unlink(missing_ok=True)
    return {"deleted": uploaded, "path": path}


def artifact_text(cfg, artifact_id: int) -> dict:
    """Read a generated document.

    Only paths this tool recorded writing are served. The page passes an id
    from the artifacts table, never a path, so it cannot ask for a file the
    tool did not make.
    """
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        row = store.conn.execute(
            "SELECT id, uid, kind, path, gates_json FROM artifacts WHERE id = ?",
            (int(artifact_id),)).fetchone()
        if row is None:
            raise ApiError("no such document", 404)

        path = Path(row["path"] or "")
        if not path.is_file():
            raise ApiError(
                f"{row['kind']} was recorded but the file is gone: {path}", 410)
        gates, output_id = _gates(row["gates_json"])
        # The page rates the ai_outputs row the document is.
        output = store.ai_output(int(output_id)) if output_id else None
    return {
        "id": row["id"], "uid": row["uid"], "kind": row["kind"],
        "path": str(path),
        "text": path.read_text(encoding="utf-8", errors="replace"),
        "gates": gates,
        "output": {"id": output["id"], "feedback": output["feedback"]}
        if output else None,
    }


# Documents that have a PDF beside them, under the same name.
PDF_KINDS = ("tailored_resume", "cv")


def artifact_pdf(cfg, artifact_id: int) -> tuple[bytes, str]:
    """A recorded resume document as a PDF, and its file name.

    Rendered from the document's own Markdown each time, so the PDF always
    says what the page shows, whichever of the two drafts was written last.
    The document is found from its recorded path, never from anything the
    page sends, so only a file this tool wrote can be served.
    """
    from ..db.store import Store
    from ..output import pdf
    from ..writing import resume_doc

    with Store(cfg.db_path) as store:
        row = store.conn.execute(
            "SELECT a.kind, a.path, r.title FROM artifacts a "
            "LEFT JOIN roles r ON r.uid = a.uid WHERE a.id = ?",
            (int(artifact_id),)).fetchone()
    if row is None or row["kind"] not in PDF_KINDS:
        raise ApiError("no such document", 404)
    path = Path(row["path"] or "")
    if not path.is_file():
        raise ApiError(f"{row['kind']} was recorded but the file is gone: {path}", 410)
    markdown = path.read_text(encoding="utf-8", errors="replace")
    name = resume_doc.name_of(markdown)
    return (pdf.render(markdown, f"{name or 'Resume'}, {row['title'] or ''}"),
            resume_doc.filename(name, row["title"] or ""))


def set_advert(cfg, uid: str, text: str) -> dict:
    """Store an advert pasted in by hand, and re-screen the role on it.

    For sources that cannot be fetched: Adzuna's API sends 500 characters and
    its pages refuse scripts, but the person reading the page in a browser can
    copy the whole thing. A later scan keeps the longer text rather than the
    teaser (see scan.run), so this is not undone by the next run.

    A role that no longer passes on the full text is marked skipped, exactly
    as `enrich` does, with the reason as its note.
    """
    from ..db import grouping
    from ..db.store import Role, Store
    from ..search import geo, screen
    from ..search.scan import _load_resume

    if not UID.match(uid or ""):
        raise ApiError("not a job post id")
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        raise ApiError("the advert is empty")
    if len(text) > MAX_ADVERT_CHARS:
        raise ApiError(f"longer than {MAX_ADVERT_CHARS:,} characters")

    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    cv = _load_resume(cfg)
    with Store(cfg.db_path) as store:
        row = store.get(uid)
        if row is None:
            raise ApiError("no such job post", 404)
        role = Role(
            platform=row["platform"], company=row["company"] or "",
            title=row["title"] or "", url=row["url"] or "",
            location_raw=row["location_raw"] or "", description=text,
            posted_at=row["posted_at"] or "", origin=row["origin"] or "scan",
            work_mode=row["work_mode"] or "",
            salary_min=row["salary_min"], salary_max=row["salary_max"],
            salary_currency=row["salary_currency"] or "",
            salary_period=row["salary_period"] or "",
            salary_stated=bool(row["salary_stated"]),
        )
        verdict = screen.screen(role, cfg, anchor, cv,
                                first_seen=grouping.earliest_seen(store.conn, uid=uid))
        if role.uid != uid:
            raise ApiError("stored url no longer maps to this job post", 409)
        store.upsert(role, seen=False)
        dropped = ""
        if not verdict.keep:
            dropped = verdict.reasons[0] if verdict.reasons else "unknown"
            store.set_status(uid, "skipped", f"advert pasted: {dropped}")
        store.conn.commit()

    return {"uid": uid, "advert_chars": len(text), "score": role.score,
            "fit": role.fit, "dropped": dropped}


def sources_report(cfg) -> dict:
    """What will run, what will not, and why — `jobdork sources` as data."""
    dormant = []
    for name in cfg.dormant_sources():
        if name == "usajobs" and not cfg.usajobs_in_scope():
            why = "US federal postings only, and US is not in your countries"
        elif name == "usajobs":
            why = "no credential. Get a free key at developer.usajobs.gov"
        else:
            why = "no credential. Get a free key at developer.adzuna.com/signup"
        dormant.append({"name": name, "why": why})

    return {
        "active": cfg.active_sources(),
        "dormant": dormant,
        "companies": [{"name": c.name, "platform": c.platform, "token": c.token}
                      for c in cfg.sources.companies],
        "directory": _directory_view(cfg),
    }


def _directory_view(cfg) -> dict:
    """The built-in employer boards: on or off, and how many this config reads."""
    from ..search import directory

    d = cfg.sources.directory
    return {"enabled": d.enabled, "boards": len(directory.select(cfg)),
            "total": len(directory.load()),
            "countries": d.countries or list(cfg.locations.countries),
            "industries": d.industries}


def try_dealbreaker(form: dict) -> dict:
    """Whether a dealbreaker finds anything in a sentence, as a scan would.

    The page sends its words (or an advanced pattern) and a sentence; the
    answer is the text found, so the matching is Python's and the same as a
    scan's, not a guess in the browser.
    """
    import re as _re

    from ..search import dealbreakers

    text = str(form.get("text") or "")[:4000]
    words = form.get("words") or []
    if isinstance(words, str):
        words = words.split(",")
    words = [str(w).strip() for w in words if str(w).strip()]
    if words:
        found = dealbreakers.find(dealbreakers.compile_words(words), text,
                                  dealbreakers.negates(words))
        return {"found": found, "matches": dealbreakers.expand(words)[:12]}
    pattern = str(form.get("pattern") or "")
    if not pattern:
        raise ApiError("give the words to look for")
    try:
        regex = _re.compile(pattern, _re.IGNORECASE)
    except _re.error as exc:
        raise ApiError(f"not a valid pattern: {exc}") from exc
    match = regex.search(text)
    return {"found": match.group(0) if match else "", "matches": []}


# ── writing ───────────────────────────────────────────────────────────────────


def save_resume(cfg, filename: str, payload: bytes) -> dict:
    """Store an uploaded resume and point the config at it.

    The browser's filename is used for one thing only — reading its extension.
    The file is written to a name and a directory chosen here, so a suggested
    path like `../../.ssh/authorized_keys` lands as `resume.pdf` beside the
    config and nowhere else.
    """
    if not payload:
        raise ApiError("empty upload")
    if len(payload) > MAX_RESUME_BYTES:
        raise ApiError(
            f"{len(payload) / 1e6:.1f}MB is over the {MAX_RESUME_BYTES // 1_000_000}MB limit")

    suffix = Path(filename or "").suffix.lower()
    if suffix not in RESUME_SUFFIXES:
        raise ApiError(
            f"{suffix or 'that'} is not a format the resume reader "
            f"understands. Use {', '.join(RESUME_SUFFIXES)}.")

    from ..core import storage
    target_dir = storage.resume_dir(cfg)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"resume{suffix}"
    target.write_bytes(payload)

    # Read it straight back. A resume that cannot be parsed is worse than none:
    # it would score every role at zero while looking configured.
    from ..search import resume as resume_mod
    try:
        parsed = resume_mod.load(str(target))
    except resume_mod.ResumeError as exc:
        target.unlink(missing_ok=True)
        raise ApiError(f"saved nothing: {exc}") from exc

    # One uploaded resume at a time: a .docx replacing a .pdf must not leave
    # the old one behind for Delete to miss. Only once the new one has read.
    for old in target_dir.glob(f"{storage.RESUME_STEM}.*"):
        if old != target:
            old.unlink(missing_ok=True)

    return {
        "path": str(target),
        "chars": len(parsed.text),
        "skills": sorted(parsed.skills),
        "years": resume_mod.years_claimed(parsed.text),
    }


def add_by_url(cfg, url: str, token: str = "", company: str = "") -> dict:
    """`jobdork add` — pull one posting in from a link you clicked."""
    from ..cli import _platform_for
    from ..db.store import Store, canonical_url
    from ..fetch import get as get_adapter
    from ..fetch.http import Fetcher
    from ..search import geo, screen

    url = canonical_url((url or "").strip())
    if not url:
        raise ApiError("give a posting URL")

    platform, found = _platform_for(url)
    token = token or found
    if not platform:
        raise ApiError(
            "cannot tell which platform that URL is on. Supported: "
            "greenhouse, ashby, lever, breezy, smartrecruiters.")
    if not token:
        raise ApiError(
            f"that is a {platform} posting on the employer's own domain, so "
            "the board token is not in the URL. Supply it alongside.")

    fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout, cfg.fetch.retries)
    result = get_adapter(platform)(fetcher, cfg, token=token,
                                   company=company or token)
    if result.skipped:
        raise ApiError(f"{platform}: {result.skipped}")

    wanted = next((r for r in result.roles if canonical_url(r.url) == url), None)
    if wanted is None:
        raise ApiError(
            f"read {token!r} on {platform} ({len(result.roles)} job posts) but none "
            "of them is that URL. It may already be filled.")

    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    verdict = screen.screen(wanted, cfg, anchor)
    with Store(cfg.db_path) as store:
        is_new = store.upsert(wanted)
        store.conn.commit()

    return {
        "uid": wanted.uid, "title": wanted.title, "company": wanted.company,
        "added": is_new,
        # Stored either way: you asked for this one by name, and a filter is
        # not a better judge of that than you are.
        "passes_filters": verdict.keep,
        "why_not": verdict.reasons[0] if verdict.reasons else "",
        "flags": verdict.flags,
    }


# ── activity ──────────────────────────────────────────────────────────────────

# A heartbeat older than this means the job is stuck or its process is gone.
QUIET_SECONDS = 20


def _alive(pid) -> bool:
    import os

    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def _age(stamp: str) -> float:
    import time

    try:
        return time.time() - time.mktime(time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return 0.0


def _activity_row(row) -> dict:
    def parsed(key):
        try:
            value = json.loads(row[key] or "{}")
        except (json.JSONDecodeError, TypeError):
            value = {}
        return value if isinstance(value, dict) else {}

    running = row["state"] == "running"
    heartbeat = _age(row["heartbeat_at"])
    health = "ok"
    if running and heartbeat > QUIET_SECONDS:
        health = "quiet" if _alive(row["pid"]) else "died"
    elapsed = (_age(row["started_at"]) if running
               else _age(row["started_at"]) - _age(row["finished_at"] or row["started_at"]))
    done, total = row["done"] or 0, row["total"]
    rate = done / (elapsed / 60) if elapsed > 5 and done else 0.0
    return {
        "id": row["id"], "job": row["job"], "origin": row["origin"],
        "pid": row["pid"], "state": "died" if health == "died" else row["state"],
        "health": health, "heartbeat_age": round(heartbeat),
        "started_at": row["started_at"], "finished_at": row["finished_at"] or "",
        "elapsed": round(elapsed), "done": done, "total": total,
        "rate_per_min": round(rate, 1),
        "eta": round((total - done) / rate * 60) if rate and total and total > done else None,
        "counters": parsed("counters"), "hosts": parsed("hosts"), "ai": parsed("ai"),
        "last_line": row["last_line"] or "", "summary": row["summary"] or "",
    }


SCAN_STALE_DAYS = 15
_JOB_NAMES = {"check": ("check", "checking postings"),
              "judge": ("judge", "AI judging")}


def _days(stamp: str) -> float:
    return _age(stamp) / 86400 if stamp else 0.0


def _ago(stamp: str) -> str:
    days = _days(stamp)
    if not stamp:
        return ""
    if days >= 1:
        return f"{days:.0f} day{'' if round(days) == 1 else 's'} ago"
    hours = days * 24
    if hours >= 1:
        return f"{hours:.0f} h ago"
    # "just now" was said of a run twenty minutes old.
    minutes = hours * 60
    return f"{minutes:.0f} min ago" if minutes >= 1 else "just now"


def _last_scan(conn) -> dict:
    """The latest scan from the scan history, with what went wrong in it."""
    runs = conn.execute("SELECT id, started_at, finished_at, counts_json "
                        "FROM runs ORDER BY id DESC LIMIT 50").fetchall()
    done = [r for r in runs if r["finished_at"]]
    if not done:
        return {"kind": "scan", "when": "", "ago": "", "summary": "never run",
                "warnings": ["No scan has finished yet."]}
    last = done[0]
    counts = json.loads(last["counts_json"] or "{}")
    sources = counts.get("sources") or {}
    warnings = []
    if _days(last["started_at"]) > SCAN_STALE_DAYS:
        warnings.append(f"Last scan was {_ago(last['started_at'])}; posts found "
                        f"then may be gone.")
    for source, n in sorted(sources.items()):
        if not n:
            warnings.append(f"{platform_name(source)} returned 0 job posts.")
    # A source that returned posts before and did not run at all this time.
    before = {s for r in done[1:] for s, n in
              (json.loads(r["counts_json"] or "{}").get("sources") or {}).items() if n}
    for source in sorted(before - set(sources)):
        warnings.append(f"{platform_name(source)} did not run in the last scan.")
    unfinished = [r for r in runs if not r["finished_at"] and r["id"] > last["id"]]
    if unfinished:
        warnings.append(f"A scan started {unfinished[0]['started_at'][:16].replace('T', ' ')} "
                        "never finished.")
    per = ", ".join(f"{platform_name(s)} {n}" for s, n in sorted(sources.items()))
    return {"kind": "scan", "when": last["started_at"], "ago": _ago(last["started_at"]),
            "summary": f"{counts.get('fetched', 0):,} fetched, {counts.get('kept', 0):,} kept, "
                       f"{counts.get('new', 0):,} new ({per})",
            "warnings": warnings}


def _last_job(conn, kind: str, fallback_sql: str) -> dict:
    """The latest run of a job over the whole list, else the latest of any size.

    A one-post run from a dialog says little about the list, so a full run is
    preferred; but when single posts are all there has been, the card says so
    rather than claiming nothing was recorded.
    """
    names = _JOB_NAMES[kind]
    marks = ",".join("?" for _ in names)
    row = conn.execute(
        # Safe: only ? placeholders are interpolated.
        f"SELECT * FROM activity WHERE job IN ({marks}) AND COALESCE(total, 2) > 1 "  # nosec B608
        "ORDER BY id DESC LIMIT 1", names).fetchone()
    single = row is None
    if single:
        row = conn.execute(
            # Safe: only ? placeholders are interpolated.
            f"SELECT * FROM activity WHERE job IN ({marks}) ORDER BY id DESC LIMIT 1",  # nosec B608
            names).fetchone()
    if row is not None:
        run = _activity_row(row)
        warnings = []
        if run["state"] in ("failed", "died", "stopped"):
            warnings.append(f"It {run['state']}: {run['summary'] or run['last_line']}")
        summary = run["summary"] or run["last_line"]
        if single:
            summary = f"one job post only: {summary}" if summary else "one job post only"
        return {"kind": kind, "when": run["started_at"], "ago": _ago(run["started_at"]),
                "summary": summary, "id": run["id"], "warnings": warnings}
    stamp = conn.execute(fallback_sql).fetchone()[0] or ""
    return {"kind": kind, "when": stamp, "ago": _ago(stamp),
            "summary": "no recorded run" if not stamp else "recorded before run history",
            "warnings": []}


def activity_report(cfg, job_id: int = 0) -> dict:
    """Running and recent jobs from any process, and one job in detail."""
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        conn = store.conn
        jobs = [_activity_row(r) for r in conn.execute(
            "SELECT * FROM activity ORDER BY id DESC LIMIT 25")]
        # Unless one was picked: what is running, else the latest run over the
        # whole list. A one-post check from a dialog is not much of a home page.
        chosen = (next((j for j in jobs if j["id"] == job_id), None)
                  or next((j for j in jobs if j["state"] == "running"), None)
                  or next((j for j in jobs if (j["total"] or 2) > 1), None)
                  or (jobs[0] if jobs else None))
        events = [] if chosen is None else [dict(r) for r in conn.execute(
            "SELECT at, level, text FROM (SELECT * FROM activity_events "
            "WHERE activity_id = ? ORDER BY id DESC LIMIT 120) ORDER BY id",
            (chosen["id"],))]

        # Writes from jobs that record no telemetry — one started before it
        # existed — still show up as rows changing.
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 600))
        checked = conn.execute(
            "SELECT COUNT(*), MAX(listing_checked_at) FROM roles "
            "WHERE listing_checked_at >= ?", (since,)).fetchone()
        states = dict(conn.execute(
            "SELECT COALESCE(listing_state, 'not checked'), COUNT(*) FROM roles r "
            "LEFT JOIN role_state s ON s.uid = r.uid "
            "WHERE COALESCE(s.status, 'new') NOT IN ('rejected','withdrawn','skipped','closed') "
            "   OR r.listing_state = 'closed' "
            "GROUP BY 1").fetchall())
        last_scan = store.last_run()
        last_runs = [
            _last_scan(conn),
            _last_job(conn, "check", "SELECT MAX(listing_checked_at) FROM roles"),
            _last_job(conn, "judge", "SELECT MAX(json_extract(llm_judgement, '$.at')) "
                                     "FROM roles"),
        ]

    return {
        "running": [j for j in jobs if j["state"] == "running"],
        "recent": jobs,
        "chosen": chosen,
        "last_runs": last_runs,
        "events": events,
        "database": {
            "checked_10m": checked[0], "last_checked": checked[1] or "",
            "listing_states": states,
            "last_scan": dict(last_scan) if last_scan else None,
        },
    }


# ── metrics ───────────────────────────────────────────────────────────────────

METRIC_DAYS = (7, 30, 90)
MAX_MODELS = 6            # lines on the hallucination chart, by model
# Fixed order: it is the chart's colour order, so a tool keeps its colour
# whichever tools ran in the period.
TOOLS = ("scan", "check", "AI judging", "AI writing", "enrich", "other")
OUTPUT_KINDS = {"judge": "verdicts", "page_read": "page reads",
                "cover_letter": "cover letters", "resume_review": "resume reviews",
                "tailored_resume": "tailored resumes",
                "draft": "Claude drafts", "resume_edits": "tailored resume edits",
                "highlight": "skills to highlight", "feedback": "recruiter feedback",
                "revise": "revisions", "keywords": "ATS keywords"}


def _tool(job: str) -> str:
    """A run's job name, from the terminal or the dashboard, as one of TOOLS."""
    job = (job or "").lower()
    if job in ("scan", "fresh scan"):
        return "scan"
    if job in ("check", "checking postings"):
        return "check"
    if job in ("judge", "ai judging"):
        return "AI judging"
    if (job in ("letter", "review", "generate", "screen", "cv", "cover letter",
                "cover letter (ai)", "resume review", "tailor", "tailored resume (ai)")
            or job.startswith("ai tool")):
        return "AI writing"
    if job == "enrich":
        return "enrich"
    return "other"


def _percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile: a value that was actually observed."""
    import math

    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def metrics(cfg, days: int = 30) -> dict:
    """The Dashboard's numbers for the last `days` days, and a day-by-day split.

    Runs come from `activity`, model calls from `llm_calls`, and the
    hallucination score, its coverage and the feedback from `ai_outputs`.
    Days are local dates, like every stamp in the database.
    """
    from ..db.store import Store

    try:
        days = int(days)
    except (TypeError, ValueError):
        raise ApiError("days must be a number") from None
    if days not in METRIC_DAYS:
        raise ApiError(f"days is one of {', '.join(map(str, METRIC_DAYS))}")
    now = time.time()
    since = time.strftime("%Y-%m-%dT00:00:00",
                          time.localtime(now - (days - 1) * 86400))
    dates = [time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
             for i in range(days - 1, -1, -1)]

    with Store(cfg.db_path) as store:
        conn = store.conn
        runs = [_activity_row(r) for r in conn.execute(
            "SELECT * FROM activity WHERE started_at >= ? ORDER BY id", (since,))]
        calls = conn.execute(
            "SELECT seconds, ok FROM llm_calls WHERE at >= ?", (since,)).fetchall()
        first_call = conn.execute("SELECT MIN(at) FROM llm_calls").fetchone()[0] or ""
        outputs = conn.execute(
            "SELECT kind, COALESCE(NULLIF(model, ''), 'unknown model') AS model, "
            "substr(created_at, 1, 10) AS day, claims, unsupported, "
            "checked, feedback FROM ai_outputs WHERE created_at >= ?",
            (since,)).fetchall()
        # Every model that has had output checked, in the order first used.
        # That order is the colour order, so a model keeps its colour when
        # another is added; it is taken over all time for the same reason.
        models = [r[0] for r in conn.execute(
            "SELECT COALESCE(NULLIF(model, ''), 'unknown model'), MIN(created_at) "
            "FROM ai_outputs WHERE checked = 1 GROUP BY 1 ORDER BY 2")]
        first_output = conn.execute(
            "SELECT MIN(created_at) FROM ai_outputs").fetchone()[0] or ""

    errored = [r for r in runs if r["state"] in ("failed", "died", "stopped")]
    by_day = {d: dict.fromkeys(TOOLS, 0) for d in dates}
    for r in runs:
        day = r["started_at"][:10]
        if day in by_day:
            by_day[day][_tool(r["job"])] += 1

    seconds = [c["seconds"] for c in calls]
    checked = [o for o in outputs if o["checked"]]
    claims = sum(o["claims"] for o in checked)
    unsupported = sum(o["unsupported"] for o in checked)
    kinds = {}
    for o in outputs:
        k = kinds.setdefault(o["kind"], {"label": OUTPUT_KINDS.get(o["kind"], o["kind"]),
                                         "outputs": 0, "checked": 0, "claims": 0,
                                         "unsupported": 0})
        k["outputs"] += 1
        if o["checked"]:
            k["checked"] += 1
            k["claims"] += o["claims"]
            k["unsupported"] += o["unsupported"]
    for k in kinds.values():
        k["rate"] = k["unsupported"] / k["claims"] if k["claims"] else None

    # Per day and kind, from checked outputs only: a day with nothing checked
    # has no rate, which is not the same as a rate of 0.
    # The same split by model. Past MAX_MODELS the rest fold into "other":
    # more lines than colours is noise, and a colour must not be reused.
    shown = models[:MAX_MODELS] if len(models) <= MAX_MODELS else models[:MAX_MODELS - 1]
    claims_by_day = {d: {} for d in dates}
    claims_by_model = {d: {} for d in dates}
    for o in checked:
        if o["day"] in claims_by_day and o["claims"]:
            model = o["model"] if o["model"] in shown else "other models"
            for split, key in ((claims_by_day, o["kind"]), (claims_by_model, model)):
                k = split[o["day"]].setdefault(key, {"claims": 0, "unsupported": 0})
                k["claims"] += o["claims"]
                k["unsupported"] += o["unsupported"]

    feedback = {d: {"up": 0, "down": 0} for d in dates}
    for o in outputs:
        if o["feedback"] and o["day"] in feedback:
            feedback[o["day"]]["up" if o["feedback"] > 0 else "down"] += 1
    ups = sum(f["up"] for f in feedback.values())
    downs = sum(f["down"] for f in feedback.values())

    return {
        "days": days, "since": since[:10], "tools": list(TOOLS),
        "runs": {"total": len(runs), "errored": len(errored),
                 "error_rate": len(errored) / len(runs) if runs else None,
                 "by_state": {s: sum(1 for r in errored if r["state"] == s)
                              for s in ("failed", "died", "stopped")}},
        "ai_calls": {"total": len(calls),
                     "failed": sum(1 for c in calls if not c["ok"]),
                     "p50": _percentile(seconds, 50), "p95": _percentile(seconds, 95),
                     "recorded_since": first_call[:10]},
        "hallucination": {"outputs": len(outputs), "checked": len(checked),
                          "coverage": len(checked) / len(outputs) if outputs else None,
                          "claims": claims, "unsupported": unsupported,
                          "rate": unsupported / claims if claims else None,
                          "by_kind": [kinds[k] for k in OUTPUT_KINDS if k in kinds],
                          "recorded_since": first_output[:10]},
        "feedback": {"up": ups, "down": downs,
                     "approval": ups / (ups + downs) if ups + downs else None},
        "kinds": [{"kind": k, "label": v} for k, v in OUTPUT_KINDS.items()],
        "models": [{"kind": m, "label": m} for m in shown]
        + ([{"kind": "other models", "label": "other models"}] if len(shown) < len(models) else []),
        "per_day": [{"date": d, "runs": by_day[d], "claims": claims_by_day[d],
                     "claims_by_model": claims_by_model[d], **feedback[d]} for d in dates],
    }


# ── cleanup ───────────────────────────────────────────────────────────────────

BACKUPS_KEPT = 10


def _cleanup_args(days, statuses) -> tuple[int, list[str], str]:
    from ..core.config import SETTLED_STATUSES

    try:
        days = int(days or 0)
    except (TypeError, ValueError):
        raise ApiError("days must be a number") from None
    if isinstance(statuses, str):
        statuses = [s for s in statuses.split(",") if s]
    statuses = list(statuses or [])
    if bool(days) == bool(statuses):
        raise ApiError("choose an age or statuses, not both")
    if days and not 1 <= days <= 3650:
        raise ApiError("days must be between 1 and 3650")
    unknown = [s for s in statuses if s not in SETTLED_STATUSES]
    if unknown:
        raise ApiError(f"only settled statuses can be cleaned up: "
                       f"{', '.join(SETTLED_STATUSES)}")
    reason = (f"first seen over {days} days ago, not being pursued" if days
              else f"status {', '.join(statuses)}")
    return days, statuses, reason


def cleanup_preview(cfg, days=0, statuses=()) -> dict:
    """What a cleanup would delete. Deletes nothing."""
    from ..db.store import Store

    days, statuses, reason = _cleanup_args(days, statuses)
    with Store(cfg.db_path) as store:
        rows = store.cleanup_candidates(days, statuses)
        total = store.conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {"count": len(rows), "total": total, "reason": reason,
            "by_status": by_status,
            "sample": [f"{r['title']} at {r['company']}" for r in rows[:5]]}


def cleanup_run(cfg, days=0, statuses=(), expect: int = -1) -> dict:
    """Back the database up, then delete what the preview showed.

    `expect` is the count the preview showed. If a scan or a status change
    moved the number since, nothing is deleted and the page previews again:
    you confirmed a number, and you get that number or nothing.
    """
    from ..db.store import Store

    days, statuses, reason = _cleanup_args(days, statuses)
    with Store(cfg.db_path) as store:
        rows = store.cleanup_candidates(days, statuses)
        if int(expect) != len(rows):
            raise ApiError(f"the count changed from {expect} to {len(rows)} "
                           "since the preview; preview again", 409)
        if not rows:
            return {"deleted": 0, "backup": ""}
        backup = _backup(cfg, store, "cleanup")
        deleted = store.delete_many((r["uid"] for r in rows), reason)
    return {"deleted": deleted, "backup": str(backup), "reason": reason}


def _backup(cfg, store, label: str) -> Path:
    """Copy the database aside before a delete; keep the last BACKUPS_KEPT."""
    import sqlite3

    folder = Path(cfg.db_path).parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / f"jobdork-{time.strftime('%Y%m%d-%H%M%S')}-before-{label}.db"
    target = sqlite3.connect(backup)
    with target:
        store.conn.backup(target)
    target.close()
    for old in sorted(folder.glob(f"jobdork-*-before-{label}.db"))[:-BACKUPS_KEPT]:
        old.unlink(missing_ok=True)
    return backup


# ── fresh scan ────────────────────────────────────────────────────────────────


def fresh_preview(cfg) -> dict:
    """What a fresh scan would delete. Deletes nothing."""
    from ..core.config import PURSUING_STATUSES
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        count = store.scanned_count()
        by_status = dict(store.conn.execute(
            "SELECT COALESCE(s.status, 'new'), COUNT(*) FROM roles r "
            "LEFT JOIN role_state s ON s.uid = r.uid WHERE r.origin = 'scan' "
            "GROUP BY 1").fetchall())
        by_hand = store.conn.execute(
            "SELECT COUNT(*) FROM roles WHERE origin <> 'scan'").fetchone()[0]
    return {"count": count, "by_status": by_status, "kept_by_hand": by_hand,
            "pursuing": sum(n for s, n in by_status.items() if s in PURSUING_STATUSES)}


def delete_scanned_job(cfg, expect):
    """Back up, then delete every scanned job post, and scan nothing.

    The fresh scan without its scan: for starting over later, or with other
    settings. Same preview, same count check now and again when it runs,
    same backup; posts added by hand are kept, and posts you deleted before
    stay deleted.
    """
    from ..db.store import Store

    try:
        expect = int(expect)
    except (TypeError, ValueError):
        raise ApiError("preview first") from None
    with Store(cfg.db_path) as store:
        now = store.scanned_count()
    if now != expect:
        raise ApiError(f"the count changed from {expect} to {now} since the "
                       "preview; preview again", 409)

    def work(progress):
        with Store(cfg.db_path) as store:
            if store.scanned_count() != expect:
                raise ApiError("the job posts changed before the delete started; "
                               "nothing was deleted", 409)
            backup = _backup(cfg, store, "delete-scanned")
            deleted = store.clear_scanned()
        progress(f"backed up to {backup}")
        return f"deleted {deleted} scanned job posts; backup at {backup}"
    return work


def fresh_scan_job(cfg, expect):
    """Back up, delete every scanned job post, then scan from scratch.

    `expect` is the count the preview showed, checked now and again when the
    run starts: you confirmed a number, and you get that number or nothing.
    """
    from ..db.store import Store

    try:
        expect = int(expect)
    except (TypeError, ValueError):
        raise ApiError("preview first") from None
    with Store(cfg.db_path) as store:
        now = store.scanned_count()
    if now != expect:
        raise ApiError(f"the count changed from {expect} to {now} since the "
                       "preview; preview again", 409)
    scan = scan_job(cfg)

    def work(progress):
        with Store(cfg.db_path) as store:
            if store.scanned_count() != expect:
                raise ApiError("the job posts changed before the run started; "
                               "nothing was deleted", 409)
            backup = _backup(cfg, store, "fresh-scan")
            deleted = store.clear_scanned()
        progress(f"backed up to {backup}")
        progress(f"deleted {deleted} job posts; scanning from scratch")
        return f"fresh scan: deleted {deleted} · " + scan(progress)
    return work


# ── the model ─────────────────────────────────────────────────────────────────


def llm_state(cfg) -> dict:
    """AI settings for the page. Says which keys are held, never what they are."""
    from ..ai import llm

    settings = llm.Settings.from_config(cfg)
    return {
        "providers": llm.PROVIDERS,
        "provider": cfg.llm.provider,
        "model": cfg.llm.model,
        "ollama_url": cfg.llm.ollama_url,
        "judge_on_scan": cfg.llm.judge_on_scan,
        "judge_top": cfg.llm.judge_top,
        "read_pages": cfg.llm.read_pages,
        "guard": cfg.llm.guard,
        "keys": {p: llm.key_for(p)[1] for p in llm.KEYED},
        "problem": settings.problem(),
        "label": settings.label if cfg.llm.provider else "",
    }


def llm_models(cfg, provider: str, ollama_url: str = "") -> dict:
    from ..ai import llm

    if provider not in llm.PROVIDERS:
        raise ApiError("unknown provider")
    settings = llm.Settings(provider=provider,
                            ollama_url=ollama_url or cfg.llm.ollama_url)
    if not re.match(r"https?://[^\s/]+$", settings.ollama_url.rstrip("/")):
        raise ApiError("the Ollama address must look like http://host:port")
    try:
        return {"models": llm.list_models(settings)}
    except llm.LLMError as exc:
        raise ApiError(str(exc), 502) from exc


def llm_key(provider: str, key: str) -> dict:
    """Hold a key in memory. It is never echoed back, logged or written."""
    from ..ai import llm

    try:
        llm.VAULT.put(provider, key)
    except llm.LLMError as exc:
        raise ApiError(str(exc)) from exc
    return {"held": llm.VAULT.held()}


def llm_forget(provider: str) -> dict:
    from ..ai import llm

    if provider == "all":
        llm.VAULT.wipe()
    else:
        llm.VAULT.forget(provider)
    return {"held": llm.VAULT.held()}


def llm_test(cfg) -> dict:
    from ..ai import llm

    try:
        return llm.ping(llm.Settings.from_config(cfg))
    except llm.LLMError as exc:
        raise ApiError(str(exc), 502) from exc


# ── long jobs, run through the Runner ─────────────────────────────────────────


def scan_job(cfg):
    def work(progress):
        from ..db.store import Store
        from ..output import render
        from ..search import scan as scan_mod

        with Store(cfg.db_path) as store:
            report = scan_mod.run(cfg, store, progress=progress)
            summary = " · ".join(report.lines())
            if cfg.llm.judge_on_scan:
                summary += " · " + _judge_after_scan(cfg, store, progress)
            render.write_all(store.list_roles(), cfg, report)
        return summary
    return work


def _judge_after_scan(cfg, store, progress) -> str:
    """The scan has already succeeded; a model problem must not undo that."""
    from ..ai import judging, llm

    problem = llm.Settings.from_config(cfg).problem()
    if problem:
        progress(f"AI judging skipped: {problem}")
        return "AI judging skipped"
    progress(f"AI reading the top {cfg.llm.judge_top} job posts against your resume")
    try:
        report = judging.run(cfg, store, progress=progress)
    except llm.LLMError as exc:
        progress(f"AI judging stopped: {exc}")
        return "AI judging stopped"
    return " · ".join(report.lines())


def judge_job(cfg, limit: int = 0, uid: str = "", force: bool = False):
    if uid and not UID.match(uid):
        raise ApiError("not a job post id")

    def work(progress):
        from ..ai import judging
        from ..db.store import Store

        with Store(cfg.db_path) as store:
            try:
                report = judging.run(cfg, store, limit=limit, uid=uid,
                                     force=force, progress=progress)
            except Exception as exc:
                raise ApiError(str(exc)) from exc
        return " · ".join(report.lines())
    return work


def check_job(cfg, limit: int = 0, uid: str = "", force: bool = False):
    if uid and not UID.match(uid):
        raise ApiError("not a job post id")

    def work(progress):
        from ..db.store import Store
        from ..fetch.http import Fetcher
        from ..search import listing

        fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout,
                          cfg.fetch.retries)
        progress("checking whether postings are still up")
        with Store(cfg.db_path) as store:
            report = listing.run(cfg, store, fetcher, limit=limit, uid=uid,
                                 force=force, progress=progress)
        return " · ".join(report.lines())
    return work


def enrich_job(cfg, limit: int = 0):
    def work(progress):
        from ..db.store import Store
        from ..fetch.http import Fetcher
        from ..search import enrich as enrich_mod

        fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout,
                          cfg.fetch.retries)
        with Store(cfg.db_path) as store:
            report = enrich_mod.enrich(cfg, store, fetcher, limit=limit,
                                       progress=progress)
        return " · ".join(report.lines())
    return work


def rescreen_job(cfg, remove: bool = False):
    def work(progress):
        from ..db.store import Store
        from ..search import scan as scan_mod

        progress("re-applying the current config to everything stored")
        with Store(cfg.db_path) as store:
            checked, stale, removed = scan_mod.rescreen(cfg, store, remove=remove)
        return (f"checked {checked}, no longer matching {stale}, "
                f"removed {removed}")
    return work


def discover_job(cfg, employer: str, add: bool = False, name: str = ""):
    def work(progress):
        from ..fetch.http import Fetcher
        from ..search import discover as discover_mod

        fetcher = Fetcher(cfg.fetch.user_agent, cfg.fetch.timeout,
                          cfg.fetch.retries)
        progress(f"looking for {employer}")
        report = discover_mod.discover(employer, fetcher)
        if report.error:
            raise ApiError(report.error)
        for line in report.lines():
            progress(line.rstrip())

        addable = [f for f in report.found if f.addable]
        if add and addable and cfg.path:
            written = discover_mod.add_to_config(cfg.path, name or employer,
                                                 addable)
            for item in written:
                progress(f"added {item.platform} / {item.token} to your config")
            if not written:
                return "already in your config; nothing added"
            return f"{len(written)} board(s) added"
        if addable:
            return f"{len(addable)} verified board(s) found"
        return "nothing addable found"
    return work


def generate_job(cfg, uid: str, kind: str):
    """Screen, CV or cover letter. Spends tokens, so it is never automatic."""
    from ..db.store import Store

    if not UID.match(uid or ""):
        raise ApiError("not a job post id")

    def work(progress):
        from ..ai import guard
        from ..writing import generate as gen
        from ..writing import resume_doc

        with Store(cfg.db_path) as store:
            row = store.get(uid)
            if row is None:
                raise ApiError("no such job post", 404)

            progress(f"running claude -p for {kind} (this spends tokens)")
            result = gen.generate(row, kind, cfg.resume_path, progress=progress,
                                  notes=resume_doc.project_notes(store.projects()),
                                  settings=guard.settings_for(cfg))

            for gate in result.gates:
                progress(gate.line().rstrip())
            gen.record(store, row, result)
            # Drafting a document means you are considering it; screening is
            # how you decide, so it does not move anything on its own.
            if kind != "screen" and (row["status"] or "new") in ("new", "viewed"):
                store.set_status(uid, "interested", f"{kind} drafted")

        failed = [g for g in result.gates if not g.passed]
        return (f"wrote {result.path.name}"
                + (f"; {len(failed)} gate(s) to read before sending"
                   if failed else "; all gates clean"))
    return work


def letter_job(cfg, uid: str):
    """A cover letter from the AI-page model, saved beside the claude drafts."""
    if not UID.match(uid or ""):
        raise ApiError("not a job post id")

    def work(progress):
        from ..ai import llm, writer
        from ..db.store import Store

        with Store(cfg.db_path) as store:
            try:
                draft = writer.letter(cfg, store, uid, progress=progress)
            except llm.LLMError as exc:
                raise ApiError(str(exc)) from exc
            row = store.get(uid)
            if (row["status"] or "new") in ("new", "viewed"):
                store.set_status(uid, "interested", "cover letter drafted (AI)")
        failed = [g for g in draft.gates if not g.passed]
        return (f"wrote {draft.path.name}"
                + (f"; {len(failed)} gate(s) to read before sending"
                   if failed else "; all gates clean"))
    return work


def tailor_job(cfg, uid: str):
    """A resume rewritten for one post, in the template, as Markdown and PDF."""
    if not UID.match(uid or ""):
        raise ApiError("not a job post id")

    def work(progress):
        from ..ai import llm, writer
        from ..db.store import Store

        with Store(cfg.db_path) as store:
            try:
                result = writer.tailor(cfg, store, uid, progress=progress)
            except llm.LLMError as exc:
                raise ApiError(str(exc)) from exc
            row = store.get(uid)
            if (row["status"] or "new") in ("new", "viewed"):
                store.set_status(uid, "interested", "resume tailored (AI)")
        failed = [g for g in result.gates if not g.passed]
        return (f"wrote {result.pdf_path.name}"
                + (f"; {len(failed)} gate(s) to read before sending"
                   if failed else "; all gates clean"))
    return work


MAX_TOOL_TEXT = 8_000       # a pasted bullet, paragraph or whole letter


def tool_job(cfg, uid: str, kind: str, text: str = ""):
    """One of the AI tools (ai/tools.py) for one job post."""
    from ..ai import tools

    if not UID.match(uid or ""):
        raise ApiError("not a job post id")
    if kind not in tools.TOOLS:
        raise ApiError("unknown tool")
    if kind == "revise" and not (text or "").strip():
        raise ApiError("paste a bullet or a paragraph to revise")
    if len(text or "") > MAX_TOOL_TEXT:
        raise ApiError(f"over {MAX_TOOL_TEXT:,} characters; paste less")

    def work(progress):
        from ..ai import llm
        from ..db.store import Store

        with Store(cfg.db_path) as store:
            try:
                result = tools.run(cfg, store, uid, kind, text, progress=progress)
            except llm.LLMError as exc:
                raise ApiError(str(exc)) from exc
        g = result.guard
        return (f"{tools.TOOLS[kind]} ready"
                + (f"; {len(g.unsupported)} of {len(g.claims)} claims not supported"
                   if g.checked and g.unsupported else ""))
    return work


def latest_tools(cfg, uid: str) -> dict:
    """The newest result of each AI tool for one job post."""
    from ..ai import tools
    from ..db.store import Store

    if not UID.match(uid or ""):
        raise ApiError("not a job post id")
    out = {}
    with Store(cfg.db_path) as store:
        for kind in tools.TOOLS:
            row = store.conn.execute(
                "SELECT id, path, created_at FROM artifacts WHERE uid = ? AND kind = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 1", (uid, kind)).fetchone()
            if row is None or not Path(row["path"] or "").is_file():
                continue
            try:
                data = json.loads(Path(row["path"]).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            out[kind] = {**data, "id": row["id"], "created_at": row["created_at"]}
    return {"tools": out, "labels": tools.TOOLS}


def review_job(cfg, uid: str = ""):
    """A resume review: general, or against one job post."""
    if uid and not UID.match(uid):
        raise ApiError("not a job post id")

    def work(progress):
        from ..ai import llm, writer
        from ..db.store import Store

        with Store(cfg.db_path) as store:
            try:
                result = writer.review(cfg, store, uid, progress=progress)
            except llm.LLMError as exc:
                raise ApiError(str(exc)) from exc
        g = result.guard
        return (f"{len(result.health)} resume point(s)"
                + (f", {len(result.alignment['reword'])} line(s) to reword"
                   if result.alignment else "")
                + (f"; {len(g.unsupported)} of {len(g.claims)} claims not supported"
                   if g.checked and g.unsupported else "")
                + f" (output {result.output_id})")
    return work


def ai_output(cfg, output_id: int) -> dict:
    """One recorded AI output, for the page (a general resume review has no file)."""
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        row = store.ai_output(int(output_id))
    if row is None:
        raise ApiError("no such AI output", 404)
    return {"id": row["id"], "kind": row["kind"], "uid": row["uid"] or "",
            "model": row["model"] or "", "created_at": row["created_at"],
            "text": row["text"] or "", "feedback": row["feedback"],
            "guard": json.loads(row["guard_json"] or "{}")}


def latest_review(cfg) -> dict:
    """The newest general resume review, or an empty answer."""
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        row = store.conn.execute(
            "SELECT id FROM ai_outputs WHERE kind = 'resume_review' AND uid IS NULL "
            "ORDER BY id DESC LIMIT 1").fetchone()
    return ai_output(cfg, row["id"]) if row else {}


def feedback(cfg, output_id, value) -> dict:
    """Thumbs up (1), down (-1) or cleared (0 / None) on one AI output."""
    from ..db.store import Store

    try:
        output_id = int(output_id)
        value = int(value) if value not in (None, "") else 0
    except (TypeError, ValueError):
        raise ApiError("output_id and value must be numbers") from None
    if value not in (1, -1, 0):
        raise ApiError("value is 1, -1 or 0")
    with Store(cfg.db_path) as store:
        if not store.set_feedback(output_id, value or None):
            raise ApiError("no such AI output", 404)
    return {"id": output_id, "feedback": value or None}


def digest_job(cfg, email: str, new_only: bool = True, attach_csv: bool = False):
    def work(progress):
        from ..db.store import Store
        from ..output import digest as digest_mod

        with Store(cfg.db_path) as store:
            rows = store.list_roles(new_only=new_only)
            built = digest_mod.build(rows, cfg, new_only=new_only)
            if built.empty:
                return "nothing new; no digest sent"
            if attach_csv:
                digest_mod.attach_csv(built, rows)
            progress(f"sending {len(rows)} role(s) to {email}")
            message_id = digest_mod.send(built, email)
        return f"sent {len(rows)} role(s) to {email} (id {message_id})"
    return work
