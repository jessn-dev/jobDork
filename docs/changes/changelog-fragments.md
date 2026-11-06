## Changed — 2026-11-05 — Changelog entries wait in files of their own, so pull requests do not conflict

Every pull request added its entry at the top of `docs/CHANGELOG.md`, so any
two open at once changed the same lines: whichever merged second was blocked
by a conflict and had to be merged again by hand (#128 and #129 both were).

Each pull request now adds one file to `docs/changes/` with its entry
instead. `scripts/changelog.py check` says whether each is well formed (the
tests run it, so CI refuses one that is not), and the release pull request
runs `scripts/changelog.py collect`, which moves them all into the changelog
above the newest entry, newest first by date and then by when each was
added, and deletes the files. Release pages read the changelog as before.
`scripts/tag_release.py` refuses to tag while an entry is left waiting, so
none is left off a release page, and `scripts/set_version.py` does not count
the waiting entries as pages that name a version.

CONTRIBUTING.md, the pull request template, `docs/changes/README.md` and the
changelog's opening say where an entry goes now. Tests cover the check
(heading, kind, date, one entry a file, no separators), collecting (order,
placement above the newest entry and the backlog left where it is, files
deleted, nothing changed when one is malformed) and every entry waiting in
the repository.
