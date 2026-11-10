## Changed — 2026-11-10 — One "Add a job post" form, and the documents you sent

**Add a Job Post** (Sources) and **Track an application you sent** (My
applications) read a link the same way, in two forms. They are one form now,
on both pages: a link, **I already applied** with its day (ticked on My
applications), and the board token under **More options**. Behind it is one
call, `POST /api/post/add` (`api.add_post`); `/api/add`, `/api/add/text` and
`/api/application/track` still answer. `jobdork add --applied-on DAY` does
the same from the command line.

**Fixed:** a link to a page that names the job but carries no advert (marked
up for search engines with no description) was stored with an empty advert:
tracked, listed, and never scored, with nothing said. Now it is refused as
"names the job but carries no advert", and the form opens its fields filled
with what the link gave (title, employer, place), asking for the advert.
A refusal like that answers JSON with what was found (`found`).

**The resume and cover letter you sent** can be uploaded, in the form when
you tick **I already applied**, or later in the post's **Application** tab
under **Documents sent** (PDF, Word, Markdown or text). Each is kept in the
post's folder as `sent-resume.*` or `sent-cover-letter.*`, read back to be
sure it reads, and recorded as that post's document (`sent_resume`,
`sent_letter`; one of each, a new upload replacing the file and keeping the
record). Documents sent can choose it, the post's window shows its text, and
the post's interview prep, recruiter message, AI tools and ATS match read
the resume you sent instead of the one set now.

The guide's My applications and Sources pages say so, with their pictures
retaken. tests/test_applications.py, test_link.py and test_serve.py cover
the refused empty advert and what it found, the one form adding and
tracking, the uploads (format, kind, post id, replacing), the tools reading
the sent resume, `--applied-on`, and the routes.
