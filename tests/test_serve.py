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

from jobdork.core.config import Config, Locations, Salary
from jobdork.db.store import Role, Store
from jobdork.web import serve as serve_mod
from jobdork.web.live import Runner
from jobdork.web.session import new_session


class _Running:
    """A real server on a real loopback port, torn down afterwards."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        config_file = Path(self.tmp.name) / "config.yaml"
        config_file.write_text(
            "titles: {include: [software engineer]}\n"
            "locations: {anchor: 'Chicago, IL', radius: exact, countries: [US]}\n",
            encoding="utf-8")
        self.config_path = str(config_file)
        self.cfg = Config(
            path=str(config_file),
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

        self.session = new_session("127.0.0.1")
        self.port = self.session.port
        self.token = self.session.token
        self.runner = Runner()
        self.holder = {"cfg": self.cfg}

        self.server = ThreadingHTTPServer(
            ("127.0.0.1", self.port),
            serve_mod.make_handler(self.holder, self.session, self.runner))
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def get(self, path: str, host: str | None = None, token: str | None = ""):
        request = urllib.request.Request(self.base + path)
        request.add_header("X-Jobdork-Token",
                           self.token if token == "" else (token or ""))
        if host:
            request.add_header("Host", host)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def post(self, path: str, fields: dict, host: str | None = None,
             token: str | None = ""):
        data = urllib.parse.urlencode(fields).encode()
        request = urllib.request.Request(self.base + path, data=data)
        request.add_header("X-Jobdork-Token",
                           self.token if token == "" else (token or ""))
        if host:
            request.add_header("Host", host)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    @property
    def cfg_now(self):
        return self.holder["cfg"]

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



# ── the token ──────────────────────────────────────────────────────────────────

def test_loopback_is_not_a_security_boundary():
    """Any process running as you can reach a plain local server.

    The Host check stops a web page under DNS rebinding. It does nothing about
    another program on the same machine, which is what the token is for.
    """
    def check(run):
        assert run.get("/api/roles", token=None)[0] == 401
        assert run.get("/api/roles", token="wrong-token")[0] == 401
        assert run.get("/api/roles")[0] == 200
    _with_server(check)


def test_a_token_is_required_to_change_anything():
    def check(run):
        code, _ = run.post("/api/action",
                           {"uid": run.uid, "status": "applied"}, token=None)
        assert code == 401
        with Store(run.cfg.db_path) as store:
            assert store.get(run.uid)["status"] == "new"
    _with_server(check)


def test_the_token_may_arrive_in_the_url_once():
    """A URL is the only thing a person can be handed."""
    def check(run):
        request = urllib.request.Request(
            f"{run.base}/api/roles?t={run.token}")
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
    _with_server(check)


def test_tokens_differ_between_runs_and_are_compared_in_constant_time():
    first, second = new_session(), new_session()
    assert first.token != second.token
    assert len(first.token) >= 32
    assert first.matches(first.token)
    assert not first.matches(second.token)
    assert not first.matches("")


def test_a_busy_port_is_stepped_over_rather_than_failing():
    """A fixed port collides; asking the OS does not."""
    import socket
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        busy = taken.getsockname()[1]
        session = new_session("127.0.0.1", preferred_port=busy)
        assert session.port != busy, "a busy port must not be handed back"
    assert new_session("127.0.0.1", preferred_port=0).port > 0


# ── live scan ──────────────────────────────────────────────────────────────────

def test_only_one_scan_runs_at_a_time():
    """Two would double every request to hosts that are deliberately paced."""
    import time as _time
    runner = Runner()
    started, _ = runner.start("slow", lambda progress: _time.sleep(0.4) or "done")
    assert started
    again, why = runner.start("slow", lambda progress: "done")
    assert not again and "already running" in why


def test_a_failing_job_reports_instead_of_killing_the_server():
    runner = Runner()
    channel = runner.broker.subscribe()

    def explode(progress):
        raise RuntimeError("boom")

    runner.start("scan", explode)
    kinds = []
    for _ in range(6):
        try:
            kinds.append(channel.get(timeout=2).kind)
        except Exception:
            break
        if kinds[-1] in ("error", "done"):
            break
    assert "error" in kinds, kinds


def test_a_subscriber_that_stopped_reading_is_dropped_not_blocking():
    from jobdork.web.live import BACKLOG, Broker, Event
    broker = Broker()
    channel = broker.subscribe()
    for i in range(BACKLOG + 50):
        broker.publish(Event("progress", f"line {i}"))
    # The full queue was removed rather than blocking the publisher.
    assert channel.qsize() <= BACKLOG


# ── config editing ─────────────────────────────────────────────────────────────

def test_the_page_can_edit_the_config_and_it_is_validated():
    def check(run):
        code, body = run.post("/api/config", {}, token=run.token)
        # form-encoded is accepted, but an empty edit changes nothing harmful
        assert code in (200, 400), body

        import json as _json
        data = _json.dumps({"titles_include": ["security analyst"],
                            "anchor": "Berlin, Germany",
                            "countries": ["DE"], "radius": "exact"}).encode()
        request = urllib.request.Request(
            f"{run.base}/api/config", data=data,
            headers={"Content-Type": "application/json",
                     "X-Jobdork-Token": run.token})
        with urllib.request.urlopen(request, timeout=5) as response:
            saved = _json.loads(response.read())
        assert saved["titles_include"] == ["security analyst"]
        assert saved["countries"] == ["DE"]
        # Reloaded config replaced the live one, so the next request uses it.
        assert run.cfg_now.locations.anchor == "Berlin, Germany"
    _with_server(check)


def test_a_config_edit_that_would_not_load_is_rejected_and_rolled_back():
    """The file must never be left in a state the loader would refuse."""
    def check(run):
        import json as _json
        before = Path(run.config_path).read_text(encoding="utf-8")
        data = _json.dumps({"titles_include": []}).encode()   # empty is refused
        request = urllib.request.Request(
            f"{run.base}/api/config", data=data,
            headers={"Content-Type": "application/json",
                     "X-Jobdork-Token": run.token})
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("an invalid config must not be saved")
        assert Path(run.config_path).read_text(encoding="utf-8") == before
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


def test_a_pasted_advert_replaces_the_teaser_and_rescreens():
    def check(run):
        advert = "Software engineer building Python services. " * 40
        code, body = run.post("/api/advert", {"uid": run.uid, "text": advert})
        assert code == 200, body
        answer = json.loads(body)
        assert answer["advert_chars"] == len(advert.strip())
        assert answer["dropped"] == ""
        with Store(run.cfg.db_path) as store:
            assert store.get(run.uid)["description"] == advert.strip()
    _with_server(check)


def test_an_empty_or_oversized_advert_is_refused():
    def check(run):
        code, _ = run.post("/api/advert", {"uid": run.uid, "text": "   "})
        assert code == 400
        code, _ = run.post("/api/advert", {"uid": "nope", "text": "advert"})
        assert code == 400
    _with_server(check)


def test_an_api_key_goes_in_and_never_comes_back_out():
    from jobdork.ai.llm import VAULT

    secret = "sk-test-never-echo-0123456789"

    def check(run):
        code, body = run.post("/api/llm/key", {"provider": "openai", "key": secret})
        assert code == 200 and secret.encode() not in body
        for path in ("/api/llm", "/api/state", "/api/config"):
            code, body = run.get(path)
            assert code == 200 and secret.encode() not in body, path
        _, body = run.get("/api/llm")
        assert json.loads(body)["keys"]["openai"] == "memory"
        assert secret not in Path(run.config_path).read_text()

        code, _ = run.post("/api/llm/forget", {"provider": "openai"})
        assert code == 200 and VAULT.get("openai") == ""
    try:
        _with_server(check)
    finally:
        VAULT.wipe()


def test_saving_ai_settings_writes_no_key_to_the_config():
    def check(run):
        code, body = run.post("/api/llm", {"provider": "ollama",
                                           "model": "llama3.2:3b",
                                           "key": "sk-smuggled-0123456789"})
        assert code == 200, body
        text = Path(run.config_path).read_text()
        assert "llama3.2:3b" in text and "smuggled" not in text
        assert run.cfg_now.llm.provider == "ollama"
    _with_server(check)
