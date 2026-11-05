## Added — 2026-11-05 — The AI tools tab says what to ask your coding agent

With a coding agent as the only reader, a job post's document buttons said
what to ask the agent, but the AI tools tab's editing help (**Tailor my
resume**, **Keyword ideas (AI)**, **Skills to highlight**, **Recruiter
feedback**, **Revise: 5 versions**, **Recruiter feedback on this letter**)
had nothing to give it: the guide said to ask the agent "directly", with no
instructions, advert or rules behind the question.

Each of those buttons now says what to ask your agent, with **Copy** (the
pasted bullet, paragraph or letter goes with it). The agent's `get_brief`
takes the editing kinds (`resume_edits`, `keywords`, `highlight`,
`feedback`, `revise`, with `text` for a revision or a letter) and gives
exactly what a model would have been given; it answers you in its own chat,
following the same rules (only what your resume says, quoting it), and
nothing is saved under the tab (`save_document` refuses those kinds). The
server refuses the tools in that mode with the same question to ask
(409), as it does the documents. The agent's connection instructions say
so.

The guide's AI and job window pages say what the buttons do with an agent.
Tests cover the editing briefs (each kind, the user's text in a revision,
revise without text or with too much refused, nothing written or saved) and
the tools refused with what to ask when the agent is the only reader.
