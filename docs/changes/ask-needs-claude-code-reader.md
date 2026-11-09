## Changed — 2026-11-07 — Ask is off until Claude Code is a reader

Ask, in the desktop app, ran whenever Claude Code was installed, even for
someone whose AI page had only Ollama or a keyed model: it spent their
Claude plan without their having chosen Claude Code anywhere in jobdork.

Now Ask is on only when Claude Code is installed **and** is a reader on the
AI page (a Coding agent line naming Claude Code, or any coding agent).
Until then the Ask menu item is dimmed, the box is disabled, and the page
says what is missing, with a button to the AI page. Claude Code as the
checker keeps Ask off, since a checker does not write. The server refuses
a question while Ask is off, whatever the page sends.
