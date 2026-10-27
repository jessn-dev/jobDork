# Decisions

Choices that shape jobdork and are not obvious from the code, each with why
it was made, what was ruled out, and **what would make it worth revisiting**.
A decision here is not permanent; it is the best answer to the requirements
as they stood, written down so a change of requirements starts from the
reasoning rather than from scratch.

Newest first.

---

## What 1.0 promises, and when it comes — 2026-10-27

**Decided.** jobdork stays at 0.x until its public launch, and 1.0.0 is
that launch. From 1.0.0 on, the version says what an update can do to you
([Semantic Versioning](https://semver.org)):

| Update | Example | What it may do |
|---|---|---|
| Patch | 1.0.0 → 1.0.1 | Fix what was wrong. Nothing else changes. |
| Minor | 1.0 → 1.1 | Add. Everything below keeps working as it did. |
| Major | 1.x → 2.0 | Break something below, only when it has to: said in the release notes, with how to move over, and the old way still read for at least one minor release before it, with a warning, where it can be. |

**What is kept working (the promise covers these):**

- **Your settings:** every key in `config.yaml` that docs/CONFIG.md
  describes, with the meaning it describes. A new key always has a default,
  so an old file still loads. A key that is going away is still read, with a
  warning, until the next major version.
- **Your data:** the database and the data folder (`data/`: the database,
  backups, your resume) are carried forward by every update; jobdork
  migrates the database itself. Going back to an
  older version is not promised: an older jobdork refuses a newer database
  rather than damage it.
- **Your keys:** keys kept in the computer's keychain stay where they are
  (the keychain entries named `jobdork`), and the choice to keep them is
  kept.
- **The commands:** `jobdork` and its subcommands and flags as `jobdork
  --help` lists them, and their exit codes (0 done, 1 failed, 2 used wrong,
  130 stopped with Ctrl-C).
- **The environment variables** docs/CONFIG.md lists (`JOBDORK_HOME`,
  `JOBDORK_CONFIG` and the others).
- **Running it:** the desktop installers' names on the release page, the
  Docker image's name and its `/app/data` folder and port, and the in-app
  Update from any 1.x to a later 1.x.
- **What it will not do:** what PRIVACY.md says jobdork never sends or
  stores. Loosening any of it is a major version, never a minor one, and
  most of it is not for changing at all.

**What is not promised**, and may change in any release: how the pages
look and where things sit on them; the dashboard's own web addresses
(`/api/...`, for the page itself, not for scripts); scores, fit and the AI's
wording; the job sources and built-in boards (sites change, ban and close);
the database's tables (use the commands or the page, not SQL); log text;
anything in a file or setting the docs call internal or experimental.

**When 1.0.** At launch, after: 0.15.2 out, and Update from 0.15.1 checked
on a Mac and on Windows (the way every later fix reaches people); the
security work from the 2026-10-27 review (hash-checked installs in CI, DNS
rebinding, invisible characters in adverts, dependency review); three to
five people who do not program installing and using it, and what they hit
fixed in 0.16.x; jobdork in WinGet, so Windows users can `winget install`
it. Linux installers and code signing are not conditions: 1.0
can name the systems it ships for, and add one in a minor release.

**Why.** Until now 0.x has meant "still changing", and minor versions were
features and patches fixes, with no promise about what a feature may break.
People launching from a list or a post will install it, set it up and leave
it running for months; they need to know an update will not lose their
settings, posts or keys. The list is what someone would have built on:
their settings file, their data, their scripts calling the commands, their
Docker setup. The pages are left out on purpose: they will keep improving,
and promising they never move would stop that.

**Ruled out.** 1.0 at the next release (0.15.2 or 0.16.0): its first users
would find what was missed, and each fix that had to change something
listed above would cost a 2.0. Staying at 0.x after launch: it tells
people nothing an update may do, and reads as "not ready".

**Revisit when** the list above blocks a change that most users want (then
it is a 2.0, planned, not a reason to drop the promise), or something not
on the list turns out to be what people build on (then it joins the list in
a minor release).

## Your own projects are always in a tailored resume — 2026-10-23

**Decided.** Every project added on the Resume page goes into a tailored
resume, at every career stage, the most relevant to the job first (at most
three or four). For someone experienced they get a section after the jobs,
holding those alone; the resume's other projects still belong in the jobs
they were done in. A project the resume only names or links to is described
from what the person wrote. Fit scores count a project's skills, and saving
one re-scores the job posts.

**Why.** The user asked: people add a project to be seen, and many resumes
list projects as bare links. The earlier rule (no projects section for the
experienced, 2026-09) dropped exactly the work they had written up. The
risk it guarded against, padding, is smaller for projects a person chose and
described than for whatever the model found in the resume.

**Revisit when** tailored resumes for experienced people read as padded, or
someone keeps many projects and wants to pick per job.

---

## A desktop app: a pywebview window, unsigned at first — 2026-10-21

**Decided.** jobdork ships as an installable app for **macOS (Apple
Silicon) and Windows** first: the existing dashboard in a native window
(pywebview), packed with PyInstaller, built in CI and attached to the
GitHub Release on a `v*` tag after approval in the `release` environment,
like the Docker image. Data lives in the platform's per-user app folder,
not in Documents. The first builds are **unsigned**: macOS says the
developer is unidentified and Windows SmartScreen warns once; the install
notes say how to get past that. No automatic updates at first: the app
says when a newer release exists.

**Why.** People who are not technical should not need Python, a terminal
or Docker, and the audience is every industry, not developers. A window
rather than the browser makes it feel like an app and keeps the token out
of browser history. The per-user folder because Documents is often synced
by iCloud or OneDrive, which corrupts a live SQLite database. Unsigned
because signing costs money every year (Apple's developer programme, a
Windows certificate) before anyone has asked for the app.

**Ruled out.** A launcher that opens the default browser with a tray icon
(simpler, but feels like a website and still needs packaging); Electron or
Tauri (a second front end to keep, for the same page); a Linux build in the
first release (the window needs WebKitGTK on the user's system; Docker and
`pip install` already serve Linux users); an Intel macOS build.

**Revisit when** users report the unsigned warnings stop them installing
(sign macOS first, then notarise in CI); Linux users ask for
an app; or updates need to reach people without them downloading again.

**2026-10-24:** free Windows signing from SignPath Foundation was applied
for and not granted. The installers stay unsigned; a certificate
authority's certificate is the next option when the warnings are reported
to stop people.

---

## First-run onboarding: a resume-first wizard, and AI does not block scanning — 2026-10-02

**Decided.** A new install opens a guided wizard, one step per screen,
saved as each step is finished so it can be left and resumed:

1. **Resume** (required), showing what was read so a bad upload is caught.
2. **AI**: Ollama or a provider key, with Save and test. **Skippable**:
   jobdork is built around a model (judging, letters, tailored resumes,
   suggestions), but a scan does not need one, so a missing model shows an
   "AI not set up" state rather than a locked Scan button.
3. **What you are looking for**: with a model, it reads the resume and
   suggests titles, titles to leave out, an industry and dealbreakers, which
   you tick; without one, you type them.
4. **Where**: the country, region and city picker, radius, work arrangement
   and the countries you would work in.
5. **Pay**, optional.
6. **What will be searched**, in plain words, with optional fields for
   keyed sources.
7. **First scan**: a quick scan (keyword sources and the built-in boards for
   your industry) whose results show within minutes, then the full scan in
   the background; the page says the background scan is running and the
   Dashboard shows it like any other run.

New installs ship with no job titles. Every answer stays editable on the
existing pages; the wizard writes the same config they do. The terminal gets
the same questions as `jobdork init`.

**Why.** Resume first because it lets the model fill in steps 3 to 5, which
is most of the typing, for people who are not technical. AI not blocking
scans, because someone without Ollama or a key would otherwise be stuck on
step 2 of a tool they have not seen work yet. The quick first scan because a
full default scan takes about 20 minutes for a US user (measured
2026-10-01), which is a poor first experience; the industry chosen in step 3
then keeps every later scan to the boards that matter.

**Ruled out.** A checklist pointing at the existing pages (less guidance for
the users who need it most); search before resume (no suggestions to give);
AI as a hard gate (2026-09-30's plan, reversed here).

**Revisit when** most installs come with a working model (the gate could
return), or the full default scan drops to a few minutes (the quick scan
would no longer be needed).

---

## API keys for job sources, and a key proxy deferred — 2026-09-30

### The question

Some job sources need an API key: Adzuna (`ADZUNA_APP_ID`, `ADZUNA_APP_KEY`)
and USAJOBS (`USAJOBS_KEY`, `USAJOBS_EMAIL`) today, JSearch or SerpApi
(Google Jobs data) perhaps later. Many users will not be technical enough to
sign up for a key and set an environment variable on a NAS. Could the keys
ship with the app, so nobody has to?

### Decided

1. **Keys never ship in the Docker image, in any form.** The image is public
   on Docker Hub. Anything inside it (a layer, an image environment
   variable, a config file) is readable by anyone who pulls it, with
   `docker inspect` or `docker save`. A GitHub repository secret stays
   secret only inside GitHub Actions; a workflow that writes it into the
   image publishes it.

   Hiding it does not change that. If the program on a user's machine can
   use a key, the user can read it, because they control the machine:
   - encrypted in the image: the code that decrypts it ships with it;
   - obfuscated, split or compiled: it is reassembled in memory, where a
     debugger, a memory dump or one `print` shows it;
   - downloaded at startup: whatever the app can download, so can the user;
   - over HTTPS: the user can read their own outgoing requests, and
     Adzuna's key is in the URL itself (`?app_id=...&app_key=...`);
   - hardware enclaves or DRM: need special hardware and a different
     architecture, and are broken in practice.

   Shipping a key would also give every user one shared quota (Adzuna's
   free tier is 2,500 calls a month in total) and very likely break the
   providers' terms, which issue keys per developer or application.

2. **Keyless sources carry the out-of-the-box experience.** A new user fills
   in the setup and gets results with no key: the shipped employer boards
   (368 as of 2026-10-02, on Workday, Oracle, Eightfold, Taleo, Greenhouse,
   Lever, Ashby, SmartRecruiters, Breezy and employers' own careers sites),
   Workable's search, Himalayas for remote work, and Kalibrr for the
   Philippines and Indonesia. Keyed sources are extras. (When this was
   decided, the boards and the company-site reader were still planned; AI
   no longer blocks a scan, see the onboarding decision above.)

3. **A user who wants a keyed source pastes their own key into the app**
   (built: a card per source on the Sources page and in setup's job-sources
   step, with what it adds, a "Get one free" link, and the key tried against
   the source when it is saved). **Changed 2026-10-27:** no key is written to
   a file. It is held in memory, or, if the user chooses (setup's first page,
   Settings), kept in the OS keychain through `keyring` (core/keystore.py).
   The earlier `source-keys.env` (2026-10-25: chosen over a keychain because
   scheduled scans need keys while jobdork is closed, and a keychain is
   missing in Docker and locked to a Linux cron job) is migrated and deleted.
   Accepted: an unsigned Mac app is asked for keychain access once per
   version, and a scheduled scan nobody answers runs without kept keys;
   Docker and NAS users give keys in the environment.

4. **AI keys follow the burn rules, unless kept by choice.** Keys for hosted
   models (Claude, Gemini, ChatGPT, Groq) are held in memory and wiped when
   the server stops; they are re-entered after a restart, which the page asks
   for (2026-10-27), or kept in the OS keychain when the user chose it. Ollama, run locally, needs no key and
   is the way to an AI that survives restarts. This is separate from job
   source keys on purpose: an AI key can spend money.

### Deferred: a key proxy

**What it would be.** A small service the project runs, for example a
Cloudflare Worker on its free tier. It holds the Adzuna, USAJOBS (and later
JSearch) keys as its own secrets, deployed from GitHub Actions. jobdork sends
a search to the proxy; the proxy adds the key, calls the source and returns
the answer. The key never reaches the image or any user's machine, and users
need no setup at all.

**What it would have to do:**
- **Per-install limits.** Each jobdork install gets an identifier, and the
  proxy caps how many searches it may make in a day and a month. Without
  this, one heavy user, or anyone who finds the endpoint, spends everyone's
  quota.
- **Abuse protection.** The endpoint is public by nature: rate limits by
  install and by IP, and a way to revoke an install.
- **A shared, cached quota.** Many users search the same titles in the same
  places; one answer, cached for a few hours, can serve several. Past a few
  users, Adzuna's free 2,500 calls a month will not be enough, and its paid
  tier has a price.
- **Terms checked first.** Whether Adzuna, USAJOBS and the Google Jobs
  resellers allow one key to serve many end users through a proxy. USAJOBS
  identifies the caller by email; some providers forbid this outright.

**What it would cost:** a hosted service to run, monitor, keep patched and
pay for once usage outgrows free tiers, separate from the app, with its own
security surface. That is why it waits.

**Revisit when any of these is true:**
- The Discover test list (US employers across industries, international
  second) shows keyless sources leaving real gaps that a keyed source fills,
  for example a whole industry or region with no reachable boards.
- Users report they want Adzuna's or USAJOBS' coverage but cannot manage a
  key, in numbers that justify running a service.
- The project gains hosting, a budget, or another reason to run a server,
  which would make the proxy a small addition rather than a new commitment.
- A provider offers multi-user or partner access that fits this model.

**Ruled out along the way:**
- **Keys inside the image** (see 1 above).
- **`python-jobspy`** and any scraper of LinkedIn, Indeed or Google's job
  results: against their terms and robots.txt, and it gets users' home IPs
  blocked. Google Jobs is reached instead by a link that opens the user's
  own browser (built: **Search Google Jobs** under the job posts list), and
  later perhaps through a licensed reseller
  (JSearch, SerpApi) as a keyed source, which would go through this same
  decision.
