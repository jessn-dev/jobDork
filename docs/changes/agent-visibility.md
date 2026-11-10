## Added — 2026-11-10 — What your coding agent has done, on the AI page and the Dashboard

jobdork never calls a coding agent: it answers what you ask it in its own
chat, through jobdork's tools. So an agent listed as a reader or checker but
never connected, or connected and never asked, did nothing and showed
nothing anywhere, which looked the same as an agent that worked. Listed as
Reader 2 after a model, it was never reached at all, and nothing said so.

Now the AI page's coding-agent box and the Dashboard, above AI usage, say:

- when your agent last used jobdork's tools, which agent and which tool,
  or that it has not yet (so it is not connected);
- how many answers and changes it has saved, and the last of each;
- who answers what jobdork asks for itself (judging after a scan, the AI
  buttons) instead of the agent;
- how many checks wait for it, when it is a checker, with what to ask it.

A run whose model calls passed over a listed agent (a scan's judging, say)
says so once in its log: "Coding agent is listed as a reader, but jobdork
never calls it: judge and the rest of this run went to …".

The agent's tools run in a process of their own, so the last time it used
them is kept in the database (`meta`, `coding_agent_seen`, written by
`web/agent.py` on every tool call); `api.agent_activity` reads it with the
agent's answers (`llm_calls`) and changes (`activity`) for `/api/llm` and
`/api/metrics`. The guide's AI and Dashboard pages say what the note means,
and the AI page's coding-agent picture shows it. tests/test_agent.py covers
an agent never seen, then seen, its answers and changes counted on both
pages, nothing shown with no agent listed, and the run's note said once.
