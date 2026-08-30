"""
jobdork.serve
=============
The dashboard with buttons, at http://127.0.0.1:8765.

The same list `jobdork list` prints and `out/index.html` renders, except that
what you click sticks. It reads and writes the same database the CLI does, so
the two cannot disagree — mark a role applied here and `jobdork list` shows it
applied, and the reverse.

Standard library only. It is a local tool, not a service: it binds to loopback,
it stops when you Ctrl-C, it has no accounts and nothing to expose.

Two things it refuses to do, both deliberate:

  **It does not bind to 0.0.0.0.** There is no `--host`. A dashboard listing
  where you are applying is not a thing to put on a network, and an option to
  do it is an option somebody uses.

  **It validates the Host header against the address it actually bound to**,
  rather than trusting Origin. Under DNS rebinding a page on an attacker's
  domain can reach 127.0.0.1 in your browser, and both Host and Origin are
  attacker-controlled together — but the bound address is not.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .config import SETTLED_STATUSES, STATUSES
from .render import STATUS_COLOURS
from .store import Store

log = logging.getLogger("jobdork.serve")

DEFAULT_PORT = 8765
HOST = "127.0.0.1"

# Only these may be reached from the page. Anything else is 404 rather than
# an attempt to serve a path from disk.
ROUTES = ("/", "/api/roles", "/api/action", "/api/open")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>jobdork</title><style>
:root { color-scheme: light dark;
  --bg:#fff; --fg:#18181b; --muted:#71717a; --line:#e4e4e7; --card:#fafafa;
  --accent:#1d4ed8; --flag:#92400e; --flagbg:#fef3c7; --btn:#fff; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#0b0b0d; --fg:#e7e7ea; --muted:#a1a1aa; --line:#27272a; --card:#141417;
  --accent:#93b4ff; --flag:#fde68a; --flagbg:#3f2d0a; --btn:#1c1c20; } }
*{box-sizing:border-box} body{margin:0;padding:1.5rem 1.25rem;background:var(--bg);
  color:var(--fg);font:15px/1.55 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1000px;margin:0 auto}
h1{font-size:1.4rem;margin:0 0 .25rem}
.sub{color:var(--muted);font-size:.85rem;margin:0 0 1.25rem}
.bar{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1.25rem;align-items:center}
select,input[type=search]{background:var(--btn);color:var(--fg);border:1px solid var(--line);
  border-radius:6px;padding:.4rem .55rem;font:inherit;font-size:.85rem}
.count{color:var(--muted);font-size:.85rem;margin-left:auto}
.role{border:1px solid var(--line);border-radius:8px;padding:.85rem 1rem;
  margin-bottom:.6rem;background:var(--card)}
.role.busy{opacity:.5}
.head{display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap}
.score{font-variant-numeric:tabular-nums;font-weight:600;color:var(--accent);min-width:3ch}
.title{font-weight:600}.title a{color:inherit;text-decoration:none}
.title a:hover{text-decoration:underline}
.pill{padding:.1rem .5rem;border-radius:999px;font-size:.7rem;font-weight:600;
  color:#fff;text-transform:uppercase;letter-spacing:.02em}
.meta{color:var(--muted);font-size:.85rem;margin-top:.3rem;display:flex;
  gap:.3rem 1rem;flex-wrap:wrap}
.flags{margin-top:.4rem;display:flex;gap:.3rem;flex-wrap:wrap}
.flag{background:var(--flagbg);color:var(--flag);font-size:.72rem;
  padding:.1rem .45rem;border-radius:4px}
.acts{margin-top:.6rem;display:flex;gap:.35rem;flex-wrap:wrap}
button{background:var(--btn);color:var(--fg);border:1px solid var(--line);
  border-radius:6px;padding:.3rem .6rem;font:inherit;font-size:.8rem;cursor:pointer}
button:hover{border-color:var(--accent);color:var(--accent)}
button:disabled{opacity:.4;cursor:default}
.uid{font-family:ui-monospace,Menlo,monospace;font-size:.72rem;color:var(--muted)}
.note{width:100%;margin-top:.4rem}
.empty{color:var(--muted);padding:2rem 0}
footer{margin-top:2rem;color:var(--muted);font-size:.78rem;
  border-top:1px solid var(--line);padding-top:1rem}
</style></head><body><div class="wrap">
<h1>jobdork</h1>
<p class="sub">Local only. What you click is written to the same database the
CLI reads. Settled roles are hidden unless you ask for them.</p>
<div class="bar">
  <select id="status"></select>
  <select id="scope">
    <option value="open">open roles</option>
    <option value="new">new since last scan</option>
    <option value="all">including settled</option>
  </select>
  <input type="search" id="q" placeholder="filter by title or company">
  <span class="count" id="count"></span>
</div>
<div id="list"><p class="empty">Loading…</p></div>
<footer id="foot"></footer>
</div><script>
const STATUSES = __STATUSES__, COLOURS = __COLOURS__;
let roles = [];

const sel = document.getElementById('status');
sel.innerHTML = '<option value="">any status</option>' +
  STATUSES.map(s => `<option value="${s}">${s}</option>`).join('');

function esc(s){ return String(s ?? '').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function load(){
  const scope = document.getElementById('scope').value;
  const status = sel.value;
  const r = await fetch(`/api/roles?scope=${scope}&status=${encodeURIComponent(status)}`);
  const data = await r.json();
  roles = data.roles;
  document.getElementById('foot').textContent = data.footer;
  draw();
}

function draw(){
  const q = document.getElementById('q').value.toLowerCase();
  const shown = roles.filter(r =>
    !q || (r.title + ' ' + r.company).toLowerCase().includes(q));
  document.getElementById('count').textContent =
    `${shown.length} of ${roles.length}`;
  document.getElementById('list').innerHTML = shown.length
    ? shown.map(card).join('')
    : '<p class="empty">Nothing matches.</p>';
}

function card(r){
  const colour = COLOURS[r.status] || '#6b7280';
  const meta = [r.company, r.location, r.distance, r.work_mode, r.salary,
                r.platform, r.first_seen].filter(Boolean);
  const flags = (r.flags||[]).map(f => `<span class="flag">${esc(f)}</span>`).join('');
  const opts = STATUSES.map(s =>
    `<option value="${s}"${s===r.status?' selected':''}>${s}</option>`).join('');
  return `<div class="role" id="r-${esc(r.uid)}">
    <div class="head">
      <span class="score">${r.score ?? '-'}</span>
      <span class="title"><a href="${esc(r.url)}" target="_blank"
        rel="noopener noreferrer">${esc(r.title)}</a></span>
      <span class="pill" style="background:${colour}">${esc(r.status)}</span>
      <span class="uid">${esc(r.uid)}</span>
    </div>
    <div class="meta">${meta.map(m=>`<span>${esc(m)}</span>`).join('')}</div>
    ${flags ? `<div class="flags">${flags}</div>` : ''}
    <div class="acts">
      <button onclick="act('${esc(r.uid)}','interested')">Interested</button>
      <button onclick="apply('${esc(r.uid)}','${esc(r.url)}')">Apply</button>
      <button onclick="act('${esc(r.uid)}','interviewing')">Interviewing</button>
      <button onclick="act('${esc(r.uid)}','skipped')">Skip</button>
      <select onchange="act('${esc(r.uid)}', this.value)">${opts}</select>
      <input class="note" placeholder="note — enter to save"
        onkeydown="if(event.key==='Enter')act('${esc(r.uid)}', null, this.value)">
    </div></div>`;
}

async function act(uid, status, note){
  const el = document.getElementById('r-' + uid);
  if (el) el.classList.add('busy');
  const body = new URLSearchParams({uid});
  if (status) body.set('status', status);
  if (note) body.set('note', note);
  const r = await fetch('/api/action', {method:'POST', body});
  if (!r.ok) { alert('Not saved: ' + await r.text()); if (el) el.classList.remove('busy'); return; }
  await load();
}

// The posting is opened by the browser, and the status is recorded. Marking
// applied without opening it would be recording something that did not happen.
function apply(uid, url){ window.open(url, '_blank', 'noopener'); act(uid, 'applied'); }

document.getElementById('scope').onchange = load;
sel.onchange = load;
document.getElementById('q').oninput = draw;
load();
</script></body></html>"""


