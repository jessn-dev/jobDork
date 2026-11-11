## Security — 2026-11-10 — Seven quick fixes from the code scans

From the code scans of 2026-11-06 (one by hand, one by Claude Security):

- **A model's name could carry a script into the page** (F4). The checker's
  name went into the job card's HTML unescaped, and a name can come from
  another computer's Ollama or a connection code. It is escaped now; a
  model name in the settings must be a name (letters, digits and
  `. _ : / @ + -`), and names from a remote Ollama's list that are not are
  left out.
- **The resume path could be pointed anywhere** (#1). Saving the settings
  took a `resume_path` from the page, and the resume file could then be
  read back through `/api/resume/file`, and its text went to the AI: any
  file, for whoever held the page's token. The resume is now set only by
  uploading it (or in config.yaml by hand); a save that names another path
  is refused.
- **A Retry-After of `-1`, `NaN` or `inf`** (#10) made the pause negative or
  endless, and `time.sleep` raised, stopping a check or a page read. Such a
  header is now ignored (`Fetcher.retry_seconds`).
- **A count the page sent that is not a number** (#12), such as
  `limit=abc` to start AI judging, got no answer and logged a traceback; it
  is now refused with a reason.
- **A `%` in a folder or program path** (#13) broke the scheduled scan on
  Linux and Docker without a word: cron reads a bare `%` as a new line. It
  is escaped in the cron line, and read back as written.
- **A formula in a CSV export** (#2): a job title from a board that began
  `=HYPERLINK(` ran as a formula when `roles.csv` or the digest's CSV was
  opened in a spreadsheet. Text cells that would start a formula get a
  leading apostrophe.
- **A `javascript:` link in the HTML report or the email digest** (#3):
  only http(s) addresses become links there now, as on the dashboard.

tests/test_quick_security.py covers each one.
