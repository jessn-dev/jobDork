"""
jobdork.dork
============
The Google query generator: builds searches you click yourself.

It reaches what no applicant tracking system exposes — role lists dropped in
public Docs, recruiter posts that go live before the listing, hiring managers
to approach directly — and adding a board to it is one line, where an API
adapter is a hundred plus its quirks.

`generator.py` is the original script, moved into the package rather than
rewritten. It still runs standalone (`python -m jobdork.dork`), and `jobdork
dork ...` dispatches to it with its own flags intact. `boards.py` holds the
site tables it reads.

Rewriting it was considered and refused: it works, it is well documented, and
a rewrite would have been change for its own sake.
"""

from . import boards

__all__ = ["boards"]
