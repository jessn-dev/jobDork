"""
Tests for the dashboard's guards.

The rendering does not need testing here — `render.py` already covers it and
the page is the same list. What needs testing is everything that decides
whether a request is allowed to touch the database, because this process
listens on a socket and the CLI does not.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
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
        # Its own database: a save re-reads this file, and without `db:` the
        # server would then use data/jobdork.db wherever the tests run from,
        # which in the repository is the live one.
        config_file.write_text(
            "titles: {include: [software engineer]}\n"
            "locations: {anchor: 'Chicago, IL', radius: exact, countries: [US]}\n"
            f"db: {Path(self.tmp.name) / 'serve.db'}\n",
            encoding="utf-8")
        self.config_path = str(config_file)
        self.cfg = Config(
            path=str(config_file),
            titles_include=["software engineer"],
            locations=Locations(cities=["Chicago, IL"], radius="exact",
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
        # A config save starts a re-screen or a scan by itself (serve._rescan),
        # and a scan here would go online. Recorded, not run; a test that
        # wants the real queue puts it back (real_queue).
        self.queued: list[str] = []
        self.runner.queue = self._record
        self.holder = {"cfg": self.cfg}

        # The dashboard's own server class, which logs a request that fails.
        self.server = serve_mod.Server(
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

    def post_json(self, path: str, payload: dict):
        request = urllib.request.Request(self.base + path,
                                         data=json.dumps(payload).encode())
        request.add_header("X-Jobdork-Token", self.token)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def _record(self, name, make) -> bool:
        self.queued.append(name)
        return True

    def real_queue(self) -> None:
        self.runner.queue = Runner.queue.__get__(self.runner)

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


def test_posts_past_the_age_limit_are_hidden_until_asked_for():
    def check(run):
        old = (__import__("datetime").date.today()
               - __import__("datetime").timedelta(days=45)).isoformat()
        with Store(run.cfg.db_path) as store:
            for name in ("old", "old_applied"):
                role = Role(platform="workable", title="Software Engineer",
                            company=name, url=f"https://x.test/{name}",
                            location_raw="Chicago, Illinois", posted_at=old)
                store.upsert(role)
                if name == "old_applied":
                    store.set_status(role.uid, "applied")
            store.conn.commit()
        run.cfg_now.freshness.show_days = 30
        d = json.loads(run.get("/api/roles?scope=open")[1])
        assert {r["company"] for r in d["roles"]} == {"Acme", "old_applied"}
        assert d["older"] == 1 and d["show_days"] == 30
        d = json.loads(run.get("/api/roles?scope=open&older=1")[1])
        assert len(d["roles"]) == 3 and d["older"] == 0
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



def test_a_token_in_the_url_cannot_change_anything():
    """The query is for the first page load only. A POST carrying it there,
    as a form on another site could, is refused: only a header counts."""
    def check(run):
        code, _ = run.post(f"/api/action?t={run.token}",
                           {"uid": run.uid, "status": "applied"}, token=None)
        assert code == 401
        with Store(run.cfg.db_path) as store:
            assert store.get(run.uid)["status"] == "new"
    _with_server(check)


def test_the_page_refuses_to_be_framed():
    def check(run):
        request = urllib.request.Request(f"{run.base}/?t={run.token}")
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.headers["X-Frame-Options"] == "DENY"
            policy = response.headers["Content-Security-Policy"]
            assert "frame-ancestors 'none'" in policy
            # The tab icon is inline (data:); no image comes from the network.
            assert "img-src data:;" in policy and "http" not in policy
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


def test_a_browser_hanging_up_is_not_reported_as_an_error():
    """A dropped keep-alive printed a full traceback; a real error still does."""
    import contextlib
    import io
    import socket

    server = serve_mod.Server(("127.0.0.1", 0), serve_mod.BaseHTTPRequestHandler)
    try:
        for exc, printed in ((ConnectionResetError(54, "reset"), False),
                             (BrokenPipeError(), False), (ValueError("real"), True)):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), socket.socket() as sock:
                try:
                    raise exc
                except Exception:
                    server.handle_error(sock, ("127.0.0.1", 1))
            assert bool(err.getvalue()) == printed, (exc, err.getvalue())
    finally:
        server.server_close()


def test_only_a_container_binds_beyond_loopback():
    """The variable alone must not open the socket: it needs the marker too."""
    import os
    saved_env = os.environ.pop(serve_mod.CONTAINER_ENV, None)
    saved_markers = serve_mod.CONTAINER_MARKERS
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / ".dockerenv"
        try:
            serve_mod.CONTAINER_MARKERS = (str(marker),)
            os.environ[serve_mod.CONTAINER_ENV] = "1"
            assert serve_mod.bind_address() == "127.0.0.1", "variable alone"
            marker.touch()
            assert serve_mod.bind_address() == "0.0.0.0"
            del os.environ[serve_mod.CONTAINER_ENV]
            assert serve_mod.bind_address() == "127.0.0.1", "marker alone"
        finally:
            serve_mod.CONTAINER_MARKERS = saved_markers
            os.environ.pop(serve_mod.CONTAINER_ENV, None)
            if saved_env is not None:
                os.environ[serve_mod.CONTAINER_ENV] = saved_env


def test_named_addresses_may_open_the_dashboard_and_nothing_else():
    """A NAS: opened from a Mac by its address, on whatever port it published.
    The token is still required, and a wildcard is refused."""
    import os
    saved = os.environ.get(serve_mod.ALLOW_ENV)
    os.environ[serve_mod.ALLOW_ENV] = "192.168.1.50, nas.local:9000, *, 0.0.0.0"
    try:
        assert serve_mod.allowed_extra_hosts() == ["192.168.1.50", "nas.local:9000"]
        assert serve_mod.bind_address() == "0.0.0.0"

        def check(run):
            assert run.get("/api/roles", host="192.168.1.50:41902")[0] == 200
            assert run.get("/api/roles", host="192.168.1.50")[0] == 200
            assert run.get("/api/roles", host="nas.local:9000")[0] == 200
            assert run.get("/api/roles", host="nas.local:9001")[0] == 421
            assert run.get("/api/roles", host="evil.example")[0] == 421
            assert run.get("/api/roles", host="192.168.1.50", token=None)[0] == 401
        _with_server(check)
    finally:
        if saved is None:
            os.environ.pop(serve_mod.ALLOW_ENV, None)
        else:
            os.environ[serve_mod.ALLOW_ENV] = saved


def test_ollama_is_asked_for_room_for_the_whole_prompt():
    """Ollama cuts a prompt that does not fit, silently; so jobdork says how
    much room to use, the same on every call, from llm.context."""
    from jobdork.ai import llm
    sent = {}
    saved = llm._post
    llm._post = lambda url, body, headers, timeout: sent.update(body) or {"message": {"content": "{}"}}
    try:
        llm._ollama(llm.Settings("ollama", "qwen2.5:3b"), "sys", "user", {"type": "object"}, 100)
        assert sent["options"]["num_ctx"] == llm.DEFAULT_CONTEXT
        llm._ollama(llm.Settings("ollama", "m", context=8192), "sys", "user", {"type": "object"}, 100)
        assert sent["options"]["num_ctx"] == 8192
    finally:
        llm._post = saved

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
        assert run.cfg_now.locations.cities == ["Berlin, Germany"]
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


def _post_json(run, path, payload):
    request = urllib.request.Request(
        f"{run.base}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Jobdork-Token": run.token})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_dealbreakers_are_saved_from_the_page_and_a_broken_pattern_is_refused():
    def check(run):
        code, saved = _post_json(run, "/api/config", {"dealbreakers": [
            {"name": "Clearance", "pattern": "security clearance|TS/SCI", "hard": True},
            {"name": "Travel", "pattern": "travel \\d+%", "hard": False}]})
        assert code == 200, saved
        assert [(d["name"], d["hard"]) for d in saved["dealbreakers"]] == [
            ("Clearance", True), ("Travel", False)]
        assert run.cfg_now.dealbreakers[0].regex.search("Needs TS/SCI")

        before = Path(run.config_path).read_text(encoding="utf-8")
        code, body = _post_json(run, "/api/config", {"dealbreakers": [
            {"name": "Broken", "pattern": "(unclosed", "hard": True}]})
        assert code == 400 and "broken pattern" in body, body
        assert Path(run.config_path).read_text(encoding="utf-8") == before
    _with_server(check)


def test_boards_are_removed_from_the_page_and_an_unknown_type_is_refused():
    def check(run):
        code, saved = _post_json(run, "/api/config", {"companies": [
            {"name": "Acme", "platform": "ashby", "token": "acme"},
            {"name": "Beta", "platform": "lever", "token": "beta"}]})
        assert code == 200, saved
        code, saved = _post_json(run, "/api/config", {"companies": [
            {"name": "Beta", "platform": "lever", "token": "beta"}]})
        assert [c["name"] for c in saved["companies"]] == ["Beta"]
        code, body = _post_json(run, "/api/config", {"companies": [
            {"name": "Nope", "platform": "myspace", "token": "x"}]})
        assert code == 400, body
        assert [c.name for c in run.cfg_now.sources.companies] == ["Beta"]
    _with_server(check)


def test_a_config_changed_on_disk_is_picked_up_by_the_next_request():
    """`Look and add` writes the file from a job; the page must see it."""
    def check(run):
        import os
        path = Path(run.config_path)
        path.write_text(path.read_text(encoding="utf-8").replace(
            "software engineer", "platform engineer"), encoding="utf-8")
        later = path.stat().st_mtime + 5
        os.utime(path, (later, later))
        code, body = run.get("/api/config")
        assert code == 200
        assert json.loads(body)["titles_include"] == ["platform engineer"]
    _with_server(check)


def test_dealbreakers_are_words_tried_and_saved_through_the_server():
    """Words, not a pattern: "try it" asks Python, and a save keeps the words."""
    def check(run):
        code, found = _post_json(run, "/api/dealbreakers/try", {
            "words": ["security clearance"], "text": "Requires an active TS/SCI clearance."})
        assert code == 200 and found["found"] == "TS/SCI", found
        code, found = _post_json(run, "/api/dealbreakers/try", {
            "words": "us citizen", "text": "You do not need to be a U.S. citizen."})
        assert code == 200 and found["found"] == "", found
        code, found = _post_json(run, "/api/dealbreakers/try", {"pattern": "on.?call(", "text": "x"})
        assert code == 400
        code, saved = _post_json(run, "/api/config", {"dealbreakers": [
            {"name": "US citizen", "words": ["us citizen"], "hard": True},
            {"name": "On-call", "pattern": "on.?call", "hard": False}]})
        assert code == 200, saved
        assert [(d["name"], d["words"], d["pattern"]) for d in saved["dealbreakers"]] == [
            ("US citizen", ["us citizen"], ""), ("On-call", [], "on.?call")]
        assert {k["name"] for k in saved["dealbreaker_suggestions"]} >= {
            "Security clearance", "US citizen", "Client-site travel"}
    _with_server(check)


def test_delete_all_scanned_needs_the_previewed_count():
    def check(run):
        code, preview = _post_json(run, "/api/scan/fresh/preview", {})
        assert code == 200, preview
        code, body = _post_json(run, "/api/scan/delete", {"expect": preview["count"] + 1})
        assert code == 409, body
        code, body = _post_json(run, "/api/scan/delete", {"expect": "x"})
        assert code == 400, body
    _with_server(check)


def test_previews_answer_an_empty_form_as_a_browser_sends_it():
    # fetch() with an empty URLSearchParams sends Content-Length 0; both
    # previews refused that as "bad request body", so Start over and the
    # stale-post clean-up never got past their first step in a browser.
    def check(run):
        for path in ("/api/start-over/preview", "/api/cleanup/aged/preview"):
            code, body = run.post(path, {})
            assert code == 200, (path, body)
        code, body = run.post("/api/start-over", {})
        assert code == 400, body                 # the real thing still needs the words
    _with_server(check)


def test_saving_a_project_re_scores_the_job_posts():
    """Fit scores count a project's skills, so a saved one re-scores."""
    import json
    import time

    def check(run):
        resume = Path(run.tmp.name) / "resume.md"
        resume.write_text("Jo Bloggs\nEngineer.\n", encoding="utf-8")
        run.holder["cfg"].resume_path = str(resume)
        run.real_queue()
        code, body = run.post("/api/projects/save", {"name": "Rota tool",
                                                     "kind": "App or software"})
        assert code == 200, body
        answer = json.loads(body)
        assert answer["project"]["kind"] == "App or software"
        assert answer["rescore"].startswith("Re-scoring"), answer
        for _ in range(50):
            if not run.runner.busy:
                break
            time.sleep(0.1)
        code, body = run.post("/api/projects/save", {"name": "X", "kind": "Juggling"})
        assert code == 400 and b"kind of project" in body
    _with_server(check)


