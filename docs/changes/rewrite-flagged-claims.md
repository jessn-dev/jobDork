## Added — 2026-11-10 — A verdict with flagged claims is written again once

Once the hallucination check itself was right (see the entries of the same
day), the claims it still flagged were the AI's own mistakes: a skill only
the advert names written as the candidate's, a gap the resume fills. The
check found them, but they stayed in the verdict you read.

Now a verdict whose claims the check flagged is put right once, after
Guardrails AI's "reask", made surgical: asked to write its whole verdict
again, `gemma4:26b` handed back the same text word for word. So the reasons
and concerns the flagged claims were split from are taken out by script
(each claim traced to the sentence sharing most of its words), and when one
came from the summary, the reader writes that one sentence again without it
(`llm.rewrite_summary`). The result is checked as the first was, and the
one with fewer flagged claims is kept and shown (`judging.rewrite`,
`judging.revise`); the other is recorded as a draft
(`judge_draft`), left out of the Dashboard's hallucination rate, which
counts what you are shown, and counted on the **Hallucination** tile as
"rewritten". A rewrite that fails, is not checked, or flags as many leaves
the verdict as it was.

On by default (`llm.rewrite`, and a box on the AI page): one more check
for each flagged verdict, and a reader call when its summary is rewritten;
nothing for a clean one. The flagged statements and the summary go to the
model fenced as
the advert is, and the fence now strips every block name jobdork uses, not
only the advert's, so text inside one cannot close another.
`scripts/hallucination_benchmark.py --rewrite` measures it. Tests:
tests/test_guard_wiring.py (a flagged concern taken out and kept, a
flagged summary written again, set aside when no better, not run when clean
or off, drafts out of the rate) and tests/test_guard.py (the prompt's
fences, a claim traced to its sentence, the summary cleaned as a verdict
is).
