# Architecture

How a role gets from a job board into your list, and why the pieces are split
the way they are.

---

## The pipeline

```
config.yaml ──┐
              ▼
         ┌─────────┐   one adapter per source, run concurrently
         │  fetch  │   fetch/*.py  →  SourceResult(roles, errors, suspect)
         └────┬────┘
              ▼
         ┌─────────┐   title → work mode → location → salary → dealbreakers
         │ screen  │   screen.py   →  Verdict(keep, reasons, flags, score)
         └────┬────┘
              ▼
         ┌─────────┐   upsert by uid; first_seen never moves
         │  store  │   store.py    →  data/jobdork.db
         └────┬────┘
              ▼
      ┌───────┴───────┐
      ▼               ▼
   render.py       cli.py
   out/index.html  list / applied / show / rescreen
```

Every stage is independent and testable on its own. `screen` never makes a
network call; `fetch` never decides whether a role is wanted; `store` never
filters.

---

## Modules

| Module | Lines | Responsibility |
|---|---|---|
| `config.py` | 494 | Load and validate YAML, read secrets from the environment |
| `store.py` | 486 | SQLite schema, upsert, status, resolution by uid/url/name |
| `geo.py` | 626 | Gazetteer, haversine, state/metro/country normalisation |
| `screen.py` | 360 | Every filtering rule and the scoring |
| `cli.py` | 389 | Argument parsing and the commands |
| `fetch/http.py` | 266 | Pacing, retries, circuit breaker — the only networking |
| `scan.py` | 205 | Orchestration, threading, rescreen |
| `render.py` | 196 | Static HTML and JSON |
| `resume.py` | 163 | Résumé parsing, skill extraction, fit scoring |
| `textutil.py` | 77 | HTML → text for advert bodies |
| `migrations.py` | 150 | Numbered, forwards-only schema steps |
| `dork/` | ~1,100 | The original Google query generator, moved not rewritten |
| `fetch/*.py` | ~900 | Eight source adapters plus shared board helpers |

---

## The database

```sql
roles       -- what was found
role_state  -- where it sits in your pipeline
artifacts   -- documents produced for it
runs        -- what each scan did
meta        -- schema version
```

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
read at once. How hard any one host is hit is set per host in `HOST_RATES` and
is not user-configurable — raising concurrency reads more boards in parallel,
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

**By employer and title, at read time.** Aggregators republish one vacancy under
six or seven distinct posting ids. Those are legitimately different uids and
merging them at store time risks discarding the only copy, so the collapse
happens on the way out: same company, same title, best score wins.
`list --duplicates` shows them all.

---

## What is not built

**Document generation** — shipped in 0.11.0. Screen, CV and cover letter, each
spawning headless `claude -p` and writing results back as `artifacts` rows.
Every invocation costs tokens, so nothing generates without a click.
Quality gates are mechanical: phrase overlap between CV and cover letter,
em-dash count, and any figure or scale word in a draft that is not in the
résumé.

If that is built, job descriptions must be treated as hostile input. They come
from thousands of third-party servers, anyone can post a job, and that text
would land in both a prompt and the working directory of a subprocess that can
write files. Fence and label the advert, strip the fence markers from it first,
scope the subprocess to one job's folder, and scheme-check every URL — apply
links are employer-supplied on several platforms.

Nothing. `discover` shipped in 0.5.0, `serve` in 0.6.0, `enrich` in 0.8.0 and
`generate` in 0.11.0.

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

The 30 tests cover the rules that fail quietly: unstated salary being shown,
unresolvable locations being kept, blocker words refusing a loose title match,
day rates being annualised, `gh_jid` surviving canonicalisation, escaped HTML
being unescaped before tags are stripped.