def test_a_request_that_crashes_is_logged_for_warnings_and_errors():
    import logging

    caught = []

    class Catch(logging.Handler):
        def emit(self, record):
            caught.append((record.getMessage(), record.exc_info and record.exc_info[1]))

    handler = Catch(logging.ERROR)
    logging.getLogger("jobdork.web.serve").addHandler(handler)
    saved = serve_mod.api_mod.list_projects

    def broken(cfg):
        raise RuntimeError("database exploded")
    serve_mod.api_mod.list_projects = broken
    try:
        def check(run):
            with contextlib.suppress(Exception):   # the connection drops: no answer
                run.get("/api/projects")
            code, body = run.post("/api/page-problem", {"level": "warning",
                                                        "text": "shown to you: no"})
            assert code == 200, body
            code, _ = run.post("/api/page-problem", {"level": "warning"}, token=None)
            assert code == 401
        _with_server(check)
    finally:
        serve_mod.api_mod.list_projects = saved
        logging.getLogger("jobdork.web.serve").removeHandler(handler)
    assert caught[0][0] == "a request to the dashboard failed", caught
    assert "database exploded" in str(caught[0][1])


def test_the_favicon_is_answered_without_the_token():
    def check(run):
        code, body = run.get("/favicon.ico", token=None)
        assert code == 204 and body == b"", (code, body)
        code, _ = run.get("/favicon.ico", host="evil.test", token=None)
        assert code == 421
    _with_server(check)


