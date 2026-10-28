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

import contextlib
import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

from ..core import feedback as feedback_mod
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
        posted_by = recruiters(store, [row])[uid]
        board_state = own_board_states(store, [row]).get(uid, "")
        unlisted = board_state == "missing"
        # The verdict's rating, so the dialog shows which thumb is pressed.
        if ai["ai"] and ai["ai"].get("ai_output_id"):
            output = store.ai_output(int(ai["ai"]["ai_output_id"]))
            ai["ai"]["feedback"] = output["feedback"] if output else None

    try:
        flags = json.loads(row["flags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        flags = []
    if unlisted:
        from ..search import ownboard
        flags.append(ownboard.flag_text(row["company"] or ""))

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
        # An aggregator's post: what the employer's own board says of it
        # (found, missing, partial, unread), for the window's check button.
        "own_board": board_state,
        "description": row["description"] or "",
        "advert_chars": len(row["description"] or ""),
        "credentials": _credentials(cfg, row["description"] or ""),
        **posted_by,
        "artifacts": artifacts,
        "copies": copies,
    }


# ── who posted it: the employer or a recruiter (search/agency.py) ─────────────

_STAFFING_BOARDS: set[str] | None = None


def _staffing_boards() -> set[str]:
    """Names of the built-in boards listed as staffing firms, read once."""
    global _STAFFING_BOARDS
    if _STAFFING_BOARDS is None:
        from ..search import directory
        _STAFFING_BOARDS = {b.name.casefold() for b in directory.load()
                            if b.industry == "staffing"}
    return _STAFFING_BOARDS


def _post(row, status: str = "") -> dict:
    """A role row as search/agency.py reads it, with who posted it."""
    from ..search import agency

    company = row["company"] or ""
    try:
        # A database row's `in` looks at its values, not its columns.
        flags = json.loads(row["flags"] or "[]")
    except (IndexError, KeyError, json.JSONDecodeError, TypeError):
        flags = []
    poster = agency.classify(company, row["description"] or "",
                             "staffing" if company.casefold() in _staffing_boards() else "",
                             flags if isinstance(flags, list) else [])
    return {"uid": row["uid"], "company": company, "title": row["title"] or "",
            "description": row["description"] or "", "work_mode": row["work_mode"] or "",
            "city": row["city"] or "", "state": row["state"] or "",
            "location": row["location_raw"] or "", "status": status or row["status"] or "new",
            "agency": poster.agency, "poster": poster}


def recruiters(store, rows) -> dict[str, dict]:
    """{uid: {"poster", "overlap"}} for these rows: who posted each, and the
    posts you are pursuing that may be the same job reached another way (a
    recruiter's post and the employer's own, or two recruiters')."""
    from ..core.config import PURSUING_STATUSES
    from ..search import agency

    marks = ",".join("?" for _ in PURSUING_STATUSES)
    pursued = [_post(r, r["status"]) for r in store.conn.execute(
        # Safe: only ? placeholders are interpolated.
        "SELECT r.*, s.status FROM roles r JOIN role_state s ON s.uid = r.uid "  # nosec B608
        f"WHERE s.status IN ({marks})", PURSUING_STATUSES)]
    out = {}
    for row in rows:
        post = _post(row)
        out[row["uid"]] = {"poster": post["poster"].to_dict(),
                           "overlap": agency.overlaps(post, pursued) if pursued else []}
    return out


def own_board_states(store, rows) -> dict[str, str]:
    """For the aggregators' posts among these rows, what the employer's own
    board says (search/ownboard.py states): found, missing, partial, unread."""
    from ..search import ownboard

    posts = [(r["uid"], r["company"] or "", r["title"] or "", r["last_seen"] or "")
             for r in rows if r["platform"] in ownboard.AGGREGATORS]
    if not posts:
        return {}
    marks = ",".join("?" for _ in ownboard.OWN_BOARDS)
    platforms = sorted(ownboard.OWN_BOARDS)
    board = store.conn.execute(
        # Safe: only ? placeholders are interpolated.
        f"SELECT company, title, last_seen FROM roles WHERE platform IN ({marks}) "  # nosec B608
        f"UNION ALL SELECT company, title, seen_at FROM dropped WHERE platform IN ({marks})",
        platforms + platforms).fetchall()
    reads = [(r["company"], r["read_at"], bool(r["complete"])) for r in store.board_reads()]
    return ownboard.states(posts, [(c or "", t or "", s or "") for c, t, s in board], reads)


def check_own_board(cfg, uid: str, fetcher=None) -> dict:
    """Ask the employer's own board now whether it carries this aggregator
    post (the post window's button): for a board a scan read only partly or
    not at all, or to look again. Searches the board for the post's own
    title, records the read, and stores nothing else.

    {"state": "found" (with "url") | "missing" | "partial" | "unknown" |
    "failed", "company", "board", "why"}.
    """
    import dataclasses

    from .. import fetch
    from ..db.store import Store
    from ..fetch.http import Fetcher
    from ..search import directory, ownboard

    if not UID.match(uid or ""):
        raise ApiError("not a job post id")
    with Store(cfg.db_path) as store:
        row = store.get(uid)
    if row is None:
        raise ApiError("no such job post", 404)
    if row["platform"] not in ownboard.AGGREGATORS:
        raise ApiError("this post is from the employer's own board already")
    company, title = row["company"] or "", row["title"] or ""
    key = ownboard.employer_key(company)
    boards = [(c.name, c.platform, c.token) for c in cfg.sources.companies] + \
        [(b.name, b.platform, b.token) for b in directory.load()]
    mine = [(n, p, t) for n, p, t in boards
            if key and ownboard.employer_key(n) == key and p in ownboard.OWN_BOARDS]
    if not mine:
        return {"state": "unknown", "company": company, "board": "",
                "why": f"jobdork does not know {company}'s own board. Add it on the "
                       "Sources page (Find an employer's board), or look on their careers site."}
    name, platform, token = mine[0]
    adapter = fetch.get(platform)
    fetcher = fetcher or Fetcher(user_agent=cfg.fetch.user_agent, timeout=cfg.fetch.timeout,
                                 retries=cfg.fetch.retries)
    # Searched for this post's own title, not your list: the question is
    # this job, whatever your titles.
    asked = dataclasses.replace(cfg, titles_include=[title])
    try:
        result = adapter(fetcher, asked, token=token, company=name)
    except Exception as exc:                      # one board's trouble, said
        return {"state": "failed", "company": company, "board": platform,
                "why": f"{type(exc).__name__}: {exc}"}
    complete = result.complete and not result.errors and not result.skipped
    if not result.skipped:
        with Store(cfg.db_path) as store:
            store.record_board_reads([(platform, token, name, complete)])
    wanted = ownboard.title_key(title)
    for role in result.roles:
        if ownboard.same_title(wanted, ownboard.title_key(role.title)):
            return {"state": "found", "company": company, "board": platform,
                    "url": role.url, "title": role.title}
    if result.skipped or (result.errors and not result.roles):
        return {"state": "failed", "company": company, "board": platform,
                "why": result.skipped or "; ".join(map(str, result.errors[:2]))}
    return {"state": "missing" if complete else "partial", "company": company,
            "board": platform}


def not_on_own_board(store, rows) -> set[str]:
    """The aggregators' posts among these rows that the employer's own
    board, read in full in the same scan, does not carry."""
    return {uid for uid, state in own_board_states(store, rows).items() if state == "missing"}


def _credentials(cfg, advert: str) -> list[dict]:
    """Certifications and licenses the advert asks for, against the resume."""
    from ..search import credentials
    from ..search import resume as resume_mod

    try:
        resume_text = resume_mod.load(cfg.resume_path).text if cfg.resume_path else ""
    except resume_mod.ResumeError:
        resume_text = ""
    return credentials.find(advert, resume_text, cfg.credentials)


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
    from ..core import setup
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
            "note": setup.resume_note(len(parsed.text)),
            "skills": [resume_mod.skill_name(s) for s in sorted(parsed.skills)],
            "years": resume_mod.years_claimed(parsed.text)}


