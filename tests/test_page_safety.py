"""
The dashboard shows text and links that come from whoever posted a job.
These read the page's source for the two ways that text could become script
in the page, which runs with the dashboard's token.

    python tests/test_page_safety.py

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAGE = ROOT / "jobdork" / "data" / "dashboard.html"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_no_escaped_text_is_put_inside_a_handlers_quotes():
    """esc() turns ' into &#39;, and the browser turns it back before an
    onclick runs: `apply('${esc(r.url)}')` let a link with a ' in it end
    the string and run what followed. Pass it as data-* and read
    this.dataset instead."""
    bad = [m.group(0) for m in
           re.finditer(r"\bon[a-z]+=\"[^\"]*'\$\{esc\(", _page())]
    assert not bad, bad


def test_a_resume_file_name_is_sent_encoded():
    """A header takes Latin-1 only: "Maria’s Resume.pdf", with a
    curly apostrophe, made Safari refuse the upload ("Type error") and the
    setup wizard sat on "Reading..." (Intel Mac, 0.15.3). Every X-Filename
    the page sets is encoded first."""
    page = _page()
    sent = re.findall(r"""['"]X-Filename['"]\s*[:,]\s*([^)}\n]+)""", page)
    assert sent, "expected the resume upload to set X-Filename"
    for expr in sent:
        assert expr.strip().startswith("encodeURIComponent("), expr


def test_every_built_link_is_a_web_address():
    """A posting's address could be javascript: or data:, which runs in the
    page when clicked. Every href built from data goes through webHref."""
    page = _page()
    built = re.findall(r'href="\$\{([^}]*)\}"', page)
    assert built, "expected some built links"
    for expr in built:
        assert expr.startswith("esc(webHref("), expr
    assert "const webHref = url => /^https?:\\/\\//i.test(url || '') ? url : '#';" in page


def test_the_google_jobs_link_carries_your_words_encoded_to_google_only():
    """A title like "Charge Nurse & RN" or a place with commas must stay one
    search, not end the query or the address; and it opens outside the app."""
    page = _page()
    builder = re.search(r"function googleJobsUrl\(title\) \{.*?\n\}", page, re.S).group(0)
    assert "return 'https://www.google.com/search?udm=8&q=' + encodeURIComponent(words);" in builder
    line = re.search(r"function drawGoogleJobs\(empty\) \{.*?\n\}", page, re.S).group(0)
    assert "openOut(this.dataset.url)" in line and "esc(t)" in line
    # Above the list, where it is seen, not after its last post; drawn with
    # every list, empty or not.
    assert page.index('id="gjobs"') < page.index('<div id="list">')
    assert "drawGoogleJobs(!shown.length);" in page


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


def test_no_nul_character_goes_into_the_page():
    """The parser turns NUL into U+FFFD, so a value built with "\\u0000"
    never matches itself once it is in an option: the model picker's
    "Other" hid its text box and filled in "\\ufffdother" instead."""
    assert "\\u0000" not in _page() and "\x00" not in _page()


def test_every_ai_provider_has_its_mark():
    from jobdork.ai.llm import PROVIDERS

    icons = _page().split("const PROVIDER_ICONS = {", 1)[1].split("\n};", 1)[0]
    missing = [p for p in PROVIDERS if f'"{p}":' not in icons]
    assert not missing, missing
