"""
Four fixes from the code scans of 2026-11-06 (SCAN-2026-11-06.local.md):
#7 (the Ollama key sent to any address the page named), #8 (a digest
mailed to any address), F11 (the token in the browser's command line) and
#11 (a turned-away request's body left on the connection). Nothing here
goes online or touches live data.

    python tests/test_web_hardening.py
"""

from __future__ import annotations

import http.client
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_serve import _with_server

from jobdork.ai import llm
from jobdork.core.config import Config, Llm, Reader
from jobdork.web import api
from jobdork.web.session import new_session


def _raw(run, method: str, path: str, body: bytes = b"", headers: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", run.port, timeout=5)
    conn.request(method, path, body=body or None, headers=headers or {})
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp


def test_the_browser_is_opened_with_a_one_use_code_not_the_token():
    session = new_session("127.0.0.1")
    assert session.token not in session.launch_url and "?c=" in session.launch_url

    def check(run):
        code = run.session.launch_code
        first = _raw(run, "GET", f"/?c={code}")
        assert first.status == 302 and first.getheader("Location") == f"/?t={run.token}"
        assert _raw(run, "GET", f"/?c={code}").status == 401          # once only
        assert _raw(run, "GET", "/?c=wrong").status == 401
    _with_server(check)


def test_a_turned_away_post_closes_its_connection():
    def check(run):
        resp = _raw(run, "POST", "/api/notes", b"x" * 5000,
                    {"Content-Type": "application/x-www-form-urlencoded"})
        assert resp.status == 401 and resp.getheader("Connection") == "close"
        code, _ = run.get("/api/roles")
        assert code == 200
    _with_server(check)


def test_the_page_cannot_mail_a_digest():
    def check(run):
        code, _ = run.post("/api/digest", {"email": "someone@example.com"})
        assert code == 404 and run.queued == []
    _with_server(check)


def test_the_ollama_key_goes_only_to_an_address_a_saved_line_sends_it_to():
    seen = []
    was = llm.list_models
    # lambda: stands in for asking an Ollama; records what would be sent.
    llm.list_models = lambda s: seen.append((s.ollama_url, s.ollama_key)) or ["gemma4:26b"]
    try:
        cfg = Config(llm=Llm(ollama_url="http://localhost:11434", readers=[
            Reader(provider="ollama", model="gemma4:26b",
                   ollama_url="http://tunnel.example:8080", ollama_key=True)]))
        api.llm_models(cfg, "ollama", "http://tunnel.example:8080", True)
        api.llm_models(cfg, "ollama", "http://elsewhere.example:80", True)
        api.llm_models(cfg, "ollama", "", True)
    finally:
        llm.list_models = was
    assert seen == [("http://tunnel.example:8080", True),
                    ("http://elsewhere.example:80", False),
                    ("http://localhost:11434", False)]


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
