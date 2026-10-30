"""
jobdork.web.mcp
===============
jobdork's tools for a coding agent (web/agent.py) as an MCP server over
stdio: `jobdork mcp`, or the installed app with `--mcp`.

The Model Context Protocol's stdio transport is JSON-RPC 2.0, one message
per line, on standard input and output. That is all this speaks, with the
standard library: `initialize`, `tools/list`, `tools/call` and `ping`. Logs
go to standard error, since anything else on standard output would break
the stream.

It shares the dashboard's database, so what the agent saves shows on the
dashboard's pages, and the dashboard can run at the same time (SQLite WAL).
"""

from __future__ import annotations

import json
import logging
import sys
from typing import IO

from .. import __version__
from . import agent

log = logging.getLogger(__name__)

# The protocol versions understood, newest first. A client asking for one of
# these gets it; any other gets the newest.
VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


class Server:
    def __init__(self, cfg, out: IO[str]):
        self.cfg = cfg
        self.out = out
        self.client = ""

    def send(self, message: dict) -> None:
        self.out.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.out.flush()

    def handle(self, line: str) -> None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            self.send({"jsonrpc": "2.0", "id": None,
                       "error": {"code": -32700, "message": "not JSON"}})
            return
        if isinstance(message, list):             # a batch (2025-03-26)
            for one in message:
                self.one(one)
            return
        self.one(message)

    def one(self, message) -> None:
        if not isinstance(message, dict):
            return
        method, mid = message.get("method"), message.get("id")
        if mid is None:                            # a notification: no answer
            return
        try:
            result = self.answer(str(method or ""), message.get("params") or {})
        except LookupError as exc:
            self.send({"jsonrpc": "2.0", "id": mid,
                       "error": {"code": -32601, "message": str(exc)}})
            return
        except Exception as exc:                   # never let the server die
            log.exception("MCP %s failed", method)
            self.send({"jsonrpc": "2.0", "id": mid,
                       "error": {"code": -32603, "message": f"jobdork failed: {exc}"}})
            return
        self.send({"jsonrpc": "2.0", "id": mid, "result": result})

    def answer(self, method: str, params: dict) -> dict:
        if method == "initialize":
            asked = str(params.get("protocolVersion") or "")
            self.client = str((params.get("clientInfo") or {}).get("name") or "")[:60]
            return {"protocolVersion": asked if asked in VERSIONS else VERSIONS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "jobdork", "version": __version__},
                    "instructions": agent.INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{"name": t.name, "description": t.description,
                               "inputSchema": t.schema} for t in agent.TOOLS]}
        if method == "tools/call":
            name = str(params.get("name") or "")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                return _text({"error": "arguments must be an object"}, error=True)
            try:
                done = agent.call(self.cfg, name, {**args, "_client": self.client}
                                  if name in ("save_document", "save_verdict") else args)
            except agent.ToolError as exc:
                return _text({"error": str(exc)}, error=True)
            return _text(done)
        raise LookupError(f"no method {method}")


def _text(value: dict, error: bool = False) -> dict:
    """A tool's answer: its JSON as text, which every client reads."""
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=1)}],
            "isError": error}


def serve(cfg, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> int:
    """Answer one message per line until standard input closes."""
    stdin = stdin or sys.stdin
    server = Server(cfg, stdout or sys.stdout)
    for line in stdin:
        if line.strip():
            server.handle(line)
    return 0
