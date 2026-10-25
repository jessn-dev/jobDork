# Privacy policy

Effective 23 October 2026. Applies to jobdork in every form: the desktop app
for macOS and Windows, the Docker image, and the Python package run from the
command line.

**In short:** jobdork runs on your own computer (or your own server) and keeps
what you give it there. Nobody who makes jobdork receives your resume, your
searches, your job posts or your keys. It has no accounts, no analytics, no
advertising and no tracking. It goes on the network to do what you set it up
to do, and the sections below list every place it goes.

---

## What jobdork keeps, and where

Everything stays in folders on the machine jobdork runs on:

| What | Where |
|---|---|
| Your settings (job titles, place, countries, pay, dealbreakers) | `config.yaml` |
| Job posts found, your statuses and notes, AI verdicts, run history, warnings and errors | `data/jobdork.db` |
| Copies of the database, made before anything is deleted | `data/backups/` |
| Your resume, as you uploaded it, and the projects and education you add | `data/` |
| Keys for Adzuna and USAJOBS, if you enter them in the app | `data/source-keys.env`, readable by your user account only |
| Cover letters and tailored resumes you ask for | `Documents/job-applications/` (in Docker, `data/documents/`) |
| What a scheduled scan printed | `logs/scheduled-scan.log` |

The desktop app keeps these in its own folder: `~/Library/Application
Support/jobdork` on macOS, `%LOCALAPPDATA%\jobdork` on Windows,
`~/.local/share/jobdork` on Linux. **Settings → Where your files are**
card shows the exact paths and opens them.

**Keys for AI providers** (Claude, Gemini, ChatGPT, Groq) are held in memory only.
They are never written to disk, and are forgotten when jobdork stops, or a
minute after the last Dashboard window closes.

**Deleting it.** The Dashboard's **Start over** deletes your settings, job
posts, resume, documents and keys, after showing you exactly what goes.
Uninstalling the desktop app removes the program and leaves your data folder,
so a reinstall finds it; delete that folder yourself to remove everything.

---

## What goes over the network, and when

jobdork makes no request that you have not set up, except the version check
described below, which you can turn off.

### When you scan for jobs

- **Job boards and employers' careers sites** (Workable, Himalayas, Kalibrr,
  the Bundesagentur für Arbeit, Arbeitnow, and employers' own boards on
  Greenhouse, Lever, Workday, Oracle, SuccessFactors and others). They receive
  your **job titles**, and the **place and country** you search in, as search
  terms, the way a search on their own site would. Requests name jobdork and
  its project page in their User-Agent. They do not receive your resume or
  anything else about you.
- **Adzuna and USAJOBS**, only if you entered keys for them. They receive the
  same search terms and your key. USAJOBS requires the email address you
  registered with it to be sent with each request.
- **Checking whether a job is still open**, and **fetching a missing advert**,
  ask the job's own page or board.
