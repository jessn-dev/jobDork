# Changelog entries waiting for a release

Each pull request adds **one file here** with its changelog entry, instead
of editing the top of [../CHANGELOG.md](../CHANGELOG.md). Two pull requests
open at once then never change the same lines, so neither is blocked by a
conflict when the other merges.

Name the file for the work (`master-resume.md`, `remove-and-quit.md`) and
put one entry in it, written as an entry in the changelog is:

```markdown
## Added — 2026-11-05 — A master resume, told apart from the one you send

What was wrong or missing, what changed, and why. Release pages are built
from these entries, so write for the person reading the release.
```

- The kind is one of Added, Changed, Fixed, Security, Removed or Checked.
- One entry per file; no `---` lines (they are added when collected).
- `python scripts/changelog.py check` says whether every file here is well
  formed; the tests run the same check, so CI refuses one that is not.

**At a release**, the release pull request runs
`python scripts/changelog.py collect`: every entry here moves into the
changelog above the newest one, newest first, and its file is deleted.
`scripts/tag_release.py` will not tag while any are left here.
