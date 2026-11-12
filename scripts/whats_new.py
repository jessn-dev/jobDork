"""
Write jobdork/data/whats-new.json: the newest release's "For you" list from
docs/CHANGELOG.md, which the app shows once after an update (web/api.py,
whats_new). The release steps run it after writing the release entry;
tests/test_whats_new.py fails while it names another version than
pyproject.toml.

    python scripts/whats_new.py           # write it
    python scripts/whats_new.py --check   # exit 1 if it is out of date
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"
OUT = ROOT / "jobdork" / "data" / "whats-new.json"
RELEASE = re.compile(r"^## Changed — \d{4}-\d{2}-\d{2} — version (\d+\.\d+\.\d+)\s*$", re.M)
LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def newest(text: str) -> dict:
    """{"version", "items"}: the first release entry's bullets after "For you:"."""
    m = RELEASE.search(text)
    if not m:
        raise SystemExit("docs/CHANGELOG.md has no release entry (## Changed — date — version X.Y.Z)")
    end = text.find("\n---", m.end())
    body = text[m.end(): end if end >= 0 else None]
    start = body.find("For you:")
    lines = body[start + len("For you:"):].splitlines() if start >= 0 else body.splitlines()
    items, current = [], None
    for line in lines:
        if line.startswith("- "):
            if current is not None:
                items.append(current)
            current = line[2:].strip()
        elif current is not None and line.startswith("  ") and line.strip():
            current += " " + line.strip()
        elif current is not None and not line.strip():
            items.append(current)
            current = None
        elif items and line.strip():
            break                      # the paragraph after the list
    if current is not None:
        items.append(current)
    return {"version": m.group(1), "items": [LINK.sub(r"\1", i) for i in items]}


def main(argv: list[str]) -> int:
    found = newest(CHANGELOG.read_text(encoding="utf-8"))
    if "--check" in argv:
        have = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
        # Read by pattern, not tomllib, which Python 3.10 lacks.
        version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(
            encoding="utf-8"), re.M).group(1)
        if have != found or found["version"] != version:
            print(f"{OUT.relative_to(ROOT)} is out of date: run python scripts/whats_new.py")
            return 1
        print(f"{OUT.relative_to(ROOT)} is {found['version']}'s, {len(found['items'])} items")
        return 0
    OUT.write_text(json.dumps(found, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {found['version']}, {len(found['items'])} items")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
