# jobDork

<!-- Health -->
[![Build](https://github.com/jessn-dev/jobDork/actions/workflows/docker.yml/badge.svg?branch=main)](https://github.com/jessn-dev/jobDork/actions/workflows/docker.yml)
[![Coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fjessn-dev.github.io%2FjobDork%2Fbadges%2Fcoverage.json)](https://github.com/jessn-dev/jobDork/actions/workflows/guide.yml)
[![Known vulnerabilities](https://img.shields.io/endpoint?url=https%3A%2F%2Fjessn-dev.github.io%2FjobDork%2Fbadges%2Fvulnerabilities.json)](SECURITY.md)
<!-- Ecosystem -->
[![Latest release](https://img.shields.io/github/v/release/jessn-dev/jobDork)](https://github.com/jessn-dev/jobDork/releases/latest)
[![Docker image](https://img.shields.io/docker/v/jessengolab/jobdork?sort=semver&label=docker)](https://hub.docker.com/r/jessengolab/jobdork)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)
<!-- Community -->
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fastral-sh%2Fruff%2Fmain%2Fassets%2Fbadge%2Fv2.json)](https://github.com/astral-sh/ruff)
[![User guide](https://img.shields.io/badge/user%20guide-read%20it-blue.svg)](https://jessn-dev.github.io/jobDork/)

**jobdork finds job posts for you, on your own computer.** It reads
employers' own hiring systems and job boards, keeps only the posts that pass
the rules you set (job titles, place, pay, dealbreakers), ranks them against
your resume, and keeps track of what you did with each one. An AI model can
read the best ones against your resume and draft a cover letter or a tailored
resume; every claim it writes is checked against your resume and the advert.

It is not a job board and has no account: nobody posts to it, and your
resume and searches stay on your machine.

![Job posts in jobdork](guide/docs/images/job-posts.png)

**[User guide](https://jessn-dev.github.io/jobDork/)** (every page of the
app, with pictures) · **[Download](https://github.com/jessn-dev/jobDork/releases/latest)**
· **[Ways to run it](docs/run/README.md)** · **[Documentation](#documentation)**

---

## What it does

- **Reads where jobs are posted.** 420 employer boards ship built in (338 of
  them US employers, across 27 industries) on Workday, Oracle Recruiting
  Cloud, Eightfold, Taleo Business Edition, Greenhouse, Lever, Ashby,
  SmartRecruiters, Breezy and employers' own careers sites. Keyword sources
  need no account: Workable's search, Himalayas (remote work), Kalibrr
  (Philippines, Indonesia), Germany's employment agency and Arbeitnow.
  Adzuna and USAJOBS work with a free key of your own, and
  `jobdork discover` adds any other employer by reading the board off their
  careers page. [Where the jobs come from](docs/SOURCES.md)
- **Screens with your rules, and says why.** Every post dropped is counted
  with its reason. Only pay the employer states can hide a post: one with no
  pay is kept and marked, since most posts state none.
  [The rules](docs/CONFIG.md)
- **Cleans up the list.** Copies of one job are shown as one post; each post
  is aged from the board's own dates, with old ones ranked lower and
  ghost listings (over 90 days) dropped; an Adzuna post the employer's own
  board does not carry is flagged.
- **Ranks against your resume**, offline: **Match** (title, place, pay) and
  **Fit** (the advert's skills you have and lack). [Scores](https://jessn-dev.github.io/jobDork/scores/)
- **Uses an AI model only when you set one up.** Ollama on your own computer,
  or Claude, Gemini, ChatGPT or Groq with your key, which is held in memory
  only. It can judge posts, write a cover letter, review your resume and
  write a tailored resume as a PDF. A second model checks each output, claim
  by claim, against your resume and the advert, and anything unsupported is
  flagged. It never applies for you. [The AI page](https://jessn-dev.github.io/jobDork/ai/)
- **Keeps track.** Statuses from *new* to *offer*, notes, a check for posts
  that have closed, scans on a schedule, notifications, and an email digest.
- **Reaches past what it can read.** A **Search Google Jobs** link opens your
  search in Google's job results, and `jobdork dork` builds Google searches
  for sites that cannot be read automatically (LinkedIn, Indeed and others).
  [docs/DORK.md](docs/DORK.md)
- **Works outside the US.** A place list of 70,026 places in 245 countries,
  any country you name, and distances in miles or kilometres to match.
  What reaches each region is measured in [docs/REGIONS.md](docs/REGIONS.md).

---

## How it differs from a job board or an AI job app

| | A job board (Indeed, LinkedIn, ZipRecruiter…) | An AI job app (matching, auto-apply) | jobdork |
|---|---|---|---|
| **Where the jobs come from** | Its own listings, and copies of other sites' | Usually a job board's feed | Employers' own hiring systems and careers sites, and keyword searches, side by side |
| **What decides what you see** | The site's ranking, often paid listings first | A match score you cannot inspect | Rules you set, with every post dropped counted and named; an AI verdict sits beside the score and never hides a post |
| **Copies and ghost jobs** | One job reposted under several listings; old posts left up | Inherited from the feed | Copies grouped into one; posts aged from the employer's own dates; ghost listings dropped |
| **What the AI writes** | n/a | Applications, often sent for you | Drafts you read, each claim checked against your resume and the advert. It never applies for you |
| **Your resume and searches** | On their servers, with an account | Uploaded to their servers | On your machine. The AI can run locally; with a hosted model, your contact details are not sent |
| **Cost** | Free, paid for with your attention and data | Usually a subscription | Free and open source; a hosted model's own fees if you choose one |

**What it is not good at:** it takes some setting up; it reaches fewer
employers outside North America ([docs/REGIONS.md](docs/REGIONS.md)); it
does not work around sites that refuse automated readers; and an advert
that arrives cut short (Adzuna sends 500 characters) cannot be screened
fully. [Limits](#limits) has the list.

---

## Install

| | For | Guide |
|---|---|---|
| **Desktop app** | macOS (Apple Silicon) and Windows: an installer, its own window, scheduled scans, notifications, and updates from inside the app | [docs/run/desktop.md](docs/run/desktop.md) |
| **From source** | Any system with Python 3.10 or newer, Linux and Intel Macs included | [docs/run/source.md](docs/run/source.md) |
| **In the terminal** | Every command without the dashboard: scripts, cron jobs, servers with no screen | [docs/run/cli.md](docs/run/cli.md) |
| **Docker** | The published image on your computer, or always on a NAS | [docs/run/docker.md](docs/run/docker.md), [docs/run/nas.md](docs/run/nas.md) |

From source, in three lines:

```bash
git clone https://github.com/jessn-dev/jobDork.git && cd jobDork
python3 -m venv .venv && .venv/bin/pip install -e '.[pdf]'
.venv/bin/python -m jobdork serve      # opens setup in your browser
```

The first start opens setup, one question per screen: your resume, an AI
model (optional), the job titles to look for, where you are, pay and job
sources. It ends with a first scan. [Getting started](https://jessn-dev.github.io/jobDork/getting-started/)

Your settings live in `config.yaml`, which is not in the repository (it is
gitignored, with `.env`, `data/` and `out/`), so your search stays yours.

**The installers are not code-signed**, so macOS and Windows warn the first
time you open one; [the desktop guide](docs/run/desktop.md#the-first-open-warning)
says how to get past it and how to check a download instead. Every installer
carries a build attestation from this repository's release workflow, and the
app's **Update** button opens a new installer only after that attestation
verifies ([SECURITY.md](SECURITY.md#how-the-app-checks-an-update-before-opening-it)).

---

## Privacy and security

- **jobdork sends nothing to its makers.** It goes on the network only to
  do what you set up (read job sources, use the AI provider you chose, send
  feedback when you press Send) and, once a day unless you turn it off, to
  check for a newer release. Every destination: [PRIVACY.md](PRIVACY.md).
- **The dashboard is yours alone.** It listens on this computer only (in
  Docker, on the addresses you name and no others) and needs a token made
  fresh for each run; a job post's text and links are treated as hostile
  ([what a job post cannot do](SECURITY.md#what-a-job-post-cannot-do)).
- **Releases are checked before they are published:** tests, vulnerability
  and secret scans on every change, dependencies pinned by hash, the Docker
  image signed (cosign) and the installers attested, and each release
  approved by hand. [SECURITY.md](SECURITY.md)
- **Found a problem?** Report it privately:
  [SECURITY.md](SECURITY.md#reporting-a-problem).

---

## Limits

- **Employers on systems with no reader** (UKG, iCIMS, Jobvite, BambooHR,
  ADP and others) are reached only when their own careers site marks its
  posts up for search engines, or through `jobdork dork`.
  [docs/PLATFORMS.md](docs/PLATFORMS.md)
- **Sites with no public way in, or that refuse automated readers**
  (LinkedIn, Indeed, Glassdoor, SEEK) are not worked around: the Google Jobs
  link and `jobdork dork` cover them.
- **Salary:** only a minority of posts state pay, so a pay floor filters
  that minority and the rest are kept, marked *unconfirmed salary*.
- **Right to work:** a post that states its sponsorship position is flagged;
  most state nothing, so treat an unflagged post as unknown.
- **An empty answer from a board is not proof it is hiring nobody:** some
  answer the same way when throttling, and jobdork reports those as
  unknown.
- **Jobs never posted online** in a system it can read, common for small
  local employers, cannot be found.

---

## Documentation

| | |
|---|---|
| [User guide](https://jessn-dev.github.io/jobDork/) | Using the app, page by page, with pictures; source in [guide/](guide/README.md) |
| [docs/run/](docs/run/README.md) | The ways to run it: [desktop](docs/run/desktop.md), [from source](docs/run/source.md), [terminal](docs/run/cli.md), [Docker](docs/run/docker.md), [NAS or home server](docs/run/nas.md) |
| [docs/CONFIG.md](docs/CONFIG.md) | Every setting, what it accepts, and what happens when it is wrong |
| [docs/SOURCES.md](docs/SOURCES.md) | Where coverage comes from, the built-in boards, board tokens, the place list |
| [docs/PLATFORMS.md](docs/PLATFORMS.md) | Each source's endpoint, quirks, rate limits and verification status |
| [docs/REGIONS.md](docs/REGIONS.md) | What a scan reaches, region by region |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the pipeline fits together, and the AI reader and its checks |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Choices that shape jobdork, what was ruled out, and when to revisit |
| [docs/DORK.md](docs/DORK.md) | `jobdork dork`, the Google search builder |
| [docs/HISTORY.md](docs/HISTORY.md) | How jobdork got here |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Every change, and what is still outstanding |
| [SECURITY.md](SECURITY.md) | How releases are checked, signed and approved; verifying a download |
| [PRIVACY.md](PRIVACY.md) | What jobdork keeps, where, and every place it goes on the network |

**Why was a post dropped?** `jobdork list --flags`, then
[how a title is matched](docs/CONFIG.md#how-a-title-is-matched) and
[the salary rule](docs/CONFIG.md#the-rule).
**Why did a source return nothing?**
[Failure usually looks like success](docs/PLATFORMS.md#failure-usually-looks-like-success).

---

## Development

Contributions are welcome: [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
pip install -e '.[dev]'     # pytest, ruff, and sigstore for the update tests
pytest                      # the whole suite; none of it goes online
ruff check .                # lint
python tests/run_all.py     # the same tests, without pytest
```

`python packaging/build.py` builds the desktop installer for the machine it
runs on ([how](docs/run/desktop.md#building-the-installers-yourself)).
Dependencies are pinned with their hashes in `requirements.lock` (the Docker
image) and `requirements-desktop.lock` (the installers).

```
.
├── jobdork/
│   ├── cli.py             # every command
│   ├── core/              # config, setup, schedule, notifications, updates, telemetry
│   ├── db/                # SQLite store, migrations, grouping copies of a job
│   ├── fetch/             # one reader per source, robots.txt, the paced HTTP client
│   ├── search/            # scan, screening, built-in boards, discover, freshness, places, resume
│   ├── ai/                # the model, judging, the hallucination check, letters and reviews
│   ├── writing/           # drafts by Claude Code, tailored resumes, the checks every draft gets
│   ├── web/               # the dashboard server, its API, and the desktop window
│   ├── output/            # the static page and the email digest
│   ├── dork/              # the Google search builder
│   └── data/              # built-in boards, the place list, the dashboard page, humanizer rules
├── guide/                 # the user guide (MkDocs)
├── docs/                  # the documentation above
├── packaging/             # the desktop build: PyInstaller spec, icon, Windows installer
├── scripts/               # board list, place list, guide pictures, release notes, image check
├── tests/
├── Dockerfile, compose.yaml
└── .github/workflows/     # checks and releases (docker.yml, desktop.yml), the user guide, the weekly board re-check
```

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains each part.

---

## Credits

- **[humanizer](https://github.com/blader/humanizer)** by blader (MIT): the
  rules for spotting signs of AI writing, drawn from Wikipedia's "Signs of AI
  writing" guide. Its `SKILL.md` is copied into
  [`jobdork/data/humanizer/`](jobdork/data/humanizer/) with its licence;
  drafting models are given it, and `jobdork/writing/humanize.py` checks
  drafts for the patterns a script can find.
- **[HalluLens](https://github.com/facebookresearch/HalluLens)** (Bang et al.,
  [arXiv:2504.17550](https://arxiv.org/abs/2504.17550)): the method the
  hallucination check follows, splitting an output into single claims and
  checking each against its source. Only the method is used; none of its
  code, prompts or data (CC BY-NC) is included.
- Place names from [GeoNames](https://www.geonames.org/) (CC BY 4.0); icons
  from [Lucide](https://lucide.dev/) (ISC).

## License

[GNU General Public License v3.0 or later](LICENSE): you may use, change and
share jobdork, and anything you distribute that is built from it must be
shared under the same licence, with its source. The humanizer rules keep
their MIT licence ([jobdork/data/humanizer/LICENSE](jobdork/data/humanizer/LICENSE)).
