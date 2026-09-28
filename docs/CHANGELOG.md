# Changelog

Each finished piece of work gets its own entry here, newest first.
[Still outstanding](#still-outstanding) is the backlog: a bullet moves out of
it and into an entry when the work is done.

---

## Fixed — 2026-09-28 — list --json, and a connection left open

- **`list --json` and `roles.json` wrote JSON inside JSON.** The verdict, the
  score parts and the reasons are stored as JSON text and were written out as
  strings, so a reader had to decode them twice. They are objects and lists
  now, and a verdict stored before its word followed its score reads as the
  score says (the rule is one function, `llm.verdict_for`, used when judging,
  on the dashboard and here).
- **A refused database left its connection open.** When `Store` could not
  open a database (one written by a newer version, a failed migration), the
  connection it had made was never closed. Found by running the tests with
  every warning as an error, which now pass too.

---

## Fixed — 2026-09-28 — rescreen hung; scans failed writing roles.json

Both found while making the demo screenshots.

- **`rescreen` hung, then failed with "database is locked".** It held one
  write open over every post and committed at the end, while each progress
  tick had the run's telemetry write through its own connection and wait up
  to ten seconds for that very lock, on the job's own thread. 588 posts took
  over five minutes and then failed; they now take three seconds. Three
  changes: telemetry never makes the job wait (a flush from the job's thread
  gives up after a quarter of a second, skips if another flush is writing,
  and keeps what it could not write for the next one; only the final state
  waits); the database runs in WAL mode, so a reader never blocks a commit
  (set on open, kept in the file; `-wal` and `-shm` files appear beside it);
  and `rescreen` and `enrich` commit as they go. From the dashboard,
  Re-apply filters had the same problem.
- **Every scan with `json` output failed at the end**, after storing
  everything: `IndexError: No item with that key`, which is the failed scan
  on the Dashboard. `render.rows_to_dicts` iterated `sqlite3.Row` for its
  keys, but that yields the values. It was `row.keys()` until the last
  commit, where a lint simplification (ruff's SIM118) rewrote it; it is
  `dict(row)` now. `out/roles.json` had not been written since 29 August.
  The writer test only checked each format had a function, never ran one;
  a test now writes all four from real database rows.

---

## Changed — 2026-09-28 — no personal details in the repository

- **Name and handle.** `LICENSE`, `pyproject.toml` and the changelog now
  name `jessn-dev`. The project and User-Agent URLs pointed at a
  `jessengolab/jobDork` that is not this repository; they point at
  `github.com/jessn-dev/jobDork`. Git history was left as it is: its
  commits keep their author.
- **Screenshots from a demo.** All five are taken from a copy of the
  database with every status, note, draft, AI output, verdict and log line
  removed, re-scored against a made-up résumé ("Alex Rivera"), and judged
  with it. The job posts are public listings. Before, the skill chips came
  from the real résumé and the verdict summarised a real career.
- **Résumé facts quoted in the docs** (years of experience, the post it was
  tried on) are replaced with neutral examples, in the README, the
  changelog and the cover-letter prompt's own example.
- **Deleted:** `docs/images/generated-cv.jpg` (it showed a name, phone
  number, email and town; never committed), the dork generator's old CSV
  exports, results file, log, and a root `__pycache__` for a `config.py`
  that no longer exists; a second, unused virtualenv (`venv/`, 18 MB); build
  and tool caches; `.DS_Store`; the stale `out/roles.{csv,json,md}`.
- **`.gitignore`: `data/` became `/data/`** (and `out/`, `/out/`). The bare
  pattern also matched `jobdork/data/`, so the dashboard page, the humanizer
  rules and the gazetteer had never been committed and a clone had no
  dashboard; the `!jobdork/data/cities.csv` exception could not work inside
  an ignored directory. Your database stays ignored.

---

## Changed — 2026-09-28 — documentation and screenshots brought up to date

Every doc was read against the code as it now is.

- **Screenshots retaken** (dark, 1440 wide) on the current interface. All
  five were from 29 August and showed the old "Roles / Scan" pages:
  `dashboard.jpg` (the Dashboard with its metrics), new `job-posts.jpg` (the
  list, with match, fit and AI badges), `role-detail.jpg` (a post with the AI
  verdict open: 20 of 20 claims found), `live-run.jpg` replacing
  `live-scan.jpg` (a run reporting itself mid-way; local Ollama, so no job
  board was called), and `static-page.jpg`. All five were taken again the
  same day from a demo, see "No personal details in the repository" above.
- **ARCHITECTURE:** the pipeline diagram now shows enrich, check, judging,
  drafts, the guard between them, and where results go; the database lists
  all ten tables, not five; grouping replaces "same company and title, best
  score wins"; new sections on the AI reader and the guard, and on run history
  and the Dashboard; "What is not built", which contradicted itself, is gone;
  the test counts are gone too, as they had gone stale twice.
- **README:** a section on the AI page (providers, keys in memory, judging,
  page reads, the hallucination check with its HalluLens credit, the résumé
  review, feedback); `check` and `prune`; the `viewed` status; the Dashboard,
  Job posts and job post window with their screenshots; draft checks named as
  they are (humanizer rules, not an em-dash count); "48 tests" gone; the
  project tree moved out of the dork generator's section. The dork section
  ran `python main.py` throughout, a file that has not existed since the
  scanner: it is `jobdork dork`, configured in `jobdork/dork/boards.py`.
- **CONFIG:** a full `llm` section (it had none), including that a key in the
  file stops the load; the AI keys in the environment table; Resend is used by
  `scan --email` and `digest`, not only the dork generator; `viewed`; a status
  is per job, and what `prune` never deletes.
- **`config.example.yaml`** had no `llm` block; it has one, which loads.
- **PLATFORMS:** "Not yet implemented: enrich, discover", both shipped months
  ago, is now what they do; Adzuna duplicates are grouped, not collapsed; the
  Lever fallback is no longer described as North American only.
- **SOURCES** and the docs index: `jobdork dork --list-sites`; the new
  screenshots and a pointer to the AI setup.
- Every relative link and anchor in the docs was checked by script.

Also fixed, found on the new screenshots: the Dashboard's run cards said "just
now" for anything under an hour (a judging run 23 minutes old); they say
"23 min ago".

---

## Changed — 2026-09-28 — modules grouped into packages

`jobdork/` was 28 modules side by side. They now sit by what they are for:

| Package | Modules |
|---|---|
| `core/` | `config`, `telemetry`, `textutil` |
| `db/` | `store`, `migrations`, `grouping` |
| `search/` | `scan`, `screen`, `enrich`, `discover`, `listing`, `geo`, `resume` |
| `ai/` | `llm`, `judging`, `guard`, `writer` |
| `writing/` | `generate`, `gates`, `humanize` |
| `web/` | `serve`, `api`, `live`, `session` |
| `output/` | `render`, `digest` |

`cli.py`, `fetch/`, `dork/` and `data/` stay where they were. Nothing
outside `web/` (and `cli.py`) imports from `web/`.

- Every import was rewritten by script, relative as before; module titles
  and logger names follow (`jobdork.ai.llm`, not `jobdork.llm`). Tracked
  files were moved with `git mv`, so their history follows them.
- `data/` is found from the package root in `search/geo.py`,
  `web/serve.py` and `writing/humanize.py`.
- `pyproject.toml` lists the new packages; `pip install -e .`,
  `jobdork --version`, `./run.sh`, `python -m jobdork.dork`, the dashboard
  and `tests/run_all.py` were each run from the new layout.
- No compatibility aliases at the old paths: `from jobdork.store import
  Store` is now `from jobdork.db.store import Store`. Only the tests
  imported by path, and they are updated.
- Docs: ARCHITECTURE's module table is now per package. The README's
  "Project structure" still showed the original `main.py` and `config.py`,
  which have not existed since the scanner; it shows the real tree now.
  SOURCES pointed at a `config.py` for both the source lists (now
  `core/config.py`) and the dork board table (`dork/boards.py`, whose own
  title still said `config.py`). The package docstring said "for North
  America", untrue since 0.3.0.
- A doubled `# noqa` in `fetch/__init__.py` is single again.

---

## Fixed — 2026-09-28 — loose ends from the guardrail work

- **The verdict word follows the score.** gemma scored a post 30 and
  called it "possible", so the badge showed a 30 in amber. The word is now
  set by the prompt's own bands (80+ strong, 50+ possible, else weak), and
  verdicts stored before this are corrected when read, without rewriting
  them: that post now shows 30, weak.
- **Last AI judging** said "recorded before run history · just now" on the
  day a post was judged, because the card skipped single-post runs and fell
  back to a stamp it then described wrongly. A full run is still preferred;
  when single posts are all there has been, the card shows the latest one,
  marked "one job post only". The same applies to Last check.
- **The 90-day metrics could undercount.** Run history kept the last 200
  runs, so a busy quarter lost its oldest. Runs and their model calls are
  now kept for 120 days whatever their number; only the per-run logs, which
  are the bulk, are still limited to the last 200 runs.
- **The thumbs beside the AI badge** said only "Useful"; they now say what
  they rate ("Useful (Was the AI verdict useful)") on hover and to screen
  readers.
- **The feedback chart's lower axis** read "5" for five thumbs down; its
  ticks read ↑5 and ↓5.

Tests in `tests/test_ai.py` and `tests/test_telemetry.py`.

---

## Added — 2026-09-28 — feedback buttons, and the AI letter and review on the page

Last part of the guardrail plan.

- **Thumbs up / down** on every AI output the page shows: beside the AI
  badge in a job post's window (the verdict), under each cover letter,
  résumé review and `claude -p` draft tab ("Was this cover letter
  useful?"), and on the Tools page's résumé review. Pressing the pressed one
  clears it. Ratings feed the Dashboard's feedback chart. A draft made with
  the guard off can be rated too: its output row is kept in the artifact
  under a hidden `_output` key, which the page never shows as a gate.
- **Job post window:** **Write cover letter (AI)** and **Review résumé for
  this post** beside Ask AI. Each runs as a normal run, and the window opens
  on the new tab when it finishes. The tab shows the checks, with the claims
  the guard flagged listed, then the text.
- **Tools → Résumé review:** **Review my résumé** runs the general review;
  the newest one is shown there whenever Tools is opened, with the model,
  the time, how many of its claims were found in your résumé, and anything
  flagged.
- Reviews are shown with their headings and lists rather than as raw
  Markdown. The text is escaped first, so nothing in it becomes markup.
- The review capitalises each point; gemma writes them in lower case.
- Tabs read "résumé review" and "CV" rather than `resume_review` and `cv`.

Checked in Chrome: the buttons in the window and the tabs, a thumb pressed
and pressed again (stored as 1, then cleared), and a real general review
from the Tools page (gemma4:26b, 18 of 18 claims found in the résumé). Tests
in `tests/test_guard_wiring.py`.

---

## Added — 2026-09-28 — metrics at the top of the Dashboard

Fifth part of the guardrail plan. Above "Last runs", scoped by a **7 / 30 /
90 days** switch (`GET /api/metrics?days=`):

- **Tiles.** Runs; errored runs (failed, died or stopped, with their share
  of runs); AI calls and how many failed; **P50 AI latency** with P95 under
  it; and the **hallucination** rate: unsupported claims over checked
  claims, with coverage (checked outputs over all AI outputs). Hover or
  focus the hallucination tile for the split by kind: verdicts, page reads,
  cover letters, résumé reviews, claude drafts.
- **Runs by tool, per day.** Stacked columns in a fixed tool order (scan,
  check, AI judging, AI writing, enrich, other), so a tool keeps its colour
  whatever ran. A job started in the terminal and one started here count as
  the same tool.
- **Feedback on AI output, per day.** Thumbs up above the line, thumbs down
  below, with approval in the heading, counted on the day the output was
  written (when a rating was given is not stored).
- Both charts have a legend with totals, a tooltip listing every series for
  the day under the pointer, and **Show as table**. Colours are the dataviz
  reference palette, validated for colour-blind separation against this
  page's own backgrounds in both themes; three light-theme hues are under 3:1
  contrast, which is what the legend and the table view are for.
- The numbers reload when the Dashboard is opened, when a run finishes, and
  when the period changes; the previous numbers stay (dimmed) while they
  load.

On this database, 30 days: 22 runs, 1 failed (4.5%); 21 AI calls, P50
5.3 s, P95 12.4 s; 20 of 143 claims unsupported (14%) over 7 outputs, all
checked. Model calls and AI outputs are only recorded from today, and a tile
says so ("recorded from 2026-09-28") when that is later than the period's
start. Runs come from run history, which keeps the last 200 runs.

Checked in Chrome at full width with the nav open and folded, in both
themes: tooltips, table view, and the hallucination breakdown, which at
first ran off the right edge and now opens leftwards. The axis rounds a peak
of 22 up to 25 rather than 50. Tests in `tests/test_metrics.py`.

---

## Added — 2026-09-28 — the guard checks verdicts, page reads and drafts

Fourth part of the guardrail plan. Every piece of text a model writes here is
now an `ai_outputs` row, and with the new **`llm.guard`** setting on (the
default; AI page: "Check each verdict and draft…") it is checked against the
advert and your résumé.

- **AI judging.** After each verdict, its summary, reasons and concerns go
  through `guard.check`. The result is kept inside the verdict (`guard`,
  `ai_output_id`). The AI badge's tip lists claims neither source supports,
  struck out, under **Not in the advert or résumé**, and ends with "N of M
  claims found in the advert or résumé" (or "claims not checked"). The score
  is left as the model gave it. The run summary counts verdicts with such a
  claim, and so does the run's Outcomes bar ("unsupported claims").
- **Abstaining.** The judge answers `enough_evidence`. When it says no, the
  badge shows **?** and "Not enough to judge" instead of a score. Verdicts
  stored before this read as having had enough.
- **Page reads.** Each time the model reads an unclear posting page, the
  answer is recorded as a `page_read` output. Its check is the quote rule it
  already had: "open" or "closed" is one claim, supported when its quote is
  on the page; "unknown" claims nothing. No extra model call.
- **`claude -p` drafts** (screen, CV, cover letter). When a model is set on
  the AI page, the draft is checked too and gets a **hallucination check**
  gate. Drafts are recorded as `draft` outputs whether or not they were
  checked, so the Dashboard's coverage counts the unchecked ones.
  `generate.record` does the recording for the terminal and the dashboard
  alike.
- **Failed gates list their items** in the job-post dialog (the flagged
  claims, the unsupported figures), not only a count.
- The AI letter and review honour `llm.guard` as well.

The cost: two more model calls per verdict and per draft. On a 26B local
model that is roughly twice the judging time; the AI page says so. Turning
the guard off still records every output, unchecked.

`guard.advert_source(row)` (title, employer, location, then the advert) and
`guard.settings_for(cfg)` are shared by judging, drafts and `writer.py`.
`cli.gates_summary` is gone; `generate.record` replaced it. Tests in
`tests/test_guard_wiring.py`.

---

## Added — 2026-09-28 — AI cover letter and résumé review (`writer.py`)

Third part of the guardrail plan. Both use the model set on the AI page
(local Ollama included), not `claude -p`.

- **`jobdork letter UID`** (dashboard: `POST /api/letter`). At most four
  short paragraphs, facts from the résumé and advert only, humanizer rules in
  the prompt and `humanize.clean` after. Gated like a `claude -p` letter
  (length, AI tells, unsupported figures, overlap with `CV.md`) plus a
  **hallucination check** gate from `guard.check`. Saved as
  `cover-letter-ai.md` in the job folder, so a `claude -p` `cover-letter.md`
  is never overwritten, and recorded as a `cover_letter` artifact, so it
  shows in the job-post dialog as the other drafts do. A new or viewed post
  moves to interested, as with any draft.
- **`jobdork review [UID]`** (`POST /api/review`). Without a post: the
  résumé's own problems, each quoting the line it is about. With one: also
  what the advert asks for that the résumé does not show, what to move up,
  and lines to reword. A suggestion quoting text that is not in the résumé
  is dropped by script and the review says how many were. When the model
  says the evidence is too thin, the review opens by saying so. Against a
  post it is saved as `resume-review.md` and a `resume_review` artifact; a
  general review lives in `ai_outputs` only (`GET /api/review/latest`).
- Both record an `ai_outputs` row with the guard result; the artifact's
  hallucination-check gate carries its `output_id`. `GET /api/ai_output`
  reads one, and `POST /api/feedback {output_id, value}` sets 👍 (1), 👎 (-1)
  or clears (0). The buttons come with the UI step.
- A letter or review needs at least 200 characters of advert, as judging
  does.

Guard fixes found on the first live run (gemma4:26b, one job post):

- A claim built from several places ("worked with Spring Boot, React and
  PostgreSQL", each in a different section) failed for want of one quote.
  The verifier may now join excerpts with ` ... `, and every excerpt must be
  found. The extractor splits lists into one claim per item.
- "The candidate is applying for the position" is the letter describing
  itself; such claims are dropped by script, since the model kept writing
  them.
- The advert source now includes the title and employer.

After the fixes the same letter went from 6 of 25 claims flagged to 1 of 25,
and the one left is a real stretch: Docker attached to an employer the
résumé does not tie it to. The first letter had claimed the résumé's total years of
experience for each language separately; the letter
prompt now says a number of years belongs to what the résumé attaches it to.

Also: the overlap gate read "no the CV to compare against yet"; it now reads
"nothing to compare: the CV is not drafted yet".

Tests in `tests/test_writer.py` and `tests/test_guard.py`.

---

## Added — 2026-09-28 — tables for AI outputs and model calls

Second part of the guardrail plan. Two tables, created on open like
`activity` (no migration step, since new tables need none):

- **`ai_outputs`** — one row per text a model wrote (verdict, page read,
  cover letter, résumé review, draft): kind, job post, model, the run it came
  from, the text, the guard report with its claim and unsupported counts,
  whether the check ran, and thumbs up/down. `Store.add_ai_output`,
  `ai_output`, `set_feedback` (1, -1 or cleared).
- **`llm_calls`** — one row per model call inside a recorded run: model,
  purpose, seconds, ok. No prompt or answer text. Needed for P50/P95 latency;
  the per-model totals on `activity` cannot give percentiles. Pruned with the
  run it belongs to.

`llm.complete_json` takes a `purpose` (judge, page_read, test,
guard_extract, guard_verify), and `telemetry.current_id()` gives the run an
output belongs to. Nothing writes `ai_outputs` yet; that comes with the
guard wiring. Tests in `tests/test_telemetry.py`.

---

## Added — 2026-09-28 — hallucination guardrail module (first part)

`jobdork/guard.py` implements the HalluLens method (LongWiki task) with our
own prompts: extract atomic claims from an AI output, verify each against
the known source (résumé, advert), and count unsupported claims. A model's
"supported" only counts when its quote is found in the named source by
script. A failed check returns `checked=False` and never blocks the output.
Tests in `tests/test_guard.py`.

Not yet wired in. Still to build, per the approved plan: the `ai_outputs`
and `llm_calls` tables, the AI cover-letter and résumé-review tools
(`writer.py`), guard checks on judging, page reads and drafts, feedback
buttons, and the observability metrics on the Dashboard.

---

## Changed — 2026-09-28 — the Dashboard is the home page, at full width

- **Home.** The page opens on the Dashboard, and Dashboard is first in the
  nav, above Job posts.
- **Width.** Page content was capped at 1060px, so on a wide screen the
  Dashboard sat in the left part of the window whether the nav was open or
  folded to the rail. The Dashboard now fills the space beside the nav in
  both states. Job posts and the Setup pages keep the 1060px measure, which
  is easier to read for lists and forms.
- **What it shows first.** With nothing picked and nothing running, the
  panels show the latest run over the whole list, not a one-post check
  started from a dialog.

---

## Changed — 2026-09-28 — "Last runs" instead of a history table

The Dashboard's **Recent jobs** table listed 25 past runs and called out
nothing, while the one thing it was for went unnoticed for a month: the
Aug 29 scan got 0 from Adzuna. It is replaced by a **Last runs** strip at
the top of the Dashboard, one card each for the last scan, the last check
and the last AI judging: when (hover for the exact time), the result, and
in amber whatever went wrong. The scan card reads the scan history itself,
so scans from before run history count, and warns when:

- the last scan is over 15 days old;
- a source returned 0 job posts;
- a source that returned posts before did not run at all;
- a scan started and never finished.

On this database it shows all four. Check and judge cards skip single-post
runs from a dialog, and show a run's failure if it failed or died; click one
to show that run above. The full list is folded into **All runs** at the
bottom. "Job" in the sense of a background task is now "run" on this page,
so it no longer reads like a job post.

---

## Added — 2026-09-28 — clean up old and settled job posts

A **Clean up job posts** panel at the bottom of the Dashboard, and
`jobdork prune` in the terminal.

- **By age:** first seen more than 15 or 30 days ago (`--older-than DAYS`),
  whatever the status, except jobs you are pursuing: applied, submitted,
  interviewing and offer are never removed this way. Offer was added to the
  three asked for, since losing one would be worse than losing the others.
  Age is when jobdork first found the post; many posts carry no date of
  their own.
- **By status:** any of rejected, withdrawn, skipped and closed (ticked in
  the panel, `--status` in the terminal).

Deleting takes two steps. **Preview** shows how many of how many, split by
status, with examples, and warns when that is every post you have. The red
**Delete N job posts** button sends that N, and the server refuses if the
number has changed since (a scan finished, a status changed). It also
refuses while a job is running. `prune` only previews unless given `--yes`.

Before every delete the database is copied to
`data/backups/jobdork-<time>-before-cleanup.db` (the last ten are kept). A
deleted post is recorded in a new `deleted` table, and scans leave it out;
otherwise a post still listed by its source would come back as new with
your decision gone. The scan report counts how many it left out. Status,
notes, AI verdicts and document records go with the post; draft files in
Documents stay on disk.

---

## Changed — 2026-09-28 — charcoal nav in dark mode

The dark nav was navy (`#0b1a2e`) against a near-black page (`#0b0b0d`). It
is now a neutral charcoal, `#151518`: a step lighter than the page, so the
two separate without a colour cast. Hover (`#202025`), the active pill
(`#34343c`, white text) and the count badge moved to the same family.
`#101010` was considered and is too close to the page to see.

Also: the AI-tells check skipped text between backticks as code, which is
right for Markdown drafts but hid every JavaScript template string in the
dashboard. `humanize.find(markdown=False)` now reads them, and it found nine
more dashed strings ("advert 500 chars — too short to screen" and others),
now reworded.

---

## Added — 2026-09-28 — humanizer: no signs of AI writing

[humanizer](https://github.com/blader/humanizer) (SKILL.md v3.1.0, MIT) is
bundled at `jobdork/data/humanizer/` with its licence, and applied to every
kind of text a model writes here, including the app's own wording.

- **Drafts (screen, CV, cover letter).** The full guide is written into each
  job folder as `writing-style.md`, and the prompt tells Claude to write by
  it. It governs how to write, never what to claim; the rules on facts and
  figures still hold. Every draft, screens included, then goes through a new
  **AI tells** gate, which lists each tell found with its rule number
  (§1 "not X but Y", §8 dashes, §12 stock AI words, §19 bold labels,
  §22 chatbot residue, and more). It replaces the em-dash count and the
  external linter that was rarely installed.
- **AI verdicts.** The local or cloud model gets a condensed version of the
  rules. Its summary, reasons and concerns are then cleaned of the two tells
  with one right answer (connector dashes and curly quotes), and verdicts
  stored earlier are cleaned the same way when shown. Anything in quotation
  marks is left as written, because it quotes the advert.
- **Page quotes** from the still-open check are never rewritten: they must
  match the page word for word.
- **The app's own wording.** Every message, label, hint, error, report line
  and email subject was written by a model too, and about 90 used a dash as
  a connector; they are rewritten ("Title at Company", "no credential. Get a
  free key at ...", "Server stopped. Reconnecting..."). The Markdown
  report's bold-label list is plain. A test now fails if a tell reappears
  in any string the app shows. Two dashes stay because they are data: the
  gate that counts dashes, and the address parser that splits on them.

`humanize.find()` catches the patterns with fixed wording. Triads, closers
that restate a point, and sentences that add nothing still need a reader.

---

## Changed — 2026-09-28 — duplicate job posts are grouped, not hidden

Copies of one job — an aggregator reposting it, or the same job on an
aggregator and the employer's board — were collapsed on display by company
and title. Three things were wrong with that, and `grouping.py` fixes them.

- **Different places were merged.** "Software Engineer" at one company in
  Chicago and in Austin became one post, and the other vanished. The group
  key now includes the place: resolved city and state, "remote", or the
  location text when it could not be resolved. On this database that
  brings back **25 job posts** that were hidden.
- **Decisions stayed on one copy.** Mark the shown copy applied, and when
  another copy became the shown one (its advert grew), the job came back as
  new. `set_status` now writes every copy in the group.
- **A dead link closed a live job.** The listing check closed a job when one
  copy was gone. Now it closes only when **every** copy is; the last copy
  found closed is the one that closes it. **10** copies had been closed
  while their job was still up elsewhere.

Every copy is kept. The list shows one per group — one not known to be
closed, then the fullest advert, then the best score — with a **+N copies**
chip; the job's dialog lists **Also posted at** with each copy's link and
its own listing state, so a dead link has a working fallback. The counter
adds "· N duplicates grouped".

Schema v6 unifies statuses already split across copies (the latest real
decision wins, its note fills empty notes) and reopens copies the check had
closed while another copy was live.

---

## Changed — 2026-09-28 — quieter status, and what each Setup page is for

- **Connection status only when it matters.** The permanent "live" line is
  gone. When the page loses the server (stopped, crashed, terminal closed)
  an amber **Server stopped — reconnecting…** appears above the theme
  switch, and disappears once it is back. The running-job name under it is
  gone too; the Dashboard dot already says that.
- **ⓘ on every Setup item.** Hover it — or tab to the item — for a short
  explanation of that page (Search, Résumé, Sources, AI, Tools). The tip
  floats beside the nav so the nav's scrolling cannot clip it. Native hover
  titles now appear only in the collapsed rail, where the names are hidden.

Caught while testing: the new status notice briefly reused the id `status`,
already taken by the Job posts status filter — the filter's options went
into the notice and the list asked for status "undefined". Renamed, and the
page now has no duplicate ids.

---

## Changed — 2026-09-28 — a new nav, and "job posts" everywhere

### Navigation

The side nav is rebuilt: a logo and name at the top, a solid icon beside
every item, and the page you are on as a filled pill — pale blue with blue
text in light mode, slate with white text in dark, on a deep navy panel.
**Job posts** carries a badge counting new posts; **Dashboard** a dot while
a job runs. At the bottom: connection status, and a **Dark mode** switch
that overrides the system setting in either direction (remembered in this
browser). The chevron beside the logo folds the nav to an icon rail (also
remembered); below 760px wide it is always the rail. Theme tokens now
follow the toggle, so every page, not just the nav, switches.

### "Roles" is "job posts" in everything you read

The dashboard, terminal help and output, error messages, the digest email
(subject included) and the HTML and Markdown reports now say "job post".
Unchanged, on purpose: output file names (`roles.json`, `roles.md`,
`roles.csv`), which scripts may read; the `roles` database table; API paths;
code identifiers, comments; and prompts sent to models.

---

## Changed — 2026-09-28 — "Job posts", and Tools under Setup

The nav's **Roles** is now **Job posts** (with "open job posts" in its
filter and "AI: judge top job posts" on the Dashboard). **Tools** moved
under Setup, after AI, leaving the top of the nav to the two pages used
daily: Job posts and Dashboard.

---

## Changed — 2026-09-28 — Scan and Activity are one Dashboard page

Two pages showed the same jobs twice: Scan had the buttons and a live log,
Activity had the progress, hosts, AI calls and a second log. They are now
one **Dashboard** page (nav: Roles, Dashboard, Tools): the job buttons on
top — run a scan, fetch missing adverts, re-apply filters, check still
open, AI judge — and the activity dashboard below, for any job started here
or in the terminal. One log, read from the database; a job started from the
page appears on it at once. A refused start (another job running, no model
set up) shows beside the buttons. The nav dot for a running job moved to
Dashboard. Tools keeps its own log for discover and digest.

`check` no longer prints a line per listed or maybe-gone role — they come
in hundreds and say the same thing; the summary counts them.

---

## Fix — 2026-09-28 — dead Adzuna links were marked "listed"

Opening many Adzuna roles gave "page not found", while the check called all
652 of them listed. Two causes:

- **Re-scoring counted as seeing.** `rescreen`, `enrich` and a pasted advert
  all went through `upsert`, which set `last_seen` to now — so after any
  rescreen every role looked freshly listed. `upsert(role, seen=False)` now
  leaves `last_seen` alone; only a scan or `add` (a source actually listing
  the role) moves it.
- **A month-old scan vouched for its ads.** The only Adzuna scan that
  returned anything ran 2026-08-28; Adzuna ads mostly expire within about a
  month. Now, for **every source**: when the last scan that returned roles
  from it is over **15 days** old, its roles are `stale`, shown as **maybe
  gone**, with the source, the scan's date and its age on hover. Direct
  evidence read during the check itself — the posting page open or closed,
  or missing from a fresh scan — still wins, because it is newer than any
  scan. After a fresh scan, roles missing from it are `unlisted` as before;
  the timestamps the old bug left behind are older than any new scan, so
  they read correctly without being rewritten.

`jobdork check --platform adzuna` checks one platform only.

---

## Added — 2026-09-28 — Activity page: every job, from any process

The dashboard's live log only ever saw jobs the dashboard started; a scan or
check run from the terminal was invisible to it. Jobs now record themselves
in the database (`telemetry.py`, tables `activity` and `activity_events`),
and the new **Activity** page reads from there, whoever started the job.

- **Header** — job, state (running / done / failed / stopped, plus *quiet*
  when the heartbeat is over 20s old and *died* when its process is gone),
  where it was started, pid, and its latest line.
- **Tiles** — progress (done / total, %), rate per minute, time left or
  time taken, requests (with rate-limited count), AI calls with average time.
- **Outcomes** — a stacked bar of the job's counters (closed / still open /
  maybe gone for a check; strong / possible / weak for judging; kept /
  dropped for a scan), status colours always paired with their labels.
- **Network, by host** — requests, 2xx/3xx, 4xx, 429, failures, average and
  slowest time. **AI calls** — per model: calls, failures, average, slowest.
- **Postings, by listing state** — counted from the roles themselves, with
  how many were checked in the last ten minutes, so work from a process that
  records no telemetry still shows.
- **Log** — the job's last 120 lines. **Recent jobs** — click one to inspect
  it.

Refreshes every 2s while open, every 10s otherwise (to light a dot on the
nav item while anything runs). Recorded: counts, hosts and timings only —
never request bodies, page text, adverts or keys. Writes are batched (one
per second plus a 5s heartbeat) on their own connection, and a telemetry
failure never stops the job. `scan`, `enrich`, `check`, `judge`,
`rescreen` and `generate` are recorded from the terminal too. The last 200
jobs are kept.

Also: `[hidden]` now always hides — `.dot`'s `display` rule had been
overriding it.

---

## Added — 2026-09-28 — an AI reader, and checking postings are still up

### AI page — local or cloud model

New **AI** page under Setup. Pick **Ollama (local)**, **Claude**, **Gemini**
or **ChatGPT**; the model list is read live from the provider (Ollama's
from `/api/tags`, the others from their models endpoints with your key).
**Save and test** makes a one-line round trip. Settings go to the `llm:`
section of the config — provider, model, Ollama address, and two opt-ins:

- **After each scan, judge the top N roles** not yet judged (default 25).
- **When checking postings, read pages that do not say** whether the job is
  open.

What the model does: reads the full advert against your résumé and returns
a 0-100 verdict (strong / possible / weak) with a summary, reasons for and
concerns against. It shows as a third badge, `AI 85`, beside match and fit,
with the reasoning on hover. It never drops or hides a role. **Ask AI** in
the role dialog judges one role; **AI: judge top roles** on the Scan page
runs the batch; `jobdork judge` does it from the terminal. A role is judged
again when its advert grows (pasted or enriched).

Adverts are fenced as untrusted data, answers are constrained to a JSON
schema where the provider supports it, and every field is clamped and
clipped before storing. Thinking models on Ollama (gemma4) are asked not to
think — otherwise they spend the token budget reasoning and are cut off
mid-answer.

### API keys — memory only

A key typed on the AI page is held in the server's memory as bytes
(`llm.VAULT`) and never written to the config, database or a log, and never
sent back to the page. It is overwritten and dropped when jobdork stops
(Ctrl-C or `kill`), when you click **Forget**, and after no dashboard tab
has been open for 60 seconds (a running job keeps it until it finishes).
A key put in `config.yaml` under `llm:` is refused at load. The terminal
commands use `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY` or
`OPENAI_API_KEY`. Claude needs `pip install -e '.[ai]'` (the Anthropic
SDK); the others use `requests`.

### Checking a posting is still up

**Check still open** on the Scan page, **Check if still open** in the role
dialog, `jobdork check` in the terminal. Evidence decides, not guesses:

| Evidence | Result |
|---|---|
| HTTP 404 or 410 (Workable answers 410) | closed |
| redirect to `?error=true` (Greenhouse's closed-job redirect) | closed |
| schema.org `validThrough` in the past (USAJOBS) | closed |
| the page says it: "no longer accepting applications", "position has been filled" | closed |
| gone from the employer's Ashby board API | closed |
| page still carries the JobPosting, or still on the Ashby board | open |
| page loads and says nothing | the AI reads it, if allowed — its "closed" counts only with a quote found on the page |

The wording is tight on purpose: every open USAJOBS posting says it "will
no longer be available once the announcement has closed".

A role found closed, and still `new`, `viewed` or `interested`, moves to
`closed` with the evidence as its note; one you applied to or are
interviewing for keeps its status. **Adzuna cannot be checked** — its
pages refuse scripts — so its roles are only `listed` or `unlisted`
(missing from Adzuna's latest results), shown as **maybe gone**, never
closed automatically. Results show on the card (`closed`, `maybe gone`)
and in the dialog, with the evidence on hover. A role checked in the last
12 hours is skipped unless forced.

Schema v5: `roles.llm_score`, `llm_judgement`, `listing_state`,
`listing_note`, `listing_checked_at`, none of which a rescan overwrites.

---

## Added — 2026-09-28 — hover match or fit to see why

Match and fit were two differently styled bits of text with a generic
tooltip. They are now a matched pair of badges — `MATCH 80`, `FIT 5 / 25`,
same size and weight, small-caps label, bold figure — and hovering or
tabbing to either opens a card that explains that role's number:

- **match** lists every rule with its points and the reason: which
  `titles.include` term matched, the arrangement, the distance against your
  radius with the formula (and, at 0 mi, that the posting only gave a city
  so it was measured to the city centre), what the salary was compared
  with, any soft dealbreakers, and résumé fit — totalled at the bottom.
- **fit** says how many of the advert's skills you have and how that became
  the number, including when a short advert was counted out of 5, then
  lists the skills on your résumé in green and the ones asked for but
  missing.

Screening now records these as `roles.score_parts` (JSON, schema v4). A
role not screened since shows "Tools → Re-apply filters fills this in".

---

## Fix — 2026-09-28 — the score is labelled "match"

A bare number beside `fit 5/25` read as a second, unexplained score. It is
now `match 80` on cards, in the role dialog and in the HTML and Markdown
reports, with a tooltip naming what it adds up: title, arrangement,
distance, salary and résumé fit. CSV keeps its `score` column name so
existing spreadsheets still line up.

---

## Fix — 2026-09-28 — fit shown beside the score, and teasers stop scoring 100

Three Adzuna roles sat at exactly 100. Not a cap — every part of the sum had
maxed: title 30, arrangement 10, distance 30 (Adzuna says "Chicago,
Illinois", which resolves to the anchor itself, so 0.0 mi), salary 5 (no
floor set), and résumé fit 25 of 25 — because the 500-character teaser named
one skill, and one of one is 100%.

### Changed

- **Fit is stored and shown on its own.** New `roles.fit` column (schema
  v3), shown as `fit N/25` next to the score on each card, in the role
  dialog, and in the HTML, Markdown and CSV reports (`fit` is appended as
  the last CSV column so existing column positions hold). A role with no
  résumé or no advert shows `–`, not 0.
- **A thin advert cannot score full fit.** The share is taken of at least
  `MIN_SKILLS` (5) skills, so a teaser naming only "java" scores 5 of 25, not
  25. A full advert you match entirely still scores 25.

### Fixed

- **A rescan overwrote fuller adverts with the teaser.** Scan screened, and
  stored, whatever the source sent this time — so an advert recovered by
  `enrich` went back to 500 characters on the next Adzuna run. Scan now uses
  the stored advert when it is longer, for screening and storage both.
- **`rescreen` skipped duplicate copies.** It walked the list with
  duplicates collapsed, so 127 hidden copies kept their old scores, and
  because the collapse ranks by score, a stale 100 then outranked the
  re-screened 80 and became the copy shown. It now re-screens every row.

### Added — paste the advert

Adzuna cannot be enriched: the API caps adverts at 500 characters, and its
pages answer scripts with a CloudFront `403 Request blocked` (re-checked
today, `robots.txt` included), which this tool does not work around. The
browser can read the page, so the role dialog now has a **Paste the full
advert** box — open by default when the stored advert is 600 characters or
fewer — that stores the text and re-screens the role on it
(`POST /api/advert`). A role that no longer passes is marked skipped with
the reason, as `enrich` does.

---

## Fix — 2026-09-28 — set a role's status from its detail view

The role dialog showed the advert but no way to act on it, so you had to
close it and use the card's dropdown. Its header now carries one button per
status you decide — interested, applied, submitted, interviewing, offer,
rejected, withdrawn, skipped, closed — with the current one filled in its
colour. `new` and `viewed` are left out: those are recorded for you. The
dialog also no longer calls `showModal()` on itself while already open,
which it did every time a status changed with it showing.

A status change keeps the dialog on the tab you were reading — a drafted CV
stays a drafted CV instead of snapping back to the advert. And acting on a
card no longer reopens that role's dialog after you have closed it.

---

## Fix — 2026-09-28 — `run.sh` points at the package

`run.sh` still ran `main.py`, which the package layout removed, so it died
with `can't open file '.../main.py'`. It now runs `python -m jobdork "$@"`,
and with no arguments it runs `serve`, so `./run.sh` opens the dashboard.

---

## 0.15.0 — 2026-08-30 — the page can do everything the terminal can

Eight commands existed only in the terminal, so the dashboard was a viewer
with four buttons. It is now a front end over the same functions — not a
second implementation, the same `scan`, `enrich`, `discover`, `generate`,
`digest` and `add` that `cli.py` calls — so there is nothing to drift.

### Added — every command, in the page

| | |
|---|---|
| **Scan** | already there, now beside enrich and rescreen |
| **Enrich** | fetch the full advert where only a summary arrived |
| **Re-apply filters** | `rescreen`, after changing your search |
| **Add a posting** | paste a link you found yourself |
| **Discover** | find an employer's board and add it, reading the token off their page |
| **Digest** | mail the list, with the CSV attachment option |
| **Generate** | screen, CV and cover letter, per role |
| **Sources** | what runs, what does not, and why |

Every long one reports over the event stream, so drafting a CV is watched
rather than waited for. Still one job at a time, and a refusal now names what
is holding the runner.

### Added — a role detail view

Clicking a title opens the advert in full, with tabs for anything generated
for it. **A document drafted in the terminal is readable in the page**, with
its gate results beside it — which is the parity the two front ends were
supposed to have and did not.

The draft buttons are disabled, with a reason, when the `claude` CLI is not on
PATH. Everything else keeps working; the feature that needs a tool you do not
have says so rather than failing when clicked.

### Added — `viewed`

A new status, between `new` and `interested`, set when you open a role.
Without it a role you have read and not decided on is indistinguishable from
one you never opened, which is the exact thing a scanner is supposed to
remember for you.

### Added — résumé upload

Drop a `.pdf`, `.docx`, `.md` or `.txt` in the page; it is parsed immediately
and reports back how many characters, years and skills it found, so a résumé
that cannot be read is caught at upload rather than silently scoring every
role at zero.

**The browser's filename is used for exactly one thing — reading its
extension.** The file is written to a name and directory this code chooses.
Verified: an upload claiming to be `../../../.ssh/authorized_keys` is refused
on its extension, and nothing is ever written outside the data directory.

### Security

- **A generated document is fetched by artifact id, never by path.** Only
  files this tool recorded writing can be read, so a bug in the front end
  cannot turn the dashboard into a file browser. A non-numeric id is 400, an
  unknown one 404, and a recorded file that has since been deleted is 410
  rather than a blank page.
- Every new endpoint is behind the same token and Host checks as the rest.

---

## 0.14.0 — 2026-08-30 — a live dashboard, and localhost is not a boundary

Groundwork for whichever way this gets packaged. Every route — a desktop app,
a container, or just running it here — needs this and none of it is wasted.

### Fixed — the server had no authentication at all

`serve` validated the Host header and nothing else. That stops a web page
reaching it under DNS rebinding; it does nothing about another program on the
same machine. **Any process running as you could `curl 127.0.0.1:8765/api/roles`
and read every role, note and status, or POST changes to them.** It was
described as "local only" as though local meant safe.

A token is now minted per run, printed once as part of the URL, held in memory
by the page and sent as a header afterwards, and compared in constant time. It
is not stored and it dies with the process. Verified live: no token 401, wrong
token 401, right token 200.

### Fixed — a hardcoded port

8765 collides, with another jobdork or with anything else that liked the
number. The port is asked for rather than assumed: the preferred one is tried,
a free one is taken if it is busy, and the actual port is printed so a parent
process can read it instead of guessing.

### Added — a scan you can watch

A scan takes minutes, which is exactly when it is worth watching: a rate limit
or a dead board shows up in the middle, not at the end. It now runs on a
background thread and reports through server-sent events — plain HTTP, no
library, no websocket.

```
[status  ] scan started
[progress] ashby: 109 roles, 1 requests
[progress] adzuna: 818 roles, 25 requests
```

**One at a time, refused rather than queued.** Two scans racing would double
every request to hosts that are deliberately paced, and the second would earn
the rate limit the first was avoiding. A second trigger answers
`a scan is already running`.

A subscriber that has stopped reading — a closed tab the server has not
noticed — fills its queue and is dropped, rather than blocking the scan that
is trying to report progress.

### Added — settings in the page

Titles, location, radius, units, countries, arrangements, salary floor and
résumé path, edited without opening YAML. The file is written, then re-read
through the normal loader; **an edit that would not survive `jobdork scan`
cannot be saved**, and a rejected edit is rolled back to the file that was
there before. Credentials are not in the payload and are not touched.

### Added — the advert cap, made visible

A role whose advert is 500 characters now says so in the list: *advert 500
chars — too short to screen*. Dealbreakers and fit scoring both read the body,
so that number is the difference between a screened role and a guess.

### Also

- Body limits are per endpoint. A status change is a uid, a word and a note;
  a config save carries every title. Letting the config's limit apply to
  actions meant accepting a quarter-megabyte note, which a test caught.
- A Content-Security-Policy of `default-src 'none'` with `connect-src 'self'`,
  so a script injected through a job title still cannot phone home.
- 21 tests for the server, covering the token, the port, the stream, the
  one-scan rule and config rollback. 142 in total.

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
Copyright held under the GitHub handle `jessn-dev`.

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
- **Uncommitted:** 0.6.0 through 0.13.0, and every dated entry above, exist
  only in the working tree. `684b7c9` is the last commit.

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