# ── projects (Resume page) ────────────────────────────────────────────────────

MAX_PROJECT_FIELD = 2_000     # one STAR answer; a whole case study is a document


def _project(row) -> dict:
    from ..writing import resume_doc

    d = {k: row[k] for k in ("id", "name", "kind", "role", "tools", "link", "situation",
                             "task", "action", "result", "updated_at")}
    d["tutorial"] = bool(resume_doc.tutorial_projects([row["name"]]))
    return d


def list_projects(cfg) -> dict:
    from ..db.store import Store
    from ..writing import resume_doc

    with Store(cfg.db_path) as store:
        rows = store.projects()
    return {"projects": [_project(r) for r in rows],
            "kinds": list(resume_doc.PROJECT_KINDS),
            "tutorial_advice": resume_doc.TUTORIAL_ADVICE,
            # One list, both sides: the page warns as you type with the same pattern.
            "tutorial_pattern": resume_doc.TUTORIAL.pattern}


def save_project(cfg, form: dict) -> dict:
    """Add or change one project. The link must be a web address, if given."""
    from ..db.store import Store
    from ..writing import resume_doc

    fields = {k: str(form.get(k) or "").strip() for k in Store.PROJECT_FIELDS}
    if not fields["name"]:
        raise ApiError("give the project a name")
    if fields["kind"] and fields["kind"] not in resume_doc.PROJECT_KINDS:
        raise ApiError("not a kind of project this knows")
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


def _education(row) -> dict:
    return {k: row[k] for k in ("id", "credential", "school", "location", "start", "end",
                                "details", "updated_at")}


def list_education(cfg) -> dict:
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        return {"education": [_education(r) for r in store.education()]}


def save_education(cfg, form: dict) -> dict:
    """Add or change one education entry: a degree, diploma or course."""
    from ..db.store import Store

    fields = {k: str(form.get(k) or "").strip() for k in Store.EDUCATION_FIELDS}
    if not fields["credential"]:
        raise ApiError("give the degree, diploma or course")
    for key, value in fields.items():
        if len(value) > (MAX_PROJECT_FIELD if key == "details" else 200):
            raise ApiError(f"{key} is too long")
    raw = str(form.get("id") or "")
    with Store(cfg.db_path) as store:
        entry_id = store.save_education(fields, int(raw) if raw.isdigit() else None)
        if not entry_id:
            raise ApiError("no such entry", 404)
        row = next(r for r in store.education() if r["id"] == entry_id)
    return {"entry": _education(row)}


def delete_education(cfg, entry_id: int) -> dict:
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        if not store.delete_education(entry_id):
            raise ApiError("no such entry", 404)
    return {"deleted": entry_id}


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
    from ..search import screen
    from ..search.scan import _load_resume

    if not UID.match(uid or ""):
        raise ApiError("not a job post id")
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        raise ApiError("the advert is empty")
    if len(text) > MAX_ADVERT_CHARS:
        raise ApiError(f"longer than {MAX_ADVERT_CHARS:,} characters")

    home = screen.home_of(cfg)
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
        verdict = screen.screen(role, cfg, home, cv,
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


def directory_boards(cfg) -> dict:
    """Every built-in employer board, for the Sources page: whether this
    config reads it and, if not, why; and the industries to choose from."""
    from ..search import directory

    boards = directory.load()
    d = cfg.sources.directory
    rows, industries = [], {}
    for b in boards:
        why = directory.why_not(cfg, b)
        rows.append({"name": b.name, "platform": b.platform, "industry": b.industry,
                     "countries": list(b.countries), "jobs": b.jobs,
                     "verified": b.verified, "site": b.site, "why": why})
        tally = industries.setdefault(b.industry or "other", {"boards": 0, "read": 0})
        tally["boards"] += 1
        tally["read"] += not why
    return {"enabled": d.enabled, "industries": d.industries, "skip": d.skip,
            "countries": d.countries or list(cfg.locations.countries),
            "read": sum(not r["why"] for r in rows), "total": len(rows),
            "by_industry": dict(sorted(industries.items())), "boards": rows}


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

    given = Path(filename or "").suffix.lower()
    # The suffix written is one of ours, not the browser's string that matched it.
    suffix = next((s for s in RESUME_SUFFIXES if s == given), None)
    if suffix is None:
        raise ApiError(
            f"{given or 'that'} is not a format the resume reader "
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
    from ..search import screen

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

    home = screen.home_of(cfg)
    verdict = screen.screen(wanted, cfg, home)
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


def _merge_counts(a: dict, b: dict) -> dict:
    """Two runs' counts as one: totals added, sources summed."""
    out = {k: a.get(k, 0) + b.get(k, 0) for k in ("fetched", "kept", "stored", "new")}
    sources = dict(a.get("sources") or {})
    for s, n in (b.get("sources") or {}).items():
        sources[s] = sources.get(s, 0) + n
    out["sources"] = sources
    # Skipped in both, or skipped in one and not read by the other.
    sa, sb = set(a.get("skipped") or []), set(b.get("skipped") or [])
    ra, rb = set(a.get("sources") or {}), set(b.get("sources") or {})
    out["skipped"] = sorted((sa & sb) | (sa - rb) | (sb - ra))
    if "failed" in a or "failed" in b:
        out["failed"] = sorted(set(a.get("failed") or []) | set(b.get("failed") or []))
    return out


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
    earlier = done[1:]
    if counts.get("part") == "rest" and earlier:
        # A first scan read the keyword sources in its quick part and the
        # rest of the boards after it: one scan, not one missing half.
        quick = json.loads(earlier[0]["counts_json"] or "{}")
        if quick.get("part") == "quick":
            counts = _merge_counts(quick, counts)
            last, earlier = earlier[0], earlier[1:]
    sources = counts.get("sources") or {}
    warnings = []
    if _days(last["started_at"]) > SCAN_STALE_DAYS:
        warnings.append(f"Last scan was {_ago(last['started_at'])}; posts found "
                        f"then may be gone.")
    skipped = set(counts.get("skipped") or [])
    before = {s for r in earlier for s, n in
              (json.loads(r["counts_json"] or "{}").get("sources") or {}).items() if n}
    # None for a scan recorded before failures were (2026-10-23): every 0 is
    # reported then, as it was.
    failed = counts.get("failed")
    for source, n in sorted(sources.items()):
        if n or source in skipped:
            continue
        name = platform_name(source)
        if failed is None:
            warnings.append(f"{name} returned 0 job posts.")
        elif source in failed:
            warnings.append(f"{name} returned 0 job posts: it failed. Why is "
                            f"under Warnings and errors on the Activity page.")
        elif source in before:
            warnings.append(f"{name} returned 0 job posts, where earlier scans "
                            f"found some.")
        # Otherwise every board of it answered and none had a job matching
        # your titles: one call-centre's board with no software jobs
        # (2026-10-23) is not something to fix.
    # A source that returned posts before and did not run at all this time.
    for source in sorted(before - set(sources)):
        warnings.append(f"{platform_name(source)} did not run in the last scan.")
    unfinished = [r for r in runs if not r["finished_at"] and r["id"] > last["id"]]
    # One still going is the scan running now, not one that died.
    alive = any(_age(r["heartbeat_at"]) < QUIET_SECONDS for r in conn.execute(
        "SELECT heartbeat_at FROM activity WHERE state = 'running' AND heartbeat_at"))
    if unfinished:
        started = unfinished[0]['started_at'][:16].replace('T', ' ')
        warnings.append(f"A scan started {started} is still running." if alive
                        else f"A scan started {started} never finished.")
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
        problems = _problems(conn)
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
        "problems": problems,
        "database": {
            "checked_10m": checked[0], "last_checked": checked[1] or "",
            "listing_states": states,
            "last_scan": dict(last_scan) if last_scan else None,
        },
    }


PROBLEM_DAYS = 7
PROBLEMS_SHOWN = 60


PAGE_LOG = logging.getLogger("jobdork.page")
MAX_PAGE_PROBLEM = 600


def page_problem(form: dict) -> dict:
    """A problem the dashboard page met (a script error, a request the server
    did not answer, an error it showed you), logged so it is under Warnings
    and errors beside the server's, ready for the Feedback page."""
    level = str(form.get("level") or "")
    if level not in ("warning", "error"):
        raise ApiError("level is warning or error")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(form.get("text") or "")).strip()
    if not text:
        raise ApiError("nothing to log")
    PAGE_LOG.log(logging.ERROR if level == "error" else logging.WARNING,
                 "in the page: %s", text[:MAX_PAGE_PROBLEM])
    return {"logged": True}


