## Added — 2026-11-10 — Eight writing and preparing tools

Asked for on 2026-11-09 from a pack of job-search prompts: the ideas and the
shape of each answer come from there, the prompts are jobdork's own
(`ai/prep.py`). By the model on the AI page, each from your resume, the job
post and what you type into its form, and nothing else.

In a job post's **AI tools** tab, under **Prepare**:

- **Tailoring report**: what the advert stresses most; each requirement, ✓
  with the line of your resume that shows it or ✗; how to handle one you
  lack; what a recruiter may question and how to prepare; what a summary
  should lead with.
- **Interview story (STAR)**: what happened, in your words, as situation,
  task, action and result, and said aloud in 60 to 90 seconds, with likely
  follow-up questions and anything that could sound like blame.
- **Thank-you email**: 150 to 200 words for the day after, about what you
  actually talked about, answering a concern if one was raised.
- **Offer negotiation**: what to say to counter, the reasons, replies to the
  usual pushbacks, what to ask for when the salary cannot move, and your
  minimum. Never an ultimatum.
- **Outreach message**: a LinkedIn connection request and InMail to someone
  at the employer, with a small ask and an easy way to say no, and a
  follow-up.

On the Resume page, under **For your search**: a **LinkedIn headline and
About** to copy (jobdork never logs into LinkedIn), **Changing field**
(what carries over, how to say it, the real gaps), and a **30-day search
plan** sized to the hours you have.

Every answer is checked by the hallucination check against the resume, the
advert and your own notes (the plan is advice, not claims, so it is not),
recorded for the Dashboard, and kept: a post's in its folder, the others
beside the resume. A script checks what it can and lists it as "Read this":
a requirement marked as yours with no line of your resume behind it is
turned to ✗, a skill not on your resume is left out of LinkedIn's list, a
story whose action says "we" or runs over 90 seconds, a message over
LinkedIn's limit or mentioning a job in a first message, a plan over your
hours, and stock phrases ("passionate", "team player", "pick your brain").
What you type is fenced as the advert is, so a pasted note cannot talk to
the model. `POST /api/writing` runs one, `GET /api/writing[?uid=]` lists
them with their forms. With a coding agent as the only reader, they say
what to ask it, as the other AI buttons do.

The guide's job window and Resume pages describe each one; their pictures
are retaken. tests/test_prep.py covers every tool with a stand-in model:
saved, recorded, guarded, each script check, the forms cut to their fields,
the API's refusals and the fence.