- **Discover** (adding an employer's board) reads the employer website you
  type in.
- **Search Google Jobs**, under the job posts list, is a link: clicking it
  opens Google in your browser with a job title of yours and your location
  (or "remote") as the search. jobdork itself sends Google nothing, and
  nothing goes until you click.

A scan runs when you start one, when a change to your search needs one, or
at the times you choose under **Settings → Schedule a run**.

### When you turn on an AI reader

If you choose an AI provider on the AI page, the job adverts it reads and
your resume (with the projects and education you added) are sent to that
provider to be judged, reviewed or written from:

- **Ollama** runs on a computer you choose, usually your own; nothing leaves
  your network unless you point it elsewhere.
- **Anthropic (Claude), Google (Gemini), OpenAI (ChatGPT) or Groq** receive
  the text of each request, under their own terms and privacy policies:
  [Anthropic](https://www.anthropic.com/legal/privacy),
  [Google](https://policies.google.com/privacy),
  [OpenAI](https://openai.com/policies/privacy-policy),
  [Groq](https://groq.com/privacy-policy). Groq runs open models (Llama,
  GPT-OSS, Qwen and others) on its own servers; by its
  [data page](https://console.groq.com/docs/your-data) it keeps no requests
  by default, apart from logs of up to 30 days for abuse and reliability,
  which Zero Data Retention in its settings turns off.
- **Drafts written with the `claude` command** (cover letters, CVs) go
  through your own Claude Code installation, under your account with
  Anthropic.

Nothing is sent to an AI provider unless you chose one.

### When you send feedback

The **Feedback** page sends a report only when you press **Send**, and shows
you first exactly what will be sent: what you wrote, jobdork's version and
your operating system, and, only if you tick it, the last week's warnings and
errors, with keys, tokens, email addresses, IP addresses and your home folder
removed. Never your resume, job posts or settings.

It goes to a small service run by jobdork's maintainers on Cloudflare
Workers, which:

- opens a **public GitHub issue** in this repository with your report's text,
  so write nothing in it you would not post publicly;
- emails the maintainers the report, your screenshots (if you added any) and
  your email address (if you gave one, so they can reply). Screenshots and
  your address are **not** put on the public issue;
- keeps your IP address for about an hour, only to limit each address to five
  reports an hour.

You can instead open the report as a GitHub issue in your browser yourself,
or save it as a file. `JOBDORK_FEEDBACK_URL=off` turns sending off entirely.
Cloudflare, GitHub and Resend (which delivers the email) handle the report
under their own privacy policies:
[Cloudflare](https://www.cloudflare.com/privacypolicy/),
[GitHub](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement),
[Resend](https://resend.com/legal/privacy-policy).

### The version check

When the Dashboard opens, jobdork asks GitHub, at most once a day, for the
number of the latest jobdork release, so it can tell you when a newer one is
out. The request goes to `api.github.com` and carries nothing about you
beyond what any connection carries (your IP address, and a User-Agent naming
jobdork and its version). The answer is kept in `version-check.json` beside
your database. To turn it off, press **Turn off the daily check** under
**Settings → Updates** (it writes `update_check: false` to your settings), or
set `JOBDORK_UPDATE_CHECK=off`. **Check now** asks once, whenever you press
it.

**Updating the desktop app.** When a newer version is out, **Update** under
**Settings → Updates** downloads that release's installer for your computer
from this project's GitHub releases into your Downloads folder, checks it
against the release's published SHA-256 checksums (deleting it if they do
not match), and opens it. Nothing is downloaded until you press it.
The Windows installer shows this before installing. See
[GitHub's privacy statement](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement).

### Email digests

If you set up `jobdork scan --email` or `jobdork digest` with your own
[Resend](https://resend.com) key, the list of new job posts is emailed to the
address you give, through Resend, under your Resend account.

---

## Notifications

When a scan finds new job posts (one you start, or a scheduled one), when a
scan fails, and when a newer jobdork is out, jobdork shows your computer's
own notification, with a bell: Notification Center on macOS, a toast on
Windows, `notify-send` on Linux. They are made on your computer and go
nowhere else; macOS asks once whether to allow them. **Settings →
Notifications** turns them, or their sound, off; so does
`JOBDORK_NOTIFY=off`.

## What jobdork does not do

- No analytics, crash reporting or usage statistics are sent anywhere. The
  Dashboard's metrics are computed from your own database and stay there.
- No accounts, sign-ins or cloud storage.
- The Dashboard listens on your own computer only (`127.0.0.1`), and every
  request to it needs a token made fresh each time it starts. In Docker it can
  be opened from other machines only if you allow them by name.
- It changes nothing on your system beyond its own folders, except, if you
  turn on **Schedule a run**, one scheduled task (a LaunchAgent on macOS, a
  Task Scheduler task on Windows, a crontab line on Linux), which turning it
  off removes.

---

## Changes and contact

Changes to this policy are recorded in the repository's history and in
[docs/CHANGELOG.md](docs/CHANGELOG.md). Questions: open an issue at
https://github.com/jessn-dev/jobDork/issues, or use the app's Feedback page.
