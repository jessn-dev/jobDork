"""
Tests for the Feedback page's report (core/feedback.py): what it lets out of
the machine, what it refuses, and that it reaches a relay.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.core import feedback
from jobdork.core.config import Config

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


def _form(**over):
    form = {"kind": "problem", "title": "Scan stops", "details": "It stops.",
            "logs": True, "app": True}
    form.update(over)
    return form


def _refused(form, problems=(), want=""):
    try:
        feedback.build(form, Config(), list(problems))
    except feedback.FeedbackError as exc:
        assert want in str(exc), exc
        return
    raise AssertionError(f"accepted {form}")


def test_scrub_takes_out_keys_tokens_emails_addresses_and_home():
    home = str(Path.home())
    text = feedback.scrub(
        f"key sk-ant-api03-abcdefghijklmnop1234 at {home}/jobdork/data, "
        "AIzaSyA1234567890abcdefghij and ?t=setuptesttoken1234567890abcdef "
        "from me@example.com via 100.77.91.66 and 127.0.0.1")
    for gone in ("abcdefghijklmnop1234", home, "AIzaSyA1234567890",
                 "setuptesttoken", "me@example.com", "100.77.91.66"):
        assert gone not in text, (gone, text)
    assert "~/jobdork/data" in text and "?t=[removed]" in text
    assert "127.0.0.1" in text


def test_the_logs_go_only_when_ticked_and_are_scrubbed():
    problems = [{"at": "2026-10-20T10:00:00", "level": "warning", "job": "scan",
                 "text": "adzuna refused key app_key=deadbeef99"}]
    with_logs = feedback.build(_form(), Config(), problems)
    assert "deadbeef99" not in with_logs.text()
    assert "WARNING [scan] adzuna refused key app_key=[removed]" in with_logs.text()
    assert "Warnings and errors" not in feedback.build(
        _form(logs=False), Config(), problems).text()


def test_the_reply_address_never_goes_in_the_public_text():
    report = feedback.build(_form(reply_to="me@example.com"), Config(), [])
    assert "me@example.com" not in report.text()
    assert "me@example.com" not in report.issue_url()
    assert report.payload()["reply_to"] == "me@example.com"


def test_what_cannot_be_sent_is_refused():
    _refused(_form(kind="rant"), want="problem")
    _refused(_form(title="  "), want="title")
    _refused(_form(title="x" * 121), want="title")
    _refused(_form(details="x" * 8001), want="details")
    _refused(_form(reply_to="not an address"), want="email")
    _refused(_form(screenshots=[{"name": "a.gif", "type": "image/gif", "data": PNG}]),
             want="PNG")
    _refused(_form(screenshots=[{"name": "a.png", "type": "image/png", "data": "!!"}]),
             want="screenshot")
    big = base64.b64encode(b"0" * (feedback.MAX_SHOT_BYTES + 1)).decode()
    _refused(_form(screenshots=[{"name": "a.png", "type": "image/png", "data": big}]),
             want="2 MB")
    shot = {"name": "a.png", "type": "image/png", "data": PNG}
    _refused(_form(screenshots=[shot] * 4), want="at most 3")


def test_a_screenshot_name_cannot_carry_a_path():
    report = feedback.build(_form(screenshots=[
        {"name": "../../etc/pass<wd>.png", "type": "image/png", "data": PNG}]), Config(), [])
    assert report.screenshots[0]["name"] == "pass_wd_.png"


def test_a_long_report_still_makes_an_address_a_browser_opens():
    problems = [{"at": "2026-10-20T10:00:00", "level": "error", "source": "app",
                 "text": "x " * 240} for _ in range(60)]
    url = feedback.build(_form(details="y " * 3000), Config(), problems).issue_url()
    assert len(url) <= feedback.MAX_ISSUE_URL
    assert url.startswith(feedback.ISSUES_URL)
    assert "cut+to+fit" in url


def test_without_a_relay_sending_says_what_to_do_instead():
    os.environ.pop("JOBDORK_FEEDBACK_URL", None)
    report = feedback.build(_form(), Config(), [])
    try:
        feedback.send(report)
    except feedback.FeedbackError as exc:
        assert "GitHub issue" in str(exc)
    else:
        raise AssertionError("sent with no relay")
    try:
        feedback.send(report, "http://relay.example.com/")
    except feedback.FeedbackError as exc:
        assert "https" in str(exc)
    else:
        raise AssertionError("sent over plain http")


def test_a_report_reaches_the_relay_as_previewed():
    got = {}

    class _Relay(BaseHTTPRequestHandler):
        def do_POST(self):
            got.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({"issue_url": "https://github.com/x/y/issues/1"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Relay)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        report = feedback.build(_form(screenshots=[
            {"name": "a.png", "type": "image/png", "data": PNG}]), Config(), [])
        answer = feedback.send(report, f"http://localhost:{server.server_port}/")
    finally:
        server.shutdown()
        server.server_close()
    assert answer["issue_url"].endswith("/issues/1")
    assert got["title"] == "[Problem] Scan stops"
    assert got["body"] == report.text()
    assert got["screenshots"][0]["data"] == PNG


def test_the_dashboard_previews_a_report():
    from test_serve import _with_server

    def check(run):
        request = urllib.request.Request(
            run.base + "/api/report/preview", data=json.dumps(_form()).encode(),
            headers={"Content-Type": "application/json", "X-Jobdork-Token": run.token})
        with urllib.request.urlopen(request, timeout=5) as response:
            shown = json.loads(response.read())
        assert shown["subject"] == "[Problem] Scan stops"
        assert "It stops." in shown["text"] and "### App" in shown["text"]
        assert shown["issue_url"].startswith(feedback.ISSUES_URL)

        bad = urllib.request.Request(
            run.base + "/api/report/preview", data=json.dumps(_form(kind="x")).encode(),
            headers={"Content-Type": "application/json", "X-Jobdork-Token": run.token})
        try:
            urllib.request.urlopen(bad, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        else:
            raise AssertionError("bad report accepted")
    _with_server(check)


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:            # SystemExit must not end the run
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
