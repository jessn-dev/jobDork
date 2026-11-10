## Security — 2026-11-09 — The Adzuna key stays out of logs and the Activity page

Adzuna takes its key only in the address's query string. When a request
could not connect (offline, DNS down, a timeout), the error repeated the
whole address, key included, and the scan logged it: the key landed in
plain text in `logs/scheduled-scan.log` or `logs/app.log`, and in the
database the Activity page reads, though jobdork keeps keys only in the
keychain or in memory (Claude Security, 2026-11-09). A problem report never
carried it: its scrubbing already took `app_key=` out.

Now a connection error's text has every query string cut to `?…` before it
is kept (`fetch/http.py`, `quiet`). Under that, every log line has the value
of any `…key=`, `…token=`, `…secret=`, `…password=` or `app_id=` removed
before a handler sees it, tracebacks included (`core/telemetry.py`,
`without_keys`), so the log files, the terminal and the Activity page all
get the cleaned line. tests/test_fetch_guard.py and tests/test_telemetry.py
cover an Adzuna-shaped error and a logged line with a key, in a log file
and on the Activity page.
