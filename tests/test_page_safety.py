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


def test_every_built_link_is_a_web_address():
    """A posting's address could be javascript: or data:, which runs in the
    page when clicked. Every href built from data goes through webHref."""
    page = _page()
    built = re.findall(r'href="\$\{([^}]*)\}"', page)
    assert built, "expected some built links"
    for expr in built:
        assert expr.startswith("esc(webHref("), expr
    assert "const webHref = url => /^https?:\\/\\//i.test(url || '') ? url : '#';" in page


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
