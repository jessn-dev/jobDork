"""
The fetcher reaches public addresses only: an address from a job post must
not send the app into this machine or its network. Nothing here goes online:
names are resolved by a stand-in, and the one server is on this machine.

    python tests/test_fetch_guard.py

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jobdork.fetch import http  # noqa: E402


def _resolves_to(*ips):
    """A stand-in for socket.getaddrinfo that answers with these addresses."""
    def resolve(host, port, proto=0):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET,
                 socket.SOCK_STREAM, proto, "", (ip, port)) for ip in ips]
    return resolve


def _fails(host, port, proto=0):
    raise socket.gaierror("no such name")


def test_addresses_in_this_machine_or_its_network_are_refused():
    for url in ("http://127.0.0.1/", "http://10.0.0.5/admin", "https://192.168.1.1/",
                "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data/",
                "http://[::1]:8080/", "http://[::ffff:127.0.0.1]/", "http://[fe80::1]/",
                "http://100.100.100.100/", "http://0.0.0.0:8000/", "http://224.0.0.1/"):
        assert http.refusal(url, resolve=_fails), url


def test_public_addresses_pass():
    assert http.refusal("https://8.8.8.8/") == ""
    assert http.refusal("https://[2606:4700::1111]/") == ""
    assert http.refusal("https://boards.greenhouse.io/x",
                        resolve=_resolves_to("104.18.1.1", "2606:4700::6812:101")) == ""


def test_a_name_is_refused_if_any_address_it_gives_is_private():
    assert "network" in http.refusal("https://localhost/", resolve=_resolves_to("127.0.0.1"))
    assert http.refusal("https://jobs.example.com/",
                        resolve=_resolves_to("104.18.1.1", "192.168.0.10"))


def test_a_name_that_does_not_resolve_is_left_to_fail_by_itself():
    assert http.refusal("https://no-such-host.invalid/", resolve=_fails) == ""


def test_the_fetcher_refuses_without_connecting_or_retrying():
    fetcher = http.Fetcher("jobdork-test", timeout=2, retries=2)
    resp = fetcher.get("http://127.0.0.1:9/", expect_json=False)
    assert resp.status == 0 and resp.error.startswith("refused"), resp.error


class _Redirect(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", "http://10.0.0.1/admin")
        self.end_headers()

    def log_message(self, *args):
        pass


def test_a_redirect_into_the_network_is_refused_too():
    """A public page that redirects to a private one is checked at the hop.
    The local server stands in for the public page, so only it is let past."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Redirect)
    start = f"http://127.0.0.1:{server.server_address[1]}/job"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    real = http.checked
    # lambda: lets the stand-in public page through and checks every other hop.
    http.checked = lambda url, resolve=_fails: ("", "") if url == start else real(url, resolve)
    try:
        resp = http.Fetcher("jobdork-test", timeout=2, retries=0).get(start, expect_json=False)
    finally:
        http.checked = real
        server.shutdown()
        server.server_close()
    assert resp.status == 0 and "10.0.0.1" in resp.error, resp.error


def test_the_connection_goes_to_the_address_that_was_checked():
    """DNS rebinding: a name that answers the check with one address and the
    connection with another. Here the check is told rebind.test is the local
    server (let through as if public), and the name resolves nowhere else:
    the page loads only if the connection went to the checked address
    instead of looking the name up again. The server still sees the name."""
    seen = {}

    class _Page(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["host"] = self.headers.get("Host")
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Page)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    saved = http._getaddrinfo, http._public
    http._getaddrinfo = _resolves_to("127.0.0.1")
    # lambda: the local server stands in for a public one, for the check only.
    http._public = lambda ip: True
    try:
        resp = http.Fetcher("jobdork-test", timeout=2, retries=0).get(
            f"http://rebind.test:{port}/job", expect_json=False)
    finally:
        http._getaddrinfo, http._public = saved
        server.shutdown()
        server.server_close()
    assert resp.status == 200 and resp.body == "ok", resp.error
    assert seen["host"] == f"rebind.test:{port}", "the name is kept for Host (and TLS)"
    assert http._pinned() == {}, "the pin goes with the request"


def test_the_check_names_the_first_address_or_refuses():
    assert http.checked("https://a.test/", _resolves_to("8.8.8.8", "1.1.1.1")) == ("", "8.8.8.8")
    why, address = http.checked("https://a.test/", _resolves_to("8.8.8.8", "10.0.0.1"))
    assert "10.0.0.1" in why and address == ""
    assert http.checked("https://8.8.4.4/") == ("", "8.8.4.4")
    assert http.checked("https://a.test/", _fails) == ("", ""), "left to fail by itself"


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
