## Added — 2026-11-05 — A master resume, told apart from the one you send

jobdork now knows the difference between a **master resume** (your private
archive of every job, part-time and freelance work, volunteering, projects,
presentations, awards, certifications and skills, never sent as it is) and
a resume you send, and advises the first:

- **Setup's resume step** says to upload your master resume if you keep
  one, and the one you send otherwise; the welcome page's list of steps says
  the same.
- **jobdork guesses which it is** when you upload (`search/master.py`):
  "master" in the file's name settles it ("MasterResumeJaneDoe.pdf" too);
  otherwise a long text (1,700 words or more) counts most, and three pages or
  more, ten or more dated entries and archive sections (volunteer work,
  awards, presentations, publications, freelance or part-time work, hard
  and soft skills) add to it. Tried on eight real
  resumes: the 1,849-word master was taken for one, and none of seven sent
  resumes of 290 to 1,566 words over two to five pages was. The guess is
  written to the config (`resume.kind`), as it is the only time the file's
  own name is known.
- **This resume is** on the Resume page, and in setup after the upload, says
  which jobdork took it for and why, and changes it: *My master resume* or
  *A resume I send*.
- **With a master resume:** *How a tracking system reads it* no longer marks
  it down for being over two pages; a tailored resume's prompt says it is
  choosing from an archive (`writer.MASTER_NOTE`); the card says *Your
  master resume*.
- **A resume longer than the AI reads** (20,000 characters) gets a note:
  what comes after is not seen, and a claim about it is marked unsupported.
- **`jobdork setup`** in a terminal gives the same advice, and says which
  it took the resume for.

The guide's Resume page explains a master resume; Getting started, the
overview, the AI and job-window pages, the glossary, README.md, the run and
CLI guides, CONFIG.md and ARCHITECTURE.md name it, and DECISIONS.md says
why. AI-MODELS.md adds the reader and checker pairs measured on a master
resume: `gpt-oss:20b` as checker as well as reader raised the rate to 18%. Tests cover the guess (the file name, a long archive, a
long CV that is sent, a designed resume with little text, archive
sections), your choice winning over it, the length check, the setting, the
page's report, and the tailoring prompt with and without a master.
