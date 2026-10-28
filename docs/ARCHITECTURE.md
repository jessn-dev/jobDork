# Architecture

How a role gets from a job board into your list, and why the pieces are split
the way they are.

---

## The pipeline

```
config.yaml ──┐   your sources and boards, plus the built-in employer
data/boards.csv┤   boards for your countries (search/directory.py)
              ▼
         ┌─────────┐   one adapter per source, run concurrently
         │  fetch  │   fetch/*.py         →  SourceResult(roles, errors, suspect)
         └────┬────┘
              ▼
         ┌─────────┐   title → work mode → location → salary → dealbreakers
         │ screen  │   search/screen.py   →  Verdict(keep, reasons, flags, score)
         └────┬────┘
              ▼
         ┌─────────┐   upsert by uid; first_seen never moves
         │  store  │   db/store.py        →  data/jobdork.db
         └────┬────┘
   ┌──────────┼──────────────┬─────────────────┬──────────────────┐
   ▼          ▼              ▼                 ▼                  ▼
 enrich     check          judge             draft              read it
 search/    search/        ai/               writing/generate   output/ (page,
 enrich.py  listing.py     judging.py        ai/writer.py       email), cli.py,
                             │                 │                web/ (dashboard)
                             └──── ai/guard.py ┘
                        every claim checked against resume and advert
```

Every run, from the terminal or the dashboard, records itself through
`core/telemetry.py` into the same database, which is how the Dashboard shows a
run it did not start.

Every stage is independent and testable on its own. `screen` never makes a
network call; `fetch` never decides whether a role is wanted; `store` never
filters.

---

## Modules

Grouped by what they are for. A package imports from `core/` and `db/`
freely; `search/`, `ai/` and `writing/` import each other only where one
genuinely uses the other (judging reads the resume, drafts are guarded), and
nothing below imports from `web/`.

