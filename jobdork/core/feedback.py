"""
jobdork.core.feedback
=====================
A problem report or an idea, sent from the Dashboard to the people who make
jobdork.

The app holds no Resend or GitHub key, ever: a key shipped inside an app is a
key anyone who has the app can read. A report goes to a relay instead (a
small service run by the maintainers, see relay/feedback/), which holds those
keys, opens the GitHub issue and mails the screenshots. The relay's address
comes from JOBDORK_FEEDBACK_URL, or RELAY_URL as a packaged build sets it.
With neither, the report can still be opened as a GitHub issue in the
browser, or saved as a file.

What leaves the machine is exactly what the preview shows: what you wrote,
the app's version and system, and, if you tick it, the last week's warnings
and errors, scrubbed of keys, tokens, email addresses and your home folder.
Never your resume, job posts or config.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# Set by a packaged build; JOBDORK_FEEDBACK_URL overrides it.
RELAY_URL = ""
ISSUES_URL = "https://github.com/jessn-dev/jobDork/issues/new"

KINDS = {"problem": "Problem", "idea": "Idea", "question": "Question"}
MAX_TITLE = 120
MAX_DETAILS = 8_000
MAX_LOG_LINES = 60
MAX_LOG_CHARS = 500
MAX_SHOTS = 3
MAX_SHOT_BYTES = 2 * 1024 * 1024
SHOT_TYPES = ("image/png", "image/jpeg", "image/webp")
# Room for the screenshots (base64 is 4/3 of the bytes) and the text.
MAX_BODY = MAX_SHOTS * MAX_SHOT_BYTES * 4 // 3 + 64 * 1024
# A browser's address bar takes about this much before servers refuse it.
MAX_ISSUE_URL = 7_500
SEND_TIMEOUT = 20


class FeedbackError(Exception):
    pass


def relay_url() -> str:
    return os.environ.get("JOBDORK_FEEDBACK_URL", "").strip() or RELAY_URL


# ── scrubbing ─────────────────────────────────────────────────────────────────

_SECRETS = [
    # Provider keys by their prefixes, then anything long and key-like.
    re.compile(r"\b(sk-ant-|sk-|re_|ghp_|gho_|github_pat_|AIza)[A-Za-z0-9_\-]{12,}"),
    re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b"),
    # The dashboard's own token in an address, and any key=value secret.
    re.compile(r"(?i)\b((?:t|\w*(?:token|key|secret|password))=)[^\s&\"']+"),
]
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_IPV4 = re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b")


def scrub(text: str) -> str:
    """The text with keys, tokens, email addresses, IPs and your home folder taken out."""
    text = str(text or "")
    home = str(Path.home())
    if len(home) > 1:
        text = text.replace(home, "~")
    for pattern in _SECRETS:
        if pattern.groups:
            # lambda: keeps the "key=" or prefix, so a reader sees what was taken.
            text = pattern.sub(lambda m: m.group(1) + "[removed]", text)
        else:
            text = pattern.sub("[removed]", text)
    text = _EMAIL.sub("[email]", text)
    return _IPV4.sub("[address]", text)


# ── the report ────────────────────────────────────────────────────────────────


@dataclass
class Report:
    kind: str
    title: str
    details: str
    reply_to: str = ""
    app: dict = field(default_factory=dict)
    logs: list[dict] = field(default_factory=list)
    screenshots: list[dict] = field(default_factory=list)

    def text(self) -> str:
        """The issue's body, and the preview: what is sent, word for word."""
        # The reply address is not here: the issue is public, so the relay
        # puts it only on the maintainers' email.
        out = [self.details.strip() or "(no details)"]
        if self.app:
            out += ["", "### App", ""] + [f"- {k}: {v}" for k, v in self.app.items()]
        if self.logs:
            out += ["", f"### Warnings and errors, last 7 days ({len(self.logs)})",
                    "", "```"]
            out += [f"{x['at'][:16].replace('T', ' ')} {x['level'].upper()} "
                    f"[{x['source']}] {x['text']}" for x in self.logs]
            out.append("```")
        if self.screenshots:
            out += ["", f"{len(self.screenshots)} screenshot(s): "
                    + ", ".join(s["name"] for s in self.screenshots)]
        return "\n".join(out)

    def subject(self) -> str:
        return f"[{KINDS[self.kind]}] {self.title}"

    def payload(self) -> dict:
        return {"kind": self.kind, "title": self.subject(), "body": self.text(),
                "reply_to": self.reply_to, "screenshots": self.screenshots}

    def issue_url(self) -> str:
        """A GitHub "new issue" address with the report filled in.

        Screenshots cannot go in an address; the page says to drop them in.
        A long log is cut from the end so the address still opens.
        """
        body = self.text()
        while True:
            url = ISSUES_URL + "?" + urllib.parse.urlencode(
                {"title": self.subject(), "body": body})
            if len(url) <= MAX_ISSUE_URL or len(body) < 200:
                return url
            body = body[: int(len(body) * 0.8)].rstrip() + "\n\n(cut to fit)"


