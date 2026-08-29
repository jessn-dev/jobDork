"""
jobdork.textutil
================
Turning board HTML into text a regex can be trusted against.

Dealbreakers are read against the job description, and a description that is
still HTML hides matches inside tags: "live<span> </span>coding" does not match
`live coding`, and a role with a coding round sails through. So the markup is
removed before anything reads it, and block-level tags become newlines rather
than vanishing, because "Requirements:Python" is not a sentence and greps like
one.
"""

from __future__ import annotations

import html
import re

_SCRIPT_STYLE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_BLOCK_TAGS = re.compile(
    r"</?(p|div|br|li|ul|ol|h[1-6]|tr|td|th|table|section|article|"
    r"header|footer|blockquote|pre)\b[^>]*>",
    re.IGNORECASE,
)
_ANY_TAG = re.compile(r"<[^>]+>")
_MULTI_BLANK = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")


_ESCAPED_HTML = re.compile(r"&lt;/?[a-zA-Z][^&]*&gt;")


def html_to_text(raw: str) -> str:
    """Flatten HTML to plain text, keeping paragraph boundaries.

    Greenhouse returns its advert HTML-escaped, so the markup arrives as
    `&lt;h2&gt;` rather than `<h2>`. Unescaping has to happen first there or
    the tag strippers match nothing and every Greenhouse description comes out
    as a wall of literal angle-bracket entities.
    """
    if not raw:
        return ""
    text = raw
    if _ESCAPED_HTML.search(text):
        text = html.unescape(text)
    text = _SCRIPT_STYLE.sub(" ", text)
    text = _BLOCK_TAGS.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = _TRAILING_SPACE.sub("\n", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip()


def looks_like_html(raw: str) -> bool:
    if not raw:
        return False
    return bool(re.search(r"<[a-zA-Z/][^>]*>", raw)) or bool(_ESCAPED_HTML.search(raw))


def to_text(raw: str) -> str:
    """html_to_text when it is HTML, otherwise the string tidied up."""
    if looks_like_html(raw):
        return html_to_text(raw)
    return _MULTI_BLANK.sub("\n\n", (raw or "").replace("\xa0", " ")).strip()


def squash(text: str, limit: int = 0) -> str:
    """One line, collapsed whitespace. For logs and list output."""
    out = re.sub(r"\s+", " ", (text or "")).strip()
    if limit and len(out) > limit:
        out = out[: limit - 1].rstrip() + "…"
    return out
