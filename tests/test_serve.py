"""
Tests for the dashboard's guards.

The rendering does not need testing here — `render.py` already covers it and
the page is the same list. What needs testing is everything that decides
whether a request is allowed to touch the database, because this process
listens on a socket and the CLI does not.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork import serve as serve_mod
from jobdork.config import Config, Locations, Salary
from jobdork.store import Role, Store


class _Running:
    """A real server on a real loopback port, torn down afterwards."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Config(
            titles_include=["software engineer"],
            locations=Locations(anchor="Chicago, IL", radius="exact",
                                units="mi", countries=["US"]),
            salary=Salary(),
            db_path=str(Path(self.tmp.name) / "serve.db"),
        )
        with Store(self.cfg.db_path) as store:
            role = Role(platform="workable", title="Software Engineer",
                        company="Acme", url="https://x.test/1",
                        location_raw="Chicago, Illinois")
            store.upsert(role)
            store.conn.commit()
            self.uid = role.uid

        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), lambda *a: None)
        port = self.server.server_address[1]
        self.server.server_close()

        self.port = port
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", port),
            serve_mod.make_handler(self.cfg, "127.0.0.1", port))
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def get(self, path: str, host: str | None = None):
        request = urllib.request.Request(self.base + path)
        if host:
            request.add_header("Host", host)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def post(self, path: str, fields: dict, host: str | None = None):
        data = urllib.parse.urlencode(fields).encode()
        request = urllib.request.Request(self.base + path, data=data)
        if host:
            request.add_header("Host", host)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()


def _with_server(fn):
    running = _Running()
    try:
        fn(running)
    finally:
        running.close()


# ── the guards ─────────────────────────────────────────────────────────────────

def test_a_foreign_host_header_is_refused():
    """DNS rebinding: an attacker's domain resolving to 127.0.0.1.

    Host and Origin are both attacker-controlled and agree with each other.
    The address this process bound to is not, so that is what is checked.
    """
    def check(run):
        assert run.get("/", host="evil.example.com")[0] == 421
        assert run.get("/", host="127.0.0.1.evil.com")[0] == 421
        assert run.get("/")[0] == 200
        assert run.get("/", host=f"localhost:{run.port}")[0] == 200
    _with_server(check)


def test_only_known_paths_answer():
    def check(run):
        assert run.get("/")[0] == 200
        assert run.get("/api/roles")[0] == 200
        for path in ("/etc/passwd", "/../config.yaml", "/index.html",
                     "/api/unknown", "/api/roles/../../secret"):
            assert run.get(path)[0] == 404, path
    _with_server(check)


def test_a_uid_must_look_like_a_uid():
    """The only value from the page that reaches the database."""
    def check(run):
        for bad in ("../../etc/passwd", "'; DROP TABLE roles;--", "",
                    "NOTAHEXUID1", "0c90271666060", "0c9027"):
            code, _ = run.post("/api/action", {"uid": bad, "status": "applied"})
            assert code == 400, bad
    _with_server(check)


def test_an_unknown_status_is_refused():
    def check(run):
        code, body = run.post("/api/action",
                              {"uid": run.uid, "status": "pwned"})
        assert code == 400 and b"unknown status" in body
    _with_server(check)


def test_an_unknown_role_is_refused():
    def check(run):
        code, _ = run.post("/api/action",
                           {"uid": "a" * 12, "status": "applied"})
        assert code == 404
    _with_server(check)


def test_an_oversized_body_is_refused():
    def check(run):
        code, _ = run.post("/api/action",
                           {"uid": run.uid, "note": "x" * 9000})
        assert code == 400
    _with_server(check)


def test_get_cannot_change_anything():
    """A status change must not be reachable by following a link."""
    def check(run):
        assert run.get(f"/api/action?uid={run.uid}&status=applied")[0] == 404
        with Store(run.cfg.db_path) as store:
            assert store.get(run.uid)["status"] == "new"
    _with_server(check)


# ── it actually works ──────────────────────────────────────────────────────────

def test_an_action_is_written_where_the_cli_reads_it():
    def check(run):
        code, _ = run.post("/api/action", {
            "uid": run.uid, "status": "interested", "note": "from the dashboard"})
        assert code == 200
        with Store(run.cfg.db_path) as store:
            row = store.get(run.uid)
            assert row["status"] == "interested"
            assert row["note"] == "from the dashboard"
    _with_server(check)


def test_a_note_alone_keeps_the_status():
    def check(run):
        run.post("/api/action", {"uid": run.uid, "status": "applied"})
        run.post("/api/action", {"uid": run.uid, "note": "second round"})
        with Store(run.cfg.db_path) as store:
            row = store.get(run.uid)
            assert row["status"] == "applied", "a note must not reset status"
            assert row["note"] == "second round"
    _with_server(check)


def test_settled_roles_are_hidden_until_asked_for():
    def check(run):
        run.post("/api/action", {"uid": run.uid, "status": "skipped"})
        assert json.loads(run.get("/api/roles?scope=open")[1])["roles"] == []
        assert len(json.loads(run.get("/api/roles?scope=all")[1])["roles"]) == 1
    _with_server(check)


def test_the_page_carries_no_external_request():
    """Local tool, no CDN: nothing here should phone anywhere."""
    def check(run):
        body = run.get("/")[1].decode()
        for marker in ("http://", "//cdn", "googleapis", "unpkg", "jsdelivr"):
            assert marker not in body.replace("http://127.0.0.1", ""), marker
    _with_server(check)


# ── keep this block LAST ───────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
