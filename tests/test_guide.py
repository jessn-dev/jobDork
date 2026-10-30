"""
The user guide (guide/) keeps up with the app: every button and heading the
dashboard shows is named somewhere in the guide, every status is explained,
every page of the menu has a page in the guide, and every picture it shows
exists and is used. A new button without a line in the guide fails here.

    python tests/test_guide.py

What to do when one fails: guide/README.md. Keep the `__main__` block at
the END of this file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAGE = ROOT / "jobdork" / "data" / "dashboard.html"
DOCS = ROOT / "guide" / "docs"
SHOTS = ROOT / "scripts" / "guide_shots.mjs"

# Words on buttons that say what any button says, and need no explaining.
GENERIC = {"Add", "Remove", "Save", "Close", "Open", "Edit", "Delete", "View", "Show",
           "Copy", "Next", "Off", "None", "Replace", "Download", "Forget", "Not now"}


def _guide_text() -> str:
    text = " ".join(p.read_text(encoding="utf-8") for p in DOCS.glob("*.md"))
    return re.sub(r"\s+", " ", text).lower()


def _labels() -> set[str]:
    """Every fixed button label and section heading on the dashboard."""
    html = PAGE.read_text(encoding="utf-8")
    labels = set()
    for m in re.finditer(r"<button[^>]*>(?:\s*<svg.*?</svg>)?([^<>${}]{2,60})</button>",
                         html, re.S):
        labels.add(re.sub(r"\s+", " ", m.group(1)).strip())
    for m in re.finditer(r"<h[23][^>]*>([^<>${}]{3,80})<", html):
        labels.add(re.sub(r"\s+", " ", m.group(1)).strip())
    return {label for label in labels if label and label not in GENERIC}


def test_every_button_and_heading_is_in_the_guide():
    guide = _guide_text()
    missing = sorted(label for label in _labels() if label.lower() not in guide)
    assert not missing, ("the dashboard shows these and the user guide never names them; "
                         "explain each in guide/docs/ (guide/README.md):\n  "
                         + "\n  ".join(missing))


def test_every_status_is_explained():
    from jobdork.core.config import STATUSES

    table = (DOCS / "statuses.md").read_text(encoding="utf-8")
    missing = [s for s in STATUSES if f"| **{s}** |" not in table]
    assert not missing, f"guide/docs/statuses.md has no row for: {missing}"


def test_every_page_of_the_menu_has_a_page_in_the_guide():
    html = PAGE.read_text(encoding="utf-8")
    menu = re.findall(r'<button class="item[^"]*" data-view="(\w+)"', html)
    page_for = {"scan": "dashboard.md", "roles": "job-posts.md", "apps": "applications.md",
                "settings": "search.md",
                "resume": "resume.md", "sources": "sources.md", "ai": "ai.md",
                "tools": "feedback.md", "prefs": "settings.md"}
    assert set(menu) == set(page_for), (
        f"the menu is now {menu}: add the new page to page_for here and to guide/docs/")
    for view, page in page_for.items():
        assert (DOCS / page).exists(), f"no guide/docs/{page} for the {view} page"
    nav = (ROOT / "guide" / "mkdocs.yml").read_text(encoding="utf-8")
    for page in DOCS.glob("*.md"):
        assert page.name in nav, f"guide/docs/{page.name} is not in mkdocs.yml's nav"


def test_every_picture_is_taken_by_the_script_and_used_by_a_page():
    shots = set(re.findall(r"""(?:shoot|tip)\('([\w-]+)'""", SHOTS.read_text(encoding="utf-8")))
    used = set(re.findall(r"\(images/([\w-]+)\.png\)",
                          " ".join(p.read_text(encoding="utf-8") for p in DOCS.glob("*.md"))))
    have = {p.stem for p in (DOCS / "images").glob("*.png")}
    assert used <= have, f"pages show pictures that do not exist: {sorted(used - have)}"
    assert used <= shots, ("pages show pictures scripts/guide_shots.mjs does not take, so "
                           f"they would go stale: {sorted(used - shots)}")
    assert have <= used, f"pictures no page shows: {sorted(have - used)}"



def _anchors(page: Path) -> set[str]:
    """The anchors a page has, as MkDocs makes them: each heading's slug
    (python-markdown's toc), a heading's own {#id}, and <span id="...">."""
    text = page.read_text(encoding="utf-8")
    found = set(re.findall(r'\{#([\w-]+)\}', text)) | set(re.findall(r'id="([\w-]+)"', text))
    for heading in re.findall(r"^#{1,6} (.+?)\s*(?:\{#[\w-]+\})?$", text, re.M):
        plain = re.sub(r"[*`]|\[([^\]]*)\]\([^)]*\)", r"\1", heading)
        slug = re.sub(r"[^\w\s-]", "", plain).strip().lower()
        found.add(re.sub(r"[-\s]+", "-", slug))
    return found


def test_every_link_to_a_part_of_a_page_finds_it():
    """A heading renamed leaves links to its old anchor pointing nowhere; the
    docs build only warns (2026-10-30: #the-four-main-buttons)."""
    broken = []
    for page in DOCS.glob("*.md"):
        for target, anchor in re.findall(r"\]\(([\w-]*\.md)?#([\w-]+)\)",
                                         page.read_text(encoding="utf-8")):
            other = DOCS / target if target else page
            if other.exists() and anchor not in _anchors(other):
                broken.append(f"{page.name} -> {target or page.name}#{anchor}")
    assert not broken, broken

if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except BaseException:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc(limit=3)
    raise SystemExit(1 if failed else 0)
