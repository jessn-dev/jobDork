# Decisions

Choices that shape jobdork and are not obvious from the code, each with why
it was made, what was ruled out, and **what would make it worth revisiting**.
A decision here is not permanent; it is the best answer to the requirements
as they stood, written down so a change of requirements starts from the
reasoning rather than from scratch.

Newest first.

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
   (planned): a card per source on the Sources page with what it adds, a
   "Get a free key" link and a Test button. The key is kept in a file in
   `data/`, readable only by jobdork's user: not the config, not the
   database, never a log, never the image. It is the user's key on the
   user's machine. Environment variables keep working for those who prefer
   them.

4. **AI keys follow the burn rules.** Keys for hosted models (Claude,
   Gemini, ChatGPT) are held in memory only and wiped when the server stops;
   they are re-entered after a restart. Ollama, run locally, needs no key and
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
  blocked. Google Jobs is reached instead by a button that opens the user's
  own browser (planned), and later perhaps through a licensed reseller
  (JSearch, SerpApi) as a keyed source, which would go through this same
  decision.
