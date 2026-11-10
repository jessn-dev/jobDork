## Added — 2026-11-10 — Job posts mark what the AI judged, and in which run

**AI: judge top job posts** ran and finished, but nothing showed which job
posts it had judged. It reads your best posts it has not judged yet, so
they are often well down the list, and their AI badges looked the same as
the ones from earlier runs. The run's summary gave only a count.

Now:

- Each judged post shows **Judged** and the day beside its AI badge, and
  **Judged in the last run** when the most recent judging run (the button,
  or the judging after a scan) read it.
- Job posts sorts by **AI score** too, and filters **AI-judged**, **Judged
  in the last run** or **Not judged yet**.
- When a judging run ends, a message says how many posts it judged, with
  **Show them**: Job posts, *Judged in the last run*, best AI score first.
- The run's summary names the first five posts it judged ("Title, Company")
  and counts the rest.

`/api/roles` gives each post `ai_score` and `ai_at` (when its verdict was
made), and `last_judging`: the run that made the newest verdict, by its
start and end in the run history, with how many posts it judged
(`api.last_judging`). The guide's Job posts and Scores pages say what the
marks, the sort and the filter mean; their pictures are retaken.
tests/test_serve.py covers the marks and the last run's window, and
tests/test_ai.py the summary's names.
