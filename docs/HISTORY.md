# How jobdork got here

The short story of what jobdork was, what it became, and the decisions that
turned around on the way. [CHANGELOG.md](CHANGELOG.md) has every change in
detail and [DECISIONS.md](DECISIONS.md) the reasoning behind the big ones;
this is the map.

---

## March 2026: a Google search builder

jobdork began as one script of about 900 lines that built Google searches
for job postings: a title, a place and a date range turned into "dorks",
Google queries with `site:` and other operators aimed at job boards, opened
in the browser. It reached anything Google had indexed, including role lists
in public Docs and recruiter posts. It still exists, unchanged in behaviour,
as `jobdork dork`.

Its limit was the reason for everything after: a Google result is a link you
have to open to judge. Nothing could filter it, score it, or remember you had
seen it.

## Late August 2026: a scanner beside it

The second tool read job postings as data, straight from the systems
employers post them to, and kept what passed rules written down once.

- **Sources:** Workable's search across its whole market with no key;
  Greenhouse, Ashby, Lever, SmartRecruiters and Breezy, one employer each;
  Adzuna and USAJOBS with a free key.
- **Screening** that says why: title, then work arrangement, then distance
  (a gazetteer of 70,000 places in 245 countries), then salary, then
  dealbreakers, each drop counted and named. A rule only drops what an
  employer actually said; an unstated salary or arrangement is kept and
  flagged.
- **Memory:** a SQLite database, so a scan reports what is new, and a status
  (interested, applied…) sticks to a job.
- **`discover`**, which reads an employer's board off their own careers page
  rather than guessing it from their name, and refuses a board it could not
  verify.
- A static page, an email digest, `enrich` for full adverts, drafts of a CV
  and cover letter through `claude -p`, and a first dashboard.

**Decided then:** no bundled list of employers. Keyword search reached whole
markets without one, and a list would need building and keeping current.

## Late September 2026: AI, a real dashboard, and releases

- **An AI reader** (Ollama locally, or Claude, Gemini, ChatGPT) that judges a
  job against the resume, writes cover letters, reviews and tailors the
  resume as a PDF, and reads posting pages. Every output is checked for
  hallucination, HalluLens-style: split into claims, each claim's quote
  looked up in the resume and the advert by script, unsupported ones listed.
  Keys are held in memory only.
- **The dashboard grew into the main way to use it**: a Dashboard of runs and
  metrics (from the terminal too), job posts with copies of one job grouped,
  a Search page with a country, region and city picker, Resume, Sources, AI
  and Tools pages.
- **Freshness:** a post's age is measured from the board's own dates, new
  posts rank higher, stale ones lower, ghost listings past 90 days are
  dropped.
- **A Docker image for a NAS**, run as a non-root user, with a guide to
  running it at home with the AI on another computer over Tailscale.
- **Releases with sign-off:** tests and security scans on every push, `main`
  changed by pull request only, and an image published only for a version
  tag, after the owner approves it, signed and with a record of how it was
  built. The code said 0.13.0 when publishing began, so releases start at
  0.14: `v0.14.0` and `v0.14.1` were never released, 0.14.2 was the first,
  then 0.14.3. (The changelog's August headings 0.14.0 and 0.15.0 predate
  this and were never releases.)
- **New sources:** Kalibrr (the Philippines and Indonesia), Himalayas (remote
  jobs filtered to your country and hours), Workday.

## 1 October 2026: built-in employer boards, and the readers to fill them

The first measurement changed the plan. On a list of 46 real employers,
mostly American and across industries, Discover found a readable board for
10. Hospitals, retailers and banks were almost all missing: they hire through
Workday, Oracle, Eightfold, Taleo and their own careers sites, and keyword
search reaches none of those.

- **Discover learnt to follow a site's own links and sitemap,** and to honour
  robots.txt properly.
- **Readers for Oracle Recruiting Cloud, Eightfold and Taleo Business
  Edition,** and for **an employer's own careers site** where it marks its
  postings up for search engines.
- **The no-bundled-list decision was reversed:** jobdork now ships hundreds
  of verified employer boards, re-checked weekly by a GitHub Action that
  proposes changes as a pull request, each board found and verified by
  Discover and never typed in by hand.
- **Dealbreakers in plain words** ("security clearance", "us citizen")
  instead of regular expressions, with the usual other wordings included and
  "no clearance required" not counting.

The test list went from 10 of 46 to 30 of 46.

## 2 October 2026: beyond the US

- **Asia measured:** a default scan for 11 Asian cities, counted by source.
  Then Asian, Canadian and Mexican employers added to the built-in list (368
  boards), and Kalibrr fixed for Indonesia. Manila, Bengaluru and Singapore
  are well covered; Tokyo, Seoul and Hong Kong are not.
- **Europe, the Middle East, and Australia and Oceania planned**, with the
  same steps ([REGIONS.md](REGIONS.md)).
- **Docker keeps the resume and letters** across restarts, warns when the
  data is not on a mounted folder, and ships a `compose.yaml` for NAS apps.
- **First-run onboarding decided:** a guided wizard that starts with the
  resume, lets the AI suggest the search, and runs a quick first scan with
  the full one in the background ([DECISIONS.md](DECISIONS.md)).

---

## Decisions that turned around

| Then | Now | Why it changed |
|---|---|---|
| No bundled list of employers; keyword search reaches whole markets (August) | 368 verified employer boards ship built in (October) | Measured: keyword search missed most hospitals, retailers and banks; the list's costs (time, rot, crawling) are kept down instead ([SOURCES.md](SOURCES.md#a-bundled-list-of-employers-and-what-it-costs)) |
| AI optional | AI required before scanning (30 September) | The owner sees jobdork as built around a model |
| AI required before scanning | AI part of the product, but a scan runs without it (2 October) | Someone without a model would be stuck before seeing anything work |
| Docker kept the resume and letters only until it stopped | Kept in the data folder; temporary only by choice | Every restart and update meant uploading the resume again |
| Dealbreakers as regular expressions | Plain words; patterns under Advanced | Most people looking for work should not need regex to say "no clearance" |
| A tool for tech jobs, tested from the Philippines | US first, every industry; then the rest of the world | Stated by the owner; benchmarks and the built-in list lead with US employers across industries |