def test_where_you_are_is_saved_from_the_picker_and_must_resolve():
    def check(run):
        code, body = run.get("/api/places/cities?country=PH&q=bagu")
        assert code == 200 and "Baguio" in json.loads(body)["cities"]
        code, saved = _post_json(run, "/api/config", {"places_pick": {
            "country": "PH", "cities": [{"region": "15", "city": "Baguio"}]}})
        assert code == 200, saved
        city = saved["places"]["cities"][0]
        assert city["text"] == "Baguio, Cordillera, Philippines"
        assert city["located"] and city["region"] == "15"
        code, body = _post_json(run, "/api/config", {"places_pick": {
            "country": "PH", "cities": [{"region": "", "city": "Atlantis"}]}})
        assert code == 400 and "suggestions" in body, body
        assert run.cfg_now.locations.cities == ["Baguio, Cordillera, Philippines"]
    _with_server(check)


def test_countries_are_saved_as_a_list_from_the_page():
    def check(run):
        code, saved = _post_json(run, "/api/config", {"countries": ["PH", "US"]})
        assert code == 200 and saved["countries"] == ["PH", "US"], saved
        code, saved = _post_json(run, "/api/config", {"countries": ["US"]})
        assert saved["countries"] == ["US"]
        assert run.cfg_now.locations.countries == ["US"]
    _with_server(check)