def _problems(conn) -> list[dict]:
    """The last week's warnings and errors, newest first: every job's, and the app's.

    A job's come from its log lines marked warning or error (telemetry); the
    rest — the server, setup, a config that stopped loading — from
    app_events. `job` names the job, or is "" for the app.
    """
    since = time.strftime("%Y-%m-%dT%H:%M:%S",
                          time.localtime(time.time() - PROBLEM_DAYS * 86400))
    return [dict(r) for r in conn.execute(
        "SELECT at, level, text, '' AS job, 0 AS job_id, source FROM app_events "
        "WHERE at >= ? "
        "UNION ALL "
        "SELECT e.at, e.level, e.text, a.job, a.id, '' FROM activity_events e "
        "JOIN activity a ON a.id = e.activity_id "
        "WHERE e.level IN ('warning', 'error') AND e.at >= ? "
        "ORDER BY at DESC LIMIT ?", (since, since, PROBLEMS_SHOWN))]


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
        # Usage: every call in the period, by day and model, all providers.
        usage_rows = conn.execute(
            "SELECT substr(at, 1, 10) AS day, COALESCE(NULLIF(model, ''), "
            "'unknown model') AS model, ok, input_tokens, output_tokens, error "
            "FROM llm_calls WHERE at >= ?", (since,)).fetchall()
        callers = [r[0] for r in conn.execute(
            "SELECT COALESCE(NULLIF(model, ''), 'unknown model'), MIN(at) "
            "FROM llm_calls GROUP BY 1 ORDER BY 2, 1")]
        first_tokens = conn.execute(
            "SELECT MIN(at) FROM llm_calls WHERE input_tokens + output_tokens > 0"
        ).fetchone()[0] or ""

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

    usage = _usage(usage_rows, callers, dates)
    usage["tokens_since"] = first_tokens[:10]

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
        "usage": {k: v for k, v in usage.items() if k != "per_day"},
        "models": [{"kind": m, "label": m} for m in shown]
        + ([{"kind": "other models", "label": "other models"}] if len(shown) < len(models) else []),
        "per_day": [{"date": d, "runs": by_day[d], "claims": claims_by_day[d],
                     "claims_by_model": claims_by_model[d], "usage": usage["per_day"][d],
                     **feedback[d]} for d in dates],
    }


