# Choosing an AI model, measured

jobdork's AI reader judges each job post against your resume and writes
letters; a second model, the checker, checks every claim it makes against
your resume and the advert (the [user guide's AI page](https://jessn-dev.github.io/jobDork/ai/)
explains both). This page is what we measured when choosing which models to
recommend, so you can decide between a model on your own computer and a
hosted one with the numbers in front of you.

**Short version.** On your own computer, read with **`gemma4:26b`** and
check with **`qwen3.8:27b`**: 2.9% of the reader's claims were unsupported,
and no one of seven resumes in six fields went above 4.5%. Every other local
model we tried was at 10% or more. Hosted models (Claude, Gemini, ChatGPT,
Groq) are not in the table yet; [measure one yourself](#measure-it-yourself).

---

## What the number means

The **hallucination rate** is the share of a verdict's factual claims that
neither your resume nor the advert supports. It is the number on jobdork's
Dashboard. Each verdict is split into single claims ("The resume lists
Kubernetes", "The advert asks for five years of AWS"), and the checker
decides each one, quoting the words that support it; a script then checks
the quote is really there, and settles claims that something is missing
against the resume itself. A claim nobody can quote counts against the
reader. The method follows [HalluLens](https://arxiv.org/abs/2504.17550);
the prompts and rules are jobdork's own (`jobdork/ai/guard.py`).

Between 2% and 5% is the range we treat as safe to rely on: a verdict of
about 17 claims has, on average, less than one you would need to cross out,
and the page strikes those out for you.

## How it was measured

- **Seven resumes, six fields:** two in software and DevOps, marketing,
  sports writing, copywriting, pharmacy, and construction quality control.
  PDFs as people send them: one came out one word per line, one with its
  font's letter pairs as stray symbols (both fixed in how jobdork reads
  PDFs before this run).
- **Job posts from real boards**, read by jobdork's own scan on 26 October
  2026: for each resume, six from its own field and two from another, 56 in
  all, the same 56 for every model.
- **The same prompts, rules and checker for every reader:** `qwen3.8:27b`
  on Ollama checked them all. jobdork's code as released in 0.15.1.
- **Two computers:** a MacBook Pro (M4, 48 GB) and a Windows 11 PC with an
  AMD Radeon RX 6700 XT (12 GB) and 64 GB of memory, joined as in
  [run/ai-on-two-computers.md](run/ai-on-two-computers.md).

## Results

| Reader (Ollama) | Download | Unsupported claims | Own field | Other field | Seconds per job post | Notes |
|---|---|---|---|---|---|---|
| **`gemma4:26b`** | 18.6 GB | **2.9%** (28 of 963) | 3.4% | 1.4% | 6.5 on the Mac, about 50 on the PC | Recommended |
| `qwen3:14b` | 9.3 GB | 9.9% | 11.2% | 6.2% | 55 on the PC | |
| `gemma3:12b` | 8.1 GB | 10.0% | 10.4% | 8.9% | 69 on the PC | |
| `phi4:14b` | 9.1 GB | 13.0% | 16.3% | 4.5% | 42 on the PC | Its context, 16k, is no larger than jobdork asks for |
| `mistral-small3.2:24b` | 15.2 GB | 13.9% | 16.4% | 5.8% | 26 on the Mac | |
| `llama3.1:8b` | 4.9 GB | 14.3% | 14.5% | 13.8% | 25 on the PC | 27 of 56 verdicts failed: it did not answer in the form asked |
| `gpt-oss:20b` | 13.8 GB | 14.9% | 13.4% | 19.6% | 22 on the Mac | Called things missing most often |
| `qwen3:30b` | 18.6 GB | 18.4% | 21.0% | 9.4% | 7 on the Mac | Gave years for single skills most often |

`gemma4:26b`, by resume (own field): software 1.1% and 3.4%, marketing
4.1%, sports writing 3.0%, copywriting 4.5%, pharmacy 4.1%, construction
3.0%.

**Read these numbers with three things in mind.**

1. **The rules were tuned on `gemma4:26b`.** The reader prompt and the
   checking script were improved over several rounds by studying where
   `gemma4:26b` went wrong. Other models go wrong in other ways (`gpt-oss`
   calls things missing that the resume lists; `qwen3:30b` gives a number of
   years to a single skill), and some of their gap is rules that were never
   tuned for them, not only a weaker model.
2. **It is a small set:** 56 job posts, about 1,000 claims per model, seven
   people. Enough to tell 3% from 15%, not 3% from 4%.
3. **One checker decides.** A different checker would move every number a
   little. `qwen3.8:27b` was chosen because it was the most accurate checker
   we measured: right about 99% of the time on 574 claims checked by hand.

## What to run on what

| Your computer | Reader | Checker | Expect |
|---|---|---|---|
| A Mac with 48 GB or more | `gemma4:26b` | `qwen3.8:27b` | Both loaded at once; about 7 s a job post to read, 40 s to check |
| A Mac with 32 GB | `gemma4:26b` | `qwen3.8:27b`, or a second computer | Both do not fit at once; each swap loads 18 GB again. A second computer avoids it |
| A PC with a 16 to 24 GB graphics card | `gemma4:26b` | on the same PC, or another computer | |
| A PC with a 12 GB card and 32 GB or more of memory | `gemma4:26b`, part of it on the processor | another computer | About 50 s a job post; the card is full while it works. AMD on Windows: read [AMD cards on Windows](run/ai-on-two-computers.md#amd-cards-on-windows) |
| A graphics card of 8 GB or less, or 16 GB of memory in all | a hosted model | a hosted model | The local models that fit were at 10% to 14% here |

A smaller local model does not leave the graphics card free while it works:
with jobdork's 16k context, `gemma3:12b` used 11.7 GB of a 12 GB card, about
as much as `gemma4:26b`. What frees the card is `OLLAMA_KEEP_ALIVE 2m`, which
unloads the model two minutes after the last call.

## Local or hosted

| | Local (Ollama) | Hosted (Claude, Gemini, ChatGPT, Groq) |
|---|---|---|
| Your resume and the job posts | Stay on your computers | Sent to that company, with your email, phone number and profile links removed first |
| Cost | Nothing per call; a computer that can hold an 18 GB model | Tokens on your key, every verdict and every check |
| Speed | 6.5 s to about 70 s a job post, by computer | Usually seconds |
| Measured here | Yes, above | Not yet |

Measured on 0.14.4 by a user, before the changes this page was measured
with: Gemini reading and `gemma4:26b` checking, 36% unsupported. Both the
rules and the prompts have changed since, so that number says nothing about
Gemini today; measure it.

## Measure it yourself

`scripts/hallucination_benchmark.py` runs the same test on your own resumes
and job posts, with any model jobdork can call. It works on a copy of your
database and writes nothing else.

```
sqlite3 data/jobdork.db ".backup /tmp/jobs-copy.db"
python scripts/hallucination_benchmark.py --db /tmp/jobs-copy.db --resume my-resume.pdf --limit 20
```

- Another reader: `--reader ollama:qwen3:14b`, or a hosted one, as
  `--reader gemini:gemini-3.1-flash-lite`, `--reader anthropic:<model>`,
  `--reader openai:<model>`, `--reader groq:<model>`. A hosted model reads
  its key from the environment where you run the command
  (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`)
  and spends tokens on it.
- Another checker: `--checker ollama:mistral-small3.2:24b`.
- A model on another computer: `--reader ollama:gemma4:26b@http://<pc-name>:11434`.
- Each resume against its own field and another: repeat
  `--case RESUME DATABASE COUNT`, one database per field.
- `--judge-only` writes the verdicts first, so one model is loaded at a
  time; run again without it to check them. Verdicts are kept in `--out`, so
  a second run checks again without asking the reader.

It prints the rate for each resume and pairing, every unsupported claim,
and writes all claims to `claims.jsonl` in `--out`.
