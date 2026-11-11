## Added — 2026-11-11 — Why no built-in employer board is read, and what to change

When a person's countries, industries or switched-off boards left none of
the built-in employer boards to read, the Sources page showed only "0 of
420 read" and a scan said nothing. Now the Sources page's built-in boards
section says why at the top, one sentence counting each reason with what
to change ("3 hire outside your countries (Philippines): add a country
under Search, or read every country"; "they are off. To read them, tick
Read the built-in boards"). A scan logs the same sentence, and `jobdork
sources` prints it under its directory line (`directory.none_read_why`).

The guide's Sources page says so. tests/test_sources_why_none.py covers
nothing said when a board is read, boards off, each reason counted, and
the Sources page's report.
