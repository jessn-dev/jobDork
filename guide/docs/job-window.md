# The job post window

Click a job title, or **Open**, to see one post in full. Opening a new post
marks it *viewed*.

![A job post's window](images/job-window.png)

## The top

- **Match**, **Fit** and **AI** scores ([explained](scores.md)), and the
  status.
- <span id="rate-the-ai"></span>**Thumbs up and down** beside the AI score:
  was the AI verdict useful? Your answers are counted on the
  [Dashboard](dashboard.md#the-numbers); they are how you can tell whether
  a model is worth keeping.
- **Open posting** opens the employer's page in your browser, to apply.
  **Close** closes the window.
- The employer, place, arrangement, source, and how long the stored advert
  is. **Also posted at** lists the other places the same job was found,
  and whether each is still up.
- **The status buttons** ([what each means](statuses.md#statuses)). The
  coloured one is the current status.

## Advert

The whole job advert, with:

- **Yellow tags**: what to know before you apply
  ([tags](statuses.md#yellow-tags)).
- **On the employer's own board?** For a post from Adzuna, Himalayas,
  Arbeitnow or Kalibrr: what the last scan found on the employer's own board
  (on it, not on it, read only partly, or not read). **Check the employer's
  own board** asks that board now, for this job's title, and says whether it
  is there, with a link if it is. Useful when the scan could not tell, or
  before you apply.
- **Certifications and licenses this post asks for**: each line of the
  advert that asks for one, marked *required* or *preferred*, and a tick for
  the ones you have (from your resume, or your list on
  [Search](search.md#your-certifications-and-licenses)).
- **Paste the full advert** (or **Replace the advert**): some sources send
  only a summary. Open the posting, copy the whole description, paste it and
  **Save and re-screen**: the rules and scores read it at once.
- **Check if still open**: asks the posting now
  ([listing tags](statuses.md#is-it-still-open)).

## AI tools

Everything the AI does for one post is on the **AI tools** tab. Orange
buttons use the AI model from the [AI page](ai.md): free with a local model,
paid by the word with Anthropic, Gemini, OpenAI or Groq.

![The AI tools tab](images/job-window-ai-tools.png)

!!! note "You are the author; the AI is an editor"
    Take only what is true, in your own words. Read the result aloud, and
    be ready to speak to every line in an interview. Some employers set
    rules on using AI in an application: check theirs. With a hosted model,
    your email, phone number and profile links are removed before anything
    is sent.

### The four main buttons

| Button | What you get |
|---|---|
| **Ask AI** / **Ask AI again** | The AI's verdict on this post: a [score](scores.md#ai-the-models-opinion), a summary, and the reasons for and against |
| **Write cover letter (AI)** | A cover letter from your resume and this advert. It opens in a new **Cover letter** tab, and is listed on the [Resume](resume.md#cover-letters) page |
| **Write tailored resume (AI)** | Your resume rewritten for this advert, as a PDF and a Word file named `FirstName_LastName_JobTitle_Resume`, in a plain layout that applicant tracking systems read well ([the layout](#the-tailored-resume)). It opens in a **Tailored resume** tab. Your contact line is copied from your resume, never written by the AI, and any employer, school, skill, certification or award your resume does not name is left out and listed |
| **Review resume for this post** | What to change in your resume for this post, each point quoting the line it is about, and what the advert asks for that your resume does not show. Opens in a **Resume review** tab |

### Editing help

| Button | What you get |
|---|---|
| **Tailor my resume** | Suggested edits, not a new resume: rewordings of your lines (tick the ones you want), which lines to move up, and a skills line from skills you have that the advert asks for. An edit that adds a number you never wrote is left unticked, in red. **Download tailored resume** gives your resume with the ticked edits |
| **ATS keywords** | The ten words an applicant tracking system would look for in this advert, each marked found or missing in your resume |
| **Skills to highlight** | The advert's three most important skills, the three things you did that best show them, and strong verbs for the role |
| **Recruiter feedback** | The AI reads your resume as this post's recruiter would: strengths and gaps |

Under **Revise a bullet or paragraph, or get feedback on a cover letter**,
paste text of your own:

- **Revise: 5 versions**: five rewordings of one bullet or paragraph, fitted
  to this post, with no new facts.
- **Recruiter feedback on this letter**: a recruiter's view of a whole
  cover letter.

Results stay under the tab, each with the model that wrote it and when; a revision has **Copy** beside each version.

### Drafts through Claude Code

**Draft: Screen, CV, Cover letter** use the `claude` command-line tool, a
separate program from the AI page (installed with
[Claude Code](https://claude.com/claude-code)). Without it these buttons are
greyed out and the rest still works.

- **Screen**: is this worth applying to? A short, cheap read of the advert
  that flags travel, title mismatches and pay problems before you spend
  time on a CV.
- **CV** and **Cover letter**: drafts saved in your documents folder.

### Every result is checked

Before you see anything the AI wrote, jobdork checks it:

- **The hallucination check**: the text is split into single facts and each
  is looked up in your resume and the advert. A fact found in neither is
  flagged: struck out in a verdict, listed with a letter. *"Ten years of
  Java"* where your resume says ten years in total does not reach an
  employer unread. [More](ai.md#the-hallucination-check)
- **Signs of AI writing**: stock phrases ("spearheaded", "leveraged"),
  long dashes, "not X but Y". Each one left is named so you can fix it.
- **Figures**: any number or "large team" in a draft that is not in your
  resume.

In a document's tab, each check shows **ok** or **READ**: READ means look at
it before you send anything. The thumbs on a document say whether it helped.
**Open PDF** and **Download PDF** are on resumes and CVs, and **Download
Word** gives the same resume as a `.docx` to edit in Word, Pages or Google
Docs before you send it.

### The tailored resume

Laid out like Indeed's free resume template, one column:

- your name, then *Phone | Email | City, State*, then your website or
  LinkedIn, centred;
- **Professional summary**, **Experience**, **Skills**, **Education**,
  **Certifications**, then **Awards & volunteer work**, each left out when
  your resume has nothing for it. A student's Education comes right after
  the summary, and projects go where your career stage puts them;
- each job as its title with the dates at the right margin, then
  *Company, City*, then its bullets; skills separated by `|`.

Its length follows [Indeed's advice](https://www.indeed.com/career-advice/resumes-cover-letters/how-long-should-a-resume-be):
one page for up to ten years of experience, two after that, and three only
past 25 years or for academic and medical jobs. Jobs that ended more than
15 years ago are left out (unless it is the only one), the newest job keeps
up to seven bullets and older ones fewer, and when it still runs over, an
older job's last bullets go first. The **page count** check says how many
pages it fills and lists everything left out to fit, so you can put back
what matters by hand in the Word file. Arial at 11 points, 0.7 inch margins,
US Letter.
