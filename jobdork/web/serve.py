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
from ..core import feedback as feedback_mod
from ..core import notify as notify_mod
from ..core import updates as updates_mod
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
from ..search import freshness, geo, ownboard
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
# core.config, which uses the same test to pick where a new config goes.

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
    which reads as a crash and is not one. Anything else is still printed,
    and logged, so it is under Warnings and errors where it can be reported:
    a request that failed was otherwise only in the terminal.
    """

    def handle_error(self, request, client_address) -> None:
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError,
                                          ConnectionAbortedError, TimeoutError)):
            return
        log.error("a request to the dashboard failed", exc_info=True)
        super().handle_error(request, client_address)


def _age(row, parts: list, fresh) -> dict:
    """How old the post is today, for its badge and the "posted within" filter."""
    part = next((p for p in parts if p.get("part") == "freshness"), None)
    a = freshness.now(part, row["posted_at"] or "", row["first_seen"] or "", fresh)
    return {"days": a.days, "tier": a.tier, "text": a.text(), "source": a.source}


def _pay(row) -> dict:
    """The top of a stated pay range, for "pay at least" on Job posts."""
    stated = bool(row["salary_stated"])
    top = row["salary_max"] if row["salary_max"] is not None else row["salary_min"]
    return {"pay_top": top if stated else None,
            "pay_currency": (row["salary_currency"] or "") if stated else ""}


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
        # Numbers for the page's distance and pay filters.
        "dist": None if row["distance_mi"] is None
        else round(geo.from_miles(row["distance_mi"], units), 1),
        **_pay(row),
        "work_mode": row["work_mode"] or "arrangement not stated",
        "salary": salary,
        "platform": row["platform"] or "",
        "advert_chars": len(row["description"] or ""),
        "first_seen": (row["first_seen"] or "")[:10],
        "flags": flags,
    }


def _places(cfg) -> dict:
    """Where you would work, as the picker shows it: the country, each region
    by code and name, each city with whether it could be placed."""
    country = cfg.locations.country
    cities = []
    for text in cfg.locations.cities:
        where = geo.resolve_anchor(text, cfg.country_prefs())
        country = country or where.country
        cities.append({"text": text, "located": where.located, "note": where.note,
                       "city": where.city, "region": geo.region_at(where),
                       "country": where.country})
    return {"country": country or (cfg.locations.countries or [""])[0],
            "regions": [{"code": r, "name": geo.region_label(country, r)}
                        for r in cfg.locations.regions],
            "cities": cities}


def _screen_key(cfg) -> str:
    """Everything screening reads, as one comparable string."""
    from dataclasses import asdict

    return json.dumps({
        "titles": [cfg.titles_include, cfg.titles_exclude],
        "dealbreakers": [(d.name, d.pattern, d.hard, d.words) for d in cfg.dealbreakers],
        "locations": asdict(cfg.locations), "salary": asdict(cfg.salary),
        "screening": asdict(cfg.screening), "ghost_days": cfg.freshness.ghost_days,
    }, sort_keys=True, default=str)


def change_words(old, fresh) -> str:
    """What a save changed, in a few words, for the queue on the Dashboard:
    "Search: added Nurse Practitioner"."""
    def diff(a, b) -> list[str]:
        have = {x.casefold() for x in a}
        return [x for x in b if x.casefold() not in have]

    def few(items) -> str:
        return ", ".join(items[:3]) + (f" and {len(items) - 3} more" if len(items) > 3 else "")

    said = []
    for label, a, b in (
            ("Search", old.titles_include, fresh.titles_include),
            ("Never show", old.titles_exclude, fresh.titles_exclude),
            ("Countries", old.locations.countries, fresh.locations.countries),
            ("Dealbreakers", [d.name for d in old.dealbreakers], [d.name for d in fresh.dealbreakers])):
        added, gone = diff(a, b), diff(b, a)
        if added or gone:
            said.append(f"{label}: " + "; ".join(
                ([f"added {few(added)}"] if added else []) + ([f"removed {few(gone)}"] if gone else [])))
    if old.locations != fresh.locations and not any(s.startswith("Countries") for s in said):
        said.append("Location or work arrangement changed")
    if old.salary != fresh.salary:
        said.append("Pay changed")
    return "; ".join(said) or "Search settings changed"


def search_changes(old, fresh) -> tuple[bool, bool]:
    """(widened, rescreen) for a config save.

    Widened: a job title, a country or an industry added, or a new place to
    search from. Posts for those were never fetched, so only a scan finds
    them. Rescreen: anything screening reads changed, so the posts already
    stored may now pass or fail.
    """
    from ..search import directory

    def added(a, b) -> bool:
        return bool({x.casefold() for x in b} - {x.casefold() for x in a})
    # Built-in boards newly read: switched on, an industry added or the
    # industries cleared (every one), a board no longer skipped.
    boards = ({b.key for b in directory.select(fresh)}
              - {b.key for b in directory.select(old)})
    widened = (added(old.titles_include, fresh.titles_include)
               or added(old.locations.countries, fresh.locations.countries)
               or bool(boards)
               or added(old.locations.cities, fresh.locations.cities)
               or added(old.locations.regions, fresh.locations.regions)
               or old.locations.country != fresh.locations.country)
    return widened, _screen_key(old) != _screen_key(fresh)


def _config_payload(cfg) -> dict:
    """The settings the page may edit. Credentials are never included."""
    return {
        "titles_include": cfg.titles_include,
        "titles_exclude": cfg.titles_exclude,
        "places": _places(cfg),
        "radius": cfg.locations.radius,
        "units": cfg.locations.units,
        "countries": cfg.locations.countries,
        "work_modes": cfg.locations.work_modes,
        "salary_floor": cfg.salary.floor,
        "currency": cfg.salary.currency,
        "show_days": cfg.freshness.show_days,
        "older_days": cfg.freshness.older_days,
        "resume_path": cfg.resume_path,
        # Where it is on disk, in full: the setting may be "data/resume.pdf",
        # relative to the folder jobdork started in, which says little.
        "resume_file": str(Path(cfg.resume_path).expanduser().resolve()) if cfg.resume_path else "",
        "credentials": cfg.credentials,
        "companies": [{"name": c.name, "platform": c.platform, "token": c.token}
                      for c in cfg.sources.companies],
        "dealbreakers": [{"name": d.name, "words": d.words, "pattern": d.pattern,
                          "hard": d.hard}
                         for d in cfg.dealbreakers],
        "dealbreaker_suggestions": _deal_suggestions(),
        "update_check": cfg.update_check,
        "remember_keys": cfg.remember_keys,
        "notifications": {"enabled": cfg.notifications.enabled,
                          "sound": cfg.notifications.sound,
                          # Whether this system can show one (not Docker).
                          "native": notify_mod.native()},
        # The environment wins over the setting; the page says so.
        "update_check_env_off": updates_mod.off(),
        "path": cfg.path,
    }


def _setup_state(cfg) -> dict | None:
    """First-run progress for the page, or None once set up."""
    from ..ai.llm import OLLAMA_FROM_DOCKER, Settings
    from ..core import setup
    from ..core.config import in_container
    if not cfg.setup_step:
        return None
    return {"step": cfg.setup_step, "path": cfg.path, "in_container": in_container(),
            "ollama_from_docker": OLLAMA_FROM_DOCKER if in_container() else "",
            "ai_ready": not Settings.from_config(cfg).problem(),
            "steps": [{"name": n, "title": t} for n, t in setup.STEPS]}


def _unkept(cfg) -> str:
    from ..core import storage
    return storage.unkept_data_dir(cfg)


def _deal_suggestions() -> list[dict]:
    from ..search import dealbreakers
    return dealbreakers.suggestions()


def make_handler(cfg_holder: dict, session: Session, runner: Runner, desk=None):
    """`cfg_holder` is a one-key dict so a config edit can swap it in place.
    `desk` is the desktop app's Bridge (web/app.py), or None in a browser."""
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
                # The tab's icon is a data: URI inside the page itself, so
                # images still come from nowhere on the network.
                "img-src data:; "
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
            # A browser asks for /favicon.ico by itself, without the token,
            # and the 401 it got sat in the network log looking like the
            # page's own failure. Nothing to give, and nothing given away.
            if urlsplit(self.path).path == "/favicon.ico" and self._host_ok():
                self.send_response(204)
                self.end_headers()
                return
            if not self._guarded():
                return
            self._sync_config()
            path = urlsplit(self.path).path
            if path == "/":
                return self._page()
            if path == "/api/roles":
                return self._roles()
            if path == "/api/dropped":
                return self._wrap(api_mod.dropped_list, cfg_holder["cfg"])
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
                    "first_scan": api_mod.FIRST_SCAN,
                    # First in, first out, each with what started it.
                    "waiting": runner.waiting(),
                    "claude": bool(__import__("shutil").which("claude")),
                    "ai": ai["label"],
                    "ai_problem": ai["problem"],
                    "unkept_data": _unkept(cfg_holder["cfg"]),
                    "notifications": {
                        "enabled": cfg_holder["cfg"].notifications.enabled,
                        "sound": cfg_holder["cfg"].notifications.sound,
                        "native": notify_mod.native()},
                    "setup": _setup_state(cfg_holder["cfg"]),
                    "keys": api_mod.keys_state(cfg_holder["cfg"]),
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
                                  query.get("url", [""])[0],
                                  query.get("key", [""])[0] == "1")
            if path == "/api/sources":
                return self._wrap(api_mod.sources_report, cfg_holder["cfg"])
            if path == "/api/directory":
                return self._wrap(api_mod.directory_boards, cfg_holder["cfg"])
            if path == "/api/role":
                uid = parse_qs(urlsplit(self.path).query).get("uid", [""])[0]
                return self._wrap(api_mod.role_detail, cfg_holder["cfg"], uid)
            if path == "/api/resume/view":
                return self._wrap(api_mod.resume_view, cfg_holder["cfg"])
            if path == "/api/resume/check":
                return self._wrap(api_mod.resume_check, cfg_holder["cfg"])
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
            if path == "/api/education":
                return self._wrap(api_mod.list_education, cfg_holder["cfg"])
            if path == "/api/tools":
                uid = parse_qs(urlsplit(self.path).query).get("uid", [""])[0]
                return self._wrap(api_mod.latest_tools, cfg_holder["cfg"], uid)
            if path == "/api/artifact":
                raw = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                if not raw.isdigit():
                    return self._reject(400, "not a document id")
                return self._wrap(api_mod.artifact_text, cfg_holder["cfg"],
                                  int(raw))
            if path in ("/api/artifact/pdf", "/api/artifact/docx"):
                raw = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                if not raw.isdigit():
                    return self._reject(400, "not a document id")
                word = path.endswith("/docx")
                try:
                    body, name = (api_mod.artifact_docx if word else api_mod.artifact_pdf)(
                        cfg_holder["cfg"], int(raw))
                except api_mod.ApiError as exc:
                    return self._reject(exc.status, str(exc))
                return self._send(200, body, api_mod.RESUME_TYPES[".docx" if word else ".pdf"],
                                  filename=name)
            if path == "/api/ai_output":
                raw = parse_qs(urlsplit(self.path).query).get("id", [""])[0]
                if not raw.isdigit():
                    return self._reject(400, "not an output id")
                return self._wrap(api_mod.ai_output, cfg_holder["cfg"], int(raw))
            if path == "/api/metrics":
                raw = parse_qs(urlsplit(self.path).query).get("days", ["30"])[0]
                return self._wrap(api_mod.metrics, cfg_holder["cfg"], raw)
            if path == "/api/setup/sources":
                return self._wrap(api_mod.setup_sources, cfg_holder["cfg"])
            if path == "/api/setup/suggest/progress":
                return self._json(200, api_mod.SUGGEST_PROGRESS)
            if path == "/api/setup/choices":
                return self._wrap(api_mod.setup_choices, cfg_holder["cfg"])
            if path == "/api/review/latest":
                return self._wrap(api_mod.latest_review, cfg_holder["cfg"])
            if path == "/api/schedule":
                return self._wrap(api_mod.schedule_state, cfg_holder["cfg"])
            if path == "/api/folders":
                return self._wrap(api_mod.folders, cfg_holder["cfg"])
            if path == "/api/version":
                return self._wrap(api_mod.newer_version, cfg_holder["cfg"])
            if path == "/api/update/progress":
                return self._wrap(api_mod.update_progress)
            if path == "/api/uninstall":
                look = parse_qs(urlsplit(self.path).query).get("look", [""])[0] == "1"
                return self._wrap(api_mod.uninstall_items, look)
            return self._reject(404, "no such path")

        def do_POST(self) -> None:
            if not self._guarded():
                return
            self._sync_config()
            path = urlsplit(self.path).path
            if path == "/api/action":
                return self._action()
            if path == "/api/desk":
                return self._desk()
            if path == "/api/page-problem":
                form = self._body(limit=4 * 1024)
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.page_problem, form)
            if (path in ("/api/scan", "/api/scan/fresh", "/api/rescreen")
                    and not cfg_holder["cfg"].titles_include):
                return self._reject(409, "no job titles to search for yet; "
                                         "finish setup first")
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
            if path == "/api/scan/delete":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                try:
                    work = api_mod.delete_scanned_job(cfg_holder["cfg"], form.get("expect"))
                except api_mod.ApiError as exc:
                    return self._reject(exc.status, str(exc))
                started, why = runner.start("delete scanned", work)
                if not started:
                    return self._reject(409, why)
                return self._json(202, {"started": True, "job": "delete scanned"})
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
            if path in ("/api/projects/save", "/api/projects/delete",
                        "/api/education/save", "/api/education/delete"):
                return self._project(path)
            if path == "/api/letters/delete":
                form = self._body()
                raw = str((form or {}).get("id") or "")
                if not raw.isdigit():
                    return self._reject(400, "not a cover letter id")
                return self._wrap(api_mod.delete_letter, cfg_holder["cfg"], int(raw))
            if path == "/api/own-board":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.check_own_board, cfg_holder["cfg"],
                                  str(form.get("uid") or ""))
            if path == "/api/uninstall":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.uninstall_now, form)
            if path == "/api/keys/legacy":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.legacy_keys, cfg_holder["cfg"], bool(form.get("keep")))
            if path == "/api/keys/forget":
                return self._wrap(api_mod.forget_saved_keys)
            if path == "/api/update/check":
                return self._wrap(api_mod.newer_version, cfg_holder["cfg"], True)
            if path == "/api/update/install":
                try:
                    work = api_mod.update_job(cfg_holder["cfg"])
                except api_mod.ApiError as exc:
                    return self._reject(exc.status, str(exc))
                started, why = runner.start("update", work)
                if not started:
                    return self._reject(409, why)
                return self._json(202, {"started": True, "job": "update"})
            if path == "/api/notify/test":
                return self._wrap(api_mod.notify_test, cfg_holder["cfg"])
            if path == "/api/schedule":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.schedule_save, cfg_holder["cfg"], form)
            if path == "/api/folders/open":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.open_folder, cfg_holder["cfg"], form.get("which"))
            if path == "/api/dealbreakers/try":
                form = self._body(limit=16 * 1024)
                if form is None:
                    return self._reject(400, "bad request body")
                return self._wrap(api_mod.try_dealbreaker, form)
            if path == "/api/setup/scan":
                cfg = cfg_holder["cfg"]
                if cfg.setup_step != "scan":
                    return self._reject(409, "the first scan is setup's last step")
                if runner.busy:
                    return self._reject(409, f"{runner.current} is already running")
                # Setup ends here, not when the scan does: the scan is watched
                # on the Dashboard rather than waited for on this screen.
                try:
                    cfg = self._write_config({"setup_step": "done"})
                except Exception as exc:
                    return self._reject(400, f"not saved: {exc}")
                (name, work), *then = api_mod.first_scan_jobs(cfg)
                started, why = runner.start(name, work, then=then)
                if not started:
                    return self._reject(409, why)
                return self._json(202, {"started": True, "job": name})
            if path == "/api/first-scan/seen":
                return self._json(200, api_mod.first_scan_seen())
            if path == "/api/stop":
                if not runner.stop():
                    return self._reject(409, "nothing is running")
                return self._json(202, {"stopping": runner.current})
            if path == "/api/queue/cancel":
                form = self._body() or {}
                try:
                    job_id = int(form.get("id") or 0)
                except (TypeError, ValueError):
                    return self._reject(400, "not a queued job id")
                if not runner.cancel(job_id):
                    return self._reject(404, "that job is not waiting; it may have started")
                return self._json(200, {"cancelled": job_id, "waiting": runner.waiting()})
            if path == "/api/setup/keys":
                return self._source_keys()
            if path == "/api/setup/suggest":
                return self._wrap(api_mod.setup_suggest, cfg_holder["cfg"])
            if path == "/api/add":
                return self._add()
            if path == "/api/add/text":
                return self._add_text()
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
            if path in ("/api/start-over/preview", "/api/start-over"):
                return self._start_over(path)
            if path == "/api/dropped/keep":
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                if runner.busy:
                    return self._reject(409, f"{runner.current} is running; "
                                        "keep it when it has finished")
                return self._wrap(api_mod.dropped_keep, cfg_holder["cfg"],
                                  str(form.get("uid") or ""))
            if path in ("/api/cleanup/aged/preview", "/api/cleanup/aged"):
                cfg = cfg_holder["cfg"]
                # The preview carries no fields, and a browser sends an empty
                # form as no body at all: read one only where it is needed.
                if path == "/api/cleanup/aged/preview":
                    return self._wrap(api_mod.aged_preview, cfg)
                form = self._body()
                if form is None:
                    return self._reject(400, "bad request body")
                if runner.busy:
                    return self._reject(409, f"{runner.current} is running; "
                                        "delete when it has finished")
                try:
                    expect = int(form.get("expect"))
                except (TypeError, ValueError):
                    return self._reject(400, "preview first")
                return self._wrap(api_mod.aged_run, cfg, expect)
            if path in ("/api/report/preview", "/api/report"):
                form = self._body(limit=feedback_mod.MAX_BODY)
                if form is None:
                    return self._reject(400, "bad request body, or screenshots too big")
                fn = api_mod.report_preview if path.endswith("preview") else api_mod.report_send
                return self._wrap(fn, cfg_holder["cfg"], form)
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

        def _desk(self) -> None:
            """A link or file for the desktop app to handle (web/app.py
            Bridge): the page in its window has no tabs or downloads."""
            if desk is None:
                return self._reject(404, "only the desktop app opens files")
            form = self._body(limit=desk.BODY_LIMIT)
            if form is None:
                return self._reject(400, "bad request body")
            try:
                value = desk.call(form.get("call"), form.get("args"))
            except ValueError as exc:
                return self._reject(400, str(exc))
            except Exception as exc:
                log.exception("the app could not %s", form.get("call"))
                return self._reject(500, f"the app could not do that: {exc}")
            return self._json(200, {"value": value})

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

        def _add_text(self) -> None:
            # Sized for a pasted advert, as _advert below is.
            form = self._body(limit=api_mod.MAX_ADVERT_CHARS * 12)
            if form is None:
                return self._reject(400, "bad request body")
            self._wrap(api_mod.add_by_text, cfg_holder["cfg"],
                       *(str(form.get(k) or "") for k in
                         ("url", "title", "company", "location", "text")))

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
            if path == "/api/llm/connection":
                return self._wrap(api_mod.llm_connection, str(form.get("code") or ""))
            if path == "/api/llm/forget":
                return self._wrap(api_mod.llm_forget,
                                  str(form.get("provider") or ""))
            if path == "/api/llm/test":
                return self._wrap(api_mod.llm_test, cfg)
            if path == "/api/llm":
                from ..core.config import MAX_READERS, SETUP_MAX_READERS
                limit = SETUP_MAX_READERS if cfg.setup_step else MAX_READERS
                for name in ("readers", "checkers"):
                    if isinstance(form.get(name), list) and len(form[name]) > limit:
                        return self._reject(400, f"at most {limit} AI {name}"
                                            + (" in setup; add more later on the AI page"
                                               if cfg.setup_step else ""))
                try:
                    fresh = self._write_config({"llm": form})
                except Exception as exc:
                    return self._reject(400, f"not saved: {exc}")
                return self._json(200, api_mod.llm_state(fresh))
            return self._reject(404, "no such path")

        def _project(self, path: str) -> None:
            """Save or delete a project or an education entry, then re-score
            the job posts with it: fit scores count them as the resume."""
            cfg = cfg_holder["cfg"]
            what = "project" if "/projects/" in path else "education"
            try:
                if path.endswith("/save"):
                    form = self._body(limit=24 * 1024)
                    if form is None:
                        return self._reject(400, "bad request body")
                    done = (api_mod.save_project if what == "project"
                            else api_mod.save_education)(cfg, form)
                else:
                    raw = str((self._body() or {}).get("id") or "")
                    if not raw.isdigit():
                        return self._reject(400, f"not an {what} id" if what == "education"
                                            else "not a project id")
                    done = (api_mod.delete_project if what == "project"
                            else api_mod.delete_education)(cfg, int(raw))
            except api_mod.ApiError as exc:
                return self._reject(exc.status, str(exc))
            # Nothing to re-score without a resume or before setup has titles.
            done["rescore"] = ""
            if cfg.resume_path and cfg.titles_include:
                # lambda: built when its turn comes, from the newest settings.
                saved = path.endswith("/save")
                given = form if saved else {}
                named = str(given.get("name") or given.get("credential") or "")
                verb = "saved" if saved else "deleted"
                now = runner.queue("re-score", lambda: api_mod.rescreen_job(cfg_holder["cfg"]),
                                   why=f"{'Projects' if what == 'project' else 'Education'}: "
                                       f"{verb}{f' {named}' if named else ''}")
                done["rescore"] = ("Re-scoring your job posts with it." if now else
                                   f"Your job posts are re-scored with it after {runner.current}.")
            return self._json(200, done)

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
                posted_by = api_mod.recruiters(store, rows)
                payload = [{**_row_to_dict(row, units, cfg.freshness), **posted_by[row["uid"]]}
                           for row in rows]
                unlisted = api_mod.not_on_own_board(store, rows)
                for post in payload:
                    if post["uid"] in unlisted:
                        post["flags"] = [*post["flags"], ownboard.flag_text(post["company"])]

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
            # Older than freshness.show_days and not acted on: hidden from the
            # list, never deleted, and counted so "Show older" can bring them
            # back. A post with no date cannot be called old, so it stays.
            older, limit = 0, cfg.freshness.show_days
            if limit and (query.get("older") or [""])[0] != "1":
                kept = [p for p in payload if not (
                    p["status"] in ("new", "viewed") and p["age"]["days"] is not None
                    and p["age"]["days"] > limit)]
                older = len(payload) - len(kept)
                payload = kept
            settled = sum(counts.get(s, 0) for s in SETTLED_STATUSES)
            self._json(200, {"roles": payload, "counts": counts,
                             "settled": settled, "ghosts": ghosts,
                             "older": older, "show_days": limit})

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

        def _source_keys(self) -> None:
            """Adzuna or USAJOBS keys into the app's keys file, then re-read."""
            from ..core import config as config_mod

            form = self._body(limit=2 * 1024)
            if form is None:
                return self._reject(400, "bad request body")
            cfg = cfg_holder["cfg"]
            try:
                note = api_mod.setup_keys(cfg, form)
            except api_mod.ApiError as exc:
                return self._reject(exc.status, str(exc))
            # Keys are read into the config when it loads.
            if Path(cfg.path).is_file():
                cfg_holder["cfg"] = config_mod.load(cfg.path)
            return self._json(200, {**api_mod.setup_sources(cfg_holder["cfg"]),
                                    "note": note})

        def _places(self, what: str) -> None:
            """Country, region and city lists for the Where you are picker."""
            q = parse_qs(urlsplit(self.path).query)
            # lambda: a one-line reader over this request's query, used three
            # times below; a def would read the same.
            arg = lambda k: (q.get(k, [""])[0] or "")[:80]    # noqa: E731
            if what == "countries":
                # A currency is offered only where a salary floor can use it.
                from ..core.config import CURRENCIES
                return self._json(200, {"countries": [
                    {**c, "currency": c["currency"] if c["currency"] in CURRENCIES else "",
                     "units": geo.default_units([c["code"]])}
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

            old = cfg_holder["cfg"]
            try:
                fresh = self._write_config(payload)
            except Exception as exc:
                return self._reject(400, f"not saved: {exc}")
            keys = (api_mod.remember_keys_changed(fresh.remember_keys)
                    if fresh.remember_keys != old.remember_keys else "")
            self._json(200, {**_config_payload(fresh), "rescan": self._rescan(old, fresh),
                             "keys": keys})

        def _rescan(self, old, fresh) -> str:
            """After a change to the search, the job posts follow it by
            themselves: re-screened when the rules changed (posts that no
            longer pass and you have not acted on move to Dropped by your
            filters), and a scan when the search widened. While a job runs
            they wait for it, and use the settings as they are by then.
            Returns what was started, for the page to say."""
            if fresh.setup_step or not fresh.titles_include:
                return ""                    # setup starts its own first scan
            widened, rescreen = search_changes(old, fresh)
            said = []
            if rescreen:
                # lambda: built when its turn comes, from the newest settings.
                now = runner.queue("rescreen", lambda: api_mod.rescreen_job(
                    cfg_holder["cfg"], remove=True), why=change_words(old, fresh))
                said.append("Re-applying your search to the job posts"
                            + ("" if now else f" after {runner.current}"))
            if widened:
                # lambda: as above; a scan reads every title, old and new.
                now = runner.queue("scan", lambda: api_mod.scan_job(cfg_holder["cfg"]),
                                   why=change_words(old, fresh))
                said.append(("Scanning" if now else "Then scanning")
                            + " for what you added")
            return (". ".join(said) + ".") if said else ""

        def _start_over(self, path: str) -> None:
            """Delete this run's settings and data, then open setup again."""
            from ..core import config as config_mod

            cfg = cfg_holder["cfg"]
            # No fields in the preview, so no body (see the aged preview).
            if path == "/api/start-over/preview":
                return self._wrap(api_mod.start_over_preview, cfg)
            form = self._body()
            if form is None:
                return self._reject(400, "bad request body")
            if runner.busy:
                return self._reject(409, f"{runner.current} is running; start over "
                                    "when it has finished")
            try:
                done = api_mod.start_over(
                    cfg, str(form.get("words") or ""),
                    backup=str(form.get("backup") or "") in ("1", "true", "yes", "on"))
            except api_mod.ApiError as exc:
                return self._reject(exc.status, str(exc))
            # Setup writes the new config where the old one was.
            fresh = config_mod.load("", require=False) if not config_mod._configured() \
                else config_mod.Config()
            fresh.path, fresh.setup_step = cfg.path, "welcome"
            cfg_holder["cfg"], cfg_holder["mtime"] = fresh, None
            return self._json(200, done)

        def _write_config(self, payload: dict):
            """Write through core.setup, which creates the file on a first run."""
            from ..core import setup

            cfg = cfg_holder["cfg"]
            if not cfg.path:
                raise ValueError("this run has no config file to write to")
            fresh = setup.write(cfg.path, payload)
            cfg_holder["cfg"] = fresh
            cfg_holder["mtime"] = Path(fresh.path).stat().st_mtime
            return fresh

        def log_message(self, fmt: str, *args) -> None:
            log.debug("%s - %s", self.address_string(), fmt % args)

    return Handler


def serve(cfg, port: int = DEFAULT_PORT, open_browser: bool = True,
          token: str = "", on_ready=None, desk=None) -> int:
    """Run until Ctrl-C. Returns an exit code.

    `on_ready(url, stop, busy)` is for the desktop app, which runs this on a
    thread of its own: it is called once the server is listening, with the
    address to show, a function that ends the run as Ctrl-C would, and one
    that names the job running ("scan"), or returns "" when none is. `desk`
    is its Bridge, answering `POST /api/desk` (links and files).
    """
    # The session keeps HOST either way: it is the address in the printed URL
    # and the one the Host check accepts, and in a container the browser
    # still reaches it as 127.0.0.1 through the published port.
    bind = bind_address()
    session = new_session(HOST, preferred_port=port, token=token)
    cfg_holder = {"cfg": cfg}
    # lambda: looked up on every use, so a config edit that moves the database
    # is followed; passing the path itself would freeze it.
    runner = Runner(db_path=lambda: cfg_holder["cfg"].db_path)
    from ..core import telemetry
    # lambda: the same reason, read at each call rather than now.
    telemetry.record_calls_to(lambda: cfg_holder["cfg"].db_path)
    # lambda: read at each call, for the same reason.
    telemetry.capture_logs(lambda: cfg_holder["cfg"].db_path)
    for warning in cfg.warnings:
        log.warning("config: %s", warning)
    # In a container the resume and documents live in a temporary folder
    # that does not outlive a run: emptied now, and again on the way out.
    cleared = api_mod.forget_temporary(cfg)
    if cleared:
        print(f"emptied the temporary folder: {cleared} file(s) from the last run")

    try:
        server = Server(
            (bind, session.port),
            make_handler(cfg_holder, session, runner, desk))
    except OSError as exc:
        print(f"cannot listen on {bind}:{session.port}: {exc}")
        return 1

    if session.port != port:
        print(f"port {port} was busy; using {session.port}")
    # The app logs to a file, and the token is never written down: it shows
    # the page itself, so the address is printed without it.
    print(f"jobdork dashboard: {session.url.split('?')[0] if on_ready else session.url}")
    if cfg.setup_step:
        print(f"Not set up yet: the dashboard opens on setup, and saves to {cfg.path}.")
    from ..core import storage
    unkept = storage.unkept_data_dir(cfg)
    if unkept:
        print(f"WARNING: {unkept} is inside this container, not a mounted folder. "
              "Your job posts, settings, resume and letters are deleted with the "
              f"container. Start it with -v <a folder on this machine>:{unkept} "
              "to keep them.")
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
    elif not on_ready:
        print("Local only, token expires with this process, Ctrl-C to stop.")
    if open_browser:
        # lambda: Timer runs it later, once the server is listening; calling
        # open() here would race the server.
        threading.Timer(0.4, lambda: webbrowser.open(session.url)).start()
    if on_ready:
        # lambda: asked when the window is closed, so it is read then, not now.
        on_ready(session.url, server.shutdown,
                 lambda: runner.current if runner.busy else "")

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
