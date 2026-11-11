## Security — 2026-11-11 — Start over, notes, the AI's fence, proxies and the screenshot script

The last five fixes from the code scans of 2026-11-06 (Claude Security
F10, F14, F18 and the hand scan's #14 and #15).

- **Start over** (#15): it deleted every file in the output folder when
  that folder was beside the config, and with `output.dir: .` the folder
  *is* the config's, so `.env` and anything else there went too. It now
  deletes only the reports jobdork writes there (`index.html`,
  `roles.json`, `roles.md`, `roles.csv`; `render.REPORT_FILES`).
- **Deleting a note** (#14): a note and its copies on the job's other posts
  were found by their words and time, so the same note saved twice in one
  second (a double click) went entirely on one delete. Now the note clicked
  goes, and one copy on each other post.
- **The fence around what the AI reads** (F10): block markers were taken
  out before hidden characters were, so `<<`, a zero-width space, then
  `/ADVERT>>` passed, became a real marker once the hidden character was
  removed, and closed the fence. Markers are now looked for in the text as
  the model will read it.
- **Through a proxy** (F14): with `HTTPS_PROXY` or `HTTP_PROXY` set, the
  proxy looked each site's name up itself, so a name that passed the
  check for a public address could resolve, inside the proxy's network,
  to a private one. The proxy is now given the address checked: CONNECT to
  it for https, with TLS still checking the certificate against the name,
  and the address in the URL for http, with the name in the Host header.
  `JOBDORK_PROXY_BY_NAME=1` sends names as before, for a proxy that
  refuses addresses (docs/CONFIG.md).
- **The guide's screenshot script** (F18): it started its demo server with
  a fixed token and the whole environment, keys included. The token is new
  each run and anything named like a key is left out.

tests/test_scan_data_fixes.py covers each one, the proxy with a local
socket that records what it was sent. tests/test_cleanup.py now uses the
report's real name (`index.html`).
