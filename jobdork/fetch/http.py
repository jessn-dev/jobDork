"""
jobdork.fetch.http
==================
The only thing in this package that touches the network.

These are other people's servers. A job board that starts blocking scrapers
makes the market worse for everyone using a tool like this, so the pacing here
is not a performance setting — it is the part that keeps the tool welcome.

Three behaviours worth knowing:

  Per-host clocks. Concurrency governs how many DIFFERENT boards are read at
  once, not how hard any one of them is hit. Each host has its own rate, and
  requests to different hosts are interleaved so a long run of Greenhouse
  entries does not park the whole pool on one host.

  A circuit breaker, not a retry loop. A host that answers 429 three times in
  a row, having already used its retries, is saying no rather than asking for
  a pause. It is blocked for five minutes instead of retried into.

  Retry-After is read as intent. Under a minute is a pause and is honoured.
  Over a minute is a refusal, and the host is dropped for the rest of the run.

Failure often looks like success on these APIs — several answer HTTP 200 with
an empty array both for a board that does not exist and for one that is
throttling you. That distinction cannot be made here; it belongs to the
adapter, which knows whether a board ever had jobs. This layer reports what
happened and never decides what it meant.

Public addresses only. Many of the addresses fetched come from job posts (an
apply link, a careers page, "Check if still open"), and anyone can write a
job post. One pointed at 192.168.1.1 or localhost would have the app send a
request into your own network: a router's page, a printer, a NAS. So every
request, and every redirect it follows, is refused unless its host resolves
to public addresses only (`refusal`). The AI models, Ollama on this machine
among them, are reached through ai/llm.py, not through here.
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import socket
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.util import connection as _connection

log = logging.getLogger("jobdork.fetch")

# Requests per second, per host. Anything not listed gets DEFAULT_RATE.
# Workable's is low because outrunning it costs a whole run: its search
# endpoint answers 429 and then hands out a day-long Retry-After.
HOST_RATES: dict[str, float] = {
    "apply.workable.com": 0.7,
    # The cross-employer SEARCH endpoint is stricter than the per-board one.
    # A 16-title config at 0.7 collected 15 consecutive 429s and tripped the
    # circuit breaker 68 requests in, losing the rest of the run.
    "jobs.workable.com": 0.4,
    "boards-api.greenhouse.io": 5.0,
    "job-boards.greenhouse.io": 5.0,
    "api.ashbyhq.com": 5.0,
    "api.smartrecruiters.com": 8.0,
    "api.lever.co": 3.0,
    "api.eu.lever.co": 3.0,
    "data.usajobs.gov": 3.0,
    "api.adzuna.com": 1.0,          # 25 calls a minute on the free tier
    # Kalibrr publishes no limit. One a second is a person paging quickly.
    "www.kalibrr.com": 1.0,
    # Himalayas answers 429 past an unpublished limit.
    "himalayas.app": 1.0,
    # The Bundesagentur publishes no limit for its search; two a second.
    "rest.arbeitsagentur.de": 2.0,
    # Arbeitnow asks not to be abused, and answered 429 at a page a second.
    "www.arbeitnow.com": 0.5,
}
DEFAULT_RATE = 3.0

# Rates for every host under a domain, where each employer has its own host
# (nvidia.wd5.myworkdayjobs.com). Workday publishes no limit; one a second is
# a person paging, and a detail is fetched per matching job.
DOMAIN_RATES: dict[str, float] = {
    "myworkdayjobs.com": 1.0,
    # Oracle Recruiting Cloud (jpmc.fa.oraclecloud.com) publishes no limit
    # either; two a second, one detail per kept job.
    "oraclecloud.com": 2.0,
    # Taleo Business Edition pages (phf.tbe.taleo.net): HTML, one a second.
    "taleo.net": 1.0,
}


def rate_for(host: str) -> float:
    if host in HOST_RATES:
        return HOST_RATES[host]
    for domain, rate in DOMAIN_RATES.items():
        if host == domain or host.endswith("." + domain):
            return rate
    return DEFAULT_RATE

BLOCK_SECONDS = 300.0               # how long a host that said no is left alone
MAX_CONSECUTIVE_429 = 3
RETRY_AFTER_REFUSAL = 60.0          # over this, read as "not today"


class Blocked(Exception):
    """The host is refusing, or has been blocked by the circuit breaker."""


class PrivateAddress(requests.RequestException):
    """The address is in this machine or its network, not on the internet."""


def _public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # ::ffff:127.0.0.1 is 127.0.0.1; Python before 3.13 does not say so.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    # is_global is False for private, loopback, link-local (169.254, where
    # cloud metadata lives), 100.64/10 (carrier NAT, Tailscale) and reserved.
    return ip.is_global and not ip.is_multicast


def checked(url: str, resolve=None) -> tuple[str, str]:
    """(why `url` is not fetched, or ""; the address to connect to, or "").

    Every address the name resolves to must be public: a name with one
    public and one private address could be connected to either. The
    connection then goes to the first of the addresses checked (_Pinned),
    so a server that answers with a public address for the check and a
    private one for the connection (DNS rebinding) reaches nothing. A name
    that does not resolve is let through with no address, to fail as the
    request would.
    """
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").rstrip(".")
    if not host:
        return f"no host in {url!r}", ""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return ("", host) if _public(literal) else (f"{host} is not a public address", "")
    try:
        found = (resolve or _getaddrinfo)(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return "", ""
    first = ""
    for *_, sockaddr in found:
        try:
            ip = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])
        except ValueError:
            continue
        if not _public(ip):
            return f"{host} is in this machine or its network ({ip})", ""
        first = first or str(ip)
    return "", first


def refusal(url: str, resolve=None) -> str:
    """Why `url` is not fetched, or "" when its host is public."""
    return checked(url, resolve)[0]


# The name lookup the check uses, here so a test can answer it.
_getaddrinfo = socket.getaddrinfo

# The address checked for each host, for the connection this thread is
# about to open: {host: address}. Set by _PublicOnly.send around one
# request, read by _Pinned._new_conn.
_pins = threading.local()


def _pinned() -> dict[str, str]:
    if not hasattr(_pins, "hosts"):
        _pins.hosts = {}
    return _pins.hosts


class _Pinned:
    """A connection that goes to the address the check found, not to a
    second lookup of the name. TLS still checks the certificate against the
    name (urllib3 takes `self.host` for that), so a pinned address that is
    not the site's fails its certificate rather than being trusted. Through
    a proxy nothing is pinned: the proxy looks the name up itself."""

    def _new_conn(self):
        address = _pinned().get(self.host)
        if not address or self._tunnel_host or getattr(self, "proxy", None):
            return super()._new_conn()
        try:
            sock = _connection.create_connection(
                (address, self.port), self.timeout,
                source_address=self.source_address, socket_options=self.socket_options)
        except TimeoutError as exc:
            raise ConnectTimeoutError(
                self, f"Connection to {self.host} timed out. (connect timeout={self.timeout})",
            ) from exc
        except OSError as exc:
            raise NewConnectionError(self, f"Failed to establish a new connection: {exc}") from exc
        return sock


class _PinnedHTTP(_Pinned, HTTPConnection):
    pass


class _PinnedHTTPS(_Pinned, HTTPSConnection):
    pass


class _PinnedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _PinnedHTTP


class _PinnedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPS


class _PublicOnly(HTTPAdapter):
    """Checks each request it sends, so a redirect is checked too: requests
    sends every hop of one through the adapter again. The connection goes
    to the address checked (_Pinned)."""

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"http": _PinnedHTTPPool,
                                                   "https": _PinnedHTTPSPool}

    def send(self, request, *args, **kwargs):
        why, address = checked(request.url)
        if why:
            raise PrivateAddress(f"refused: {why}")
        host = (urllib.parse.urlsplit(request.url).hostname or "").rstrip(".")
        pins = _pinned()
        if address and host:
            pins[host] = address
        try:
            return super().send(request, *args, **kwargs)
        finally:
            pins.pop(host, None)


@dataclass
class Response:
    url: str
    status: int
    body: str = ""
    json: object = None
    error: str = ""
    host: str = ""
    # Where the request ended up after redirects. A closed Greenhouse posting
    # answers 200 — from the board's index, reached by redirect.
    final_url: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.error


@dataclass
class _HostState:
    rate: float
    next_allowed: float = 0.0
    consecutive_429: int = 0
    blocked_until: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


class Fetcher:
    """Paced HTTP client. One per run; share it across adapters.

    Thread-safe: the pacing lock is per host, so two threads reading two
    different boards never wait on each other.
    """

    def __init__(
        self,
        user_agent: str,
        timeout: int = 20,
        retries: int = 2,
        session: requests.Session | None = None,
    ):
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()
        if hasattr(self.session, "mount"):
            for prefix in ("http://", "https://"):
                self.session.mount(prefix, _PublicOnly())
        self.session.headers["User-Agent"] = user_agent
        self._hosts: dict[str, _HostState] = {}
        self._hosts_lock = threading.Lock()
        self.blocked_hosts: set[str] = set()

    # ── pacing ─────────────────────────────────────────────────────────────────

    def _state(self, host: str) -> _HostState:
        with self._hosts_lock:
            state = self._hosts.get(host)
            if state is None:
                state = _HostState(rate=rate_for(host))
                self._hosts[host] = state
            return state

    def pace(self, host: str, rate: float) -> None:
        """Slow one host to `rate` a second, never speed it up.

        For hosts no table can name in advance: an employer's own careers
        site, read by fetch/site.py.
        """
        state = self._state(host.lower())
        with state.lock:
            state.rate = min(state.rate, rate)

    def _wait_turn(self, host: str) -> None:
        """Sleep until this host's clock allows another request."""
        state = self._state(host)
        while True:
            with state.lock:
                now = time.monotonic()
                if state.blocked_until > now:
                    raise Blocked(
                        f"{host} blocked for another "
                        f"{state.blocked_until - now:.0f}s"
                    )
                if now >= state.next_allowed:
                    state.next_allowed = now + (1.0 / state.rate)
                    return
                delay = state.next_allowed - now
            time.sleep(delay)

    def _block(self, host: str, seconds: float, why: str) -> None:
        state = self._state(host)
        with state.lock:
            state.blocked_until = time.monotonic() + seconds
        self.blocked_hosts.add(host)
        log.warning("%s blocked for %.0fs: %s", host, seconds, why)

    def _note_429(self, host: str, retry_after: str) -> None:
        """Decide whether a 429 is a pause or a refusal."""
        state = self._state(host)
        with state.lock:
            state.consecutive_429 += 1
            count = state.consecutive_429

        seconds = 0.0
        if retry_after:
            try:
                seconds = float(retry_after)
            except ValueError:
                seconds = 0.0

        if seconds > RETRY_AFTER_REFUSAL:
            self._block(host, seconds, f"Retry-After {seconds:.0f}s reads as a refusal")
        elif count >= MAX_CONSECUTIVE_429:
            self._block(
                host, BLOCK_SECONDS,
                f"{count} consecutive 429s after retries, treating as no",
            )

    def _note_ok(self, host: str) -> None:
        state = self._state(host)
        with state.lock:
            state.consecutive_429 = 0

    # ── requests ───────────────────────────────────────────────────────────────

    def get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        expect_json: bool = True,
    ) -> Response:
        return self._timed("GET", url, params=params, headers=headers,
                           expect_json=expect_json)

    def post(
        self,
        url: str,
        json_body: dict | None = None,
        headers: dict | None = None,
        expect_json: bool = True,
    ) -> Response:
        return self._timed("POST", url, json_body=json_body, headers=headers,
                           expect_json=expect_json)

    def _timed(self, method: str, url: str, **kwargs) -> Response:
        """A request, reported to the Activity page by host and outcome."""
        from ..core import telemetry

        started = time.monotonic()
        resp = self._request(method, url, **kwargs)
        telemetry.fetch(resp.host, resp.status, time.monotonic() - started,
                        resp.error)
        return resp

    def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        json_body: dict | None = None,
        headers: dict | None = None,
        expect_json: bool = True,
    ) -> Response:
        host = urllib.parse.urlsplit(url).netloc.lower()
        attempts = self.retries + 1
        last = Response(url=url, status=0, host=host, error="not attempted")

        for attempt in range(attempts):
            try:
                self._wait_turn(host)
            except Blocked as exc:
                return Response(url=url, status=0, host=host, error=str(exc))

            try:
                # Greenhouse answers 403 to a GET carrying a body, so a body is
                # only ever attached to a POST.
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json_body if method == "POST" else None,
                    headers=headers,
                    timeout=self.timeout,
                )
            except PrivateAddress as exc:      # asking again changes nothing
                return Response(url=url, status=0, host=host, error=str(exc))
            except requests.RequestException as exc:
                last = Response(url=url, status=0, host=host, error=str(exc))
                if attempt + 1 < attempts:
                    time.sleep(1.0 + attempt)
                continue

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "")
                if attempt + 1 < attempts:
                    pause = 2.0 + attempt * 2
                    with contextlib.suppress(ValueError):
                        pause = min(float(retry_after), RETRY_AFTER_REFUSAL) or pause
                    time.sleep(pause)
                    continue
                self._note_429(host, retry_after)
                return Response(url=url, status=429, host=host,
                                error="rate limited")

            if resp.status_code >= 500 and attempt + 1 < attempts:
                time.sleep(1.0 + attempt)
                last = Response(url=url, status=resp.status_code, host=host,
                                error=f"server error {resp.status_code}")
                continue

            self._note_ok(host)
            out = Response(url=url, status=resp.status_code, host=host,
                           final_url=str(resp.url or url))
            if not out.ok:
                out.error = f"HTTP {resp.status_code}"
                return out
            out.body = resp.text
            if expect_json:
                try:
                    out.json = resp.json()
                except ValueError:
                    out.error = "response was not JSON"
            return out

        return last