def app_info(cfg) -> dict:
    from .. import __version__
    from .config import in_container
    info = {
        "jobdork": __version__,
        "system": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": sys.version.split()[0],
        "in Docker": "yes" if in_container() else "no",
    }
    llm = getattr(cfg, "llm", None)
    if llm is not None:
        info["AI"] = f"{llm.provider} {llm.model}".strip() or "off"
    return info


def _screenshots(raw) -> list[dict]:
    shots = []
    for item in (raw or [])[:MAX_SHOTS + 1]:
        if len(shots) == MAX_SHOTS:
            raise FeedbackError(f"at most {MAX_SHOTS} screenshots")
        if not isinstance(item, dict):
            raise FeedbackError("bad screenshot")
        kind = str(item.get("type") or "")
        if kind not in SHOT_TYPES:
            raise FeedbackError("screenshots must be PNG, JPEG or WebP")
        try:
            data = base64.b64decode(str(item.get("data") or ""), validate=True)
        except ValueError as exc:
            raise FeedbackError("bad screenshot") from exc
        if not data or len(data) > MAX_SHOT_BYTES:
            raise FeedbackError("a screenshot is empty or over 2 MB")
        name = re.sub(r"[^\w.\- ]", "_", Path(str(item.get("name") or "")).name)[:80]
        shots.append({"name": name or f"screenshot-{len(shots) + 1}",
                      "type": kind, "data": base64.b64encode(data).decode("ascii")})
    return shots


def build(form: dict, cfg, problems: list[dict]) -> Report:
    """A report from the Dashboard's form; refuses what cannot be sent."""
    kind = str(form.get("kind") or "")
    if kind not in KINDS:
        raise FeedbackError("pick a problem, an idea or a question")
    title = " ".join(str(form.get("title") or "").split())
    if not title:
        raise FeedbackError("give it a short title")
    if len(title) > MAX_TITLE:
        raise FeedbackError(f"keep the title under {MAX_TITLE} characters")
    details = str(form.get("details") or "").strip()
    if len(details) > MAX_DETAILS:
        raise FeedbackError(f"keep the details under {MAX_DETAILS:,} characters")
    reply_to = str(form.get("reply_to") or "").strip()
    if reply_to and not _EMAIL.fullmatch(reply_to):
        raise FeedbackError(f"{reply_to!r} is not an email address")
    logs = []
    if form.get("logs"):
        logs = [{"at": str(p.get("at") or ""), "level": str(p.get("level") or ""),
                 "source": p.get("job") or p.get("source") or "app",
                 "text": scrub(p.get("text"))[:MAX_LOG_CHARS]}
                for p in problems[:MAX_LOG_LINES]]
    return Report(kind=kind, title=scrub(title), details=scrub(details),
                  reply_to=reply_to, app=app_info(cfg) if form.get("app", True) else {},
                  logs=logs, screenshots=_screenshots(form.get("screenshots")))


def send(report: Report, url: str = "") -> dict:
    """POST the report to the relay; what it answers (an issue address, say)."""
    url = url or relay_url()
    if not url:
        raise FeedbackError("sending is not set up in this copy of jobdork; "
                            "open it as a GitHub issue or save it instead")
    if not url.startswith("https://") and not url.startswith("http://localhost"):
        raise FeedbackError("the feedback address must be https")
    request = urllib.request.Request(
        url, data=json.dumps(report.payload()).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "jobdork-feedback"})
    try:
        # Safe: the address is checked above to be https (or localhost).
        with urllib.request.urlopen(request, timeout=SEND_TIMEOUT) as resp:  # nosec B310
            answer = resp.read(64 * 1024)
    except urllib.error.HTTPError as exc:
        why = exc.read(2000).decode("utf-8", "replace").strip() or exc.reason
        raise FeedbackError(f"the feedback service refused it ({exc.code}): {why}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FeedbackError(f"could not reach the feedback service: {exc}") from exc
    try:
        parsed = json.loads(answer or b"{}")
    except json.JSONDecodeError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}
