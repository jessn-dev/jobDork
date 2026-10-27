---
template: home.html
title: jobdork · find jobs on employers' own sites, privately
description: >-
  jobdork is a free, open-source job search app for your own computer. It
  reads 420 employers' hiring systems and job boards, screens posts with your
  rules, and ranks them against your resume. No account.
hide:
  - navigation
  - toc
---

## What it does for you

<div class="grid cards" markdown>

-   :material-office-building-marker:{ .lg } **Reads employers' own boards**

    ---

    420 boards ship built in, on Workday, Oracle, Greenhouse, Lever, Ashby
    and more, beside keyword sources that need no account. Add any other
    employer from its careers page.

-   :material-filter-check:{ .lg } **Your rules, with reasons**

    ---

    Job titles, place, pay and dealbreakers decide what you see. Every post
    it drops is counted, with the reason. No paid listings, no hidden
    ranking.

-   :material-file-account:{ .lg } **Ranked against your resume**

    ---

    A **Match** score for title, place and pay, and a **Fit** score for the
    skills an advert asks for that you have and lack. Worked out on your
    computer. [Scores explained](scores.md)

-   :material-robot-outline:{ .lg } **AI that shows its work**

    ---

    Optional. Ollama on your own computer, or Claude, Gemini, ChatGPT or
    Groq with your key. It judges posts and drafts cover letters; a second
    model checks every claim against your resume and the advert. It never
    applies for you. [The AI page](ai.md)

-   :material-ghost-off-outline:{ .lg } **Fewer repeats and ghost jobs**

    ---

    Copies of one job show as one post. Posts are aged from the employer's
    own dates, and listings over 90 days old are dropped.

-   :material-bell-ring-outline:{ .lg } **Runs while you're away**

    ---

    A daily scan on your computer's own scheduler, with a notification when
    it finds new posts. [Settings](settings.md)

</div>

## For every kind of job, not only tech

The built-in boards span 27 industries, from banking, healthcare and retail
to energy, education, logistics and manufacturing. Federal jobs come in
through USAJOBS with a free key. The demo in this guide is a nurse in
Chicago looking for a nurse manager role.

Outside the US, a place list of 70,026 places in 245 countries understands
where you are, and distances come in miles or kilometres. Fewer employers
are reached outside North America; the
[region-by-region numbers](https://github.com/jessn-dev/jobDork/blob/main/docs/REGIONS.md)
say how many.

## Three steps

1. **Install it and answer setup's questions**, about five minutes: your
   resume, an AI if you want one, the job titles you want, where you are and
   your pay. [Getting started](getting-started.md)
2. **Run a scan.** The first posts arrive in about a minute.
   [The Dashboard](dashboard.md)
3. **Read the best first and mark what you did:** interested, applied,
   interviewing. The next scan shows only what is new.
   [Job posts](job-posts.md)

## How it compares

| | A job board | jobdork |
|---|---|---|
| **Where jobs come from** | Its own listings, and copies of other sites' | Employers' own hiring systems and careers sites, and keyword searches |
| **What decides what you see** | The site's ranking, often paid listings first | Your rules; every dropped post counted and named |
| **Your resume and searches** | On their servers, with an account | On your computer, with no account |
| **Cost** | Free, paid for with your attention and data | Free and open source; a hosted AI's own fees if you pick one |

## Questions

**Is it free?**
Yes. jobdork is open source under the GNU GPL v3. If you choose a hosted AI
such as Claude or ChatGPT, that provider charges for its use; Ollama on your
own computer costs nothing.

**Does it apply for jobs for me?**
No. It finds and ranks posts and drafts letters for you to read. You apply
on the employer's site.

**Does it search LinkedIn or Indeed?**
No: those sites refuse automated readers, and jobdork does not work around
them. A **Search Google Jobs** link opens your search in Google's job
results instead.

**Where does my data go?**
Your resume, searches and job posts stay in a folder on your computer. The
[privacy policy](https://github.com/jessn-dev/jobDork/blob/main/PRIVACY.md)
lists every address jobdork contacts and why.

**Why does my computer warn me when I open it?**
The installers are not code-signed, so macOS and Windows warn once.
Each installer carries a build attestation instead, so you can check it was
built by this project's own workflow. On a Mac, installing with
[one command in Terminal](getting-started.md#install-it) checks it for you
and skips the warning.
[How to open it and check it](https://github.com/jessn-dev/jobDork/blob/main/docs/run/desktop.md#the-first-open-warning)

## Get started

<div class="jd-cta" markdown>

[Download jobdork](https://github.com/jessn-dev/jobDork/releases/latest){ .md-button .md-button--primary }
[Read the guide](overview.md){ .md-button }
[Star it on GitHub](https://github.com/jessn-dev/jobDork){ .md-button }

</div>

New versions: on GitHub, choose **Watch → Custom → Releases**, or follow the
[releases feed](https://github.com/jessn-dev/jobDork/releases.atom). The app
also tells you once a day when one is out.
