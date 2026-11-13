# The Dashboard

The Dashboard is where you start a scan and the other jobs jobdork runs, and
where you see how they went. Every run shows here, whether you started it
here, from a schedule or from a terminal.

![The Dashboard](images/dashboard.png)

When a follow-up on one of [your applications](applications.md) is past its
date, a note above the buttons says which, with **Open My applications**.

## The buttons

![The Dashboard's buttons](images/dashboard-buttons.png)

**Run a scan** is the one filled button. The three that delete sit apart at
the end of the row, with a red icon, and turn red when you point at one; the
button that confirms a delete is red throughout.

| Button | What it does |
|---|---|
| **Run a scan** | Reads every source for new job posts and checks them against your rules. Posts you have seen before are updated, not repeated. Once a day is plenty: boards are read slowly on purpose, and scanning more often gets you blocked for a while |
| **Fetch missing adverts** | Some sources send only a short summary. This fetches the full advert from the posting page, so the rules and the scores can read it. A post you already acted on (applied, say) keeps its status even when the fuller advert misses a rule |
| **Re-apply filters** | Checks every stored post against your current [Search](search.md) settings again. Changing a setting does this by itself; this is for when you want to be sure |
| **Check still open** | Asks each posting whether the job is still up, and closes the ones that are gone (see [listing tags](statuses.md#is-it-still-open)). A job found on several sites is checked at each, so it counts more postings than Job posts shows jobs; one checked in the last 12 hours is left as it is, and the run's first line says how many of each |
| **AI: judge top job posts** | The AI reads your best-scored posts against your resume and gives each an [AI score](scores.md#ai-the-models-opinion). Needs an AI on the [AI page](ai.md). Buttons with an amber icon use the AI, which may cost money with a paid provider |
| **Run fresh scan** | *Deletes.* Deletes every job post scans found (with its status, notes and AI verdict), then scans from nothing. Jobs you applied to are kept, with their stages, notes and documents, so My applications stays as it is; the confirmation says how many. The database is backed up first, and you confirm the number before anything goes |
| **Delete all scanned posts** | *Deletes.* The same delete, without a scan after it |
| **Start over** | *Deletes.* Deletes everything: settings, job posts, your uploaded resume, documents and keys. Then setup opens from the start. You see exactly what goes, then confirm with **Delete everything and start setup**, or **Cancel** |

While a job runs, a progress line shows under the buttons; only one runs at
a time. A yellow or red box under them says what went wrong, if anything did:
a source that returned nothing, a scan that never finished, or a last scan
over 15 days old.

After a scan, jobdork may offer to remove posts that are old (*risky*,
*stale* or *ghost*, see [age tags](statuses.md#how-old-a-post-is)) that you
have not acted on. **Not now** keeps them.

## A run in detail

Under the buttons, a card for the last run of each kind (**Last scan**,
**Last check**, **Last AI judging**); pick one to show it below. Then that
run in full:

- **Progress**, **Rate**, **Time left** (or **Took**, once it ends),
  **Requests** and **AI calls**, as tiles.
- **Outcomes**: what the run counted: posts kept and dropped, verdicts given.
- **Network, by host**: each website read, how many requests, and how many
  were refused or slow.
- **AI calls**: each model, how many calls and how long they took.
- **Postings, by listing state**: how many posts are still up, gone or
  unknown.

## The numbers

Below the run, the weeks behind it. Pick **7 days**, **30 days** or **90 days** to see that period.

| Tile | Means |
|---|---|
| **Runs** | How many scans, checks and AI runs there were |
| **Errored runs** | How many failed, died or were stopped |
| **AI calls** | How many times the AI was asked, and how many of those failed |
| **P50 AI latency** | How long an AI answer usually takes (P50 is the middle; P95 is a slow one) |
| **Hallucination** | Of the facts the AI wrote, the share it could not back up from your resume or the advert. Lower is better: green at 5% or under, amber to 10%, red above, with the words beside it. *Coverage* is how much of the AI's writing was checked ([why](ai.md#the-hallucination-check)) |

The charts below them:

- **Runs by tool, over time**: scans, checks, AI judging, AI writing and the
  rest, day by day.
- **Hallucination, over time**: claims not supported, by kind of writing
  (**By kind**), by the AI model that wrote them (**By model**), or by the
  model that checked them (**By checker**), over the same green, amber and
  red bands. The legend gives each one's total and rate for the period.
  The **Hallucination** tile mixes every checker used in the period, so
  after you change checker, **By checker** shows the new one's rate at
  once, while the tile catches up as the old runs leave the period.
- **Running and waiting**: the job running now, and the ones waiting
  their turn, first in first out, each with what started it ("Search: added
  Nurse Practitioner"). A change to your search, Projects or Education
  starts a scan or a re-scoring by itself, and waits here while another job
  runs. **Cancel** takes a waiting one off. **Stop**, beside a running scan,
  stops it reading more boards: the boards being read at that moment
  finish, and every job post found so far is kept. The AI reading after a
  scan is skipped when it is stopped.
- **Feedback on AI output, per day**: your thumbs up and down on AI
  writing ([how to rate it](job-window.md#rate-the-ai)).

**Show as table** turns any chart into the numbers.

### How long it is kept

The numbers cover the period you pick: 7, 30 or 90 days. Older records
stop counting once they are outside it; some are also deleted:

| What | Kept |
|---|---|
| The hallucination check of each AI output (its claims and what was flagged) | Always. A fresh scan deletes the job posts, not this history |
| Runs, and every call to an AI model (Runs, Errored runs, AI calls, AI usage) | 120 days |
| A run's log lines | The last 200 runs |
| Warnings and errors from outside a run | The last 500 |

### AI usage

![AI usage](images/dashboard-usage.png)

Every call jobdork made to an AI model, local or on your keys, in the
period chosen above. **Provider** narrows all of it to one provider.

With a [coding agent](ai.md#coding-agent) among your readers or checkers,
a note above the charts says when it last used jobdork's tools (or that it
has not yet), how many answers and changes it saved, who answers what
jobdork asks for itself, and how many checks wait for it. jobdork never
calls your agent, so it shows up here only once you ask it something in
its own chat.

- **Total AI requests**: calls per day, and the share answered as a line.
- **AI errors, by kind**: the calls that failed, per day: rate limited
  (429), key refused, provider error (5xx), timed out, could not reach,
  an answer cut off at its length limit, an answer that was not JSON, and
  so on. A provider busy for a moment (502, 503, 504) is asked twice more,
  a few seconds apart, and only counts as an error if all three fail.
- **Usage per model**, one line per model; **Model** shows one:
  - **Input tokens per model**: what was sent: the prompt, the advert,
    your resume.
  - **Output tokens per model**: what the model wrote, its thinking
    included.
  - **Requests per model**: how many times each was asked.

Tokens are as each provider counted them, so they are what a paid key is
billed by. Calls made before jobdork counted tokens show requests but no
tokens.

## Log and history

At the bottom:

- **Log**: what the run printed, line by line.
- **Warnings and errors**: the last 7 days' problems, from every run and
  from the app itself. Pick a line to show that run. These are also what the
  [Feedback](feedback.md) page offers to send.
- **All runs**: every run; pick one to show it above.
