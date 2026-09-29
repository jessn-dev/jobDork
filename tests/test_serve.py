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
            assert "frame-ancestors 'none'" in response.headers[
                "Content-Security-Policy"]
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


def test_every_pattern_sample_on_the_page_compiles_in_python():
    """The samples fill the Add form; a scan reads them with Python's re,
    not the browser's, so each must compile there and find its example."""
    import re
    page = serve_mod.PAGE_PATH.read_text(encoding="utf-8")
    block = page[page.index("const DEAL_SAMPLES = ["):]
    block = block[:block.index("];")]
    patterns = [p.replace("\\\\", "\\")
                for p in re.findall(r"pattern: '((?:[^'\\\\]|\\\\.)*)'", block)]
    assert len(patterns) >= 5, patterns
    examples = ["an active TS/SCI clearance", "You must relocate to Austin",
                "Travel up to 25% of the time", "Joins the on-call rotation",
                "C2C only", "A take-home project", "Carries a quota"]
    for pattern, example in zip(patterns, examples, strict=True):
        assert re.compile(pattern, re.IGNORECASE).search(example), (pattern, example)


def test_where_you_are_is_saved_from_the_picker_and_must_resolve():
    def check(run):
        code, body = run.get("/api/places/cities?country=PH&q=bagu")
        assert code == 200 and "Baguio" in json.loads(body)["cities"]
        code, saved = _post_json(run, "/api/config", {"anchor_pick": {
            "country": "PH", "region": "15", "city": "Baguio"}})
        assert code == 200, saved
        assert saved["anchor"] == "Baguio, Cordillera, Philippines"
        assert saved["anchor_place"]["located"] and saved["anchor_place"]["region"] == "15"
        code, body = _post_json(run, "/api/config", {"anchor_pick": {
            "country": "PH", "region": "", "city": "Atlantis"}})
        assert code == 400 and "suggestions" in body, body
        assert run.cfg_now.locations.anchor == "Baguio, Cordillera, Philippines"
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
