"""
jobdork.web.session
===================
The token and the port a dashboard run binds to.

Two things the CLI never needed and a long-running local server does.

**A token, because localhost is not a security boundary.** The Host check in
`serve.py` stops a web page from reaching this server under DNS rebinding. It
does nothing about another program on the same machine: any process running as
you can `curl 127.0.0.1:8765/api/roles` and read every role, every note and
every status, or POST changes to them. A token minted per run and required on
every request closes that.

It is not a password and it is not stored. It lives for one `serve` run, it is
printed once as part of the URL, and it dies with the process.

**A port that is asked for rather than assumed.** A fixed 8765 collides — with
another jobdork, or with anything else that liked the number. Binding port 0
lets the operating system hand out a free one, and the chosen port is printed
and returned so a parent process (a launcher, a packaged app, a test) can read
it rather than guess.
"""

from __future__ import annotations

import contextlib
import hmac
import secrets
import socket
from dataclasses import dataclass

# Long enough that guessing is hopeless, short enough to sit in a URL.
TOKEN_BYTES = 32


@dataclass(frozen=True)
class Session:
    """One dashboard run: where it listens and what it will answer to."""

    host: str
    port: int
    token: str

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def url(self) -> str:
        """The address to open. The token rides in the query on first load.

        A URL is the only thing a person can be handed, and a fragment would
        not reach the server. Once the page has loaded it keeps the token in
        memory and sends it as a header instead, so it stops appearing in
        anything that logs URLs.
        """
        return f"{self.origin}/?t={self.token}"

    def matches(self, candidate: str) -> bool:
        """Constant-time comparison — a timing side channel is still a channel."""
        return bool(candidate) and hmac.compare_digest(candidate, self.token)


def free_port(host: str = "127.0.0.1", preferred: int = 0) -> int:
    """A port that is actually available.

    `preferred` is tried first so a familiar number is kept when it is free;
    0 asks the operating system. Either way the answer is a port that bound
    successfully a moment ago, rather than one assumed to be spare.
    """
    if preferred:
        with contextlib.suppress(OSError), socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, preferred))
            return preferred

    with socket.socket() as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


def new_session(host: str = "127.0.0.1", preferred_port: int = 0,
                token: str = "") -> Session:
    """Mint a session. `token` is only passed in by a parent that supplied one."""
    return Session(
        host=host,
        port=free_port(host, preferred_port),
        token=token or secrets.token_urlsafe(TOKEN_BYTES),
    )
