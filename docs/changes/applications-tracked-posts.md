## Fixed — 2026-11-12 — Applications keep their advert and what you sent, and Delete deletes the resume chosen

**A USAJOBS link came in with no advert.** Adding a job you applied to from
its USAJOBS link tracked it "without its advert": USAJOBS writes its job
data's type as `application/ld&#x2B;json`, which jobdork did not recognise,
and puts the duties and qualifications outside the short description. Both
are read now, on any site: one USAJOBS post went from nothing to 8,200
characters. A post already tracked without its advert gets it from **Fetch
missing adverts**, which no longer marks a job you applied to *skipped*
when its fuller advert misses one of your rules.

**A resume you sent read as cut off.** Some PDFs draw their bullets apart
from the text: every bullet's words came out without its bullet, and the
bullets piled up as empty lines at the end of each page. Such a PDF is now
read by its layout, so each bullet stays with its line. This also applies to
the resume you upload as your own.

**One upload box, and the contact on Add.** The Application tab and **Add a
job post you applied to** each had two upload boxes. Now there is one,
**Upload what you sent**, with a choice of **Resume** or **Cover letter**.
Add also takes the **Name**, **Email** and **Link** of who you are in touch
with, saved with the post, and saving them never clears a next step saved
before. The Application tab's picture in the guide showed an empty pane; it
shows the tab again.

**Delete deleted your own resume.** On the Resume page, choosing a tailored
resume and pressing **Delete resume** deleted the resume you uploaded, not
the one chosen. The button now follows the card chosen and says which:
**Delete your resume** or **Delete this tailored resume**, which removes that
one with its PDF and Word copies. A tailored resume could not be deleted
before at all, and a cover letter only from the list at the bottom of the
page; a cover letter's tab now has **Delete this cover letter** wherever it
is shown. A file a second version of the same resume still uses is kept.
