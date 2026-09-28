# Documentation

| Document | What is in it |
|---|---|
| [CONFIG.md](CONFIG.md) | Every setting, what it accepts, what happens when it is wrong, including the [AI reader](CONFIG.md#llm) |
| [PLATFORMS.md](PLATFORMS.md) | Each source's endpoint, quirks, rate limits and verification status |
| [SOURCES.md](SOURCES.md) | Where coverage comes from, board tokens, the gazetteer, what is out of reach |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the pipeline fits together and why, the package layout, the AI guard and run history |
| [CHANGELOG.md](CHANGELOG.md) | What changed, and every bug found on the way |

---

## What it looks like

| | |
|---|---|
| ![dashboard](images/dashboard.jpg) | `jobdork serve` opens on the Dashboard: runs, AI calls and latency, the hallucination rate, what went wrong in the last scan |
| ![job posts](images/job-posts.jpg) | Job posts: the list with buttons, match, fit and AI scores, copies of one job grouped |
| ![a job post](images/role-detail.jpg) | One post: the advert, drafts, and the AI verdict with how many of its claims were found in your résumé and the advert |
| ![a run](images/live-run.jpg) | A run reporting itself, from the page or the terminal |
| ![static page](images/static-page.jpg) | `out/index.html` — the list, self-contained, written by every scan |

---

## Start here

**Setting it up** — [CONFIG.md](CONFIG.md), then the
[minimal config](CONFIG.md#minimal-working-config).

**Wondering why a role was dropped** — `jobdork list --flags`, then
[the screening rules](CONFIG.md#how-a-title-is-matched) and
[the salary rule](CONFIG.md#the-rule).

**Wondering why a source returned nothing** —
[Failure usually looks like success](PLATFORMS.md#failure-usually-looks-like-success).

**Adding an employer's board** — [Board tokens](SOURCES.md#board-tokens).

**Writing an adapter** — [Adding a source](SOURCES.md#adding-a-source) and
[the adapter contract](ARCHITECTURE.md#adapter-contract).

**Setting up the AI reader** — [llm](CONFIG.md#llm), then
[how its output is checked](ARCHITECTURE.md#the-ai-reader-and-the-guard).

---

## The five things worth knowing before you trust the output

**Only a positive statement by the employer can disqualify a role.** Silence
never does. A posting that states no salary, no work arrangement, or a location
nothing can parse is kept and flagged, not dropped.

**Around 12% of postings state pay.** A salary floor filters that minority and
leaves the rest visible, marked `unconfirmed salary`.

**About 60% state no work arrangement.** Those are kept whatever
`work_modes` says.

**Adzuna truncates every advert to 500 characters.** Dealbreakers, work-mode
detection and résumé fit scoring all read the advert body, so Adzuna roles
cannot really be screened — it is a discovery-and-salary source. See
[the 500-character cap](PLATFORMS.md#the-500-character-cap).

**An empty answer from an employer board means nothing.** Several of these APIs
return HTTP 200 with an empty array both for a board that does not exist and
for one that is throttling. Those roles are reported as `SUSPECT`, not as
"not hiring".