def _usage(rows, callers: list[str], dates: list[str]) -> dict:
    """Model calls per day and model: requests, failures by kind, tokens.

    `callers` is every model ever called, in the order first used: that is
    the colour order, so a model keeps its colour. Past MAX_MODELS the rest
    fold into "other models", as on the hallucination chart. A failure from
    before kinds were recorded is "unrecorded".
    """
    shown = (callers if len(callers) <= MAX_MODELS else callers[:MAX_MODELS - 1])
    per_day = {d: {} for d in dates}
    kinds: dict[str, int] = {}
    for r in rows:
        if r["day"] not in per_day:
            continue
        model = r["model"] if r["model"] in shown else "other models"
        m = per_day[r["day"]].setdefault(model, {"requests": 0, "failed": 0, "input": 0,
                                                 "output": 0, "errors": {}})
        m["requests"] += 1
        m["input"] += r["input_tokens"] or 0
        m["output"] += r["output_tokens"] or 0
        if not r["ok"]:
            kind = r["error"] or "unrecorded"
            m["failed"] += 1
            m["errors"][kind] = m["errors"].get(kind, 0) + 1
            kinds[kind] = kinds.get(kind, 0) + 1
    used = {model for day in per_day.values() for model in day}
    models = [m for m in shown if m in used] + (["other models"] if "other models" in used else [])
    return {
        "models": [{"kind": m, "label": m,
                    # The colour slot: its place among every model ever called.
                    "ink": shown.index(m) if m in shown else len(shown),
                    "provider": m.split(" · ")[0] if " · " in m else ""} for m in models],
        # Most frequent first: the chart colours the first few and folds the rest.
        # lambda: sort key, a kind's count in the period, highest first, then
        # by name so equal counts keep one order.
        "error_kinds": sorted(kinds, key=lambda k: (-kinds[k], k)),
        "per_day": per_day,
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


# ── risky and stale ───────────────────────────────────────────────────────────
# Screening keeps an old post, marked and ranked lower (freshness.py): one
# for the job you want most is still worth a try. These let you drop them
# all at once instead, after a scan or from Job posts, on your say-so.

AGED_TIERS = ("older", "stale", "ghost")
# Only posts not yet acted on: one you marked interested, or applied to, is
# yours to settle.
AGED_STATUSES = ("new", "viewed")


def _aged(cfg, store) -> tuple[list[dict], list[str]]:
    """Risky, stale and ghost posts not acted on: one per job, and every copy's uid.

    Counted per job as Job posts shows them (grouping.py), so the number on
    the button is the number of posts you see go; their copies go with them,
    or the next copy would take the deleted one's place in the list.
    """
    from ..db import grouping
    from ..search import freshness

    posts, uids = [], []
    for row in store.list_roles():
        if row["status"] not in AGED_STATUSES:
            continue
        part = next((p for p in score_parts(row) if p.get("part") == "freshness"), None)
        tier = freshness.now(part, row["posted_at"] or "", row["first_seen"] or "",
                             cfg.freshness).tier
        if tier in AGED_TIERS:
            posts.append({"title": row["title"] or "", "company": row["company"] or "",
                          "tier": tier})
            uids.extend(grouping.uids(store.conn, row["uid"]))
    return posts, uids


def aged_preview(cfg) -> dict:
    """The risky, stale and ghost posts a removal would delete. Deletes nothing."""
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        posts, uids = _aged(cfg, store)
    by_tier: dict[str, int] = {}
    for p in posts:
        by_tier[p["tier"]] = by_tier.get(p["tier"], 0) + 1
    return {"count": len(posts), "copies": len(uids), "by_tier": by_tier,
            "older_days": cfg.freshness.older_days, "week_days": cfg.freshness.week_days,
            "sample": [f"{p['title']} at {p['company']}" for p in posts[:5]]}


def aged_run(cfg, expect: int = -1) -> dict:
    """Back the database up, then delete what aged_preview showed.

    Refused when the count has moved since the preview, as cleanup_run is.
    Deleted posts are remembered, so a later scan does not bring them back.
    """
    from ..db.store import Store

    with Store(cfg.db_path) as store:
        posts, uids = _aged(cfg, store)
        if int(expect) != len(posts):
            raise ApiError(f"the count changed from {expect} to {len(posts)} "
                           "since the preview; preview again", 409)
        if not posts:
            return {"deleted": 0, "copies": 0, "backup": ""}
        backup = _backup(cfg, store, "aged")
        copies = store.delete_many(uids, "risky or stale, removed by you")
    return {"deleted": len(posts), "copies": copies, "backup": str(backup)}


# ── dropped by your filters ───────────────────────────────────────────────────
# A scan keeps only what passes your filters; the rest is remembered for a
# while (store.save_dropped) so Job posts can show it on request, with the
# rule and the reason, and one can be kept anyway.

def dropped_list(cfg) -> dict:
    """Dropped posts as Job posts cards, and how many each rule dropped."""
    from ..db.store import DROPPED_DAYS, Store
    from ..search import freshness, geo
    from ..search.screen import DROP_RULES

    units = cfg.locations.units or "mi"
    posts, by_rule = [], dict.fromkeys(DROP_RULES, 0)
    with Store(cfg.db_path) as store:
        rows = store.list_dropped()
    for row in rows:
        rule = row["rule"] or "other"
        by_rule[rule] = by_rule.get(rule, 0) + 1
        # The board's date only: `seen_at` moves with every scan, so it says
        # nothing about the post's age.
        a = freshness.age(row["posted_at"] or "", "", cfg.freshness)
        stated = bool(row["salary_stated"])
        top = row["salary_max"] if row["salary_max"] is not None else row["salary_min"]
        posts.append({
            "uid": row["uid"], "title": row["title"] or "", "company": row["company"] or "",
            "url": row["url"] or "", "platform": row["platform"] or "",
            "location": row["location_raw"] or "", "work_mode": row["work_mode"] or "",
            "distance": geo.distance_label(row["distance_mi"], units),
            "dist": None if row["distance_mi"] is None
            else round(geo.from_miles(row["distance_mi"], units), 1),
            "pay_top": top if stated else None,
            "pay_currency": (row["salary_currency"] or "") if stated else "",
            "age": {"days": a.days, "tier": a.tier, "text": a.text(), "source": a.source},
            "rule": rule, "reason": row["reason"] or "", "seen": (row["seen_at"] or "")[:10],
        })
    return {"dropped": posts, "by_rule": {k: v for k, v in by_rule.items() if v},
            "days": DROPPED_DAYS}


def dropped_keep(cfg, uid: str) -> dict:
    """Keep a dropped post anyway: into Job posts, marked interested, with a note.

    Keeping it is a decision, so it is marked as one: re-applying filters,
    the age limit and the risky-and-stale removal all leave an interested
    post alone. It has no score: the rules dropped it, and a score from them
    would rank it as if they had not.
    """
    from ..db.store import Role, Store

    with Store(cfg.db_path) as store:
        row = store.get_dropped(uid)
        if row is None:
            raise ApiError("that dropped post is no longer remembered", 404)
        role = Role(platform=row["platform"], company=row["company"] or "",
                    title=row["title"] or "", url=row["url"] or "",
                    location_raw=row["location_raw"] or "", posted_at=row["posted_at"] or "",
                    distance_mi=row["distance_mi"], work_mode=row["work_mode"] or "",
                    salary_min=row["salary_min"], salary_max=row["salary_max"],
                    salary_currency=row["salary_currency"] or "",
                    salary_stated=bool(row["salary_stated"]),
                    flags=[f"kept by you; your filters dropped it: {row['reason']}"])
        store.upsert(role)
        store.conn.commit()
        store.set_status(role.uid, "interested", f"Kept anyway. Dropped for: {row['reason']}")
        store.forget_dropped([uid])
    return {"uid": role.uid, "kept": True}


# ── start over ────────────────────────────────────────────────────────────────
# Setup again from the welcome screen, with nothing of the old run left:
# the settings file, the database (job posts, statuses, notes, AI verdicts,
# runs), the uploaded resume, the documents written for job posts, the
# reports in the output folder, the job-source keys file and the AI keys
# held in memory. Only files jobdork wrote: a resume you pointed the config
# at yourself, and anything else in your folders, are left alone.

START_OVER_WORDS = "start over"


def _start_over_targets(cfg) -> dict:
    """What a start-over would delete, as paths that exist now."""
    from ..core import storage
    from ..core.config import source_keys_path
    from ..db.store import Store

    db = Path(cfg.db_path)
    files, documents, posts = [], [], 0
    if cfg.path and Path(cfg.path).is_file():
        files.append(Path(cfg.path))
    if db.is_file():
        files += [p for p in (db, Path(f"{db}-wal"), Path(f"{db}-shm")) if p.is_file()]
        with Store(cfg.db_path) as store:
            posts = store.conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
            documents = [Path(r[0]) for r in store.conn.execute(
                "SELECT DISTINCT path FROM artifacts WHERE COALESCE(path, '') <> ''")
                if Path(r[0]).is_file()]
    if cfg.resume_path and storage.is_uploaded_resume(cfg.resume_path, cfg) \
            and Path(cfg.resume_path).expanduser().is_file():
        files.append(Path(cfg.resume_path).expanduser())
    if source_keys_path(cfg).is_file():
        files.append(source_keys_path(cfg))
    # Reports, only from an output folder beside the config: one pointed
    # somewhere else may hold more than jobdork's own files.
    out = Path(cfg.output.dir)
    home = Path(cfg.path).parent if cfg.path else Path.cwd()
    if not out.is_absolute():
        out = home / out
    try:
        inside = out.resolve().is_relative_to(home.resolve())
    except OSError:
        inside = False
    reports = [p for p in out.glob("*") if p.is_file()] if inside and out.is_dir() else []
    return {"files": files, "documents": documents, "reports": reports, "posts": posts}


def start_over_preview(cfg) -> dict:
    """What starting over deletes. Deletes nothing."""
    t = _start_over_targets(cfg)
    return {"posts": t["posts"], "documents": len(t["documents"]),
            "reports": len(t["reports"]),
            "settings": bool(cfg.path and Path(cfg.path).is_file()),
            "resume": next((p.name for p in t["files"] if p.stem == "resume"), ""),
            "files": [str(p) for p in t["files"]],
            "words": START_OVER_WORDS}


def start_over(cfg, words: str, backup: bool = True) -> dict:
    """Delete everything start_over_preview listed. Needs the words typed.

    With `backup`, the settings, database and resume are copied first into
    a folder of their own beside the database, which a start-over leaves
    alone; keys are never copied.
    """
    import shutil

    from ..ai import llm
    from ..core.config import source_keys_path

    if (words or "").strip().lower() != START_OVER_WORDS:
        raise ApiError(f'type "{START_OVER_WORDS}" to confirm')
    t = _start_over_targets(cfg)
    kept = ""
    if backup:
        folder = (Path(cfg.db_path).parent / "backups" /
                  f"start-over-{time.strftime('%Y%m%d-%H%M%S')}")
        folder.mkdir(parents=True, exist_ok=True)
        db = Path(cfg.db_path)
        if db.is_file():
            import sqlite3
            target = sqlite3.connect(folder / db.name)
            with sqlite3.connect(db) as source, target:
                source.backup(target)
            target.close()
        for p in t["files"]:
            if p != source_keys_path(cfg) and not p.name.startswith(db.name):
                shutil.copy2(p, folder / p.name)
        kept = str(folder)
    removed = 0
    for p in [*t["documents"], *t["reports"], *t["files"]]:
        try:
            p.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    llm.VAULT.wipe()
    # And the keys you chose to keep: a fresh start keeps nothing.
    from ..core import keystore
    from ..core.config import APP_KEYS, SOURCE_KEY_NAMES
    keystore.forget_all()
    for name in SOURCE_KEY_NAMES:
        if name in APP_KEYS:
            os.environ.pop(name, None)
            APP_KEYS.discard(name)
    return {"removed": removed, "backup": kept}


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
    from ..core.config import MAX_READERS, SETUP_MAX_READERS

    settings = llm.Settings.from_config(cfg)

    def listed(models) -> list[dict]:
        out = []
        for r in models:
            one = llm.Settings(provider=r.provider, model=r.model,
                               ollama_url=r.ollama_url or cfg.llm.ollama_url)
            out.append({"provider": r.provider, "model": r.model,
                        "ollama_url": r.ollama_url, "label": one.label,
                        "problem": one.problem()})
        return out

    return {
        "providers": llm.PROVIDERS,
        "readers": listed(cfg.llm.readers),
        "checkers": listed(cfg.llm.checkers),
        # Setup offers a few; the AI page, later, the rest.
        "max_readers": SETUP_MAX_READERS if cfg.setup_step else MAX_READERS,
        "provider": cfg.llm.provider,
        "model": cfg.llm.model,
        "ollama_url": cfg.llm.ollama_url,
        # Only the built-in default: not shown in a line's box as if chosen.
        "ollama_url_default": cfg.llm.ollama_url in (llm.DEFAULT_OLLAMA_URL,
                                                     llm.OLLAMA_FROM_DOCKER),
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
    """Hold a key in memory, and keep it in the keychain when you chose to
    (core/keystore.py). It is never echoed back, logged or written to a file."""
    from ..ai import llm
    from ..core import keystore

    try:
        llm.VAULT.put(provider, key)
    except llm.LLMError as exc:
        raise ApiError(str(exc)) from exc
    note = ""
    if keystore.remembering:
        try:
            keystore.save(keystore.AI_PREFIX + provider, key.strip())
            note = "kept in this computer's keychain"
        except keystore.KeystoreError as exc:
            note = f"held until jobdork closes: {exc}"
    return {"held": llm.VAULT.held(), "note": note}


def _note_key_source(cfg, source: str, given: bool) -> None:
    """Remember that you gave this source keys (its name, never the keys),
    so a restart can ask for them again."""
    from ..core import setup

    have = set(cfg.key_sources)
    want = have | {source} if given else have - {source}
    if want != have and cfg.path:
        cfg.key_sources = sorted(want)
        with contextlib.suppress(Exception):    # a note, not worth failing the save
            setup.write(cfg.path, {"key_sources": cfg.key_sources})


def keys_state(cfg) -> dict:
    """For the page on every start: whether keys are kept, where, and which
    keys jobdork needs and does not hold (after a restart or an update, with
    keys held in memory only). Never a key."""
    from ..ai import llm
    from ..core import keystore

    store = {"darwin": "macOS Keychain", "win32": "Windows Credential Manager"}.get(
        sys.platform, "your Secret Service (GNOME Keyring or KWallet)")
    missing = []
    wanted = [r.provider for r in [*cfg.llm.readers, *cfg.llm.checkers]] or [cfg.llm.provider]
    for provider in dict.fromkeys(p for p in wanted if p in llm.KEYED):
        # Memory or the environment only: asking the keychain on every poll
        # could prompt on a Mac; keys kept there were loaded at start.
        if not llm.VAULT.get(provider) and not any(
                os.environ.get(n) for n in llm.ENV_KEYS[provider]):
            missing.append({"kind": "ai", "name": provider, "label": llm.PROVIDERS[provider]})
    ready = {"adzuna": cfg.sources.adzuna_ready(), "usajobs": cfg.sources.usajobs_ready()}
    for source in cfg.key_sources:
        if not ready.get(source, True):
            missing.append({"kind": "source", "name": source,
                            "label": "Adzuna" if source == "adzuna" else "USAJOBS"})
    return {"remember": cfg.remember_keys, "store": store,
            "unavailable": keystore.unavailable(), "legacy": bool(cfg.legacy_keys_file),
            "missing": missing}


def legacy_keys(cfg, keep: bool) -> dict:
    """An old source-keys.env (0.15.1 and before): its keys into the keychain
    (`keep`, which turns Remember keys on), or for this run only. The plain
    file is deleted either way."""
    from ..core import keystore, setup
    from ..core.config import settle_legacy_keys

    if keep and keystore.unavailable():
        raise ApiError(f"keys cannot be kept here: {keystore.unavailable()}", 409)
    try:
        moved = settle_legacy_keys(cfg, keep)
    except keystore.KeystoreError as exc:
        raise ApiError(str(exc)) from exc
    if keep and not cfg.remember_keys and cfg.path:
        setup.write(cfg.path, {"remember_keys": True})
        cfg.remember_keys = keystore.remembering = True
    return {"moved": moved}


def forget_saved_keys() -> dict:
    """Settings: remove every key kept in the keychain. Those held now stay
    in memory until jobdork closes."""
    from ..core import keystore

    keystore.forget_all()
    return {"forgotten": True}


def remember_keys_changed(on: bool) -> str:
    """Remember keys turned on: the keys held now go into the keychain.
    Turned off: the kept copies are removed; memory keeps them for this run.
    Returns what to tell the person."""
    from ..ai import llm
    from ..core import keystore
    from ..core.config import APP_KEYS

    if not on:
        keystore.forget_all()
        return "Keys are no longer kept: removed from the keychain, held until jobdork closes."
    why = keystore.unavailable()
    if why:
        return f"Keys cannot be kept here: {why}."
    kept = 0
    try:
        for provider in llm.VAULT.held():
            keystore.save(keystore.AI_PREFIX + provider, llm.VAULT.get(provider))
            kept += 1
        for name in sorted(APP_KEYS):
            if os.environ.get(name):
                keystore.save(name, os.environ[name])
                kept += 1
    except keystore.KeystoreError as exc:
        return f"Some keys were not kept: {exc}."
    return (f"Kept {kept} key{'s' * (kept != 1)} in this computer's keychain." if kept
            else "Keys you enter from now on are kept in this computer's keychain.")


def llm_forget(provider: str) -> dict:
    """Stop holding a key, and remove any copy kept in the keychain."""
    from ..ai import llm
    from ..core import keystore

    for one in (llm.KEYED if provider == "all" else (provider,)):
        llm.VAULT.forget(one)
        keystore.delete(keystore.AI_PREFIX + one)
    return {"held": llm.VAULT.held()}


def llm_test(cfg) -> dict:
    """Ask every reader, one by one, and every chosen checker, to answer.
    Fails only when no reader answers."""
    from ..ai import llm

    settings = llm.Settings.from_config(cfg)

    def ask(models) -> list[dict]:
        answers = []
        for one in models:
            try:
                if one.problem():
                    raise llm.LLMError(one.problem())
                answers.append(llm.ping(one))
            except llm.LLMError as exc:
                answers.append({"model": one.label, "error": str(exc)})
        return answers

    answers = ask([llm.Settings(provider=r.provider, model=r.model,
                                ollama_url=r.ollama_url or cfg.llm.ollama_url,
                                context=settings.context)
                   for r in cfg.llm.readers] or [settings])
    working = [a for a in answers if "error" not in a]
    if not working:
        raise ApiError("; ".join(f"{a['model']}: {a['error']}" for a in answers), 502)
    return {**working[0], "readers": answers, "checkers": ask(settings.checkers)}


# ── first-run setup ───────────────────────────────────────────────────────────


def setup_choices(cfg) -> dict:
    """What "What you are looking for" offers, and what is chosen already."""
    from ..ai.suggest import known_industries
    from ..search import dealbreakers

    catalog = dealbreakers.suggestions()
    # Ones already in the config but not in the catalog are offered too, so
    # saving the step keeps them.
    names = {d["name"] for d in catalog}
    catalog += [{"name": d.name, "words": d.words, "pattern": d.pattern, "hard": d.hard}
                for d in cfg.dealbreakers if d.name not in names]
    from ..search import credentials
    from ..search import resume as resume_mod
    try:
        resume_text = resume_mod.load(cfg.resume_path).text if cfg.resume_path else ""
    except resume_mod.ResumeError:
        resume_text = ""
    return {"industries": known_industries(),
            "dealbreakers": catalog,
            # Certifications and licenses the resume names, offered ticked.
            "credentials_found": credentials.named_in(resume_text),
            "chosen": {"titles": cfg.titles_include, "exclude": cfg.titles_exclude,
                       "industries": cfg.sources.directory.industries,
                       "dealbreakers": [d.name for d in cfg.dealbreakers],
                       "credentials": cfg.credentials}}


def setup_sources(cfg) -> dict:
    """What a scan will read, in plain words, and the two optional keys."""
    from ..core.config import APP_KEYS
    from ..fetch.adzuna import ISO_TO_INDEX
    from ..search import directory

    countries = list(cfg.locations.countries)
    searched = [{"name": "Workable", "what": "its job search, by your job titles"},
                {"name": "Himalayas", "what": "remote jobs worldwide, kept to your countries"}]
    if {"PH", "ID"} & set(countries) or not countries:
        searched.append({"name": "Kalibrr",
                         "what": "Philippine and Indonesian jobs, by your job titles"})
    d = cfg.sources.directory

    def where(names: tuple[str, ...]) -> str:
        """"app" (typed here: in memory, and the keychain if you chose it),
        "environment" (.env or the real environment), or "" (none)."""
        if not all(os.environ.get(n) for n in names):
            return ""
        return "app" if all(n in APP_KEYS for n in names) else "environment"

    adzuna_here = not countries or any(c in ISO_TO_INDEX for c in countries)
    keyed = [
        {"name": "adzuna", "label": "Adzuna",
         "what": "many job boards at once, searched by your job titles",
         "offer": f"It searches many job boards at once, in {len(ISO_TO_INDEX)} countries.",
         "applies": adzuna_here,
         "why_not": "" if adzuna_here else "Adzuna does not cover your countries",
         "ready": cfg.sources.adzuna_ready(),
         "held": where(("ADZUNA_APP_ID", "ADZUNA_APP_KEY")),
         "fields": [{"name": "ADZUNA_APP_ID", "label": "App ID"},
                    {"name": "ADZUNA_APP_KEY", "label": "App key"}],
         "signup": "https://developer.adzuna.com/signup"},
        {"name": "usajobs", "label": "USAJOBS",
         "what": "US federal government jobs",
         "offer": "It lists US federal government jobs.",
         "applies": cfg.usajobs_in_scope(),
         "why_not": "" if cfg.usajobs_in_scope() else "US federal jobs only, and the US "
                                                       "is not in your countries",
         "ready": cfg.sources.usajobs_ready(),
         "held": where(("USAJOBS_API_KEY", "USAJOBS_EMAIL")),
         "fields": [{"name": "USAJOBS_API_KEY", "label": "API key"},
                    {"name": "USAJOBS_EMAIL", "label": "Email you signed up with"}],
         "signup": "https://developer.usajobs.gov/APIRequest/Index"},
    ]
    return {
        "titles": cfg.titles_include,
        "searched": searched,
        "boards": {"enabled": d.enabled, "count": len(directory.select(cfg)),
                   "industries": d.industries, "countries": d.countries or countries},
        "own_boards": len(cfg.sources.companies),
        "keyed": keyed,
    }


def try_source_keys(cfg, values: dict[str, str]) -> tuple[str, str]:
    """Ask the source whether it accepts these keys: one search, so a wrong
    key is found when it is typed, not as a failed scan later."""
    from ..fetch import adzuna, usajobs
    from ..fetch.http import Fetcher

    fetcher = Fetcher(cfg.fetch.user_agent, min(cfg.fetch.timeout, 15), 0)
    if "USAJOBS_API_KEY" in values:
        return usajobs.try_key(fetcher, values["USAJOBS_API_KEY"],
                               values.get("USAJOBS_EMAIL", ""))
    return adzuna.try_key(fetcher, values.get("ADZUNA_APP_ID", ""),
                          values.get("ADZUNA_APP_KEY", ""))


def setup_keys(cfg, form: dict) -> str:
    """Save or remove one source's keys. Nothing typed is ever sent back.

    New keys are tried first, and only keys the source accepted are saved:
    a refused key is not, and neither is one the source could not be asked
    about (offline, down), so a key that does not work is never kept. The
    page says which, and to try again later in the second case.
    """
    from ..core.config import (
        SOURCE_KEY_NAMES,
        ConfigError,
        check_source_key,
        write_source_keys,
    )
    from ..core.keystore import KeystoreError

    values = {k: str(form.get(k) or "").strip() for k in SOURCE_KEY_NAMES if k in form}
    if not values:
        raise ApiError("no key given")
    remove = bool(form.get("remove"))
    if not remove and not all(values.values()):
        raise ApiError("fill in both boxes")
    note = ""
    try:
        if not remove:
            # Checked before trying: a key with a space in it is not sent anywhere.
            for name, value in values.items():
                check_source_key(name, value)
            verdict, why = try_source_keys(cfg, values)
            if verdict == "refused":
                raise ApiError(why)
            if verdict != "ok":
                raise ApiError(f"Not saved: {why}, so the key could not be tested. "
                               "Try again when it answers", 503)
            source = "USAJOBS" if "USAJOBS_API_KEY" in values else "Adzuna"
            note = (f"Tested: {source} accepted the key. Saved in this computer's keychain."
                    if cfg.remember_keys else
                    f"Tested: {source} accepted the key. Held until jobdork closes; "
                    "to keep it, turn on Remember keys in Settings.")
        write_source_keys(cfg, {k: "" if remove else v for k, v in values.items()})
        _note_key_source(cfg, "usajobs" if "USAJOBS_API_KEY" in values else "adzuna", not remove)
    except KeystoreError as exc:
        note = f"Held until jobdork closes: {exc}."
    except ConfigError as exc:
        raise ApiError(str(exc)) from exc
    return note


# How far the suggestion call has got, for the page to poll while it waits:
# one server, one person setting up, so one record.
SUGGEST_PROGRESS = {"fraction": 0.0, "label": ""}


def setup_suggest(cfg, progress=None) -> dict:
    """The model's suggestions from the resume. Slow on a local model."""
    from ..ai import llm
    from ..ai.suggest import suggest
    from ..search import resume as resume_mod

    def note(fraction, label):
        SUGGEST_PROGRESS.update(fraction=fraction, label=label)
        if progress:
            progress(fraction, label)
    try:
        text = resume_mod.load(cfg.resume_path).text if cfg.resume_path else ""
        return suggest(llm.Settings.from_config(cfg), text, progress=note)
    except (llm.LLMError, resume_mod.ResumeError) as exc:
        raise ApiError(str(exc), 502) from exc


# ── long jobs, run through the Runner ─────────────────────────────────────────


# Setup's first scan as the Dashboard tells its two parts apart: the employer
# boards each reads, and whether the second has ended unseen. Held in memory:
# after a restart the computer's notification has said it already.
FIRST_SCAN: dict = {}


def first_scan_jobs(cfg) -> list[tuple[str, object]]:
    """Setup's last step: a quick scan, which finishes setup, then the rest.

    The quick part reads the keyword sources and a sample of the built-in
    boards, so job posts are there within a minute or two; setup is marked
    done when it ends, and the page opens on the Dashboard while the rest of
    the boards are read as a background scan of their own. When that ends,
    the page offers View job posts, and the computer says so too, the window
    open or not.
    """
    from ..core import setup
    from ..search import scan as scan_mod

    quick_boards = sum(1 for _, how in scan_mod._jobs_for(cfg, "quick") if how.get("token"))
    rest_boards = len(scan_mod._jobs_for(cfg, "rest"))
    FIRST_SCAN.clear()
    FIRST_SCAN.update(quick=quick_boards, rest=rest_boards, ready=False, kept=0)
    quick = scan_job(cfg, part="quick")

    def first(progress):
        progress(f"quick scan: the job sites and {quick_boards} employer boards")
        summary = quick(progress)
        setup.write(cfg.path, {"setup_step": setup.DONE})
        progress(f"setup finished; the other {rest_boards} employer boards are read next")
        return summary
    return [("first scan", first), ("full scan", scan_job(cfg, part="rest", ready=True))]


def first_scan_seen() -> dict:
    """The ready notice dismissed, or its View job posts clicked."""
    FIRST_SCAN["ready"] = False
    return {"seen": True}


def scan_job(cfg, part: str = "all", ready: bool = False):
    """A scan as a background job. `ready`: the end of setup's first scan,
    told as "your job posts are ready" whether anything was new or not."""
    def work(progress):
        from ..core import notify
        from ..db.store import Store
        from ..output import render
        from ..search import scan as scan_mod

        with Store(cfg.db_path) as store:
            try:
                report = scan_mod.run(cfg, store, progress=progress, part=part)
            except Exception as exc:
                notify.scan_failed(cfg, f"{type(exc).__name__}: {exc}")
                raise
            summary = " · ".join(report.lines())
            if ready:
                kept = len(store.list_roles())
                FIRST_SCAN.update(ready=True, kept=kept)
                notify.first_scan_ready(cfg, kept)
            else:
                notify.scan_finished(cfg, report.newly_seen, report.kept)
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
                                  notes=resume_doc.record_notes(store.projects(), store.education()),
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



def report_preview(cfg, form: dict) -> dict:
    """The problem report or idea, exactly as it would be sent (core/feedback.py)."""
    report = _report(cfg, form)
    return {"subject": report.subject(), "text": report.text(),
            "issue_url": report.issue_url(), "can_send": bool(feedback_mod.relay_url()),
            "screenshots": len(report.screenshots)}


def report_send(cfg, form: dict) -> dict:
    report = _report(cfg, form)
    try:
        answer = feedback_mod.send(report)
    except feedback_mod.FeedbackError as exc:
        raise ApiError(str(exc), 502) from exc
    log.info("feedback sent: %s", report.subject())
    return {"sent": True, "issue_url": str(answer.get("issue_url") or "")}


def _report(cfg, form: dict):
    from ..db.store import Store

    problems = []
    if form.get("logs"):
        with Store(cfg.db_path) as store:
            problems = _problems(store.conn)
    try:
        return feedback_mod.build(form, cfg, problems)
    except feedback_mod.FeedbackError as exc:
        raise ApiError(str(exc)) from exc

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


# ── the scan schedule ─────────────────────────────────────────────────────────


def schedule_state(cfg) -> dict:
    """What the system's scheduler has for this install (core/schedule.py)."""
    from ..core import schedule

    return schedule.status(cfg.path or "")


def schedule_save(cfg, form: dict) -> dict:
    """Turn the scan schedule on (every, at, day) or off (every=off)."""
    from ..core import schedule
    from ..core.config import ConfigError

    every = str(form.get("every") or "").strip().lower()
    try:
        if every == "off":
            return schedule.uninstall(cfg.path or "")
        plan = schedule.Plan(every, str(form.get("at") or ""), str(form.get("day") or "mon"))
        return schedule.install(cfg.path or "", plan)
    except ConfigError as exc:
        raise ApiError(str(exc)) from None


# ── where the app keeps things ────────────────────────────────────────────────

FOLDERS = ("settings", "backups", "logs", "documents")


def folders(cfg) -> dict:
    """The folders worth knowing about, and whether this server can open them.

    Opening a folder happens on the machine the server runs on, so it is
    offered only when that is the machine the page is on: not in a container,
    and not when the dashboard is opened from other machines on the network.
    """
    from ..core.config import CONTAINER_ENV
    from ..writing import generate
    from .serve import ALLOW_ENV

    settings = Path(cfg.path or "config.yaml").resolve().parent
    data = Path(cfg.db_path).resolve().parent
    where = {
        "settings": {"path": str(settings),
                     "what": "Your settings, keys file, database and resume"},
        "backups": {"path": str(data / "backups"),
                    "what": "Copies of the database, made before anything is deleted"},
        "logs": {"path": str(settings / "logs"),
                 "what": "The app's log and the scheduled scans' log"},
        "documents": {"path": str(Path(generate.default_root()).expanduser()),
                      "what": "Cover letters and tailored resumes, a folder per job"},
    }
    for item in where.values():
        item["exists"] = Path(item["path"]).is_dir()
    local = not os.environ.get(CONTAINER_ENV) and not os.environ.get(ALLOW_ENV, "").strip()
    return {"folders": where, "can_open": local}


def open_folder(cfg, which: str) -> dict:
    """Open one of `folders()` in Finder, Explorer or the file manager."""
    from .app import open_with_system

    report = folders(cfg)
    if not report["can_open"]:
        raise ApiError("folders can only be opened on the machine jobdork runs on", 409)
    item = report["folders"].get(str(which or ""))
    if item is None:
        raise ApiError(f"no such folder; one of {', '.join(FOLDERS)}")
    path = Path(item["path"])
    if not path.is_dir():
        raise ApiError("that folder does not exist yet: nothing has been written to it", 404)
    open_with_system(path)
    return {"opened": which}


def newer_version(cfg=None, force: bool = False) -> dict:
    """Whether a newer jobdork is out (core/updates.py), for the page; and
    the first time a version is seen, a notification about it."""
    from ..core import notify, updates

    folder = Path(cfg.db_path).parent if cfg is not None else Path("data")
    found = updates.check(folder, enabled=getattr(cfg, "update_check", True), force=force)
    found["enabled"] = bool(getattr(cfg, "update_check", True)) and not updates.off()
    found["can_install"] = bool(found.get("installer"))
    if found.get("newer") and cfg is not None and updates.first_notice(folder, found["latest"]):
        notify.notify(cfg, f"jobdork {found['latest']} is out",
                      f"You have {found['current']}. Settings, Updates installs it.")
    return found


def notify_test(cfg) -> dict:
    """Show one notification now, as the settings would, so the person can
    see and hear it (and macOS can ask for permission)."""
    from ..core import notify

    if not cfg.notifications.enabled:
        raise ApiError("notifications are off; turn them on first", 409)
    sound = cfg.notifications.sound
    if not notify.native():
        return {"shown": False, "why": "this system shows none (jobdork is in a "
                                       "container, or Linux has no notify-send)"}
    shown = notify.notify(cfg, "jobdork notifications are on",
                          "This is how a scan that finds new job posts tells you.")
    return {"shown": shown, "sound": sound,
            "why": "" if shown else "the system did not take it; see Warnings and errors"}


def _finish_removing() -> str:
    """What is left to do once jobdork's traces are gone: the program itself."""
    if sys.platform == "darwin":
        return "mac"
    if sys.platform == "win32":
        return "windows"
    return "appimage" if os.environ.get("APPIMAGE") else "linux"


def uninstall_items() -> dict:
    """Settings' "Remove jobdork from this computer": what there is, item by
    item, with its size, for the person to choose from."""
    from ..core import uninstall

    if not getattr(sys, "frozen", False):
        raise ApiError("this is for the desktop app; a copy run from source keeps its data "
                       "in its own folder, which ./run.sh clean empties", 409)
    return {"finish": _finish_removing(), "appimage": os.environ.get("APPIMAGE", ""),
            "items": [{"key": i.key, "label": i.label, "what": i.what, "size": i.size,
                       "present": i.present} for i in uninstall.inventory()]}


def uninstall_now(form: dict) -> dict:
    """Remove jobdork's traces and what the person chose (core/uninstall.py).

    Not on Windows: the database is open while jobdork runs and Windows will
    not delete an open file. Its uninstaller (Settings, Apps) asks the same
    questions and removes them after jobdork has closed."""
    from ..core import uninstall

    uninstall_items()                        # the desktop app only
    if sys.platform == "win32":
        raise ApiError("on Windows, uninstall jobdork from Settings, Apps: it asks the "
                       "same questions, and can remove files jobdork has open", 409)
    choose = form.get("remove") if isinstance(form, dict) else None
    if not isinstance(choose, list) or not all(isinstance(c, str) for c in choose):
        raise ApiError("remove is a list of items")
    out = uninstall.remove(set(choose))
    out["finish"] = _finish_removing()
    out["appimage"] = os.environ.get("APPIMAGE", "")
    return out


# Where the update the page's window follows has got to (update_progress).
# One update at a time: the runner runs one job at a time.
_UPDATE: dict = {"stage": "idle"}
_UPDATE_LOCK = threading.Lock()


def _update_at(stage: str, **facts) -> None:
    with _UPDATE_LOCK:
        if stage == "bytes":
            _UPDATE.update(facts)
        else:
            _UPDATE.update(stage=stage, **facts)


def update_progress() -> dict:
    """The update window's state: its stage ("idle", "asking", "downloading",
    "checksum", "attestation", "opened", "failed"), the bytes so far, and
    what to say. 0.15.0 showed "Downloading the update" while the job had
    already failed; the window shows the failure and its reason."""
    with _UPDATE_LOCK:
        return {**_UPDATE, "platform": "mac" if sys.platform == "darwin"
                else "windows" if sys.platform == "win32" else "other"}


def update_job(cfg):
    """Download this computer's installer for the newest release, check it
    against the release's checksums, and open it: the Windows installer
    replaces this copy (closing it first); the Mac disk image opens for the
    new app to be dragged into Applications."""
    from ..core import updates
    from .app import open_with_system

    if not getattr(sys, "frozen", False):
        raise ApiError("only the desktop app installs its own updates; see how "
                       "to update this copy under Settings, Updates", 409)
    with _UPDATE_LOCK:
        _UPDATE.clear()
        _UPDATE.update(stage="asking", done=0, total=0)

    def work(progress):
        folder = Path.home() / "Downloads"
        try:
            path = updates.download_installer(folder, progress=progress, step=_update_at)
        except updates.UpdateError as exc:
            _update_at("failed", error=str(exc))
            raise RuntimeError(str(exc)) from None
        except Exception as exc:
            _update_at("failed", error=f"{type(exc).__name__}: {exc}")
            raise
        open_with_system(path)
        _update_at("opened", path=str(path), file=path.name)
        return f"opened {path.name}; follow the installer to finish the update"
    return work
