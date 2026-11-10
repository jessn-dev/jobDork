## Changed — 2026-11-09 — One copy of each small helper

The code scan of 2026-11-06 found small helpers kept in two or three places,
some of which had drifted apart. Each now has one copy, and the
behaviour is the same apart from the two fixes noted below:

- Comparing a quote with its source (lower case, single spaces):
  `core/textutil.folded`, used by the AI writer, the guard and the
  listing check, which each had a `_norm`.
- Reading an environment switch as off (`JOBDORK_NOTIFY`,
  `JOBDORK_UPDATE_CHECK`): `core/config.env_off`.
- Escaping text for XML (a Windows notification, a Task Scheduler task):
  `core/textutil.xml_text`. The scheduler's copy did not escape `"`; it
  does now, which reads back the same.
- A board's number and a Unix timestamp's day: `fetch.number` and
  `fetch.day_from_epoch`, for Ashby, Lever, USAJOBS, Greenhouse, Adzuna,
  Arbeitnow and Himalayas. **Fixed with it:** `"nan"` and `"inf"` parse as
  numbers, so a board that sent one gave a salary that failed every
  comparison with your pay floor and printed as "nan". They are now read
  as no salary.
- The email digest's flags and its company · place · pay line come from
  the report's (`output/render`, `flags_of`, `salary_text`,
  `meta_parts`), and the dork generator's email reads its Resend settings
  from the digest's.
- Sitemaps: discover reads them with the site reader's parser
  (`fetch/site.sitemap_urls`) instead of its own, which ignored `lastmod`.
  **Fixed with it:** the `<loc>` pattern no longer stalls on a sitemap
  with a long run of spaces and no closing tag.
- Same name, different job: `storage.documents_root` (only a container's
  folder) is now `container_documents_root`; listing's `_visible` (a page's
  text) is `_page_text` and readable's (a count of printed characters)
  `_ink_count`. The two `_resume_text` functions stay separate, on purpose,
  and each now says why it differs from the other.

tests/test_shared_helpers.py pins each shared helper, including the NaN
salary and the stalled sitemap.
