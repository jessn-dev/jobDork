## Added — 2026-11-11 — Employers to skip

Asked for on 2026-11-11. A list of employers whose job posts are dropped
wherever they come from (Adzuna, Workable, USAJOBS, the built-in employer
boards, your own boards): a past employer, one you would never work for, a
staffing agency that floods your results. Built-in boards could already be
switched off one by one, and keyword sources as a whole, but nothing took
an employer out of every source; dealbreakers read the advert, not the
company.

- **Search → Employers to skip**: add, remove, or remove all, like the other
  lists (`skip_employers` in the config, one of each however it is cased).
- **Skip this employer** in the job post window adds its employer in one
  click and closes the window.
- Names are compared as advert names are, without case or endings like Inc,
  LLC and Corp (`agency.core_name`): "Acme" skips "ACME Corp." and "Acme,
  Inc.", not "Acme Health". A skipped post is dropped first, before its
  title is read, with the reason "an employer you skip" on Job posts'
  Dropped list (`screen.skipped_employer`).
- A change re-screens the stored posts, named on the Dashboard's queue
  ("Employers to skip: added Initech").

The guide's Search and job window pages and `docs/CONFIG.md` say so, with
`search.png` and `job-window.png` retaken (the demo skips one agency).
tests/test_skip_employers.py covers the matching, the save and load, and
the re-screen.
