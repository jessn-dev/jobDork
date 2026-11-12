## Changed — 2026-11-11 — Each release is announced in Discussions

Asked for on 2026-11-11: every release is also posted in the repository's
Discussions, under **Announcements**, with the same text as its release
page (what changed, the downloads, how to check them), so people following
the project hear of updates there. The release run's `gh release create`
makes the discussion itself (`--discussion-category Announcements`); its
job may now write discussions, nothing more.