| Package | Modules |
|---|---|
| `cli.py` | Argument parsing and every command |
| `core/` | `config` (YAML, secrets from the environment), `setup` (first-run steps), `storage` (where the resume and documents are kept), `telemetry` (what a running job is doing, readable from any process), `schedule` (scans from the system's own scheduler), `notify` (the system's notifications), `updates` (is a newer release out, and checking an installer before it opens), `feedback` (a report to the maintainers), `textutil` (HTML → text) |
| `db/` | `store` (schema, upsert, status, AI outputs), `migrations` (numbered, forwards-only), `grouping` (copies of one job) |
| `fetch/` | `http` (pacing, retries, circuit breaker — the only networking), `robots` (robots.txt, RFC 9309), one adapter per source (keyword searches: Workable, Himalayas, Kalibrr, Germany's employment agency, Arbeitnow, and with keys Adzuna and USAJOBS; employer boards on Greenhouse, Ashby, Lever, SmartRecruiters, Breezy, Workday, Oracle, Eightfold and Taleo; and an employer's own careers site, SuccessFactors career sites included), shared board helpers |
| `search/` | `scan` (orchestration, rescreen), `screen` (every filter and the score), `dealbreakers` (plain words into patterns), `directory` (the built-in employer boards), `freshness` (how old a post is), `enrich` (full adverts), `discover` (an employer's board), `listing` (is it still open), `ownboard` (an Adzuna post the employer's board does not carry), `agency` (employer or recruiter), `credentials` (certifications a post asks for), `geo` (gazetteer, distance), `resume` (skills, fit) |
| `ai/` | `llm` (providers, keys in memory), `judging`, `guard` (hallucination checks), `writer` (AI cover letter, resume review), `tools` (the model as an editor for resume and letter), `suggest` (job titles from the resume, in setup) |
| `writing/` | `generate` (`claude -p` drafts), `resume_doc` (the tailored resume's template), `length` (its page budget, after Indeed), `gates` (scripted checks), `humanize` (signs of AI writing) |
| `web/` | `serve` (HTTP), `api` (every command for the page, metrics), `live` (runs and events), `session` (token, port), `app` (the desktop window and its bridge) |
| `output/` | `render` (static HTML and JSON), `pdf` (a resume as a PDF), `docx` (the same as a Word file), `digest` (email) |
| `dork/` | The original Google query generator, moved not rewritten |
| `data/` | `boards.csv` (the built-in employer boards), `cities.csv` (places, with each one's region), `regions.csv` (region and country names), `dashboard.html`, the humanizer rules, `attestation-check.json` (a real build attestation, for the desktop app's self-test) |

---

## The database

```sql
roles            -- what was found, with its score, AI verdict and listing state
role_state       -- where it sits in your pipeline (shared by copies of one job)
artifacts        -- documents produced for it, with their gate results
runs             -- what each scan did, per source
deleted          -- posts you deleted, so a scan does not bring them back
activity         -- every run, from any process: progress, hosts, AI, heartbeat
activity_events  -- each run's log lines (the last 200 runs)
ai_outputs       -- every text a model wrote, its guard result and your rating
llm_calls        -- every model call inside a run: purpose, seconds, ok
meta             -- schema version
```

A new table is created by `CREATE TABLE IF NOT EXISTS` on open; a change to an
existing one is a numbered step in `db/migrations.py`, forwards only.

### Why state and artifacts are separate tables

They could have been columns on `roles`. Keeping them apart is what makes
*"which roles have a CV but no application"* a query rather than a
combinatorial explosion of status values — you would otherwise need
`applied_with_cv`, `applied_without_cv`, `interested_with_cv` and so on.

### uid

```python
uid = sha1(platform + "|" + canonical_url(url))[:12]
```

Short enough to type on the command line, stable across runs.

`canonical_url` strips tracking parameters (`utm_*`, `gclid`, `fbclid`,
`gh_src`), lowercases the host, drops the fragment and normalises the trailing
slash — so the same posting arriving from a Google click and from a scan is one
row, not two.

**`gh_jid` is deliberately not stripped.** It identifies the posting on
Greenhouse boards served from the employer's own domain; removing it collapsed
579 jobs to a single uid.

### first_seen never moves

An existing row keeps its `first_seen` on every later scan. That is the date
the tool learned about the job, and re-reading it does not make it newer. It is
what `list --new` is measured against.

### Descriptions are never blanked

The upsert uses `COALESCE(NULLIF(excluded.description, ''), roles.description)`.
A later fetch that could not read the advert must not destroy one an earlier
fetch managed to read.

---

## The fetch layer

One `Fetcher` per run, shared by every adapter, thread-safe.

**Per-host clocks.** `fetch.concurrency` governs how many *different* boards are
read at once. How hard any one host is hit is set per host in `HOST_RATES`, per
domain in `DOMAIN_RATES` (every `*.myworkdayjobs.com` host, every Oracle and
Taleo host), or by the adapter for a host no table can name (an employer's own
site, `Fetcher.pace`), and is not user-configurable — raising concurrency reads more boards in parallel,
it does not make one board answer faster. Requests to different hosts
interleave, so a long run of one platform does not park the pool on a single
host.

**A circuit breaker, not a retry loop.** Three consecutive 429s after retries
means the host is saying no, not asking for a pause: it is blocked for five
minutes rather than retried into. A `Retry-After` under a minute is honoured;
over a minute it is read as a refusal for the rest of the run.

**The layer reports, it does not interpret.** Several of these APIs answer 200
with an empty array both for a dead board and for a throttle. `http.py` cannot
tell those apart and does not try — that judgement belongs to the adapter,
which knows whether the board ever had jobs.

### Adapter contract

```python
fetch(fetcher, cfg, **kwargs) -> SourceResult
```

`SourceResult` carries `roles`, `requests_made`, `errors`, `skipped` and
`suspect`. A dormant keyed source returns `skipped` with the reason, because a
source that silently does not run looks exactly like one that found nothing.

---

## The screening rules

Every rule has the same shape:

```
employer said something, and it fails    → drop
employer said something, and it passes   → keep, score up
employer said nothing                    → keep, flag
```

A filter built the other way round looks tidy and quietly throws away most of
the market. Concretely:

- **60% of postings state no work arrangement.** Reading "we cannot tell" as
  "not remote" hides more real remote roles than it removes office ones.
- **88% state no salary.** Only a published number can disqualify a role.
- **A location that will not parse** is a string this tool failed to read, not
  evidence the job is far away.

Order matters, and it is cheapest-first: title, then work mode, then location,
then salary, then dealbreakers. Title rejects most of the input — 586 of 1,517
on one run — and costs one regex, so it runs before anything touches the
gazetteer or scans a 5,000-character advert.

The `Verdict` carries `reasons` (why it was dropped) separately from `flags`
(what to know if it was kept). Adapter-set flags are merged in rather than
overwritten.

---

## Threading

`ThreadPoolExecutor`, one future per (source, company) pair. These are IO-bound
HTTP calls, so threads are the right tool and the GIL is not in the way.

Screening happens on the main thread as results arrive, which keeps the rules
single-threaded and the shared `Store` untouched by workers.

**An adapter that raises kills one board, not the run.** The exception is
caught, logged, and recorded as that source's error.

---

## Deduplication, in two places

**By uid, at store time.** Same platform and same canonical URL is the same
posting. This is exact and safe.

**By employer, title and place, at read time** (`db/grouping.py`).
Aggregators republish one vacancy under six or seven distinct posting ids, and
an employer's own board carries the job an aggregator does. Those are
legitimately different uids and merging them at store time risks discarding
the working link, so copies are grouped instead: one post on screen, one
status for the group, closed only when every copy is. Place is part of the key,
or a company hiring the same title in two cities would lose one.
`list --duplicates` shows them all.

---

## The AI reader, and the guard

A scan runs without it, and it is never a filter: a verdict sits beside the
rule-based score and never hides a post.

**One entry point for every provider.** `ai/llm.py` asks for one JSON object
matching a schema, from Ollama, Claude, Gemini, ChatGPT or Groq, and records the
call (`llm_calls`, with its purpose). Keys live in memory in the server
process and nowhere else.

**The advert is hostile input**, as it is for `claude -p`: fenced, fence
markers stripped from the text first, and the prompt says everything inside
is data.

**Every output is guarded** (`ai/guard.py`), by the HalluLens method with our
own prompts: extract single claims, verify each against the known sources
(resume, advert, page), and count the unsupported ones. The model's
"supported" is not trusted on its own: it must give a quote, and a script
checks the quote is in the source it named (by words, so punctuation and
PDF text that runs words together do not matter). A gap ("does not mention
X") is settled by script the other way: X must be named in the claim and
absent from the source, or the gap is contradicted. Claims are matched to
the checker's answers by their words, then by number. A verdict's years of
experience come from `resume.work_span`, counted from the resume's dates
and given to the model as `<<MEASURED>>`, which the guard can quote. A check that fails is recorded as
unchecked; it never blocks the output. Page reads are checked by the quote rule
alone, with no extra call.

**Another model checks than the one that wrote it** (`guard.checking`). One
model marking its own work misses what it got wrong the same way twice. The
order is the chosen checkers (`llm.checkers`), then the other readers, then
the writer itself as the last resort, all as one chain: `complete_json` asks
the next when one cannot answer, exactly as it does for readers. The writer
is whichever reader answered (`Settings.answered`), so when the first reader
was down and the second wrote, the first may check. The checking chain is a
copy, so the guard's calls never change the label the output is recorded
under.

Each output is an `ai_outputs` row with its guard counts and your rating, which
is what the Dashboard's hallucination rate, coverage and feedback are counted
from.

---

## Runs, and the Dashboard

`core/telemetry.py` records whatever job is running (scan, check, judge,
letter…) in `activity`: progress, per-host request counts, AI calls, a
heartbeat every five seconds, and log lines. It writes through its own
connection, at most once a second, and a failure to write never fails the job.
A run whose heartbeat stops and whose process is gone is shown as died.

`web/api.py` reads that for the Dashboard: the running job, the last scan,
check and judging with what went wrong, and `metrics` over 7, 30 or 90 days,
including each day's checked claims per kind of output for the hallucination
chart.
Runs and model calls are kept 120 days; log lines for the last 200 runs.

---

## Tests

```bash
python tests/run_all.py     # what CI should run; no pytest needed
python -m pytest -q         # same tests, if you have it
```

`run_all.py` **discovers** every `tests/test_*.py` rather than naming them.
Naming one file means a new test file runs nowhere until somebody remembers to
add it, and the suite reports a confident pass over tests it never executed.

Two details that matter:

- The `__main__` block in a test file stays at the **end**. Collecting
  `globals()` partway up sees only the tests defined above it and runs half the
  file while printing what looks like a full pass.
- The runner catches `BaseException`, not `Exception`. A test raising
  `SystemExit` would otherwise end the run mid-file with no failure line and no
  summary.

The tests cover the rules that fail quietly: unstated salary being shown,
unresolvable locations being kept, blocker words refusing a loose title match,
day rates being annualised, `gh_jid` surviving canonicalisation, escaped HTML
being unescaped before tags are stripped, a model's "supported" not counting
without a quote found in its source, and a run's metrics counting only its
period. No test calls a real model or a real site: model answers are
scripted.
