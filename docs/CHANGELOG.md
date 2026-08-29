# Changelog

Each finished piece of work gets its own entry here, newest first.
[Still outstanding](#still-outstanding) is the backlog: a bullet moves out of
it and into an entry when the work is done.

---

## 0.5.0 — 2026-08-29 — `discover`

Finds an employer's job board by reading it off their own site, so the five
per-employer adapters have something to fetch. Those boards are the fix for
Adzuna's 500-character advert cap: 653 of 855 roles in one run came back too
truncated to screen.

### Added

- **`jobdork discover <employer>`** — fetches their careers pages and takes
  the board token out of the links they publish themselves.

  ```
  $ jobdork discover vectra.ai
  Looking for vectra.ai...
    greenhouse         16 jobs  [verified]  .../boards/vectranetworks/jobs
                      board names itself 'Vectra'

  Re-run with --add to write these into your config.
  ```

  `vectranetworks` is the point. Tokens are not company names — it is also
  `mymoose` for Rapid7 and `evergreenix` for Garrison — so nothing here
  guesses one from a name.

- **`--add`** writes verified boards into `sources.companies`. The file is
  rewritten as text rather than dumped through the YAML round-trip, because
  a dump strips every comment out of a file that is mostly comments; a test
  asserts the comment count is unchanged and that a second `--add` appends
  rather than clobbering.

### Four outcomes, kept distinct

Verified against live sites while building this, one per case:

| | Example | Meaning |
|---|---|---|
| `[verified]` | vectra.ai, ramp.com | found on their site **and** the board returned jobs |
| `[token not on page]` | stripe.com | the platform is plainly there — 535 mentions of Greenhouse, a `greenhouseId` on every posting — and the board token is named nowhere |
| `[no adapter]` | crowdstrike.com | a Workday board, located and named rather than folded into "nothing found" |
| `[empty board]` | — | answered 200 with no jobs, which on Ashby and SmartRecruiters is also what throttling looks like |

**Only `[verified]` can be added.** An unread board is a guess, and banking a
guess into the source list is worse than leaving it out — a board that answers
is not proof you found the right company. On Ashby, `primer` is a Florida
micro-schools operator; on Greenhouse, `peak` is a Texas physiotherapy chain.
Where the platform states the employer, the board's own claim about itself is
printed next to the result so a mismatch is visible.

### Fixed while building it

- **The `embed/job_board/js?for=` script-tag form was not matched**, which is
  how Vectra publishes theirs. Missing it lost a board whose token is nothing
  like the company name — exactly the case this command exists for.
- **The listing page often carries the token where the landing page does
  not.** `stripe.com/jobs` has no board reference at all; `stripe.com/jobs/search`
  has 535. `/jobs/search` and `/careers/search` are now tried.
- **A company name is refused rather than turned into a domain.** Guessing
  `acme.com` from "Acme Corporation" is the same mistake as guessing a token
  from a name.

---

## 0.4.0 — 2026-08-29 — Email digest

The roles come to you now. A dashboard is something you have to remember to
open; a digest arrives, and what arrived with it is what was not there before.

### Added

- **`jobdork digest`** — mails what the last scan found, without rescanning.

  ```bash
  jobdork digest --email you@example.com          # only what is new
  jobdork digest --all --csv --email you@...      # everything open, CSV attached
  jobdork digest --dry-run                        # print it, send nothing
  ```

- **`jobdork scan --email`** — one command for a cron job: fetch, screen,
  store, write the files, then mail the new roles. The mail is sent *after*
  the files are written and its failure is reported without unwinding the
  scan, because a mail that bounces must not cost you the roles it was about.

- Plain-text and HTML bodies, and an optional CSV attachment written through
  `render.to_csv` rather than a second implementation — so the columns in your
  inbox and the columns in `out/roles.csv` cannot drift apart. A test asserts
  the two headers match.

- Credentials are the two the dork generator already uses, `RESEND_API_KEY`
  and `RESEND_FROM` from `.env`, including its older `JOB_DORK_EMAIL_FROM`
  spelling.

### Fixed

- **"New" meant "first seen on the most recent calendar date."** That looks
  equivalent to "first seen in the most recent scan" and is not: scan twice in
  one day and the second digest resends everything the first one already sent,
  and a day with no scan at all reports yesterday's roles as new. It is now
  anchored to the last completed run in the `runs` table, falling back to the
  date rule only when no run has ever been recorded.

### Deliberate

- **An empty digest is not sent** unless you pass `--even-if-empty`. A mail
  that says "nothing new" every morning trains you to ignore the one that says
  something.

- **Building a digest never needs a credential**, only sending does, so
  `--dry-run` works on a fresh clone and the rendering is testable without a
  key.

- **A missing or wrong credential is named**, with the URL to fix it, rather
  than failing silently or exiting the process out from under a scheduled
  scan.

---

## 0.3.1 — 2026-08-29 — Markdown and CSV output

### Fixed

- **`output.formats` accepted `md` and `csv` and wrote neither.** Config
  validation passed them and `cli.py` only handled `html` and `json`, so
  asking for Markdown produced nothing and reported success — the one silent
  failure left in a config layer built to refuse exactly that.

  Both are now written. `out/roles.md` is the list as text, for pasting into a
  note or an email; `out/roles.csv` is one row per role across 18 stable
  columns, with the advert left out because a 5,000-character description in a
  spreadsheet cell breaks every viewer that opens it. `salary_stated` is its
  own column, because a blank pay range means nobody published one and that is
  not a zero.

  `markdown` is normalised to `md` at load, so the two cannot reach the writer
  as different strings. A test now asserts that every format the validator
  accepts has a writer behind it, and an unknown format still stops the run.

---

## Still outstanding

Nothing here is built. It is written down so that a gap is a decision rather
than a surprise, and so the next session starts from a list instead of from
memory.

### Designed, never built

- **`jobdork serve`** — the interactive dashboard. `scan` already writes a
  static `out/index.html`; this is the version with buttons. Standard library
  `http.server` only, bound to `127.0.0.1`, validating the `Host` header
  against the address it actually bound to, sharing the database with the CLI
  so the two cannot disagree. See
  [ARCHITECTURE.md](ARCHITECTURE.md#what-is-not-built).
- **Document generation** — screen, CV and cover letter, each spawning
  headless `claude -p` in the background and writing results back as
  `artifacts` rows. Every invocation costs tokens, so nothing generates
  without a click. Quality gates would be mechanical: phrase overlap between
  CV and cover letter, em-dash count, and any figure or scale word in a draft
  that is not in the résumé. Job descriptions must be treated as hostile
  input if this is built.
- **`enrich`** — Breezy and SmartRecruiters return a summary index; their
  full adverts need a second request per role. Until then those roles carry
  thin descriptions and cannot really be screened.

### Started, incomplete

- **No CLI overrides.** Only `-c/--config`, `--db` and `-v` exist. Changing
  country, anchor, radius or titles means editing the config or keeping
  several files and passing `-c`. Workable for a multi-country search, but
  not obvious.

### Known-unreliable, not fixable here

- **SmartRecruiters is unverified.** Every token tried returned
  `totalFound: 0`, which is also what the platform returns when throttling,
  so the two cannot be told apart. First successful run is the test.
- **Adzuna `au`, `nz` and `sg` answer 503.** The indexes exist and are
  currently unavailable. Nothing to fix; retry later.
- **`jobs.workable.com` is rate-limited until roughly 2026-08-29 evening.**
  Checked 2026-08-29: `Retry-After: 28525`. Earned by re-running full scans
  while tuning a config; use `scan --limit` for that instead.

### Smaller gaps

- **Metro aliases are US and Canada only.** `Bay Area`, `GTA` and `DMV`
  resolve; `Kanto`, `Klang Valley`, `NCR` and `Randstad` do not.
- **Dork results reach the database one at a time.** `jobdork add <url>`
  bridges a single posting; there is no bulk path from a dork run.
- **`locations.exclude` is a substring match** on the raw location string,
  with no region-level exclusion.
- **There is no `LICENSE` file**, though `README.md` and `pyproject.toml`
  both declare MIT. It needs a copyright holder name.
- **Nothing is committed.** HEAD is `8d151a3`; all of 0.2.0 and 0.3.0 exists
  only in the working tree.

---

## 0.3.0 — 2026-08-28

Removes the North America assumption. The tool now works from any country.

### Changed

- **`locations.countries` accepts any ISO 3166-1 alpha-2 code.** It was an
  allow-list of `US` and `CA`, backed by a hardcoded list of "foreign"
  countries to drop. That design would have silently deleted a Manila reader's
  entire market. Out of scope now means "not in **your** countries", and the
  same line drops a Berlin posting for a Chicago reader and a Chicago posting
  for a Manila reader. An empty list accepts everywhere.
- **`locations.units`** — `mi` or `km`, defaulting to miles for the US and UK
  and kilometres elsewhere. A `radius: 25` in Berlin was being read as 25
  miles, which is 2.6x the intended area.
- **`radius`** accepts any positive number, not just 5/10/25.
- **`salary.currency`** accepts 45 currencies, up from 2.
- **Adzuna follows `locations.countries`** instead of defaulting to `["us"]`
  for every reader regardless of where they live. Probed live: it serves
  `gb us ca ie in de fr nl at be ch es it pl br mx za`; `au nz sg` answer 503;
  `ph id my jp ae ru` answer 404 and have no index at all. A country it cannot
  serve is named rather than silently skipped.
- **USAJOBS skips itself** when `US` is not in `locations.countries`.
- **The gazetteer covers 245 countries**, 69,933 places, 2.3MB. The builder
  takes country codes, defaults to your config, and accepts `all`.
- **Australian state codes** (`NSW`, `VIC`, `QLD`…) are recognised, and
  `state_name` spells them out — Workable ignores two-letter codes silently,
  so `NSW` returned the whole world.

### Fixed

- **Accents now fold both ways.** `Zurich` finds `Zürich`, `Sao Paulo` finds
  `São Paulo`.
- **English exonyms resolve.** `München` and `Munich` share almost no letters,
  so folding cannot connect them; a curated table covers ~40 cities.
- **`Makati` and `Makati City` are one place.**
- **City-states resolve.** In Singapore the country name is also the city name,
  and a country-only string was being refused.
- **`Remote - Australia` no longer resolves to Cuba.** There is a town called
  Australia there, population three thousand. A country name that is the whole
  string names no city.
- **Alias rows no longer create false ambiguity.** Writing an ASCII alias
  beside every accented name made São Paulo look like two different places, so
  the ambiguity check refused to resolve it. Aliases are now only written when
  they fold differently, and same-coordinate entries are treated as one place.
- **A city ambiguous *within* your own countries** now resolves to the largest,
  marked approximate, instead of being abandoned.

### Measured

Adzuna coverage, probed live with a key, and the reason the Philippines needs
a different answer than Germany:

| Region | Adzuna | Practical coverage |
|---|---|---|
| EU / UK | 10 indexes live | full |
| Australia, NZ, Singapore | 503 | Workable + boards + dorks until restored |
| Philippines, Indonesia, Malaysia, Japan, UAE | 404, no index | Workable + boards + dorks |

---

## 0.2.0 — 2026-08-28

Adds a scanner alongside the existing Google-dork generator. The dork tool is
unchanged in behaviour; everything new is additive and lives in a `jobdork/`
package. Works in any country.

Coverage comes from keyword search rather than a bundled list of employer
boards, so there is no crawl index to maintain and no source file to keep
current. Boards for named employers are added individually when you want them.

---

### Added

**Package `jobdork/`** — 2,700 lines across 20 modules.

| Module | What it does |
|---|---|
| `config.py` | YAML config, validated at load. Secrets read from `.env` only |
| `store.py` | SQLite: roles, role_state, artifacts, runs |
| `geo.py` | Offline gazetteer, radius, state/metro/country normalisation |
| `screen.py` | Title, location, salary, work-mode and dealbreaker filtering |
| `scan.py` | Orchestration, threading, rescreen |
| `resume.py` | Offline résumé parsing and skill-overlap scoring |
| `render.py` | Static HTML + JSON output |
| `cli.py` | `scan / list / show / applied / rescreen / add / sources / dork` |
| `textutil.py` | HTML-to-text for advert bodies |
| `fetch/http.py` | Per-host pacing, retries, 429 circuit breaker |
| `fetch/*.py` | Eight source adapters |

**Sources.** Keyless: Workable cross-employer search, plus Greenhouse, Ashby,
Lever, Breezy and SmartRecruiters per employer board. Keyed and dormant until
credentials exist: USAJOBS, Adzuna. A dormant source reports why it skipped
rather than silently not running.

**Radius filtering.** `locations.anchor` plus `radius: exact | 5 | 10 | 25`
(miles). Measured against a bundled gazetteer of 8,879 US and Canadian places
(GeoNames `cities5000`, 321KB, built by `scripts/build_gazetteer.py`). No
geocoding API, no key, no per-role network call.

**Status tracking.** `new → interested → applied → submitted → interviewing →
offer`, plus `rejected`, `withdrawn`, `skipped`, `closed`. The last four are
hidden from results. A status you set outranks a later filter change:
`rescreen --remove` never deletes a role you acted on.

**Résumé scoring**, offline and free. Reads `.docx`, `.md`, `.txt` and — via
the optional `pypdf` extra — `.pdf`. Sorts the list by skill overlap and names
the gaps. Never drops a role; it only adds points.

**Static dashboard** at `out/index.html`. Self-contained, light and dark, no
server and no external request.

**Tests.** `tests/run_all.py` discovers every `tests/test_*.py` and needs no
pytest. 30 tests covering the rules that fail quietly.

**Docs.** `config.example.yaml`, `pyproject.toml`, expanded `README.md`.

---

### Fixed — pre-existing

- **`.gitignore` patterns were `.csv` and `.txt`**, which match a file named
  exactly `.csv`. Generated result files were never actually ignored. Now
  `*.csv` / `*.txt`, plus `.env`, `config.yaml`, `config.local.yaml`, `data/`
  and `out/`.
- **Greenhouse dork pointed at the retired domain.** Greenhouse moved to
  `job-boards.greenhouse.io`; the dork searched only `boards.greenhouse.io` and
  missed current postings. Both are searched now.
- **The virtualenv was broken** — `.venv/bin/python` was a dangling symlink to
  a removed pyenv 3.12, so `run.sh` silently fell back to a system Python with
  no `resend` installed. Rebuilt on 3.13.
- **Dork board list skewed to startups.** Added 16 North American mid-market
  ATS domains: Paycom, ADP WorkforceNow, UKG, Paylocity, JazzHR, BambooHR,
  Jobvite, Taleo, SuccessFactors, Oracle Cloud, Recruitee, Teamtailor,
  Eightfold, Dover, Pinpoint, USAJOBS. 33 standard boards, up from 22.

### Fixed — introduced and caught during this work

- **`gh_jid` was stripped as a tracking parameter.** Greenhouse's
  `absolute_url` is often the employer's own domain with the job id in the
  query string (`stripe.com/jobs/search?gh_jid=7532733`), so stripping it
  collapsed 579 Stripe jobs into a single uid. A parameter that identifies the
  posting is not tracking.
- **`screen()` overwrote adapter flags.** It replaced `role.flags` wholesale at
  the end, so anything the fetch layer knew — "adzuna predicted salary
  ignored" — never reached the database. Now merged.
- **Foreign roles leaked through.** "Berlin, Germany" is not in a US/CA
  gazetteer, so it resolved as *unreadable* and was kept under the
  keep-when-unresolvable rule. A named foreign country is now a positive
  statement about where the job is, and drops it. "Atlanta, Georgia" still
  resolves to the US state.
- **`Washington, D.C.` resolved to Washington *state*** — a 2,300-mile error.
  Periods are stripped before the state lookup.
- **Adzuna location parsed from the wrong field.** `display_name` is city plus
  *county* ("Round Rock, Williamson County"), which no gazetteer can place;
  187 of 238 roles were unplaced and the radius was quietly doing nothing. The
  structured `location.area` is now used.
- **USAJOBS pay periods.** `RateIntervalCode` is a two-letter code (`PA`), not
  a word. An unrecognised code fell through to a default of "year", which
  would have stored $50/hour as $50/year and let any salary floor hide the job.
  Unknown codes are now refused rather than assumed.
- **USAJOBS multi-location postings.** A federal role is routinely open in 20+
  cities; taking `PositionLocation[0]` displayed an Austin-matching job as
  "Salt Lake City" and failed a radius it was never outside. The nearest
  location is now chosen using the latitude and longitude USAJOBS supplies.
- **Greenhouse adverts are double-escaped HTML** (`&lt;h2&gt;`). A tag
  stripper matches nothing and returns the entities verbatim, so every
  Greenhouse dealbreaker silently stopped matching. Unescaped first now.
- **`jobdork dork` swallowed its own flags.** `argparse.REMAINDER` treats a
  leading `--flag` as an option to the parent parser. `dork` is now dispatched
  before argparse sees anything.
- **Aggregator duplicates.** One Adzuna vacancy arrives under six or seven
  distinct posting ids. `list` collapses repeats of the same employer and
  title, keeping the best-scoring copy; `list --duplicates` shows them all.
  One run went from 855 rows to 729.

---

### Verified against live APIs

Every adapter was probed before it was written, and several published
behaviours turned out to be wrong.

**Workable** — `GET jobs.workable.com/api/v1/jobs?query=&location=`, no key.
Adverts come back inline, so there is no enrich step. `location` takes exactly
one value; repeating the parameter answers 400. It accepts a city, state or
country spelled out, and silently ignores two-letter codes — `TX` returns the
whole world. `workplace` filters `remote`/`hybrid`/`on_site` server-side.
`pageToken` pages cleanly with no overlap. **There is no salary field at all.**

**Greenhouse** — `boards-api.greenhouse.io/v1/boards/{token}/jobs`.
`content=true` is required or there is no advert. `pay_transparency=true`
returns `pay_input_ranges`, which was empty on every Stripe role.

**Ashby** — `api.ashbyhq.com/posting-api/job-board/{name}`. `isRemote` is a
decoy: Ramp returned `isRemote: true` on a role whose `workplaceType` was
`Hybrid`. `workplaceType` is authoritative. Compensation is well structured.

**Lever** — `api.lever.co/v0/postings/{token}?mode=json`. Bare top-level list.
Separate US and EU deployments; a token on one 404s on the other.

**Adzuna** — verified with a live key. `title_only`, not `what` (`what`
searches the advert body and returns every engineer whose advert mentions
their manager). `distance` is **kilometres**. `salary_is_predicted` is the
string `"1"`, and a predicted figure always has `min == max` — 251 of 292 in
one run were predicted, and predicted figures are discarded rather than
stored, because a guess must never disqualify a job.

**USAJOBS** — verified with a live key. `Radius` is real and in miles: Austin
at 25 returned 23 postings, at 200 returned 52. **An unknown parameter is
ignored silently with HTTP 200** — a search carrying `NotARealParam` returned
the same 501 results — so a misspelled filter does not fail, it just does not
filter. `JobSummary` is truncated to about 500 characters, so all prose fields
are concatenated before a dealbreaker reads them.

**SmartRecruiters** — **unverified.** The envelope is right
(`{offset, limit, totalFound, content}`) but every token tried returned
`totalFound: 0`. That is the platform's known failure mode: it answers 200
with nothing both for a board that is not there and for one that is throttling.
Believe your first successful run over this file.

---

### Measured

One Chicago run, 16 titles, radius 25 miles, 855 roles before dedupe:

| Source | Roles | Avg advert | Arrangement stated | Pay stated |
|---|---|---|---|---|
| adzuna | 653 | **500 chars (hard cap)** | 136/653 | 30% |
| workable | 200 | 4,903 chars | **200/200** | 0 (no field) |
| usajobs | 2 | 4,102 chars | 0/2 | **100%** |

**Adzuna truncates every advert to exactly 500 characters.** Dealbreakers,
work-mode detection and résumé fit scoring all read the advert body, so Adzuna
is a discovery-and-salary source and Workable is the one that can be filtered
on. This is the single most important limitation in the tool.

Federal hiring uses a different vocabulary. With private-sector titles USAJOBS
kept 0 of 23 roles; with `IT specialist`, `computer engineer`, `computer
scientist` and `software developer` it kept 17 of 101 — and every one stated
pay.

---

### Known limitations

- **No bundled employer list.** Coverage comes from keyword search plus boards
  you name. `jobdork dork` covers the rest.
- **Adzuna free tier** is 2,500 calls a month, about four scans a day at three
  titles; a second country doubles it.
- **`jobs.workable.com` is strict.** A 16-title config at 0.7 requests/second
  collected 15 consecutive 429s and then a `Retry-After` of 86,130 seconds — a
  24-hour refusal. The rate is now 0.4/s with a 6-page cap. Use
  `scan --limit` while tuning a config rather than re-running full scans.
- **Indeed, Glassdoor, LinkedIn, Dice and ZipRecruiter** have no usable public
  API and remain dork-only.
- **`enrich` is not implemented.** Breezy and SmartRecruiters return a summary
  index; their full adverts need a second request per role.
- **No `discover` command yet.** Board tokens have to be supplied by hand.
- **PDF résumés need `pypdf`**, an optional extra. A PDF that extracts under
  200 characters is refused rather than silently scoring every role zero.

### Not built

`jobdork serve` (interactive dashboard) and `claude -p` document generation —
screen, CV and cover letter with quality gates — are designed but unwritten.
Everything else works without them.

---

### Dependencies

Added `PyYAML` and `requests` as required, `pypdf` as an optional extra for
PDF résumés. `resend` unchanged.
