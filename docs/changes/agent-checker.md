## Added — 2026-11-07 — Your coding agent as a checker

A coding agent could only write: it was never offered as a checker, and a
config that listed it under `llm.checkers` was refused. Someone with no
second model had no way to have their readers' work checked by anything
but another of their readers.

Now **Coding agent** can be chosen as a checker on the AI page, and
`{provider: agent}` is accepted in `llm.checkers`. A Coding agent line also
says **which agent** (Claude Code, Codex, Cursor, GitHub Copilot, Claude
Desktop, Antigravity CLI, or any; `model` in the config). One agent is a
reader or a checker, never both, since it would mark its own writing:
Claude Code can write while Codex checks, but with Claude Code as a reader
it is not offered as the checker, and the other way round. A config naming
the same agent on both sides, or "any" on one side and an agent on the
other, is refused. The tools hold each connected agent to its role by the
name it connects with: the checker agent cannot write in a reader's place,
a reader agent cannot check, and no agent can check what it wrote itself.

jobdork never calls an agent, so a check that reaches it waits: the
output says **waiting for your coding agent**, and a document's checks list
it as one to read. When you ask your agent to check jobdork's AI writing,
it uses three new tools: `list_checks` (what waits), `get_check_brief` (the
claims to find, then the sources to check them against, as a checker model
is asked) and `save_check`. jobdork holds every quote it gives to its
source, as it does a model's, and the check then replaces the waiting one
on the output, on the document's checks, and in a verdict. A checker listed
before the agent checks first; the agent checks what it could not. The
agent gives no second score (**models disagree**). What a waiting check is
to check is kept in the database (`ai_outputs.check_input`, schema 17) and
cleared once checked.
