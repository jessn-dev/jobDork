"""
jobdork.web.serve
=================
The dashboard with buttons, and a scan you can watch.

The same list `jobdork list` prints, except that what you click sticks and a
scan reports itself while it runs. It reads and writes the same database the
CLI does, so the two cannot disagree — mark a role applied here and
`jobdork list` shows it applied, and the reverse.

Standard library only. It is a local tool, not a service: it stops when you
Ctrl-C, it has no accounts, and there is nothing to expose.

Three things it refuses to do, all deliberate:

  **It does not bind to 0.0.0.0.** There is no `--host`. A dashboard listing
  where you are applying is not a thing to put on a network, and an option to
  do it is an option somebody uses. The one exception is inside a container,
  where 127.0.0.1 is the container's own loopback and a published port cannot
  reach it: `JOBDORK_IN_CONTAINER=1` *and* a container marker file together
  bind 0.0.0.0, so the variable alone does nothing on a bare host. The host
  then publishes it to its own loopback, `-p 127.0.0.1:8765:8765`. The
  other is `JOBDORK_ALLOW_HOSTS`, which names the exact addresses another
  machine may open it by (a NAS's, say): those join the Host check, and the
  token is required as ever. It names addresses; it cannot say "anything".

  **It validates the Host header against the address it actually bound to**,
  rather than trusting Origin. Under DNS rebinding a page on an attacker's
  domain can reach 127.0.0.1 in your browser, and Host and Origin are
  attacker-controlled together — but the bound address is not.

  **It requires a token minted for this run.** Loopback is not a security
  boundary: any program running as you can reach a plain local server and read
  every role, note and status, or change them. The token is printed once in
  the URL, held in memory by the page, and dies with the process.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import signal
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..ai.llm import VAULT
from ..core.config import (
    CONTAINER_ENV,
    CONTAINER_MARKERS,
    SETTLED_STATUSES,
    STATUSES,
    WORK_MODES,
    Freshness,
)
from ..db.store import Store
from ..output.render import STATUS_COLOURS
from ..search import freshness, geo
from ..search.resume import SKILL_NAMES
from . import api as api_mod
from .live import Runner
from .session import Session, new_session

log = logging.getLogger("jobdork.web.serve")

DEFAULT_PORT = 8765
HOST = "127.0.0.1"

# Inside a container, 127.0.0.1 is the container's own loopback: a port
# published with `docker run -p` arrives on its network interface and finds
# nothing listening. The variable is set by the Dockerfile; the marker file
# is set by the runtime. Both are required, so exporting the variable on a
# bare host changes nothing. CONTAINER_ENV and CONTAINER_MARKERS live in
# core.config, which uses the same test to seed a config in a container.

# Opening the dashboard from another machine, such as a Mac reaching a NAS,
# takes naming the address it is opened by: "192.168.1.50" or "nas.local".
# Those names join the Host check (any port, since a NAS may publish the
# dashboard on a port of its own), and the server listens on every interface.
# The token is still required on every request. Nothing is allowed by default,
# and a wildcard is refused: the Host check is the defence against DNS
# rebinding, and "any host" would switch it off.
ALLOW_ENV = "JOBDORK_ALLOW_HOSTS"
_HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:\d{1,5})?$")


def allowed_extra_hosts() -> list[str]:
    """The addresses named in JOBDORK_ALLOW_HOSTS, lower-cased, checked."""
    names = []
    for raw in os.environ.get(ALLOW_ENV, "").split(","):
        name = raw.strip().lower()
        if not name:
            continue
        # Safe: "0.0.0.0" is refused here, never bound.
        if name in ("*", "0.0.0.0") or not _HOSTNAME.match(name):  # nosec B104
            log.warning("%s: %r is not an address; ignored", ALLOW_ENV, raw.strip())
            continue
        names.append(name)
    return names


def bind_address() -> str:
    """Where the socket listens. Not where the browser goes: that is HOST."""
    if (os.environ.get(CONTAINER_ENV) == "1"
            and any(Path(m).exists() for m in CONTAINER_MARKERS)):
        # Safe: deliberate, only inside a container.
        return "0.0.0.0"  # nosec B104
    if allowed_extra_hosts():
        # Safe: deliberate, only for addresses named in JOBDORK_ALLOW_HOSTS.
        return "0.0.0.0"  # nosec B104
    return HOST

PAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "dashboard.html"


class Server(ThreadingHTTPServer):
    """The standard threading server, quiet about browsers hanging up.

    A browser keeps a connection open for the next request and drops it when
    the page reloads, the tab closes or the laptop sleeps. The standard
    server prints a full traceback for each ("Connection reset by peer"),
    which reads as a crash and is not one. Anything else is still printed.
    """

    def handle_error(self, request, client_address) -> None:
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError,
                                          ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def _age(row, parts: list, fresh) -> dict:
    """How old the post is today, for its badge and the "posted within" filter."""
    part = next((p for p in parts if p.get("part") == "freshness"), None)
    a = freshness.now(part, row["posted_at"] or "", row["first_seen"] or "", fresh)
    return {"days": a.days, "tier": a.tier, "text": a.text(), "source": a.source}


def _row_to_dict(row, units: str, fresh=None) -> dict:
    try:
        flags = json.loads(row["flags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        flags = []

    if row["salary_stated"]:
        lo, hi, cur = row["salary_min"], row["salary_max"], row["salary_currency"] or ""
        if lo and hi:
            salary = f"{cur} {lo:,.0f}–{hi:,.0f}"
        elif hi or lo:
            salary = f"{cur} {(hi or lo):,.0f}"
        else:
            salary = "unconfirmed salary"
    else:
        salary = "unconfirmed salary"

    return {
        "uid": row["uid"],
        "score": None if row["score"] is None else round(row["score"]),
        "fit": None if row["fit"] is None else round(row["fit"]),
        "parts": (parts := api_mod.score_parts(row)),
        "age": _age(row, parts, fresh or Freshness()),
        "copies": row["copies"],
        **api_mod.ai_fields(row),
        "status": row["status"] or "new",
        "title": row["title"] or "",
        "company": row["company"] or "",
        "url": row["url"] or "",
        "note": row["note"] or "",
        "location": row["location_raw"] or "",
        # Stored in miles; shown in the reader's units, converted.
        "distance": geo.distance_label(row["distance_mi"], units),
        "work_mode": row["work_mode"] or "arrangement not stated",
        "salary": salary,
        "platform": row["platform"] or "",
        "advert_chars": len(row["description"] or ""),
        "first_seen": (row["first_seen"] or "")[:10],
        "flags": flags,
    }


def _anchor_place(cfg) -> dict:
    """The anchor as the picker shows it: country, region and city, if placed."""
    where = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    if not where.located:
        return {"located": False, "note": where.note}
    return {"located": True, "country": where.country, "city": where.city,
            "region": geo.region_at(where)}


def _config_payload(cfg) -> dict:
    """The settings the page may edit. Credentials are never included."""
    return {
        "titles_include": cfg.titles_include,
        "titles_exclude": cfg.titles_exclude,
        "anchor": cfg.locations.anchor,
        "anchor_place": _anchor_place(cfg),
        "radius": cfg.locations.radius,
        "units": cfg.locations.units,
        "countries": cfg.locations.countries,
        "work_modes": cfg.locations.work_modes,
        "salary_floor": cfg.salary.floor,
        "currency": cfg.salary.currency,
        "resume_path": cfg.resume_path,
        "companies": [{"name": c.name, "platform": c.platform, "token": c.token}
                      for c in cfg.sources.companies],
        "dealbreakers": [{"name": d.name, "pattern": d.pattern, "hard": d.hard}
                         for d in cfg.dealbreakers],
        "path": cfg.path,
    }


def make_handler(cfg_holder: dict, session: Session, runner: Runner):
    """`cfg_holder` is a one-key dict so a config edit can swap it in place."""
    # The file as loaded counts as seen: only a later change reloads it, so
    # the overrides given to `serve` on the command line hold until then.
    with contextlib.suppress(OSError, TypeError):
        cfg_holder.setdefault("mtime", Path(cfg_holder["cfg"].path).stat().st_mtime)
    allowed_hosts = {
        f"{session.host}:{session.port}",
        f"localhost:{session.port}",
        session.host,
        "localhost",
    }
    # Named with a port: that exact pair. Named alone: that host on any port.
    extra = allowed_extra_hosts()
    allowed_hosts |= {h for h in extra if ":" in h}
    any_port = {h for h in extra if ":" not in h}

    class Handler(BaseHTTPRequestHandler):
        server_version = "jobdork"
        protocol_version = "HTTP/1.1"

        # ── guards ─────────────────────────────────────────────────────────────

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").strip().lower()
            if host in allowed_hosts:
                return True
            name, _, port = host.partition(":")
            return name in any_port and (not port or port.isdigit())

        def _token_ok(self) -> bool:
            """Header first; the query is only for the initial page load.

            A URL is the only thing a person can be handed, so the token has to
            survive one trip through the address bar. After that the page holds
            it in memory and sends a header, which keeps it out of anything
            that logs URLs.
            """
            header = (self.headers.get("X-Jobdork-Token") or "").strip()
            if session.matches(header):
                return True
            if self.command == "GET":
                supplied = parse_qs(urlsplit(self.path).query).get("t", [""])[0]
                return session.matches(supplied)
            return False

        def _reject(self, code: int, message: str) -> None:
            payload = message.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(payload)

        def _send(self, code: int, body: bytes, content_type: str,
                  filename: str = "") -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            if filename:
                # Names come from resume_doc.filename: letters, digits, "_".
                self.send_header("Content-Disposition",
                                 f'inline; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            # The page loads nothing from anywhere. Saying so means a script
            # injected through a job title still cannot phone home.
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; connect-src 'self'; "
                # A PDF shown in the page is a blob the page made itself from
                # a document fetched with the token; nothing else may frame.
                "frame-src blob:; "
                "form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _guarded(self) -> bool:
            if not self._host_ok():
                self._reject(421, "unrecognised Host header")
                return False
            if not self._token_ok():
                self._reject(
                    401, "missing or wrong token. Open the URL jobdork "
                         "printed when it started")
                return False
            return True

        # ── routes ─────────────────────────────────────────────────────────────

        def _sync_config(self) -> None:
            """Pick up a config file changed behind this server's back.

            `Look and add` writes the file from a job, and a person may edit it
            by hand while the dashboard is open. Either way the next request
            sees the file as it is now, so a scan does not run on a list of
            boards the page no longer shows. A file that no longer loads is
            left alone and the last good config kept, with a warning.
            """
            from ..core import config as config_mod

            path = cfg_holder["cfg"].path
            if not path:
                return
            try:
                mtime = Path(path).stat().st_mtime
            except OSError:
                return
            if mtime == cfg_holder.get("mtime"):
                return
            try:
                cfg_holder["cfg"] = config_mod.load(path)
            except Exception as exc:
                log.warning("config changed on disk but does not load: %s", exc)
            cfg_holder["mtime"] = mtime

        def do_GET(self) -> None:
            if not self._guarded():
                return
            self._sync_config()
            path = urlsplit(self.path).path
            if path == "/":
                return self._page()
            if path == "/api/roles":
                return self._roles()
            if path == "/api/config":
                return self._json(200, _config_payload(cfg_holder["cfg"]))
            if path.startswith("/api/places/"):
                return self._places(path.rsplit("/", 1)[1])
            if path == "/api/state":
                ai = api_mod.llm_state(cfg_holder["cfg"])
                return self._json(200, {
                    "busy": runner.busy,
                    "job": runner.current,
                    "last_summary": runner.last_summary,
                    "claude": bool(__import__("shutil").which("claude")),
                    "ai": ai["label"],
                    "ai_problem": ai["problem"],
                })
            if path == "/api/events":
                return self._events()
            if path == "/api/llm":
                return self._json(200, api_mod.llm_state(cfg_holder["cfg"]))
            if path == "/api/activity":
                raw = parse_qs(urlsplit(self.path).query).get("id", ["0"])[0]
                return self._wrap(api_mod.activity_report, cfg_holder["cfg"],
                                  int(raw) if raw.isdigit() else 0)
            if path == "/api/llm/models":
                query = parse_qs(urlsplit(self.path).query)
                return self._wrap(api_mod.llm_models, cfg_holder["cfg"],
                                  query.get("provider", [""])[0],
                                  query.get("url", [""])[0])
            if path == "/api/sources":
                return self._wrap(api_mod.sources_report, cfg_holder["cfg"])
            if path == "/api/role":
                uid = parse_qs(urlsplit(self.path).query).get("uid", [""])[0]
                return self._wrap(api_mod.role_detail, cfg_holder["cfg"], uid)
            if path == "/api/resume/view":
                return self._wrap(api_mod.resume_view, cfg_holder["cfg"])
            if path == "/api/resume/file":
                try:
                    body, kind, _name = api_mod.resume_file(cfg_holder["cfg"])
                except api_mod.ApiError as exc:
                    return self._reject(exc.status, str(exc))
                return self._send(200, body, kind)
            if path == "/api/letters":
                return self._wrap(api_mod.list_letters, cfg_holder["cfg"])
            if path == "/api/projects":
                return self._wrap(api_mod.list_projects, cfg_holder["cfg"])
            if path == "/api/tools":
                uid = parse_qs(urlsplit(self.path).query).get("uid", [""])[0]
                return self._wrap(api_mod.latest_tools, cfg_holder["cfg"], uid)
            if path == "/api/artifact":
                raw = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                if not raw.isdigit():
                    return self._reject(400, "not a document id")
                return self._wrap(api_mod.artifact_text, cfg_holder["cfg"],
                                  int(raw))
            if path == "/api/artifact/pdf":
                raw = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                if not raw.isdigit():
                    return self._reject(400, "not a document id")
                try:
                    body, name = api_mod.artifact_pdf(cfg_holder["cfg"], int(raw))
                except api_mod.ApiError as exc:
                    return self._reject(exc.status, str(exc))
                return self._send(200, body, "application/pdf", filename=name)
            if path == "/api/ai_output":
                raw = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                if not raw.isdigit():
                    return self._reject(400, "not an output id")
                return self._wrap(api_mod.ai_output, cfg_holder["cfg"], int(raw))
            if path == "/api/metrics":
                raw = parse_qs(urlsplit(self.path).query).get("days", ["30"])[0]
                return self._wrap(api_mod.metrics, cfg_holder["cfg"], raw)
            if path == "/api/review/latest":
                return self._wrap(api_mod.latest_review, cfg_holder["cfg"])
            return self._reject(404, "no such path")

        def do_POST(self) -> None:
            if not self._guarded():
                return
            self._sync_config()
            path = urlsplit(self.path).path
            if path == "/api/action":
                return self._action()
            if path == "/api/scan":
                return self._scan()
            if path == "/api/scan/fresh/preview":
                return self._wrap(api_mod.fresh_preview, cfg_holder["cfg"])
            if path == "/api/scan/fresh":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                try:
                    work = api_mod.fresh_scan_job(cfg_holder["cfg"], form.get("expect"))
                except api_mod.ApiError as exc:
                    return self._reject(exc.status, str(exc))
                started, why = runner.start("fresh scan", work)
                if not started:
                    return self._reject(409, why)
                return self._json(202, {"started": True, "job": "fresh scan"})
            if path == "/api/config":
                return self._save_config()
            if path == "/api/resume":
                return self._resume()
            if path == "/api/resume/delete":
                try:
                    gone = api_mod.delete_resume(cfg_holder["cfg"])
                    self._write_config({"resume_path": ""})
                except api_mod.ApiError as exc:
                    return self._reject(exc.status, str(exc))
                except Exception as exc:
                    return self._reject(400, f"not removed: {exc}")
                return self._json(200, gone)
            if path == "/api/projects/save":
                form = self._body(limit=24 * 1024)
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.save_project, cfg_holder["cfg"], form)
            if path == "/api/projects/delete":
                raw = str((self._body() or {}).get("id") or "")
                if not raw.isdigit():
                    return self._reject(400, "not a project id")
                return self._wrap(api_mod.delete_project, cfg_holder["cfg"], int(raw))
            if path == "/api/letters/delete":
                form = self._body()
                raw = str((form or {}).get("id") or "")
                if not raw.isdigit():
                    return self._reject(400, "not a cover letter id")
                return self._wrap(api_mod.delete_letter, cfg_holder["cfg"], int(raw))
            if path == "/api/add":
                return self._add()
            if path == "/api/advert":
                return self._advert()
            if path.startswith("/api/llm"):
                return self._llm(path)
            if path in ("/api/cleanup/preview", "/api/cleanup"):
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                cfg = cfg_holder["cfg"]
                days, statuses = form.get("days") or 0, form.get("statuses") or ""
                if path == "/api/cleanup/preview":
                    return self._wrap(api_mod.cleanup_preview, cfg, days, statuses)
                if runner.busy:
                    return self._reject(409, f"{runner.current} is running; "
                                        "delete when it has finished")
                try:
                    expect = int(form.get("expect"))
                except (TypeError, ValueError):
                    return self._reject(400, "preview first")
                return self._wrap(api_mod.cleanup_run, cfg, days, statuses, expect)
            if path == "/api/feedback":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.feedback, cfg_holder["cfg"],
                                  form.get("output_id"), form.get("value"))
            if path in ("/api/enrich", "/api/rescreen", "/api/discover",
                        "/api/generate", "/api/digest", "/api/judge",
                        "/api/check", "/api/letter", "/api/review", "/api/tool",
                        "/api/tailor"):
                return self._job(path.rsplit("/", 1)[1])
            return self._reject(404, "no such path")

        # ── handlers ───────────────────────────────────────────────────────────

        def _wrap(self, fn, *args) -> None:
            """Run an api function and turn its refusal into a status code."""
            try:
                self._json(200, fn(*args))
            except api_mod.ApiError as exc:
                self._reject(exc.status, str(exc))

        def _resume(self) -> None:
            """Raw bytes with the name in a header — no multipart parser.

            The browser sends the file as the body and its name in
            X-Filename. That name is used only to read an extension; the file
            is written where this code decides.
            """
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._reject(400, "bad Content-Length")
            if length <= 0 or length > api_mod.MAX_RESUME_BYTES:
                return self._reject(400, "empty or oversized upload")
            payload = self.rfile.read(length)
            filename = (self.headers.get("X-Filename") or "").strip()

            cfg = cfg_holder["cfg"]
            try:
                saved = api_mod.save_resume(cfg, filename, payload)
            except api_mod.ApiError as exc:
                return self._reject(exc.status, str(exc))

            # Point the config at it so a scan and a draft both find it.
            try:
                self._write_config({"resume_path": saved["path"]})
            except Exception as exc:
                return self._reject(400, f"saved the file but not the path: {exc}")
            self._json(200, saved)

        def _add(self) -> None:
            form = self._body()
            if form is None:
                return self._reject(400, "bad request body")
            self._wrap(api_mod.add_by_url, cfg_holder["cfg"],
                       str(form.get("url") or ""), str(form.get("token") or ""),
                       str(form.get("company") or ""))

        def _advert(self) -> None:
            # Sized for the advert, not the 8 KB an action gets: a pasted
            # advert is routinely longer than that. UTF-8 can be 4 bytes a
            # character, and form encoding up to 3 per byte.
            form = self._body(limit=api_mod.MAX_ADVERT_CHARS * 12)
            if form is None:
                return self._reject(400, "bad request body")
            self._wrap(api_mod.set_advert, cfg_holder["cfg"],
                       str(form.get("uid") or ""), str(form.get("text") or ""))

        def _llm(self, path: str) -> None:
            """AI settings. A key goes into memory and is never sent back."""
            form = self._body(limit=4 * 1024)
            if form is None and path != "/api/llm/test":
                return self._reject(400, "bad request body")
            form = form or {}
            cfg = cfg_holder["cfg"]
            if path == "/api/llm/key":
                return self._wrap(api_mod.llm_key, str(form.get("provider") or ""),
                                  str(form.get("key") or ""))
            if path == "/api/llm/forget":
                return self._wrap(api_mod.llm_forget,
                                  str(form.get("provider") or ""))
            if path == "/api/llm/test":
                return self._wrap(api_mod.llm_test, cfg)
            if path == "/api/llm":
                try:
                    fresh = self._write_config({"llm": form})
                except Exception as exc:
                    return self._reject(400, f"not saved: {exc}")
                return self._json(200, api_mod.llm_state(fresh))
            return self._reject(404, "no such path")

        def _job(self, which: str) -> None:
            """Start one of the long-running commands on the background runner."""
            form = self._body(limit=32 * 1024) or {}
            cfg = cfg_holder["cfg"]
            try:
                if which == "enrich":
                    name, work = "enrich", api_mod.enrich_job(
                        cfg, int(form.get("limit") or 0))
                elif which == "rescreen":
                    name, work = "rescreen", api_mod.rescreen_job(
                        cfg, str(form.get("remove") or "") in ("1", "true", "yes"))
                elif which == "discover":
                    employer = str(form.get("employer") or "").strip()
                    if not employer:
                        return self._reject(400, "give an employer's website")
                    name = f"discover {employer}"
                    work = api_mod.discover_job(
                        cfg, employer,
                        add=str(form.get("add") or "") in ("1", "true", "yes"),
                        name=str(form.get("name") or ""))
                elif which in ("judge", "check"):
                    uid = str(form.get("uid") or "")
                    force = str(form.get("force") or "") in ("1", "true", "yes")
                    limit = int(form.get("limit") or 0)
                    maker = api_mod.judge_job if which == "judge" else api_mod.check_job
                    name = {"judge": "AI judging", "check": "checking postings"}[which]
                    work = maker(cfg, limit=limit, uid=uid, force=force)
                elif which == "generate":
                    kind = str(form.get("kind") or "screen")
                    if kind not in ("screen", "cv", "cover_letter"):
                        return self._reject(400, "unknown document kind")
                    name = f"{kind.replace('_', ' ')}"
                    work = api_mod.generate_job(
                        cfg, str(form.get("uid") or ""), kind)
                elif which == "letter":
                    name = "cover letter (AI)"
                    work = api_mod.letter_job(cfg, str(form.get("uid") or ""))
                elif which == "tailor":
                    name = "tailored resume (AI)"
                    work = api_mod.tailor_job(cfg, str(form.get("uid") or ""))
                elif which == "review":
                    name = "resume review"
                    work = api_mod.review_job(cfg, str(form.get("uid") or ""))
                elif which == "tool":
                    kind = str(form.get("kind") or "")
                    name = f"AI tool: {kind.replace('_', ' ')}"
                    work = api_mod.tool_job(cfg, str(form.get("uid") or ""), kind,
                                            str(form.get("text") or ""))
                else:
                    email = str(form.get("email") or "").strip()
                    if not email:
                        return self._reject(400, "give a recipient")
                    name = "digest"
                    work = api_mod.digest_job(
                        cfg, email,
                        new_only=str(form.get("all") or "") not in ("1", "true"),
                        attach_csv=str(form.get("csv") or "") in ("1", "true"))
            except api_mod.ApiError as exc:
                return self._reject(exc.status, str(exc))

            started, why = runner.start(name, work)
            if not started:
                return self._reject(409, why)
            self._json(202, {"started": True, "job": name})

        def _page(self) -> None:
            html = PAGE_PATH.read_text(encoding="utf-8")
            html = (html
                    .replace("__STATUSES__", json.dumps(list(STATUSES)))
                    .replace("__COLOURS__", json.dumps(STATUS_COLOURS))
                    .replace("__WORK_MODES__", json.dumps(list(WORK_MODES)))
                    .replace("__SKILL_NAMES__", json.dumps(SKILL_NAMES)))
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

        def _roles(self) -> None:
            query = parse_qs(urlsplit(self.path).query)
            scope = (query.get("scope") or ["open"])[0]
            status = (query.get("status") or [""])[0]
            if status and status not in STATUSES:
                return self._reject(400, "unknown status")

            cfg = cfg_holder["cfg"]
            with Store(cfg.db_path) as store:
                rows = store.list_roles(
                    status=status,
                    new_only=(scope == "new"),
                    include_settled=(scope == "all"),
                )
                counts = store.status_counts()
                units = cfg.locations.units or "mi"
                payload = [_row_to_dict(row, units, cfg.freshness) for row in rows]

            # Past freshness.ghost_days a post is dropped at screening, but one
            # stored before it aged stays in the database until a rescreen
            # --remove. Not acted on, it is left out of the list here, and
            # counted; a post you applied to is never hidden for its age.
            ghosts = 0
            if scope != "all":
                kept = [p for p in payload if not (
                    p["age"]["tier"] == "ghost" and p["status"] in ("new", "viewed"))]
                ghosts = len(payload) - len(kept)
                payload = kept
            settled = sum(counts.get(s, 0) for s in SETTLED_STATUSES)
            self._json(200, {"roles": payload, "counts": counts,
                             "settled": settled, "ghosts": ghosts})

        def _events(self) -> None:
            """Server-sent events. Held open for the life of the page."""
            channel = runner.broker.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    try:
                        event = channel.get(timeout=20)
                        self.wfile.write(event.encode())
                    except Exception:
                        # Nothing to send: a comment keeps the connection and
                        # any proxy in between from deciding it has died.
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass                                        # the tab closed
            finally:
                runner.broker.unsubscribe(channel)

        def _body(self, limit: int = 8 * 1024) -> dict | None:
            """Read and parse a request body, refusing anything oversized.

            The limit is per endpoint. A status change is a uid, a word and a
            note; a config save carries every title and dealbreaker. Letting
            the config's limit apply to actions would mean accepting a
            quarter-megabyte note.
            """
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if length <= 0 or length > limit:
                return None
            raw = self.rfile.read(length).decode("utf-8", "replace")
            if (self.headers.get("Content-Type") or "").startswith(
                    "application/json"):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    return None
                return parsed if isinstance(parsed, dict) else None
            return {k: v[0] for k, v in parse_qs(raw).items()}

        def _action(self) -> None:
            form = self._body()
            if form is None:
                return self._reject(400, "bad request body")
            uid = str(form.get("uid") or "").strip()
            status = str(form.get("status") or "").strip()
            note = str(form.get("note") or "").strip()

            # A uid is 12 hex characters, and it is the only value from the
            # page that reaches the database.
            if not re.fullmatch(r"[0-9a-f]{12}", uid):
                return self._reject(400, "not a job post id")
            if status and status not in STATUSES:
                return self._reject(400, "unknown status")
            if not status and not note:
                return self._reject(400, "nothing to record")

            with Store(cfg_holder["cfg"].db_path) as store:
                current = store.get(uid)
                if current is None:
                    return self._reject(404, "no such job post")
                store.set_status(uid, status or (current["status"] or "new"), note)
            self._json(200, {"ok": True, "uid": uid})

        def _scan(self) -> None:
            # api.scan_job, as every other run: this had its own copy, which
            # skipped judging after the scan and every format but html/json.
            started, why = runner.start("scan", api_mod.scan_job(cfg_holder["cfg"]))
            if not started:
                return self._reject(409, why)
            self._json(202, {"started": True})

        def _places(self, what: str) -> None:
            """Country, region and city lists for the Where you are picker."""
            q = parse_qs(urlsplit(self.path).query)
            arg = lambda k: (q.get(k, [""])[0] or "")[:80]    # noqa: E731
            if what == "countries":
                # A currency is offered only where a salary floor can use it.
                from ..core.config import CURRENCIES
                return self._json(200, {"countries": [
                    {**c, "currency": c["currency"] if c["currency"] in CURRENCIES else ""}
                    for c in geo.picker_countries()], "currencies": list(CURRENCIES)})
            if what == "regions":
                return self._json(200, geo.picker_regions(arg("country")))
            if what == "cities":
                return self._json(200, {"cities": geo.picker_cities(
                    arg("country"), arg("region"), arg("q"))})
            return self._reject(404, "no such path")

        def _save_config(self) -> None:
            """Write config.yaml from the page, validating before replacing it.

            The file is re-read through the normal loader afterwards, so an
            edit that would not survive `jobdork scan` cannot be saved here
            either. Credentials are not in the payload and are not touched.
            """

            payload = self._body(limit=256 * 1024)
            if payload is None:
                return self._reject(400, "bad request body")

            try:
                fresh = self._write_config(payload)
            except Exception as exc:
                return self._reject(400, f"not saved: {exc}")
            self._json(200, _config_payload(fresh))

        def _write_config(self, payload: dict):
            """Write, then re-read through the normal loader.

            An edit that would not survive `jobdork scan` cannot be saved here
            either, and a rejected edit leaves the file exactly as it was.
            """
            from ..core import config as config_mod

            cfg = cfg_holder["cfg"]
            if not cfg.path:
                raise ValueError("this run has no config file to write to")
            path = Path(cfg.path)
            original = path.read_text(encoding="utf-8")
            try:
                path.write_text(_rewrite_config(original, payload),
                                encoding="utf-8")
                fresh = config_mod.load(str(path))
            except Exception:
                path.write_text(original, encoding="utf-8")   # put it back
                raise
            cfg_holder["cfg"] = fresh
            cfg_holder["mtime"] = path.stat().st_mtime
            return fresh

        def log_message(self, fmt: str, *args) -> None:
            log.debug("%s - %s", self.address_string(), fmt % args)

    return Handler


def _rewrite_config(original: str, payload: dict) -> str:
    """Replace the editable settings in a config file, keeping its comments.

    Rewritten as text rather than dumped through YAML, because a dump strips
    every comment out of a file that is mostly comments explaining what the
    settings mean.
    """
    import yaml

    data = yaml.safe_load(original) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml is not a mapping")

    titles = data.setdefault("titles", {})
    if "titles_include" in payload:
        titles["include"] = [str(t).strip() for t in payload["titles_include"]
                             if str(t).strip()]
    if "titles_exclude" in payload:
        titles["exclude"] = [str(t).strip() for t in payload["titles_exclude"]
                             if str(t).strip()]

    locations = data.setdefault("locations", {})
    if "anchor_pick" in payload:
        # The picker's three choices, written as text resolve() reads back.
        # A city not in the gazetteer is refused rather than saved unplaced,
        # which would quietly turn the radius off.
        pick = payload["anchor_pick"] or {}
        city = str(pick.get("city") or "").strip()
        country = str(pick.get("country") or "").strip().upper()
        region = str(pick.get("region") or "").strip().upper()
        if not city or not country:
            raise ValueError("choose a country and a city")
        anchor = geo.picker_anchor(city, region, country)
        where = geo.resolve_anchor(anchor, (country,))
        if (not where.located or where.country != country
                or (region and geo.region_at(where) != region)):
            raise ValueError(f"{city!r} is not in the place list for that "
                             "country and region; choose one from the suggestions")
        payload = {**payload, "anchor": anchor}
    for key, field in (("anchor", "anchor"), ("radius", "radius"),
                       ("units", "units"), ("countries", "countries"),
                       ("work_modes", "work_modes")):
        if key in payload:
            locations[field] = payload[key]

    salary = data.setdefault("salary", {})
    if "salary_floor" in payload:
        floor = payload["salary_floor"]
        salary["floor"] = None if floor in (None, "", "null") else float(floor)
    if "currency" in payload:
        salary["currency"] = str(payload["currency"]).upper()

    # Whole lists, as the page's tables hold them after an add or a delete.
    # Named fields only; the loader then refuses a broken pattern, a missing
    # token or an unknown board type, and the file is put back.
    if "dealbreakers" in payload:
        data["dealbreakers"] = [
            {"name": str(d.get("name") or "").strip(),
             "pattern": str(d.get("pattern") or ""),
             "hard": str(d.get("hard")).lower() in ("1", "true", "yes", "on")}
            for d in payload["dealbreakers"] or [] if isinstance(d, dict)]
    if "companies" in payload:
        data.setdefault("sources", {})["companies"] = [
            {"name": str(c.get("name") or "").strip(),
             "platform": str(c.get("platform") or "").strip().lower(),
             "token": str(c.get("token") or "").strip()}
            for c in payload["companies"] or [] if isinstance(c, dict)]

    if "resume_path" in payload:
        data.setdefault("resume", {})["path"] = payload["resume_path"]

    if "llm" in payload:
        given = payload["llm"] or {}
        section = data.setdefault("llm", {})
        # Named fields only: whatever else the page sends, a key included,
        # never reaches the file.
        for key, cast in (("provider", str), ("model", str),
                          ("ollama_url", str), ("judge_top", int)):
            if key in given:
                section[key] = cast(given[key]).strip() if cast is str \
                    else cast(given[key])
        for key in ("judge_on_scan", "read_pages", "guard"):
            if key in given:
                section[key] = str(given[key]).lower() in ("1", "true", "yes", "on")

    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                            default_flow_style=False)
    header = (
        "# Written by the jobdork dashboard.\n"
        "# Comments from a hand-edited config are not preserved through a\n"
        "# save here; keep annotations in config.local.yaml if you want them.\n"
        "# API keys are never written to this file; they live in .env.\n\n"
    )
    return header + dumped


def serve(cfg, port: int = DEFAULT_PORT, open_browser: bool = True,
          token: str = "") -> int:
    """Run until Ctrl-C. Returns an exit code."""
    # The session keeps HOST either way: it is the address in the printed URL
    # and the one the Host check accepts, and in a container the browser
    # still reaches it as 127.0.0.1 through the published port.
    bind = bind_address()
    session = new_session(HOST, preferred_port=port, token=token)
    cfg_holder = {"cfg": cfg}
    runner = Runner(db_path=lambda: cfg_holder["cfg"].db_path)
    # In a container the resume and documents live in a temporary folder
    # that does not outlive a run: emptied now, and again on the way out.
    cleared = api_mod.forget_temporary(cfg)
    if cleared:
        print(f"emptied the temporary folder: {cleared} file(s) from the last run")

    try:
        server = Server(
            (bind, session.port),
            make_handler(cfg_holder, session, runner))
    except OSError as exc:
        print(f"cannot listen on {bind}:{session.port}: {exc}")
        return 1

    if session.port != port:
        print(f"port {port} was busy; using {session.port}")
    print(f"jobdork dashboard: {session.url}")
    extra = allowed_extra_hosts()
    if extra:
        # A port named with the host is how that address reaches it (a NAS
        # may publish 8765 as another port); a bare name uses this one.
        for name in extra:
            where = name if ":" in name else f"{name}:{session.port}"
            print(f"  also at: http://{where}/?t={session.token}")
        print(f"Open to {', '.join(extra)} on your network ({ALLOW_ENV}); "
              "the token is still required. Ctrl-C to stop.")
    elif bind != HOST:
        print(f"In a container, listening on {bind}. Publish it to the host's "
              f"loopback only: -p 127.0.0.1:{session.port}:{session.port}, "
              f"or set {ALLOW_ENV} to open it from another machine.")
    else:
        print("Local only, token expires with this process, Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(session.url)).start()

    stop = threading.Event()
    threading.Thread(target=_forget_keys_when_unwatched,
                     args=(runner, stop), daemon=True).start()
    # A plain `kill` must burn keys too, not only Ctrl-C.
    with contextlib.suppress(ValueError):      # only the main thread may
        signal.signal(signal.SIGTERM, _interrupt)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        stop.set()
        burned = VAULT.wipe()
        if burned:
            print(f"forgot API keys: {', '.join(burned)}")
        with contextlib.suppress(Exception):
            cleared = api_mod.forget_temporary(cfg_holder["cfg"])
            if cleared:
                print(f"emptied the temporary folder: {cleared} file(s)")
        server.server_close()
    return 0


def _interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


# Long enough to survive a page reload, short enough that a closed tab does
# not leave a paid key sitting in a server nobody is looking at.
UNWATCHED_SECONDS = 60


def _forget_keys_when_unwatched(runner: Runner, stop: threading.Event) -> None:
    """Burn held keys once no dashboard tab has been open for a minute.

    A tab holds an event stream open for its whole life, so no streams means
    no tabs. A job still running (a scan judging with a paid model) keeps its
    key until it finishes.
    """
    alone_since = None
    while not stop.wait(5):
        if not VAULT.held() or runner.broker.listeners or runner.busy:
            alone_since = None
            continue
        alone_since = alone_since or time.monotonic()
        if time.monotonic() - alone_since >= UNWATCHED_SECONDS:
            burned = VAULT.wipe()
            print(f"no dashboard open for {UNWATCHED_SECONDS}s, so "
                  f"forgot API keys: {', '.join(burned)}")
            alone_since = None
