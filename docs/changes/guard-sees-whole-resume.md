## Fixed — 2026-11-10 — The hallucination check reads the whole resume, and the work history

The checker read each source only up to 16,000 characters, while the model
that wrote a verdict read up to 20,000 of the resume. jobdork's measured
work history ("10 years 10 months in all") was added after the resume, so
on a long resume it was always cut off, with the resume's end. The checker
then called claims taken from them unsupported, and the Dashboard's
hallucination rate rose with every long resume. On a real 16,718-character
resume, four of the nine claims `qwen3.8:27b` flagged in a day were the work
history.

Now every source the checker reads goes as far as what the writer read,
plus room for the work history (`guard.MAX_SOURCE`, from `llm.MAX_RESUME`
and `llm.MAX_ADVERT`), and the work history comes first in the resume source
(`judging.guard_sources`), so no cut can take it. tests/test_guard.py checks
both on a resume longer than the old limit.
