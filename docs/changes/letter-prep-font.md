## Changed — 2026-11-10 — Cover letter rules, fuller interview prep, and the resume's font

Asked for on 2026-11-09 from the same pack of job-search prompts as the new
writing tools.

**Cover letters** (by the AI page model and through Claude Code) are written
to a shape: four short paragraphs, 250 to 300 words: an opening on something
specific in the advert, never "I am excited to apply"; one achievement from
the resume that answers the advert's first requirement; why this job and
not any job; one sentence asking for a conversation. Every sentence says
something the resume does not already say, and a requirement the person
lacks is never mentioned. Two new checks say **Read this**: **length**
(220 to 330 words passes) and **stock phrases** ("passionate", "team
player", "excited about this opportunity", "perfect fit" and others; the
recruiter message gets this one too) (`gates.letter_length`,
`gates.stock_phrases`).

**Interview prep** asks for fifteen likely questions, as interviews are run
today, in three groups (behavioral, about the work, what would you do), each
saying what it really finds out, the ones nearly every interview asks marked
**high priority**, and at least two on a failure or a weakness (a new check,
**a failure or weakness**, says **Read this** when fewer). It adds **Answers
to build (STAR)**: outlines from the resume for the three hardest behavioral
questions, checked by the hallucination check with the rest. An answer from
an older model with no groups reads as questions about the work.

**The resume's font**: the Resume page's **The resumes jobdork writes are
set in** chooses a sans serif (Arial; Helvetica in the PDF) or a serif
(Georgia; Times in the PDF) for every tailored resume, PDF and Word
(`resume.font`). Left to jobdork, it is a serif when every industry chosen
under Search is one where serif is usual (law, finance, academia,
government), else a sans serif (`config.resume_font`). A serif PDF is
measured with Helvetica's widths, so its lines wrap a little early and never
run past the margin. The PDF's sizes were already the usual advice (11 point
body, 18 point name).

The guide's job window and Resume pages, `docs/CONFIG.md` and the interview
prep picture (with the demo's prep in the new layout) say so.
tests/test_letter_prep_font.py covers the letter checks and prompt, the
grouped questions, priority, the failure check and the stories, and the font
chosen, by industry, saved, and in Word and the PDF. The Resume page's
picture is retaken once the writing tools' change, which retakes it too, is
in.