def _letter(run, folder: Path) -> tuple[int, int, Path]:
    """Record a cover letter as writer.letter would: file, output, artifact."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "cover-letter-ai.md"
    path.write_text("Dear team,\n\nI would like the job.\n", encoding="utf-8")
    with Store(run.cfg.db_path) as store:
        out = store.add_ai_output("cover_letter", "Dear team, I would like the job.",
                                  uid=run.uid, model="test")
        art = store.add_artifact(run.uid, "cover_letter", str(path),
                                 gates={"guard": {"output_id": out}})
        store.conn.commit()
    return art, out, path


def test_a_cover_letter_is_listed_viewed_and_deleted_at_once():
    def check(run):
        art, out, path = _letter(run, Path(run.tmp.name) / "docs" / "job")
        code, body = run.get("/api/letters")
        letters = json.loads(body)["letters"]
        assert code == 200 and [x["id"] for x in letters] == [art]
        assert letters[0]["company"] == "Acme" and letters[0]["exists"]
        code, body = run.get(f"/api/artifact?id={art}")
        assert code == 200 and "would like the job" in json.loads(body)["text"]

        code, body = run.post("/api/letters/delete", {"id": art})
        assert code == 200, body
        assert not path.exists()
        with Store(run.cfg.db_path) as store:
            assert store.conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0
            # The text is gone; the claim counts the chart is built from stay.
            assert store.conn.execute("SELECT text FROM ai_outputs WHERE id = ?",
                                      (out,)).fetchone()[0] == ""
        assert json.loads(run.get("/api/letters")[1])["letters"] == []
    _with_server(check)


def test_an_uploaded_resume_is_deleted_but_your_own_file_is_only_unset():
    def check(run):
        request = urllib.request.Request(
            f"{run.base}/api/resume", data=b"# Me\n\nPython, SQL, Docker, AWS, Linux, Git\n" * 20,
            headers={"X-Filename": "cv.md", "X-Jobdork-Token": run.token,
                     "Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(request, timeout=5) as response:
            uploaded = Path(json.loads(response.read())["path"])
        assert uploaded.is_file() and uploaded.name == "resume.md"
        code, body = run.post("/api/resume/delete", {})
        assert code == 200 and json.loads(body)["deleted"] is True, body
        assert not uploaded.exists() and run.cfg_now.resume_path == ""

        mine = Path(run.tmp.name) / "my-own-cv.md"
        mine.write_text("# Me\n\nPython\n", encoding="utf-8")
        code, _ = _post_json(run, "/api/config", {"resume_path": str(mine)})
        assert code == 200
        code, body = run.post("/api/resume/delete", {})
        assert code == 200 and json.loads(body)["deleted"] is False, body
        assert mine.is_file(), "a file you chose must never be deleted"
        assert run.cfg_now.resume_path == ""
    _with_server(check)


def test_a_resume_with_an_encoded_name_is_saved_by_its_extension():
    """The page sends the name encoded (a header takes Latin-1 only);
    only the extension matters, and it survives the encoding."""
    def check(run):
        request = urllib.request.Request(
            f"{run.base}/api/resume", data=b"# Me\n\nPython, SQL, Docker, AWS, Linux, Git\n" * 20,
            headers={"X-Filename": urllib.parse.quote("Maria’s Resume – 2026.md"),
                     "X-Jobdork-Token": run.token,
                     "Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(request, timeout=5) as response:
            uploaded = Path(json.loads(response.read())["path"])
        assert uploaded.is_file() and uploaded.name == "resume.md"
    _with_server(check)


def test_in_a_container_the_resume_and_letters_are_kept_unless_asked_otherwise():
    """JOBDORK_DOCS_DIR keeps them in the volume; JOBDORK_TEMP_DOCS, opt-in, wins."""
    import os

    from jobdork.core import storage
    with tempfile.TemporaryDirectory() as tmp:
        saved = {k: os.environ.get(k) for k in (storage.DOCS_ENV, storage.TEMP_ENV)}
        try:
            os.environ.pop(storage.TEMP_ENV, None)
            os.environ[storage.DOCS_ENV] = str(Path(tmp) / "data" / "documents")
            cfg = Config(titles_include=["x"])
            assert storage.resume_dir(cfg) == Path(tmp) / "data" / "documents" / "resume"
            assert storage.documents_root() == Path(tmp) / "data" / "documents" / "job-applications"
            assert storage.temp_root() is None and storage.wipe() == 0   # nothing emptied
            os.environ[storage.TEMP_ENV] = str(Path(tmp) / "temp")
            assert storage.resume_dir(cfg) == Path(tmp) / "temp" / "resume"
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_docker_without_a_mounted_data_folder_is_warned():
    """No -v for /app/data: the data goes with the container, and the page says so."""
    from jobdork.core import config as config_mod
    from jobdork.core import storage

    line = "36 35 98:0 / {} rw,relatime - overlay overlay rw\n"
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "app" / "data"
        data.mkdir(parents=True)
        cfg = Config(titles_include=["x"], db_path=str(data / "jobdork.db"))
        plain, mounted = Path(tmp) / "plain", Path(tmp) / "mounted"
        plain.write_text(line.format("/"))
        mounted.write_text(line.format("/") + line.format(data.resolve()))
        saved = config_mod.in_container
        try:
            config_mod.in_container = lambda: True
            assert storage.unkept_data_dir(cfg, plain) == str(data.resolve())
            assert storage.unkept_data_dir(cfg, mounted) == ""
            config_mod.in_container = lambda: False           # not in a container
            assert storage.unkept_data_dir(cfg, plain) == ""
        finally:
            config_mod.in_container = saved


def test_the_temporary_folder_is_emptied_and_forgotten():
    """In a container, nothing personal outlives a run: files and records."""
    import os

    from jobdork.core import config, storage
    from jobdork.web import api
    def check(run):
        temp = Path(run.tmp.name) / "temp"
        saved = os.environ.get(storage.TEMP_ENV)
        os.environ[storage.TEMP_ENV] = str(temp)
        try:
            _, _, path = _letter(run, temp / "job-applications" / "job")
            resume = temp / "resume" / "resume.md"
            resume.parent.mkdir(parents=True)
            resume.write_text("# Me\n\nPython\n", encoding="utf-8")
            run.cfg.resume_path = str(resume)
            assert api.forget_temporary(run.cfg) == 2
            assert not path.exists() and not resume.exists()
            assert run.cfg.resume_path == ""
            with Store(run.cfg.db_path) as store:
                assert store.conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0

            # A config still naming the vanished resume loads, with a warning.
            cfg_file = Path(run.config_path)
            cfg_file.write_text(cfg_file.read_text() + f"resume: {{path: '{resume}'}}\n")
            loaded = config.load(str(cfg_file))
            assert loaded.resume_path == "" and any("temporary" in w for w in loaded.warnings)
        finally:
            if saved is None:
                os.environ.pop(storage.TEMP_ENV, None)
            else:
                os.environ[storage.TEMP_ENV] = saved
    _with_server(check)


def test_a_first_run_serves_setup_and_writes_the_config_when_answered():
    from jobdork.core.config import Config

    def check(run):
        target = Path(run.tmp.name) / "data" / "config.yaml"
        run.holder["cfg"] = Config(path=str(target), setup_step="welcome",
                                   db_path=run.cfg.db_path)
        code, body = run.get("/api/state")
        state = json.loads(body)
        assert code == 200 and state["setup"]["step"] == "welcome"
        assert state["setup"]["steps"][0]["name"] == "welcome"

        code, _ = run.post("/api/scan", {})
        assert code == 409, "nothing to search for yet"
        assert not target.exists()

        code, _ = _post_json(run, "/api/config", {"setup_step": "resume"})
        assert code == 200 and target.is_file()
        assert json.loads(run.get("/api/state")[1])["setup"]["step"] == "resume"
    _with_server(check)


def test_setup_offers_industries_and_dealbreakers_and_saves_industries():
    def check(run):
        code, body = run.get("/api/setup/choices")
        choices = json.loads(body)
        assert code == 200 and "healthcare" in choices["industries"]
        assert any(d["name"] == "Night shift" for d in choices["dealbreakers"])
        assert choices["chosen"]["titles"] == ["software engineer"]
        code, _ = _post_json(run, "/api/config", {"industries": ["Healthcare"]})
        assert code == 200
        assert run.holder["cfg"].sources.directory.industries == ["healthcare"]
    _with_server(check)


def _idle(runner):
    import time as _time
    for _ in range(100):
        if not runner.busy:
            return
        _time.sleep(0.05)
    raise AssertionError(f"still running {runner.current}")


def test_a_queued_job_waits_and_runs_once_from_the_newest_settings():
    runner, ran, gate = Runner(), [], threading.Event()

    def blocking(progress):
        gate.wait(5)
        ran.append("scan")

    assert runner.start("scan", blocking)[0]
    settings = {"v": 1}
    # lambda: builds the work when its turn comes, reading the settings then.
    make = lambda: (lambda progress: ran.append(("rescreen", settings["v"])))  # noqa: E731
    assert runner.queue("rescreen", make) is False
    settings["v"] = 2
    assert runner.queue("rescreen", make) is False      # still one waiting
    assert runner.waiting() == ["rescreen"]
    gate.set()
    _idle(runner)
    assert ran == ["scan", ("rescreen", 2)]
    # Idle: it starts at once.
    assert runner.queue("rescreen", make) is True
    _idle(runner)


def test_what_a_search_change_starts():
    old = Config(titles_include=["nurse"], locations=Locations(countries=["US"]))
    same = Config(titles_include=["Nurse"], locations=Locations(countries=["US"]))
    assert serve_mod.search_changes(old, same) == (False, True)   # case is a change to screen
    more = Config(titles_include=["nurse", "midwife"], locations=Locations(countries=["US"]))
    assert serve_mod.search_changes(old, more) == (True, True)
    fewer = Config(titles_include=[], locations=Locations(countries=["US"]))
    assert serve_mod.search_changes(old, fewer) == (False, True)
    abroad = Config(titles_include=["nurse"], locations=Locations(countries=["US", "CA"]))
    assert serve_mod.search_changes(old, abroad)[0]
    copy = Config(titles_include=["nurse"], locations=Locations(countries=["US"]))
    assert serve_mod.search_changes(old, copy) == (False, False)


def test_removing_a_title_re_screens_and_adding_one_scans():
    """2026-10-23: the search applies itself; nothing to press afterwards."""
    started = []
    saved = serve_mod.api_mod.scan_job, serve_mod.api_mod.rescreen_job
    # lambda: stand-ins that record which job ran, so no scan goes online.
    serve_mod.api_mod.scan_job = lambda cfg, part="all": (lambda p: started.append("scan"))
    # lambda: as above, for the re-screen, recording whether it removes.
    serve_mod.api_mod.rescreen_job = lambda cfg, remove=False: (
        lambda p: started.append(("rescreen", remove)))
    try:
        def check(run):
            run.real_queue()
            code, body = _post_json(run, "/api/config", {"titles_include": [
                "software engineer", "platform engineer"]})
            assert code == 200, body
            assert body["rescan"].startswith("Re-applying your search"), body["rescan"]
            assert "for what you added" in body["rescan"]
            _idle(run.runner)
            code, body = _post_json(run, "/api/config", {"titles_include": ["platform engineer"]})
            assert code == 200 and "Scanning" not in body["rescan"], body
            _idle(run.runner)
            code, body = _post_json(run, "/api/config", {"show_days": 14})
            assert code == 200 and body["rescan"] == "", body
            _idle(run.runner)
        _with_server(check)
    finally:
        serve_mod.api_mod.scan_job, serve_mod.api_mod.rescreen_job = saved
    assert started == [("rescreen", True), "scan", ("rescreen", True)], started


def test_a_chain_runs_its_jobs_in_turn_and_stops_at_a_failure():
    import time as _time
    runner, ran = Runner(), []

    def job(name, fail=False):
        def work(progress):
            ran.append((name, runner.current))
            if fail:
                raise RuntimeError("boom")
            return name
        return work
    runner.start("first", job("first"), then=[("second", job("second", fail=True)),
                                             ("third", job("third"))])
    for _ in range(50):
        if not runner.busy:
            break
        _time.sleep(0.05)
    assert ran == [("first", "first"), ("second", "second")]
    assert runner.current == "" and runner.last_summary == "second failed"


def test_the_first_scan_starts_only_at_setups_last_step():
    from jobdork.core import setup

    def check(run):
        code, _ = run.post("/api/setup/scan", {})
        assert code == 409, "a set-up config does not run setup's scan"
        resume = Path(run.tmp.name) / "r.md"
        resume.write_text("# Me\n\nNurse\n", encoding="utf-8")
        target = Path(run.tmp.name) / "setup.yaml"
        # Its own database: reloading a config without `db:` would point at
        # data/jobdork.db in whatever folder the tests run from.
        target.write_text(f"db: {run.cfg.db_path}\n", encoding="utf-8")
        run.holder["cfg"] = setup.write(str(target), {
            "resume_path": str(resume), "titles_include": ["nurse"],
            "anchor": "Chicago, IL", "setup_step": "scan"})
        saved = serve_mod.api_mod.first_scan_jobs
        serve_mod.api_mod.first_scan_jobs = lambda cfg: [
            ("first scan", lambda progress: "quick"), ("full scan", lambda progress: "rest")]
        try:
            code, body = run.post("/api/setup/scan", {})
        finally:
            serve_mod.api_mod.first_scan_jobs = saved
        assert code == 202 and json.loads(body)["job"] == "first scan"
        # Setup ends when the scan starts: the page goes to the Dashboard.
        assert run.holder["cfg"].setup_step == ""
        assert "setup:" not in target.read_text()
    _with_server(check)


def test_your_credentials_are_saved_and_an_advert_is_checked_against_them():
    def check(run):
        code, saved = _post_json(run, "/api/config", {"credentials": ["IAT I", "CISSP"]})
        assert code == 200 and saved["credentials"] == ["IAT I", "CISSP"]
        with serve_mod.Store(run.cfg.db_path) as store:
            store.conn.execute(
                "UPDATE roles SET description = ? WHERE uid = ?",
                ("Certifications (one or more required):\nIAT I\nCISSP or CISM required",
                 run.uid))
            store.conn.commit()
        detail = json.loads(run.get(f"/api/role?uid={run.uid}")[1])
        assert [(c["line"], c["have"]) for c in detail["credentials"]] == [
            ("IAT I", ["IAT I"]), ("CISSP or CISM required", ["CISSP"])]
    _with_server(check)


# ── the desktop app's links and files ─────────────────────────────────────────

def test_the_desktop_apps_calls_go_through_the_server_with_the_token():
    """The app's window asks for links and files by POST /api/desk, not
    pywebview's js_api (built with eval, which the page's policy refuses).
    Only the app has a desk; a browser gets 404."""
    class Desk:
        BODY_LIMIT = 4096
        calls = []

        def call(self, name, args):
            if name != "open_url":
                raise ValueError("not something the app does")
            self.calls.append((name, args))
            return True

    def check(run):
        code, _ = _post_json(run, "/api/desk", {"call": "open_url", "args": ["https://a.example/"]})
        assert code == 404, "a browser has no desk"
        desk = Desk()
        run.server.RequestHandlerClass = serve_mod.make_handler(
            run.holder, run.session, run.runner, desk)
        code, body = _post_json(run, "/api/desk", {"call": "open_url", "args": ["https://a.example/"]})
        assert (code, body) == (200, {"value": True}) and desk.calls == [
            ("open_url", ["https://a.example/"])]
        code, body = _post_json(run, "/api/desk", {"call": "forget", "args": []})
        assert code == 400 and "not something" in body
        code, _ = _post_json(run, "/api/desk", {"call": "open_url", "args": ["x" * 5000]})
        assert code == 400, "over the desk's size limit"
        code, _ = run.post("/api/desk", {"call": "open_url"}, token=None)
        assert code == 401
        assert len(desk.calls) == 1
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

    secret = "sk-test-never-echo-0123456789"  # gitleaks:allow (a fake key the test sends)

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


# ── the scan schedule, the folders, a newer version ───────────────────────────


def test_the_schedule_is_saved_and_read_back_through_the_page():
    from jobdork.core import schedule

    calls = []

    def run_cmd(argv, **kw):
        calls.append(argv)
        return type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    def check(run):
        agent = schedule.LaunchAgent(folder=Path(run.tmp.name) / "agents",
                                     run=run_cmd, uid=1)
        saved = schedule.scheduler, schedule.unsupported
        # lambda: every request gets this stand-in instead of the real launchd.
        schedule.scheduler = lambda: agent
        # lambda: as on a Mac, whatever machine the tests run on.
        schedule.unsupported = lambda: ""
        try:
            code, body = run.get("/api/schedule")
            assert code == 200 and json.loads(body) == {"supported": True, "on": False}
            code, body = run.post("/api/schedule", {"every": "weekly", "at": "07:00",
                                                    "day": "tue"})
            state = json.loads(body)
            assert code == 200 and state["on"] and state["describe"] == "every Tuesday at 07:00"
            assert agent.path.is_file()
            code, body = run.post("/api/schedule", {"every": "hourly", "at": "07:00"})
            assert code == 400 and b"every must be" in body
            code, body = run.post("/api/schedule", {"every": "off"})
            assert code == 200 and not json.loads(body)["on"] and not agent.path.exists()
        finally:
            schedule.scheduler, schedule.unsupported = saved
    _with_server(check)


def test_the_folders_are_listed_and_only_opened_on_this_machine():
    from jobdork.web import app as app_mod

    opened = []

    def check(run):
        code, body = run.get("/api/folders")
        report = json.loads(body)
        assert code == 200 and set(report["folders"]) == {"settings", "backups", "logs",
                                                          "documents"}
        assert report["folders"]["settings"]["path"] == str(Path(run.tmp.name).resolve())
        saved = app_mod.open_with_system
        app_mod.open_with_system = opened.append
        try:
            code, _ = run.post("/api/folders/open", {"which": "settings"})
            assert code == 200 and opened == [Path(run.tmp.name).resolve()]
            code, body = run.post("/api/folders/open", {"which": "backups"})
            assert code == 404 and b"does not exist yet" in body
            code, _ = run.post("/api/folders/open", {"which": "/etc"})
            assert code == 400
            os.environ["JOBDORK_ALLOW_HOSTS"] = "nas.local"
            try:
                code, _ = run.post("/api/folders/open", {"which": "settings"})
                assert code == 409
            finally:
                os.environ.pop("JOBDORK_ALLOW_HOSTS")
        finally:
            app_mod.open_with_system = saved
        assert len(opened) == 1
    _with_server(check)


def test_the_version_check_is_off_in_tests():
    def check(run):
        code, body = run.get("/api/version")
        assert code == 200 and json.loads(body)["newer"] is False
    _with_server(check)


def test_the_built_in_boards_are_listed_with_why_each_is_read_or_not():
    def check(run):
        code, body = run.get("/api/directory")
        d = json.loads(body)
        assert code == 200 and d["enabled"] and d["total"] == len(d["boards"]) > 300
        read = [b for b in d["boards"] if not b["why"]]
        assert d["read"] == len(read) and all("US" in b["countries"] for b in read)
        assert any(b["why"] == "hires outside your countries" for b in d["boards"])
        assert sum(v["boards"] for v in d["by_industry"].values()) == d["total"]
    _with_server(check)


def test_the_page_reads_and_writes_the_update_check():
    def check(run):
        code, body = run.get("/api/config")
        state = json.loads(body)
        assert code == 200 and state["update_check"] is True
        assert state["update_check_env_off"] is True          # the tests set it off
        code, body = run.post("/api/config", {"update_check": "false"})
        assert code == 200 and json.loads(body)["update_check"] is False
        assert run.queued == []                                # nothing to re-screen
    _with_server(check)
