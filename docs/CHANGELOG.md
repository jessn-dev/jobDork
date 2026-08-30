# Changelog

Each finished piece of work gets its own entry here, newest first.
[Still outstanding](#still-outstanding) is the backlog: a bullet moves out of
it and into an entry when the work is done.

---

## 0.13.1 — 2026-08-29 — Workable is back

### Resolved

- **The Workable rate limit expired.** `jobs.workable.com` answers 200 again;
  a `security analyst` search in Chicago returns 512 results. Nothing was
  fixed and nothing needed to be — the circuit breaker read the refusal
  correctly and waited it out, which was the whole design.

  It cost roughly 24 hours of the widest keyless source, and it was earned by
  re-running full scans to test config changes. `scan --limit` exists for that.

- **The backlog is empty.** Every item that has been in *Still outstanding*
  has either shipped or expired. The section is kept as a heading, with the
  standing operational notes that are not work: Adzuna's permanent advert cap,
  SmartRecruiters' ambiguous silence, and Workable's temper.

### Changed

- Ruff's per-file ignores for `jobdork/dork/` extended to `RUF005` and `E741`.
  The generator was moved rather than rewritten, and linting 992 working lines
  to today's style is the change-for-its-own-sake that decision avoided.
  `ruff check .` is clean.

---

## 0.13.0 — 2026-08-29 — the review pass

Six structural problems raised in review. Five accepted as stated, one accepted
with a caveat.

### The dork generator lives in the package now

`main.py` and `config.py` sat at the repository root and were reached by
`runpy.run_path` on a hardcoded path — a hack that worked and would break the
first time the file moved. They are now `jobdork/dork/generator.py` and
`jobdork/dork/boards.py`, and there is a real entry point:
`python -m jobdork.dork`. `jobdork dork ...` still dispatches with the
generator's own flags intact.

**The generator itself was not rewritten.** It works, it is well documented,
and rewriting it would have been change for its own sake.

**Fixed during the move:** it resolved logs, `.env` and result files relative
to its own file, so moving it moved the user's files into the package.
`PROJECT_ROOT` now points where it did before.

### Schema migrations

`CREATE TABLE IF NOT EXISTS` gets a database created and then quietly stops
being enough — it cannot add a column, and a database created before a column
existed keeps opening cleanly and fails on the first write that mentions it.

`jobdork/migrations.py` runs numbered, append-only, forwards-only steps, each
in its own transaction, with the version in `meta.schema_version`. A database
newer than the code is refused rather than opened.

The first step reconciles `roles` against every column the current schema
expects, which closes the gap for good rather than for one column. Your
database migrated in place: **888 roles, 10 artifacts and 6 statuses intact.**

Eight tests build the case that cannot be reached by using the tool — an old
database opened by new code — including a step that fails mid-way and must
leave the version where it was.

### `pyproject.toml` is the only place dependencies are declared

`requirements.txt` now contains `-e .` and a comment explaining why. Two lists
of dependencies drift, and the one that drifts is the one nobody edited.

Same problem, same fix, for the version: `__version__` reads installed package
metadata instead of a second literal. **`jobdork --version` had been reporting
0.2.0 through five releases.**

### ruff, configured and clean

75 issues at the start, zero now. The configuration says which rules are
ignored and why — `BLE001` because catching broadly around one job board is
deliberate and commented at every site, `RUF001` because en dashes in salary
ranges are correct punctuation rather than confusables.

### Screening heuristics are configurable

`BLOCKERS` and the work-mode patterns were hardcoded. They encode a judgement
about one job market — "program" turns an engineering manager into a different
job in the US and may not elsewhere — and a judgement baked into source is one
nobody can disagree with.

```yaml
screening:
  blockers: [product, business, program, sales]
  loose_gap: 2
  office_patterns: ["in the Chicago office"]
```

Extra patterns are **merged** with the built-in ones rather than replacing
them, so adding one never silently loses the defaults. A broken pattern stops
the run, like every other regex in the config. Defaults are unchanged, so a
config that says nothing behaves exactly as before.

### pytest, with the custom runner kept

Accepted with a caveat. The suite is plain functions and asserts, so pytest
already collected all of it — this was configuration, not a rewrite, and
`[tool.pytest.ini_options]` now provides it.

`tests/run_all.py` stays, and is not redundant. It runs the same files **with
nothing installed**, which is what makes a fresh clone testable before
`pip install`, and it exists because CI once ran one test file and reported a
confident pass over the rest. Both are wired up; they run the same 132 tests.

---

## 0.12.2 — 2026-08-29 — documents go in Documents

Generated CVs, cover letters and screens were being written to
`~/job-applications`, dropped straight into the home directory. That is not
where documents belong on any of the three platforms this runs on.

### Changed

The default is now the user's **Documents** folder — `~/Documents/job-applications`
on macOS and Windows, and on Linux whatever `XDG_DOCUMENTS_DIR` or
`~/.config/user-dirs.dirs` says it is, because a localised desktop calls it
`Dokumente` or `Documentos` rather than `Documents`.

If none of those resolves to a real directory the home directory is used
rather than creating a `Documents` folder that the machine had evidently
chosen not to have.

`--dir` still overrides everything.

### Migrated

The seven folders already written to the old location were moved, and **ten
artifact rows in the database were repointed** — moving the files alone would
have left every recorded screen and CV pointing at a path that no longer
existed, which is the sort of breakage that only shows up weeks later when
somebody clicks one.

---

## 0.12.1 — 2026-08-29 — dealbreakers, and a duplicate picking the wrong copy

### Fixed — the dedupe was showing the worse copy

Adding employer boards produced the same Vectra role twice: truncated to 500
characters from an aggregator, and complete at 4,701 from the company's own
Greenhouse board. **The list showed the 500-character one.**

Duplicates were ranked by score alone, and the truncated copy scored *higher* —
a tidier location string, and no advert content on which to lose points.
Nothing about that is visible from the outside; it just quietly hands you the
version that cannot be screened, since dealbreakers and fit scoring both read
the advert body.

The fuller advert now wins, and score only breaks ties between copies that say
as much as each other. Bucketed by thousands of characters, because 4,700 and
4,900 are the same advert and the score should decide between those.

### Added — six dealbreakers, all soft

```
extended client-site travel · unpaid take-home · heavy on-call
active clearance required · contract or staffing agency · relocation required
```

Every one starts `hard: false`, which shows the role with a warning rather
than hiding it. None of these is a preference anybody stated; promoting one to
`hard: true` is a decision for the reader once they are sure.

They caught **29 roles** on the first pass. One of them is the cross-check
worth having: the ITRS role that the `screen` had independently flagged for
buried travel expectations was caught by the regex too — a model reading the
advert and a pattern matching it agreeing about the same sentence.

**Widened while testing:** the travel pattern missed its own motivating
example. The advert reads "consecutive weeks **are spent** full-time at a
client site", and the pattern allowed no intervening words.

Dealbreakers only fire on adverts long enough to contain them, so they are
quiet on the 500-character aggregator rows and useful on the rest — another
place the cap costs something.

---

## 0.12.0 — 2026-08-29 — employer boards, and what they are worth

Not a code change. `sources.companies` had been empty since the scanner was
built, so all five per-employer adapters fetched nothing and every advert came
from an aggregator that truncates at 500 characters. `discover` existed to fix
that and had never been pointed at anything.

### Added

Eight boards, found with `discover` and verified before being written:

| Company | Platform | Token |
|---|---|---|
| Vectra | greenhouse | `vectranetworks` |
| Tenable | greenhouse | `tenableinc` |
| Enova International | greenhouse | `enova` |
| Huntress | greenhouse | `huntress` |
| Dragos | greenhouse | `dragos` |
| Expel | greenhouse | `expel` |
| Vanta | ashby | `vanta` |
| Drata | ashby | `drata` |

`vectranetworks` and `tenableinc` are the argument for reading tokens rather
than guessing them.

### Measured: this is what the aggregator cap costs

| Source | Roles | Average advert | Arrangement unstated |
|---|---|---|---|
| ashby | 17 | **6,375 chars** | 0 / 17 |
| greenhouse | 16 | **5,896 chars** | 0 / 16 |
| workable | 200 | 4,903 chars | 0 / 200 |
| usajobs | 2 | 4,121 chars | 2 / 2 |
| adzuna | 653 | **500 chars** | **517 / 653** |

Résumé fit scoring reads the advert body, and the difference is not subtle. The
same feature, on the same résumé:

```
adzuna, 500 chars   fit: has security
ashby, 6,375 chars  fit: has compliance, penetration testing, security;
                         wants hipaa, iso 27001, soc 2, vulnerability management
```

The second is a gap analysis. The first is a coincidence.

### Also learned

Most large employers are on Workday, which has no adapter here — `arcticwolf`,
`relativity` and others were located and named as such rather than reported as
"nothing found". Several more, including `rapid7`, `cloudflare`, `datadog` and
`sproutsocial`, render their careers pages in JavaScript and expose no token to
read, so `discover` correctly declined rather than guessing.

Eight boards from nineteen employers tried. The hit rate is the reason
`discover` reports four distinct outcomes instead of found/not-found.

---

## 0.11.1 — 2026-08-29 — what the first live generation found

`generate` shipped in 0.11.0 having never been run. Two runs against real roles
corrected three things, which is the argument for running it rather than
trusting it.

### Fixed

- **The résumé was outside the sandbox and therefore unreadable.** `--add-dir`
  names the job folder and nothing else, so a résumé at `~/Documents` could not
  be opened. The first screen came back *"file access was not granted"* and
  assessed nothing.

  Widening the sandbox to reach it would undo the point of having one, so the
  résumé is **copied into the job folder** instead and referenced by local
  name. The scope stays one directory.

- **A screen was being held to send-time gates.** It flagged
  `"$140,000 - $170,000"` as a figure not in the résumé — the advertised
  salary, read correctly off the posting. Those gates guard documents you
  *send*; a screen is notes to yourself and is *supposed* to quote the advert.
  Gates are now per-kind: a screen gets a length check and nothing else.

- **Identifiers inside URLs were read as claims.** A draft quoting
  `https://www.adzuna.com/details/5792028474` had the posting id flagged as an
  unsupported figure. URLs and code spans are stripped before the check.

### What the runs showed

On a role with a **full 4,511-character advert**, the screen was worth having:
it found a title mismatch (advertised "DevOps Engineer", described a Forward
Deployed Engineer), buried travel expectations — "consecutive weeks spent
full-time at a client site" against an advert headlined as 2-days-a-week
hybrid — a currency typo in the salary, and named four requirements not on the
résumé.

On a role whose advert had been **truncated to 500 characters by an
aggregator**, it refused: *"cannot screen yet. Advert is a stub. Re-scrape
before spending time."* It did not guess a match from company marketing. That
refusal is the behaviour worth having, and it is the Adzuna cap showing up
where it costs something.

Both runs ended with the model reporting, as instructed, that nothing inside
the advert markers had attempted to issue instructions.

### Also

- **`sources` reported USAJOBS as active for a reader outside the US**, while
  the adapter skipped itself. The report and the behaviour now agree, and the
  reason is printed.
- Screenshots of the dashboard and the static page added under
  `docs/images/`.

---

## 0.11.0 — 2026-08-29 — `generate`

Screens a role, and drafts a CV or a cover letter, by spawning headless
`claude -p`. The last feature on the list, and the only one that spends money.

### Added

```bash
jobdork generate <ref> -k screen         # do this first: seconds, pennies
jobdork generate <ref> -k cv
jobdork generate <ref> -k cover_letter   # refused until the CV exists
jobdork generate <ref> --dry-run         # the prompt and the command, spending nothing
```

The Claude Code CLI rather than the API, deliberately: the agent reads your
résumé off disk, writes the draft, and is checked by scripts afterwards.
Through a bare API call all of that would be reassembled out of prompt text,
and the drafting quality lives in the reading and writing. The desktop chat
app ships no command-line entry point and cannot be driven from here.

Documents land in `~/Documents/job-applications/<date>-<company>-<role>/` alongside a
**snapshot of the advert**. Postings are pulled the moment they are filled,
which is usually just before somebody calls you about one.

**Nothing generates unless you ask.** No schedule, no watcher, no speculative
drafting.

### The gates are scripts, not judgement

A model asked to re-read its own draft will say it looks fine. A script
counting em-dashes says how many there are.

| Gate | What it catches |
|---|---|
| **unsupported figures** | any number or scale word in the draft that is not in your résumé |
| **phrase overlap** | a cover letter repeating the CV — no run of six words may appear in both |
| **em dashes** | more than two |
| **length** | a draft that came back empty |
| **slop score** | the natural-writing linter, when installed — and it says so when not, rather than passing silently |

`unsupported figures` is the one that matters. A tailored CV is the easiest
place in a job search to acquire a statistic nobody can back up. Tested: a
draft claiming "2.5 million" and "tripled" against a résumé that says neither
is caught on all three, while the figures that *are* in the résumé are not
flagged. Dates and small integers are ignored — they are list counts, not
claims.

**Nothing is redrafted automatically.** A failed gate means read this before
you send it, not this is broken; a second pass would cost tokens you did not
ask for. Results are recorded against the document either way.

**The cover letter is refused until the CV exists**, so the overlap gate has
something to compare against. The CV carries the facts, the letter carries
judgement, and they should share nothing but your name.

### A job description is hostile input

It comes from thousands of third-party servers, anybody can post a job, and
here that text lands in a prompt *and* in the working directory of a
subprocess that can write files. Each of these is tested:

- **Fenced and labelled**, with the fence markers stripped out of the advert
  first — verified with an advert that tries to close the fence and continue
  as instructions. Exactly one marker of each survives, and the injected text
  remains inside as data. Neutralised by position, not by censorship.
- **Every prompt states** that everything inside the fence is a claim about a
  job, never an instruction, whatever it says or claims to be from.
- **The subprocess is scoped to one folder.** `--add-dir` names that
  directory and nothing else — never `~/.claude/skills`, which would be write
  access to every skill you own. A compromise damages one role's folder.
- **Links are scheme-checked.** `javascript:`, `data:` and `file:` never reach
  a file; the line reads "link withheld: unsafe scheme".

None of this makes an agent immune to persuasion. Prompt injection has no
complete fix, and a determined posting may still get odd wording into a draft
you were going to read anyway. The blast radius is one folder and one
document.

### Recorded

Each run writes an `artifacts` row with the path and the gate results, so
"which roles have a CV but no application" stays one query. Drafting a
document moves a role from `new` to `interested`; screening does not, because
screening is how you decide.

---

## 0.10.0 — 2026-08-29 — SmartRecruiters verified

Two of the three "not fixable here" items turned out to be fixable, once
something answered.

### SmartRecruiters was never broken, only silent

Ten well-known company names in a row returned HTTP 200 with `totalFound: 0`.
On this platform that is also what a throttle and a non-existent board look
like, so none of them proved anything either way — which is why the adapter
shipped marked unverified rather than assumed working.

`Bytedance` finally returned rows, and real data corrected three guesses:

- **`location.fullLocation` is already assembled** — "Mumbai, MH, India".
  Building the string from `city, region, country` produced "Mumbai, MH, in",
  because `country` is a lowercase two-letter code. The assembled version
  geocodes; the built one does not.
- **`location.hybrid` exists alongside `location.remote`.** Reading only
  `remote` filed every hybrid role as arrangement-not-stated.
- **`ref` is the API's own detail URL.** It was winning the URL precedence, so
  clicking a stored role handed you a page of JSON. The human posting page is
  used now, and `enrich` derives the detail URL back from it.

### `enrich` gained a SmartRecruiters reader

Its public posting page carries no schema.org data, so the generic JSON-LD
reader finds nothing there. The advert lives on the detail endpoint, split
across `jobAd.sections` — job description, qualifications, additional
information and company description — and all four are joined, because a
dealbreaker about qualifications sits in a different section from one about
the role.

Verified end to end: two roles stored with empty adverts came back at 1,181
and 1,016 characters.

### Adzuna `au`, `nz` and `sg` are live again

They answered 503 while 0.3.0 was being written and were recorded as such.
Re-probed today: all three return 200. The outage was theirs and it is over —
`au nz sg` join the working indexes, and only `ph id my jp ae ru` have no
index at all.

---

## 0.9.0 — 2026-08-29 — the small gaps

Four things that were each individually minor and collectively the reason the
backlog never emptied.

### Metro names now work outside North America

`Bay Area`, `GTA` and `DMV` resolved; `Kanto`, `Klang Valley` and `Randstad`
did not. About seventy more are recognised across Asia Pacific, Europe, Latin
America, Africa and the Middle East — `Metro Manila`, `BGC`, `Jabodetabek`,
`Greater Tokyo`, `Île-de-France`, `Ruhrgebiet`, `Öresund`, `Gauteng`, `CDMX`,
`Greater Sydney`.

**One name can belong to several countries.** `NCR` is the National Capital
Region in Canada, India *and* the Philippines, and `Bay Area` is San Francisco
to most readers and Hong Kong to some. Those are settled by your configured
countries, exactly as an ambiguous region code is — a country named in the
string itself outranks even that.

**Fixed:** the cleanup turns hyphens into commas, so `Île-de-France` split into
three fragments, the last of which is a country, leaving a city called `Île`.
Metro names are now checked against the untouched string first.

### `locations.exclude` matches what a location resolved to

It was a substring match on the raw string, which is too literal to be useful:
`exclude: [TX]` matched nothing, because postings say "Austin, Texas" and never
"TX" — while `exclude: [Texas]` missed every posting that wrote the code.

An entry is now tried as a region code, then a country, then a city, then a
metro name, and finally as a substring. So `TX`, `Texas`, `Chicago`,
`Bay Area`, `Canada` and an arbitrary phrase all work.

### `jobdork add` takes many URLs

```bash
jobdork add <url> <url> <url>
jobdork add --from-file urls.txt
```

The file is one URL per line, tolerating `#` comments, `- ` bullets and
`title<TAB>url`, because that is how a pasted list actually looks.

**It reads posting URLs, not the dork generator's output.** That file holds
Google *search* URLs, and turning those into postings would mean scraping
Google's results — bot-protected, and a control this tool does not work
around. Click the results, paste the ones worth keeping.

A role that fails your filters is still stored, and says so: you asked for that
one by name, and a filter is not a better judge of that than you are.

### LICENSE

MIT, matching what `README.md` and `pyproject.toml` already declared.
Copyright Jesse Ngolab, taken from the repository's own git author.

---

## 0.8.0 — 2026-08-29 — `enrich`

Fetches the full advert for roles stored as summaries. Dealbreakers read the
advert body, so does work-mode detection, so does résumé fit scoring — a role
stored with 200 characters of teaser was waved through rather than screened,
and the flags on it were guesses.

### Added

- **`jobdork enrich`** — reads schema.org `JobPosting` JSON-LD, which posting
  pages publish for Google's benefit and which is therefore both stable and
  meant for machines.

  Measured on live pages: six roles seeded with 180-character teasers came back
  at 1,462 to 4,479 characters. **17,498 characters of advert recovered,
  2,916 average.**

- **A role whose advert grows is re-screened.** A dealbreaker that could not
  match 200 characters may well match 7,000, and leaving the old verdict in
  place would be worse than never having fetched. Three of the six test roles
  stopped passing once the real text arrived, and were marked skipped with the
  reason.

- `--dry-run`, `--limit`, `--platform`, and `--thin N` for what counts as a
  summary rather than a description.

### Adzuna cannot be enriched, and this refuses to try

Its `redirect_url` answers **403 from bot protection**. Getting past that is
breaking a control rather than declining a request, which is a line this tool
does not cross — so Adzuna is skipped by name, with the reason.

**Adzuna's 500-character cap is therefore permanent.** Worth knowing before
writing a dealbreaker that depends on advert text and wondering why it never
fires: on one run that was 653 of 855 roles.

Platforms whose adverts already arrive whole — Workable, Greenhouse, Ashby,
Lever, USAJOBS — are skipped too, rather than spending a request per role to
learn nothing.

---

## 0.7.0 — 2026-08-29 — command-line overrides

Every setting that mattered lived only in `config.yaml`, so trying a different
country meant editing a file you had tuned, or keeping several and passing
`-c`.

### Added

- `--title` · `--exclude-title` · `--anchor` · `--country` · `--radius` ·
  `--units` · `--work-mode` · `--salary-floor` · `--currency` · `--resume` ·
  `--out` · `--db`. The list ones repeat.

  ```bash
  jobdork sources --anchor "Berlin, Germany" --country DE
  jobdork list --title "penetration tester" --work-mode remote --salary-floor 150000
  ```

- **They go after the verb**, where people write them, rather than having to
  precede it — every subcommand inherits the same group.

### Deliberate

- **An override is validated exactly as the file is**, so it cannot be a
  looser way in than the config it replaces. `--country ZZ`, `--currency XYZ`,
  `--radius nonsense`, a résumé path that does not exist, and a numeric radius
  with no anchor are all refused the same way they would be in YAML.

- **`--country` moves units and the Adzuna index with it.** Carrying miles
  over from a config written for Chicago into a German search would silently
  cover 2.6x the intended area, and a pinned `adzuna_countries: [us]` would
  otherwise have searched America for a Berlin reader.

---

## 0.6.0 — 2026-08-29 — `serve`

The dashboard with buttons, at `http://127.0.0.1:8765`. The same list `jobdork
list` prints, except that what you click sticks.

### Added

- **`jobdork serve`** — filter by status, scope (open / new since last scan /
  including settled) and a text box; per-role buttons for interested, apply,
  interviewing and skip, a status dropdown carrying all ten states, and a note
  field.

- **It reads and writes the same database the CLI does**, so the two cannot
  disagree. Verified both directions: a status set in the browser shows up in
  `jobdork list`, and one set by `jobdork applied` shows up in the browser
  without a restart.

- **Apply opens the posting and then records it.** Marking a role applied
  without opening it would be recording something that did not happen.

### Local only, deliberately

- **It binds to `127.0.0.1` and there is no `--host`.** A dashboard listing
  where you are applying is not a thing to put on a network, and an option to
  do it is an option somebody uses.

- **The `Host` header is validated against the address actually bound to**,
  not against `Origin`. Under DNS rebinding a page on an attacker's domain
  resolves to 127.0.0.1 and reaches this server from your browser; `Host` and
  `Origin` are both attacker-controlled and agree with each other, and the
  bound address is not. A foreign `Host` gets 421.

- **A uid must be twelve hex characters** — it is the only value from the page
  that reaches the database. Path traversal, SQL and short or long ids are all
  400.

- **`GET` cannot change anything.** A status change is not reachable by
  following a link.

- **Standard library only, no external request.** No CDN, no fonts, no
  framework; a test asserts the page contains no outside URL.

- Unknown paths are 404 rather than an attempt to read something off disk, and
  a body over 8KB is refused.

### Tests

`tests/test_serve.py` runs a real server on a real loopback port for each
case — 12 tests covering the guards above and the read/write parity, bringing
the suite to 74.

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

Nothing. Every item that has been in this section has moved into an entry
above, and the last one — a rate limit that was somebody else's clock —
expired on its own.

It is kept as a heading rather than deleted, because the next gap goes here
and a section that has to be re-invented is a section that gets skipped.

### Operational notes, not work

- **`jobs.workable.com` bans hard.** The ban that ran through 0.6.0 to 0.12.x
  was earned by re-running full scans while tuning a config: fifteen
  consecutive 429s, then a `Retry-After` of 86,130 seconds. Cleared 2026-08-29.
  Use `scan --limit` while experimenting.
- **Adzuna adverts are capped at 500 characters and cannot be enriched** — its
  links answer 403 from bot protection, which this tool does not work around.
  That cap is permanent, and it is the reason employer boards matter.
- **SmartRecruiters answers 200 with `totalFound: 0`** for a throttle and for
  a board that is not there alike. An empty answer from it proves nothing
  either way.
- **Uncommitted:** 0.6.0 through 0.13.0 exist only in the working tree.
  `f550183` carries 0.2.0 through 0.5.0.

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
