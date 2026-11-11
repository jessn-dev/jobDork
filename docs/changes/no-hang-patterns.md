## Security — 2026-11-10 — A stranger's page cannot freeze jobdork or fill its memory

From the code scans of 2026-11-06 (Claude Security F1, F3, F12, F13, F15 and
the hand scan's #6). Each of these read text from someone else's server with
a pattern that, fed the right input, tried every way through it: one page
could freeze the whole process, and with it the scan and the dashboard.

- **robots.txt wildcards** (F1): each `*` became `.*` in a regex, and a rule
  like `/*a*a*a…*b` made it backtrack without end. Now matched by `str.find`,
  piece by piece (RFC 9309 meaning unchanged), and only the first 500 rules,
  with at most 20 wildcards each, are read.
- **The recruiter check** (F3): "our client" followed by a long run of
  space tried every split of it between two `\s*`; now one run.
- **Sitemaps and search-engine data** (F12): `<url>(.*?)</url>` and the
  JSON-LD `<script>` pattern read an unclosed tag to the end of the page
  once for every tag; now found by `str.find` (`site._url_blocks`,
  `textutil.ld_json_blocks`, used by the site reader, enrich and the
  listing check).
- **The page title** (F13): read in two steps, the title first and its
  parts in Python, instead of one pattern that stalled on spaces with no
  `</title>`.
- **HTML to text** (F15): a tag can no longer span another `<` (a page of
  `<<<<` with no `>` was read to the end for each), and scripts and styles
  are cut at their closing tag by `str.find`.
- **One answer's size** (#6): every answer is read streamed, at most 32 MB
  of it (room for the largest board answers); past that the rest is not
  read and a warning names the site (its host only: a query string can carry a key).

tests/test_hang_patterns.py feeds each one the input that used to stall it,
with a two-second limit, and checks the ordinary case still reads the same.