def _row_to_dict(row, units: str) -> dict:
    try:
        flags = json.loads(row["flags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        flags = []

    if row["salary_stated"]:
        lo, hi, cur = row["salary_min"], row["salary_max"], row["salary_currency"] or ""
        salary = (f"{cur} {lo:,.0f}–{hi:,.0f}" if lo and hi
                  else f"{cur} {(hi or lo):,.0f}" if (hi or lo) else "unconfirmed salary")
    else:
        salary = "unconfirmed salary"

    return {
        "uid": row["uid"],
        "score": None if row["score"] is None else round(row["score"]),
        "status": row["status"] or "new",
        "title": row["title"] or "",
        "company": row["company"] or "",
        "url": row["url"] or "",
        "location": row["location_raw"] or "",
        "distance": (f"{row['distance_mi']:.0f} {units}"
                     if row["distance_mi"] is not None else ""),
        "work_mode": row["work_mode"] or "arrangement not stated",
        "salary": salary,
        "platform": row["platform"] or "",
        "first_seen": f"first seen {row['first_seen'][:10]}" if row["first_seen"] else "",
        "flags": flags,
    }


def make_handler(cfg, bound_host: str, bound_port: int):
    """The handler closes over the config and the address actually bound."""
    allowed_hosts = {
        f"{bound_host}:{bound_port}",
        f"localhost:{bound_port}",
        bound_host,
        "localhost",
    }
    units = cfg.locations.units or "mi"

    class Handler(BaseHTTPRequestHandler):
        server_version = "jobdork"
        protocol_version = "HTTP/1.1"

        # ── guards ─────────────────────────────────────────────────────────────

        def _host_ok(self) -> bool:
            """Checked against what we bound to, not against Origin.

            Under DNS rebinding a page on an attacker's domain resolves to
            127.0.0.1 and reaches this server from your browser. Host and
            Origin are both attacker-controlled and agree with each other;
            the address this process actually bound to is not.
            """
            host = (self.headers.get("Host") or "").strip().lower()
            return host in allowed_hosts

        def _reject(self, code: int, message: str) -> None:
            payload = message.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"),
                       "application/json; charset=utf-8")

        # ── routes ─────────────────────────────────────────────────────────────

        def do_GET(self) -> None:
            if not self._host_ok():
                return self._reject(421, "unrecognised Host header")
            path = urlsplit(self.path).path
            if path == "/":
                page = (PAGE
                        .replace("__STATUSES__", json.dumps(list(STATUSES)))
                        .replace("__COLOURS__", json.dumps(STATUS_COLOURS)))
                return self._send(200, page.encode("utf-8"),
                                  "text/html; charset=utf-8")
            if path == "/api/roles":
                return self._roles()
            return self._reject(404, "no such path")

        def do_POST(self) -> None:
            if not self._host_ok():
                return self._reject(421, "unrecognised Host header")
            if urlsplit(self.path).path != "/api/action":
                return self._reject(404, "no such path")
            return self._action()

        def _roles(self) -> None:
            query = parse_qs(urlsplit(self.path).query)
            scope = (query.get("scope") or ["open"])[0]
            status = (query.get("status") or [""])[0]
            if status and status not in STATUSES:
                return self._reject(400, "unknown status")

            with Store(cfg.db_path) as store:
                rows = store.list_roles(
                    status=status,
                    new_only=(scope == "new"),
                    include_settled=(scope == "all"),
                )
                counts = store.status_counts()
                payload = [_row_to_dict(row, units) for row in rows]

            settled = sum(counts.get(s, 0) for s in SETTLED_STATUSES)
            self._json(200, {
                "roles": payload,
                "footer": (
                    f"{len(payload)} shown · {settled} settled and hidden · "
                    "salary reads unconfirmed where the employer published no "
                    "figure, which is most of them"
                ),
            })

        def _action(self) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._reject(400, "bad Content-Length")
            if length <= 0 or length > 8192:
                return self._reject(400, "bad request body")

            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
            uid = (form.get("uid") or [""])[0].strip()
            status = (form.get("status") or [""])[0].strip()
            note = (form.get("note") or [""])[0].strip()

            # A uid is 12 hex characters. Anything else is not one, and this
            # is the only value from the page that reaches the database.
            if not re.fullmatch(r"[0-9a-f]{12}", uid):
                return self._reject(400, "not a role id")
            if status and status not in STATUSES:
                return self._reject(400, "unknown status")
            if not status and not note:
                return self._reject(400, "nothing to record")

            with Store(cfg.db_path) as store:
                if store.get(uid) is None:
                    return self._reject(404, "no such role")
                if status:
                    store.set_status(uid, status, note)
                else:
                    current = store.get(uid)
                    store.set_status(uid, current["status"] or "new", note)
            self._json(200, {"ok": True, "uid": uid})

        def log_message(self, fmt: str, *args) -> None:
            log.debug("%s - %s", self.address_string(), fmt % args)

    return Handler


def serve(cfg, port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    """Run until Ctrl-C. Returns an exit code."""
    server = ThreadingHTTPServer((HOST, port), lambda *a: None)
    server.server_close()                       # release the probe socket

    try:
        server = ThreadingHTTPServer(
            (HOST, port), make_handler(cfg, HOST, port))
    except OSError as exc:
        print(f"cannot listen on {HOST}:{port} — {exc}. "
              "Another jobdork may already be running; try --port.")
        return 1

    url = f"http://{HOST}:{port}"
    print(f"jobdork dashboard on {url}")
    print("Local only, and it stops when you Ctrl-C.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0
