"""
Claude Security F2 (2026-11-06): opened to the network, the dashboard's
token crossed it in plain text. Now it opens only over HTTPS, to Tailscale
addresses, or with plain HTTP accepted out loud; otherwise it stays on this
computer. Nothing here leaves the machine: the HTTPS check is a local
socket with a certificate made for the test.

    python tests/test_lan_https.py
"""

from __future__ import annotations

import datetime
import os
import socket
import ssl
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork.web import serve as serve_mod

ENVS = (serve_mod.ALLOW_ENV, serve_mod.ALLOW_HTTP_ENV, serve_mod.TLS_CERT_ENV,
        serve_mod.TLS_KEY_ENV)


def _env(**values):
    saved = {k: os.environ.get(k) for k in ENVS}
    for k in ENVS:
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in values.items() if v is not None})
    return saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _cert(folder: Path) -> tuple[str, str]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = folder / "c.pem", folder / "k.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                           serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return str(cert_path), str(key_path)


def test_plain_http_to_the_network_stays_on_this_computer():
    saved = _env(**{serve_mod.ALLOW_ENV: "192.168.1.50"})
    try:
        assert serve_mod.allowed_extra_hosts() == []
        assert serve_mod.bind_address() == "127.0.0.1"
    finally:
        _restore(saved)


def test_tailscale_https_or_an_explicit_yes_opens_it():
    saved = _env(**{serve_mod.ALLOW_ENV: "100.101.102.103, nas.tail1234.ts.net:9000"})
    try:
        assert serve_mod.allowed_extra_hosts() == ["100.101.102.103", "nas.tail1234.ts.net:9000"]
    finally:
        _restore(saved)
    saved = _env(**{serve_mod.ALLOW_ENV: "100.101.102.103, 192.168.1.50"})
    try:
        assert serve_mod.allowed_extra_hosts() == ["100.101.102.103"], \
            "the one outside Tailscale is dropped, the Tailscale one kept"
        os.environ[serve_mod.ALLOW_HTTP_ENV] = "1"
        assert serve_mod.allowed_extra_hosts() == ["100.101.102.103", "192.168.1.50"]
    finally:
        _restore(saved)
    with tempfile.TemporaryDirectory() as tmp:
        cert, key = _cert(Path(tmp))
        saved = _env(**{serve_mod.ALLOW_ENV: "nas.local", serve_mod.TLS_CERT_ENV: cert,
                        serve_mod.TLS_KEY_ENV: key})
        try:
            assert serve_mod.tls_files() == (cert, key)
            assert serve_mod.allowed_extra_hosts() == ["nas.local"]
        finally:
            _restore(saved)


def test_with_a_certificate_the_dashboard_answers_only_over_https():
    from http.server import BaseHTTPRequestHandler

    class Hello(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory() as tmp:
        cert, key = _cert(Path(tmp))
        server = serve_mod.Server(("127.0.0.1", 0), Hello)
        assert serve_mod.wrap_tls(server, (cert, key)) == ""
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = ssl.create_default_context(cafile=cert)
            client.minimum_version = ssl.TLSVersion.TLSv1_2
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw, \
                    client.wrap_socket(raw, server_hostname="localhost") as tls:
                tls.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                assert b" 200 " in tls.recv(100).split(b"\r\n")[0]
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                raw.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
                try:
                    got = raw.recv(100)
                except OSError:
                    got = b""
                assert not got.startswith(b"HTTP/"), "plain HTTP answered"
        finally:
            server.shutdown()
            server.server_close()
        bad = serve_mod.Server(("127.0.0.1", 0), Hello)
        try:
            assert "cannot use the certificate" in serve_mod.wrap_tls(bad, (key, cert))
        finally:
            bad.server_close()


def test_the_session_says_https_when_it_is():
    from jobdork.web.session import new_session
    s = new_session("127.0.0.1", scheme="https")
    assert s.url.startswith("https://127.0.0.1:") and s.launch_url.startswith("https://")
    assert new_session("127.0.0.1").origin.startswith("http://")


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
