## Changed — 2026-11-11 — The writing tools read the resume you sent, one list of stock phrases, and the docs caught up

Follow-ups left until the one Add a job post form, the writing tools and
the letter rules were all merged, to keep their pull requests apart.

- **A job post's writing tools read the resume you sent** for it, when you
  uploaded one (the tailoring report, interview story, thank-you email,
  offer and outreach message), as its interview prep and recruiter message
  already did; the tools with no job post read the resume set now
  (`prep.run`, `writer._resume_text(cfg, store, uid)`).
- **One list of stock phrases** (`gates.STOCK`): the cover letter's and
  recruiter message's check and the writing tools' were two lists that
  differed. Each now refuses every phrase either refused.
- **Docs**: the README names the writing tools, interview prep's STAR
  outlines, the resume's font, the mended verdicts and the documents you
  sent; ARCHITECTURE.md the `prep` module, the checker reading the whole
  resume and the rewrite of a flagged verdict; PRIVACY.md where the
  documents you sent are kept. The changelog's backlog drops the one form
  and the writing tools, both done. The Resume page's picture is retaken
  with the font choice.
