# Changelog

Each finished piece of work gets its own entry here, newest first.
[Still outstanding](#still-outstanding) is the backlog: a bullet moves out of
it and into an entry when the work is done.

---

## Changed — 2026-09-30 — version 0.14.3; `v0.14.2` was never released either

The entry below said the first release would be 0.14.2. It was not: the
`v0.14.2` tag was pushed from a `main` that had not been pulled after the
pull request was merged, so it points at `2bd3d41`, the same commit as
`v0.14.1`, whose code says 0.14.0. The version check stopped the run before
anything was built or offered for approval, as it did for `v0.14.1`. Nothing
was published: no image, no GitHub Release.

`pyproject.toml` now says 0.14.3, and the first release is 0.14.3. The
release steps in `SECURITY.md` add one check between the pull and the tag:
`grep -m1 '^version' pyproject.toml` must show the new version, because
"pull first" alone was already written there and was still skipped.

Also on `main` since 0.14.2, from Dependabot: `actions/checkout` 7.0.1 and
`actions/setup-python` 7.0.0. The first run after those merges failed in the
image scan because Trivy's vulnerability database mirror answered 404
(`mirror.gcr.io/aquasec/trivy-db:2`); the next run, with both bumps, passed.

---

## Changed — 2026-09-29 — version 0.14.2; `v0.14.0` and `v0.14.1` were never released

Both tags were pushed before the pull request that set their version was
merged, so each points at a commit whose code says an older version.

- **`v0.14.0`** points at `a3df943`, which says 0.13.0. That commit predates
  the check that a tag matches the version, so the run passed every check
  and waited for approval; the approval was rejected.
- **`v0.14.1`** points at `2bd3d41`, which says 0.14.0. That commit has the
  check, and it stopped the run before anything was built or offered for
  approval: "tag v0.14.1 does not match version 0.14.0 in pyproject.toml".

Nothing was published for either: no image, no GitHub Release. Release tags
can never be moved or deleted, by design, so both stay as tags with no
release, and the first release is 0.14.2. The release steps in `SECURITY.md`
now say that pushing a branch or opening a pull request puts nothing on
`main`; merging does, and only then is `main` pulled and tagged.

## Changed — 2026-09-29 — version 0.14.0, and a tag must match the version

The code still said 0.13.0, and the first release was to be tagged
v0.14.0: an image tagged `0.14.0` whose `jobdork --version` answered
`0.13.0`. `pyproject.toml` now says 0.14.0, and on a tag push the `image` job
checks the tag against it first, so a mismatched tag fails before anything is
built or approved. Rehearsed: `v0.14.0` passes, `v0.15.0` is stopped. The
release steps in `SECURITY.md` start with setting the version.

The Docker Hub account and token are now in the `release` environment only,
the username as a variable; the copies at repository level are deleted.

---

## Added — 2026-09-29 — releases are version tags, approved before they publish

Nothing gave a release a sign-off. On GitHub there was no `release`
environment, so the first run would have created it with no approval and a
push to `main` would have published at once; `main` had no protection; and
`DOCKERHUB_USERNAME` was saved as a secret where the workflow reads a
variable, so the image name would have come out as `/jobdork`. There was also
an empty environment of that name.

- **A release is a version tag** (`v0.14.0`). A push to `main` is built,
  scanned and checked, but no longer published.
- **The `release` environment** now exists: the owner must approve each run,
  and it can only be deployed from a `v*` tag. The Docker Hub token belongs
  in it, so it is only handed to an approved run.
- **Rulesets:** `main` cannot be deleted or force-pushed, takes changes by
  pull request, and needs `test (3.10)`, `test (3.14)`, `security` and
  `image` to pass; `v*` tags can never be moved or deleted, and only an admin
  can create one.
- **A GitHub Release page** for each version, from its own job (it needs to
  write to the repository; publishing must not): the image by exact digest,
  the command to verify its signature, a link to this changelog at that tag,
  and GitHub's list of changes since the last release.
- Turned on: Dependabot alerts and security updates, and private
  vulnerability reporting, which `SECURITY.md` tells people to use. Already
  on: secret scanning with push protection, read-only workflow permissions.
- The stray `DOCKERHUB_USERNAME` environment, empty, deleted.

`SECURITY.md` has the release steps and which settings are done and which
are left to the owner: two-factor authentication on GitHub and Docker Hub,
the Docker Hub token in the `release` environment, and the username as a
variable. The workflow passes actionlint, and the Release notes were rendered
with sample values; it has not run on GitHub yet.

---

## Added — 2026-09-29 — security checks before publishing, and a signed image on Python 3.14

Before an image goes to Docker Hub, it and the code it came from are now
checked, and what is published can be verified by anyone who pulls it.
`SECURITY.md` says what is checked, how to verify an image, and which account
settings only the owner can turn on.

**Checks on every push and pull request** (`.github/workflows/docker.yml`),
all of which must pass before anything is published:

- `pip-audit` on every dependency the image installs: no known
  vulnerabilities.
- `bandit` over jobdork's code, medium severity and up. It found 11 things;
  all were checked. Eight "SQL injection" findings interpolate only fixed SQL
  fragments, `?` placeholders or table names from a hard-coded list, with
  every value a parameter; three "binds all interfaces" are the deliberate
  container and `JOBDORK_ALLOW_HOSTS` cases. Each is marked in the code with
  its reason. One was a real fix: the SHA-1 that makes job post ids now says
  it is not for security (`usedforsecurity=False`).
- `gitleaks` over the whole git history, since a key committed once is still
  there after it is deleted. It found none: your API keys are in `.env`,
  which has never been committed. Its only finding is a fake key a test
  sends, excused by exact commit and line in `.gitleaksignore`.
- `hadolint` on the Dockerfile, which asked for a numeric user.
- The built image scanned by Trivy for high and critical vulnerabilities,
  fixed or not, secrets and misconfiguration; then `scripts/check_image.sh`,
  15 checks on what is inside it and how it behaves.

**The image, rebuilt to be hard to tamper with:**

- **Python 3.14**, the newest stable release (3.14.7, supported to 2030). It
  was on 3.10, whose support ends on 2026-10-31.
- **Alpine instead of Debian slim.** Trivy found 44 high-severity findings in
  the slim image's system packages, none with a fix released (util-linux,
  ncurses, perl, systemd libraries), none used by jobdork; in Alpine, none.
  159 MB instead of 278 MB. The full test suite passes on it.
- **Every dependency pinned with its checksum** in `requirements.lock`,
  generated inside the base image and installed with `--require-hashes`,
  build tooling included. It used to install whatever the newest matching
  versions were, and upgraded pip unpinned.
- **The base image pinned by digest,** not a tag that can be moved.
- **No pip in the image,** the app's code owned by root and read-only to the
  user it runs as (it owned its own code before), and that user numeric,
  `1000:1000`.
- **The access token reaches the log.** Without `PYTHONUNBUFFERED`, Python
  held output back in a container and the startup line with the dashboard's
  address and token never appeared in `docker logs`, the only place to read
  it on a NAS. Found by the new image checks.
- `pyproject.toml` writes its licence the current way (`license = "MIT"`).

**Publishing:** only after every check passes, only from `main` or a version
tag, and only once the `release` environment approves. The image is pushed
for Intel and ARM with a provenance record and a bill of materials, then
signed with Sigstore keyless signing tied to this workflow and commit (no key
to steal), and the signature verified in the same run. Scanners run from their
official images pinned by digest rather than through third-party actions.
Dependabot proposes updates to the actions, the base image and the Python
dependencies, which then go through the same checks.

Checked here: the image built on Alpine and Python 3.14; Trivy, pip-audit,
bandit, gitleaks (history and working tree), hadolint and actionlint all
clean; the 15 image checks passed; the tests passed on 3.14 Alpine and on
3.13 locally. Not yet run on GitHub or pushed to Docker Hub.

---

## Added — 2026-09-29 — a guide to running jobdork on a NAS, with the AI elsewhere

`docs/DEPLOY.md`, from setting it up on a UGREEN DXP4800 (8 GB): the NAS
runs jobdork, a computer with a graphics card or Apple Silicon runs Ollama,
and Tailscale connects them and lets you open the dashboard from anywhere.
Measured on that NAS, one AI verdict with `qwen2.5:3b` took 8 minutes at
100% processor load (3 min 52 s for the verdict, 21 s and 3 min 56 s for the
two hallucination-check calls), so a model does not belong on a NAS
processor. The guide covers:

- installing Docker on UGREEN, Synology, QNAP, Unraid, TrueNAS SCALE and any
  Linux server, and Tailscale on each and on the AI machine, linking each
  system's own documentation (every link checked to open the page it names);
- a test that containers on the NAS can reach Tailscale, since Tailscale in
  a container of its own often cannot pass it on;
- Ollama listening on the AI machine's Tailscale address only (macOS,
  Windows, Linux), so hotel Wi-Fi cannot reach it, and which models suit
  which memory, from the three tested with jobdork;
- the jobdork container: image, volumes, `JOBDORK_ALLOW_HOSTS`, memory, and
  reading the access token from its log;
- what changes with a larger NAS or one with a graphics card, and a table of
  what each error means.

**The image's user now has the fixed id 1000.** It had whatever `useradd -r`
gave it, so a folder mounted from a NAS could be unwritable with no one fix to
give; now it is `chown -R 1000:1000 <folder>` on any system, and 1000 is
usually the NAS's first user already.

The README's Docker section points to the guide, and no longer suggests
running Ollama on the NAS.

---

## Added — 2026-09-29 — open the dashboard on a NAS from another computer; Ollama given room

For running jobdork and Ollama on a NAS (a UGREEN DXP4800, 8 GB) and using it
from a laptop.

- **`JOBDORK_ALLOW_HOSTS`** names the addresses another computer may open the
  dashboard by (`192.168.1.50`, `nas.local`, or `address:port` for one port
  only). Before, the server let in `127.0.0.1` and `localhost` and nothing
  else, so a dashboard in a container on a NAS could not be opened from the
  laptop at all. A named address is let in on any port, since a NAS may
  publish the dashboard on a port of its own; everything else is still
  refused, a wildcard or `0.0.0.0` is ignored with a warning, and the access
  token is required on every request as before. The startup lines print the
  URL for each named address. The README's Running in Docker has the NAS
  command.
- **Ollama is told how much text to make room for** (`num_ctx`) on every
  call: `llm.context`, 16,384 tokens by default, 4,096 to 131,072 allowed.
  jobdork never said, so Ollama used its own default, which is smaller than a
  prompt carrying a full advert and a resume; and Ollama does not refuse a
  prompt that does not fit, it drops the start of it, instructions included,
  and answers anyway. It is one fixed size rather than sized per call,
  because Ollama reloads the model whenever the size changes. A prompt that
  may still not fit is logged.

Measured before this, on this Mac with the real resume and three job posts,
to choose a model for 8 GB: `llama3.2:3b` rated all three "strong" (82 to
92), failed to produce tailored edits, and had 6 of 7 cover letter claims
unsupported; `qwen2.5:3b` told the posts apart (45, 80 and 40; `gemma4:26b`
had given the one it had also judged 55), ran every tool, and had 8 of 17
letter claims unsupported. So `qwen2.5:3b` for judging on the NAS, and a
larger model for writing.

Tests in `tests/test_serve.py`: named addresses let in on any port or only
their own, others refused, the token still required, a wildcard ignored; and
the context size sent to Ollama, default and set.

---

## Added — 2026-09-29 — tests, then a Docker image, on every push to main

There was no automation: nothing ran the tests on a push, and the image was
only ever built by hand. `.github/workflows/docker.yml` now does both.

- **Tests first.** Every push and pull request runs `ruff` and the test suite
  on Python 3.10, which the image runs, and 3.13. The image is only built
  once both pass, so a change that breaks a test is never published.
- **Published from main and from version tags only.** A pull request builds
  the image to prove it still builds, and pushes nothing. A push to `main`
  publishes it for Intel and ARM machines (Apple Silicon included); a pull
  request builds Intel only, which is much faster.
- **Tags you can pin.** A Git tag `v1.2.3` publishes `1.2.3`, `1.2`,
  `latest` and `sha-abc1234`; a push to `main` publishes `main` and
  `sha-abc1234`. `latest` is always the newest release, never an untagged
  commit on `main`, and the `sha-` tag names exactly the commit an image was
  built from, for a rollback.
- **Locked down.** The job's GitHub token can only read the repository, and
  every third-party action is pinned to a commit rather than a tag that could
  be moved (the version is in a comment beside each).
- The Docker Hub account is a repository **variable**, `DOCKERHUB_USERNAME`,
  with the token a **secret**, `DOCKERHUB_TOKEN`. The account name is part of
  the image name, which a secret would mask in the logs and blank out on a
  pull request from a fork, failing the build.

Not yet run on GitHub: it needs that variable and secret set first. The test
job's steps were run by hand in a clean install on Python 3.13 (ruff clean,
255 tests passed); 3.10 is not installed here, so its first run will be the
real check, though every file parses under 3.10's grammar. The image build
has not been run, as the Docker daemon is not running on this machine.

---

## Added — 2026-09-29 — AI tools for your resume and cover letters, as an editor

Built to the guidance that AI should edit what you have rather than author
it. A job post's window has an **AI tools** tab, opening with that rule: you
are the author and the AI an editor; take only what is true, in your words;
read it aloud and be ready to speak to every line; check the employer's rules
on AI in applications; and whether the model runs on this machine or is
hosted (and what that means for your contact details). Then five tools, each
from your resume and the post (`jobdork/ai/tools.py`):

- **Tailor my resume**, as suggested edits, not a new resume: a rewording of
  up to 8 of your lines, with why; lines to move up; and a Skills line of
  skills you have that the ad asks for, with the ones it asks for that you do
  not have listed apart ("add one only if it is true"). Tick the edits you
  want and **Download tailored resume** writes your resume with them applied,
  as plain text, which an applicant tracking system reads best.
- **ATS keywords**: the ten terms a tracking system would look for, each
  marked on your resume or missing.
- **Skills to highlight**, before a cover letter: the ad's three most needed
  skills with its own words, the line of yours that best shows each, and
  action verbs for the role.
- **Recruiter feedback**: the model as this post's recruiter, strengths and
  gaps, on your resume, or on a cover letter you paste.
- **Revise**: five wordings of a bullet or paragraph you paste, in your
  style, with Copy on each.

**How each is checked**, shown on every result:

- **A script drops what it cannot find** where the model says it came from:
  an edit's line not in your resume, a keyword or a requirement not in the
  ad, a strength not in what was reviewed. The count is shown. Found or
  missing for keywords, and the Skills line, are the script's, not the
  model's.
- **The humanizer** cleans every sentence and counts the tells left; an
  action verb it flags ("Leveraged", "Showcased") is dropped.
- **The hallucination guard** checks the claims against your resume and the
  ad, is counted on the Dashboard's hallucination chart (five new kinds), and
  each unsupported claim is pinned to the edit or version it came from.
- **Each tailored edit is checked on its own**: a figure your resume does not
  have; a tool its line does not name; too little in common with its line;
  and dropping a word that says the work was shared or unfinished (began,
  helped, assisted, currently, with the other…). Any of these leaves the edit
  unticked, with the reason in red.

Found in live runs with the local model on the real resume, and fixed before
this entry: "Designed and **began implementing** a hybrid monitoring model"
came back as "**Implemented** a hybrid monitoring model", "**currently**
completing a Master of Science" as training from one, and "code reviews
**with the other** senior developer" as "Performed code reviews"; neither the
guard nor the figure check saw these, so the shared-or-unfinished check was
added. The first version of the "different line" check measured overlap
against the original line and marked fair condensations of long lines; it now
measures against the shorter of the two. And Download placed none of seven
edits: text read from a PDF breaks lines mid-sentence and writes "ff" as one
character. A line is now found by its words with any spacing between, after
ligatures are spelled out; all seven placed.

Tests in `tests/test_tools.py`, with scripted model answers. Checked live with
Ollama gemma4:26b on a copy of the database: all five tools on one post, the
tab, the checks, and the edits placed.

---

## Added — 2026-09-29 — hosted models are not sent your contact details

A resume's email address, phone number and LinkedIn, GitHub and GitLab links
help no model judge fit or write a letter. Every prompt to Claude, Gemini or
ChatGPT now has them removed, for every use: verdicts, page reads, letters,
reviews, the new tools and the hallucination guard. Year ranges ("2019-2023"),
figures ("1,200 hosts"), standards ("NIST 800-53") and salary ranges are left
alone. A local Ollama model gets the text unchanged: nothing leaves the
machine. A street address is not removed, and `docs/CONFIG.md` says so. Tests
in `tests/test_tools.py`: the redaction, and that it applies to hosted
providers only.

---

## Added — 2026-09-29 — View resume

The Resume page has **View resume**: the text as the fit score and the AI
read it, the skills recognised in it, and **Download original**. What the
reader missed shows here, usually text a table or text box hid, and the
window says to read it aloud and be ready to speak to every line. Checked in
Chrome with the real resume: 7,562 characters, 7 years, 33 skills.

---

## Added — 2026-09-29 — cover letters listed, viewed and deleted; temporary in Docker

**On the Resume page, everywhere:**

- **Cover letters**, a table of every one written: the job post, company,
  when, and **View** and **Delete**, five to a page. View opens the letter
  in a window, rendered, with **Download** (as a `.md` file), **Delete** and
  **Close**. Delete asks twice, then removes the file, its record and the
  AI's copy of its text at once; the claim counts stay, because the
  hallucination chart is built from them.
- **Delete resume** beside Upload. An uploaded resume is deleted; a resume
  you pointed the config at yourself is only no longer used, and your file
  is left where it is.
- Uploading a new resume removes the previous upload (a `.docx` replacing a
  `.pdf`), once the new one has been read.
- Uploads, deletes and failures answer with a notice, as on the Search page.
  `**bold**` in a letter or review now shows as bold.

**In Docker, nothing personal outlives a run.** `JOBDORK_TEMP_DOCS`, set by
the Dockerfile to a private folder inside the container, is where the
uploaded resume and every generated document go: cover letters, CVs,
screens, per-post reviews and the advert snapshots beside them. The
dashboard empties it when it starts and when it stops, and forgets what was
in it: the letters' records and text go, and the resume setting is cleared.
A config still naming that resume loads with a warning to upload it again,
where a missing resume otherwise stops the run. The Resume page says so
while it applies.

This also fixes where Docker put documents. They went under the container
user's home folder, which `useradd -r` never creates and `/home` does not
let that user write; so saving a cover letter in Docker would most likely
have failed with a permission error, and anything saved would have been
lost with the container anyway.

On your own machine nothing changes: the resume in `data/`, documents in
`~/Documents/job-applications`. The README has a Running in Docker section.

Tests in `tests/test_serve.py`: a letter listed, read and deleted (file,
record, text; counts kept); an uploaded resume deleted and your own file
only unset; the temporary folder emptied and forgotten, and a config naming
a vanished temporary resume still loading. Checked in Chrome on a copy of
the database in container mode with seven test letters: the table and its
pages, View, bold, Delete from the window and from the table with their
notices, and on stopping, the folder emptied (5 files) and the records
forgotten. No Docker image was built; the Docker daemon is not running here.

---

## Fixed — 2026-09-29 — the UK's regions read "Country" beside Country

For the United Kingdom the picker's region box, holding England, Scotland,
Wales and Northern Ireland, was labelled "Country", right beside the Country
box: Country, Country, City. It is labelled "Constituent", as in the
UK's constituent countries. Test in
`tests/test_international.py`.

---

## Added — 2026-09-29 — icons on Remote, Hybrid and Office

The three arrangements under Arrangements to keep have an icon each, from
the same set as the buttons: a house for remote, two arrows for hybrid, an
office building for office. Checked in Chrome: one row, beside their boxes.

---

## Changed — 2026-09-29 — "Location, work arrangement and pay", one heading

The section was headed "Where, how and how much" and its first field was
labelled "Where you are", above boxes labelled Country, Region and City:
three labels saying where before anything was chosen. The heading now names
what the section holds, and the "Where you are" label is gone; Country,
Region and City say it.

---

## Added — 2026-09-29 — the Search page says what is saved and what is not

A save used to answer with the word "Saved" under the button, gone after
six seconds, and nothing said whether there was anything to save at all.

- **Save says whether there is anything to save.** Greyed out, with "All
  changes saved" under it, until a field changes; then "Unsaved changes"
  and a dot on Search in the menu. Changing a field back to what is saved
  makes it clean again.
- **The note under the page title is shorter:** "Lists save as soon as you
  add or remove a row. Location, work arrangement and pay save with Save
  changes at the bottom." It said the same in a sentence that was hard to
  follow.
- **The note at the foot of the page is gone.** It named the config file
  and said when each part was written; Save and the notices now say that
  as it happens.
- **While it saves** the button reads "Saving…" with a turning icon and
  cannot be pressed twice.
- **A notice in the corner** for every save on the page, naming it:
  "Added 'Intern' to Never show these titles", "Removed 'Vanta' from
  Employer boards", "Location, work arrangement and pay saved", and when a
  country is listed for you, which one. It goes after a few seconds. A
  refusal stays longer, in red, with a close button, and is also shown
  where it happened: under Save, or beside the list's form. The small
  "Saved" beside each list's form is gone.
- **Unsaved edits are kept.** Opening the Search page redrew the form from
  the saved config, so a change left unsaved while you looked at another
  page was lost without a word. The form is now only redrawn when nothing
  is waiting to be saved.

Checked in Chrome on a copy of the config: clean, changed (menu dot),
another page and back with the change still there, changed back to clean,
Saving… then saved with its notice, a list add's notice, and a radius of
"far" refused with the reason under Save and in a red notice.

---

## Changed — 2026-09-29 — Save centred and larger

Save on the Search page sat at the left edge at the size of every Add and
Remove button, easy to miss after three columns of fields. It is centred
under those fields and larger, and "Saved" or the reason it was not
appears on the line under it, so the button does not move when it does.
Checked in Chrome: the button's centre is the fields' centre.

---

## Changed — 2026-09-29 — Where, how and how much lines up with the lists

The section under the lists had columns of its own width, and the Country,
Region and City boxes were a fixed 14rem, so nothing in it lined up with the
three lists above and the right of the page stood empty. The lists, the
place picker and the fields under it now share one set of columns: Country,
Region and City sit under Job titles, Never show these titles and Countries,
each filling its column, with Radius, Arrangements to keep and Salary floor
in the same three columns below. Two columns below 1,100px and one below
700px, as the lists. Left-aligned rather than centred, so each label and box
still starts on the same edge as the one above it.

Checked in Chrome: the three rows begin at the same three points across
the page.

---

## Added — 2026-09-29 — Search page tables show five rows a page

A list of fifteen job titles pushed everything below it off the screen. The
four tables on the Search page (job titles, never show these titles,
countries, dealbreakers) now show five rows at a time, with Previous and
Next and where you are ("6 to 10 of 15") under the table. A list of five or
fewer has no pager. Adding a row turns to the page it landed on; removing
one keeps the page, or the one before if that page is now empty. Each
table remembers its own page while you stay on the Search page.

Checked in Chrome on a copy of the config: fifteen titles in three pages,
Previous disabled on the first, a sixteenth added and shown on page four,
then removed back to page three; eight dealbreakers in two pages.

---

## Changed — 2026-09-29 — the Search page uses the width of the screen

The page stopped at 1,060px, and its tables and help at 48rem inside that,
so on a wide screen, and more so with the menu folded, most of it was
empty. It is now a grid across the whole width:

- **Job titles, Never show these titles and Countries to keep job posts
  from** side by side: three columns on a wide screen, two below 1,100px,
  one below 700px. Each add form stays on one line, its box filling the
  column.
- **Dealbreakers** across the page, so a long pattern reads on one line
  where it used to wrap three or four times; its pattern box stretches.
- **Where, how and how much** across the page: the place picker on a row of
  its own, then radius, arrangements and salary floor in columns. Save is
  still last.
- Notes keep a readable line length (75 characters) whatever the width.
  The other pages keep their 1,060px limit.

Checked in Chrome with the menu folded on a wide window (three columns, no
empty right half) and at 820px (two columns, no sideways scrolling).

---

## Fixed — 2026-09-29 — Countries to keep job posts from sat below Save

It was placed after the Save button, so Save looked like it belonged to the
countries and the page's last section looked unsaved. It saves on its own
like the other lists, so it is now with them: after Dealbreakers, before
"Where, how and how much", whose fields Save is for. Save is last again,
and its note says a place's country was added to the countries "above".

---

## Fixed — 2026-09-28 — three Search page notes that misled

- **Under Save** it said "Written to your config file. API keys are never
  stored here; they live in .env." There are no API keys on the Search page;
  a key pasted on the AI page is held in memory, with `.env` only a
  fallback; and the lists above now save without Save. It now names the
  file the page is kept in, and says a list saves as soon as it changes and
  the rest on Save.
- **Under the salary floor** it said "Only a published figure can hide a
  job post. About 12% of postings state one; the rest show as
  'unconfirmed'." It now says what happens in plain words: a post is hidden
  only when it lists a salary and even the top of it is below the floor;
  one with no salary, or paid in another currency (never converted), is
  kept and marked; empty hides nothing. The tooltip that said the same a
  second way is gone.
- **Under the radius** it said '"exact" matches the city only. Remote job
  posts skip the radius, because distance means nothing for a job with no
  office.' It now says what the number is (how far from your city a job's
  office may be), that `exact` means your city only, and what is kept
  whatever the distance: remote jobs, and a post whose location cannot be
  read.

---

## Added — 2026-09-28 — the salary currency follows the country

Choosing a country under Where you are sets the salary floor's currency to
that country's (Germany, EUR; the Philippines, PHP), with a note to change
it if you are paid in another. A country whose currency a floor cannot use
leaves it as it was and says so. The currency is now a list of the 45 a
floor accepts, where it was a text box. The currencies come from GeoNames
`countryInfo`, written by the builder as a fourth column on each country's
row in `regions.csv`.

---

## Changed — 2026-09-28 — Countries to keep job posts from; Naperville by default

- **Its own section, its own name.** "Countries" sat under Where you are and
  read as the same thing twice. It is "Countries to keep job posts from",
  after Save, with a note that it is not where you are: living in Baguio
  and open to remote work for US employers is the Philippines and the
  United States. It also says these choose which sources search.
- **A table and an add form**, like the other lists, in place of a list
  that needed Ctrl or Cmd held to choose more than one. Each change saves
  at once.
- **Saving a place with no countries listed lists its country**, and the
  Save note says so. None listed would otherwise keep job posts from every
  country, which a new user almost never means.
- **Naperville, Illinois, United States is the default.** A config that
  leaves out `locations.anchor` is at "Naperville, IL", and one that leaves
  out `locations.countries` keeps US job posts; the picker offers
  Naperville, in USD, when no place is saved. Only a missing key takes the
  default: `anchor: ""` and `countries: []` keep their meaning. The example
  config and `docs/CONFIG.md` say Naperville.

Tests in `tests/test_international.py` (the defaults, and that an explicit
empty value is kept) and `tests/test_serve.py` (countries saved as a list).
Checked in Chrome on a copy with no place and no countries: Naperville
offered, Save stored "Naperville, IL, United States" and listed the United
States, a second country added from the form, and Germany set EUR.

---

## Added — 2026-09-28 — Where you are is picked: country, region, city

**Where you are** was one free-text box, and a place it could not find
turned the radius off with nothing on the page to say so: a scan only
logged "distance filtering is off". The anchor in use, "Baguio City", was
one of those. It is now three choices, all from the bundled place list:

- **Country**, every one of the 245 with a listed place, by English name.
- **Region**, that country's first level under its own name for it: State
  (US, Australia, India, Germany…), Province (Canada, the Netherlands…),
  Region (the Philippines, France…), Prefecture (Japan), Country (the UK),
  Canton (Switzerland). Hidden where a country has none, such as Singapore.
- **City**, suggested as you type, biggest first, narrowed by the region.

It saves `locations.anchor` as `City, Region, Country` ("Baguio, Cordillera,
Philippines"; "Austin, TX, United States"), and a city not in the list is
refused with the reason. Under it the page says whether the radius is
measured from that city, or that the saved location cannot be placed and
the radius is off. No postal code: postings almost never carry one, so it
would only sharpen your own point.

- **The place list keeps every city's region.** `scripts/build_gazetteer.py`
  writes a sixth column, the GeoNames first-level region, and a new
  `jobdork/data/regions.csv` of region and country names (GeoNames
  `admin1CodesASCII` and `countryInfo`, CC BY 4.0). Rebuilt from today's
  GeoNames: 70,026 places, up from 69,933; 2.5MB plus 77KB. `--source DIR`
  builds from files already downloaded. `.gitignore` ignored every `*.csv`
  but `cities.csv`, so `regions.csv` is let through too.
- **A region settles same-named cities.** "San Fernando, Ilocos" and "San
  Fernando, Central Luzon" are 180 km apart, and both read as the larger
  before. A region is only read from after the city, so "Tokyo, Tokyo"
  keeps its city. How a posting's location is read is otherwise unchanged:
  the `state` column still holds only US, Canadian and Australian codes.
- **A trailing "City" is tried without it** when the name as given finds
  nothing, so "Baguio City" now finds Baguio, and the radius works with the
  anchor as it is in your config. Quezon City, whose name really ends in
  "City", is found first as written.
- The main Save's error now starts with a capital, like the rest.

Tests in `tests/test_international.py` (regions, the "City" fallback, the
picker's lists and what they save resolving back) and `tests/test_serve.py`
(saved from the picker, and a city not in the list refused). Checked in
Chrome on copies of the config and database, this time with the copy's
`db:` confirmed first: the picker opens on Philippines, Cordillera,
Baguio; Cordillera's cities list Baguio first; a change saves, an unknown
city is refused, and the labels read State for the US and hide for
Singapore.

---

## Changed — 2026-09-28 — the job post search box says "Search"

Its placeholder read "Filter by title or company", and now reads "Search".
What it searches is unchanged, title and company, and screen readers are
told so through its label.

---

## Added — 2026-09-28 — an icon on every button

Buttons were words only, so a row of them read as a block of text: Run a
scan, Run fresh scan, Fetch missing adverts, Re-apply filters, Check still
open and AI judging looked alike at a glance. Each now has an icon in front
of its label, from Lucide (ISC licence), inlined because the page loads
nothing from anywhere.

- **Actions:** run (play), fresh scan (rotate), fetch adverts (download),
  re-apply filters (filter), check still open (circle check), AI (sparkles),
  add (plus), remove and delete (trash), save, upload, review (file search),
  look up a board (search), send, cancel and close (x).
- **Statuses** in a job post's window each have their own: interested
  (star), applied (send), interviewing (speech bubbles), offer (award),
  rejected (circle x), and so on; the tabs too (advert, screen, CV, cover
  letter, resume review).
- **Show as table** switches to a chart icon when it reads Show as chart;
  By kind and By model have layers and a chip; the AI page's Off is a power
  icon beside the providers' logos.
- Left as text: the 7 / 30 / 90 days switch, where the same calendar on
  each would say nothing.
- A button names its icon in `data-icon`, and one observer adds it, so a
  label rewritten while a job runs ("Scanning…") gets its icon back.

Checked in Chrome: every page and a job post's window walked for a visible
button without an icon (none but the days switch), and a label rewrite.

---

## Added — 2026-09-28 — help writing a dealbreaker pattern

A dealbreaker is a regular expression, and nothing on the page said so or
how to write one. Under the Dealbreakers table, **How to write a pattern,
with samples** opens:

- **The eight building blocks** that cover almost every dealbreaker (`|`,
  `.`, `?`, `\b`, `\d`, `{2}`, `(?:a|b)`, `\s?`), each with an example,
  what it finds and what it does not, and how to match a symbol itself
  (`C\+\+`).
- **Seven samples** (security clearance, relocation, heavy travel, on-call,
  contract or agency, unpaid take-home, sales quota). A click fills the Add
  form with the name, the pattern and whether it hides the post; nothing is
  added until you press Add.
- **Try it:** paste a sentence from an advert and it says whether the
  pattern in the form finds it, and what it found, as you type. It runs in
  the browser; Add checks the pattern again with Python, which is what a
  scan uses.
- **Links to public documentation:** Python's Regular Expression HOWTO, its
  syntax reference, and regex101 set to the Python flavour.

`docs/CONFIG.md` has the same guide under dealbreakers, with the samples as
YAML and how quoting changes backslashes there. Tests: every sample on the
page compiles with Python's `re` and finds its example
(`tests/test_serve.py`); the YAML samples were loaded and compiled by hand.
Checked in Chrome: a sample fills the form, and the tester finds, misses,
and reports a pattern that is not valid yet.

---

## Added — 2026-09-28 — each AI provider shows its own logo

The provider buttons on the AI page were words only. Each now carries its
provider's mark: Ollama's llama, Claude's spark, the Gemini star and the
OpenAI knot, from Simple Icons (CC0), inlined because the page loads
nothing from anywhere. Claude and Gemini keep their brand colours on an
unselected button; the selected one takes the button's text colour, so the
mark keeps its contrast on the accent background. Off has none. Checked in
Chrome.

---

## Fixed — 2026-09-28 — Look and add could break the config; the server kept an old one

- **Look and add wrote YAML that does not parse** once the dashboard had
  saved the config. A dashboard save writes the list with its dashes level
  with `companies:`; Look and add indented new entries under it. Mixed in
  one list that is a parse error, and from then on `jobdork scan` could not
  load the config at all. New entries now take the indent of the entries
  already there, in a hand-written file or a dumped one.
- **Looking an employer up twice added its board twice.** A board already
  listed (same type and token) is skipped, and the log says "already in your
  config; nothing added", in the terminal too.
- **The server kept the config it started with.** Look and add writes the
  file from a background job, and a hand edit changes it too, but the
  running dashboard never re-read it: a scan started from the page ran
  without the new board until jobdork was restarted. Each request now
  re-reads the file if it changed; a file that no longer loads is left
  alone and the last good config kept, with a warning in the log.

Tests in `tests/test_core.py` (a dumped list, and a repeat lookup) and
`tests/test_serve.py` (a file changed on disk is seen by the next request).

---

## Added — 2026-09-28 — lists are added to by a form and removed from a table

Four list settings now show as a table with a Remove button on each row and
a form beneath it that is the only way to add one. Each add or removal is
saved at once, through the same check as Save: a list the loader would
refuse is not written, and the table stays as it was.

- **Job titles** and **Never show these titles**, on the Search page. They
  were free-text boxes, one per line, where a stray blank line or a
  select-all-and-type could empty the list. A title already listed (in any
  case) is refused.
- **Dealbreakers**, on the Search page: name, pattern, and whether it hides
  the job post or costs 8 points. The sidebar said the Search page edited
  them, but there was no control for them anywhere on the dashboard; they
  could only be changed in `config.yaml`. A pattern that does not compile is
  refused with the reason, and the file is left as it was.
- **Employer boards**, on the Sources page, which listed them but could not
  remove one. The add form is Look and add, moved here from Tools: a board's
  token is read off the employer's own site and checked against the board
  before it is written, never typed in. The table refreshes when the lookup
  finishes. Tools keeps Add a posting and Email a digest.
- **Remove asks twice:** the first click turns the button into "Remove?" for
  three seconds.
- The rest of the Search page (where, radius, countries, arrangements, pay)
  stays a form with Save, under "Where, how and how much"; Save no longer
  sends the lists.
- `/api/config` accepts `dealbreakers` and `companies` as whole lists, named
  fields only.

Tests in `tests/test_serve.py`: dealbreakers saved and a broken pattern
refused with the file unchanged; a board removed and an unknown board type
refused. Checked in Chrome on copies of the config and database: add, a
duplicate refused, remove, a broken pattern refused, and on Sources a board
removed then added back by Look and add (Vanta, Ashby, 88 jobs verified).

---

## Changed — 2026-09-28 — "resume" without the accents

Every "résumé" jobdork writes is now "resume": the page, the terminal, the
static page, the Markdown and the digest, the prompts, and the docs. Place
names that carry an accent (Québec, México) are data and are unchanged.

- **Schema version 7** changes what jobdork wrote itself into the database:
  the score's part name ("résumé fit", which the page looks up for the fit
  tip, so rows scored before would have lost it), run names and log lines,
  and the text of AI outputs. Adverts and your notes are not touched: those
  are someone else's words. On a copy of the database: 678 job posts moved
  to "resume fit", 2 runs renamed, no advert changed.

Tests in `tests/test_migrations.py`.

---

## Changed — 2026-09-28 — resume review moved to the Resume page

**Review my resume** was on Tools, a page away from the resume it reviews:
you uploaded in one place and asked for a review in another. It is on the
Resume page now, under the upload, with the latest review shown there. It
has its own log, which appears when a review starts; the progress was in
the Tools log at the bottom of a different page. Tools goes back to helpers
that do not need the resume: add a posting, find an employer's board, email
a digest. The Resume page stays in Setup, because every scan reads the file
for fit and the AI reads it for verdicts: it is a setting, not a one-off.

- The Resume entry's sidebar tip says the review is there.
- Log lines on Tools and Resume start with a capital ("Resume review
  started"); a status column ("ok") is left as it is.

Checked in Chrome on a copy of the database, with the local model: Tools
without the review, the Resume page with the earlier review drawn, and a
review run from there (17 of 17 claims found in the resume) that logged on
that page and drew the new review when done.

---

## Fixed — 2026-09-28 — a search box too narrow to read; the capitals still missed

- **The Job posts search box** was the browser's default width, about 180px,
  so a company name like "iSupport Worldwide" scrolled inside it. It now
  takes the room left on its row, up to 40rem (about 550px on a laptop),
  and never less than the screen on a phone.
- **Skills read as they are written.** Matching is on lower case terms, and
  the fit tip and the "Fit: has … wants …" flag showed them that way:
  "aws", "ci/cd", "postgresql". `resume.SKILL_NAMES` gives every acronym and
  product its own spelling ("AWS", "CI/CD", "PostgreSQL", "GitHub Actions",
  "Argo CD"); anything else reads in sentence case ("Machine learning").
  The flags were written into the database at scan time, so they are put
  right where they are shown (`resume.flag_label`: the dashboard, the static
  page, the Markdown, the digest and `list --flags`), and a scan made before
  this still reads correctly.
- **Job boards by their own names** where the last scan is reported:
  "Adzuna returned 0 job posts", "Workable did not run", and the per-board
  counts on the Last scan card, which read "adzuna 822, ashby 88".
- **The rest, found by walking every page's text in Chrome:** the badge
  keys on each job post (Match, Fit, AI), the status and scope menus
  ("Any status", "Open job posts"), placeholders ("Filter by title or
  company", "Note (Enter saves)", "Paste the key"), the Hallucination tip's
  table (its kinds and its Checked / Unsupported / Rate headings), "No key
  held", "Claude drafts", and the screen-reader labels on the charts.
- **Country names.** The Countries list mixed English and local names and
  capitalized small words: "United States Of America", "Bosnia And
  Herzegovina", "Deutschland", "España", "Italia", "Viet Nam". They are
  English throughout now, with "and" and "of" in lower case.

Left in lower case on purpose: company names as the company writes them
(tastytrade, iManage), dbt and gRPC, the units mi and km, the example URL,
domain and email address, and a hint that continues a sentence begun in its
label. Checked in Chrome on a copy of the database: every page walked again
for text starting in lower case, the search box with a long company name,
and the fit flags on posts scanned before the change. Tests in
`tests/test_international.py` and `tests/test_telemetry.py`.

---

## Added — 2026-09-28 — hallucination over time, by model

A **By kind / By model** switch on the Hallucination chart. By kind asks
which output makes things up; by model asks whether the model does, which
is the question after switching models or providers. Same claims, grouped
the other way: the totals agree (20 of 181 either way on the check below).

- **Models in the order first used, over all time**, and that order is the
  colour order, so a model keeps its colour when another is added or when
  the period changes.
- **At most six lines.** Past that, the rest fold into "Other models": more
  lines than distinct colours is noise, and a colour must not be reused.
- Output recorded before models were logged is "Unknown model" rather than
  left out, so the totals still match By kind.
- `/api/metrics` returns `models` and each day's `claims_by_model`.
- The table view's column headers were not capitalized, unlike the legend;
  they are now.

Checked in Chrome on the scrubbed copy of the database: both settings of
the switch, the legend totals under each, the tooltip, and the table. The
Dashboard screenshot is retaken. Tests in `tests/test_metrics.py`.

---

## Fixed — 2026-09-28 — the Docker image could not be reached or started

Three things kept the image from the previous entries from working at all.
No image was built for this: the Docker daemon was not running here.

- **The dashboard listened where nothing could reach it.** `serve` binds
  127.0.0.1, and inside a container that is the container's own loopback: a
  port published with `-p` arrives on the container's network interface and
  finds nothing there. It now binds 0.0.0.0 when `JOBDORK_IN_CONTAINER=1`
  (set by the Dockerfile) **and** a container marker file (`/.dockerenv`,
  `/run/.containerenv`) are both present, so exporting the variable on a
  bare host changes nothing and the "no `--host`" rule stands. The printed
  URL and the Host check stay on 127.0.0.1, and `serve` says to publish to
  the host's loopback only, on the same port both sides:
  `-p 127.0.0.1:8765:8765`.
- **It exited at once.** The image baked in an empty `config.yaml`, which
  does not load ("titles.include is empty"). No config or `.env` is baked in
  now; `config.example.yaml` is, and the Dockerfile gives the `docker run`
  line that mounts your own config, `.env`, `data/` and `out/`. The config
  mount is writable, because the dashboard edits it.
- **It tried to open a browser** it does not have. `CMD` is now
  `serve --no-open`.
- **`.dockerignore`**, so `.env`, `config.yaml`, `data/` and the virtualenv
  are not sent to the daemon as build context, even though the build copies
  none of them.

Tests in `tests/test_serve.py`: the variable alone, the marker alone, and
both together.

---

## Fixed — 2026-09-28 — a token in the URL could change things; the page could be framed

- **A POST was accepted with the token in the query string.** The query is
  there so a person can be handed one URL; after the first load the page
  sends the token as the `X-Jobdork-Token` header. Accepting `?t=` on a POST
  as well meant a leaked URL (browser history, a screenshot, a proxy log) was
  enough to change statuses, delete job posts or start scans. `?t=` now
  counts only on a GET: the first page load and the live-scan stream.
- **Another site could put the dashboard in a frame** and lay its own page
  over it, so a click meant for that page landed on a dashboard button.
  Every response now says `X-Frame-Options: DENY`, and the page's
  Content-Security-Policy adds `frame-ancestors 'none'`.

Tests in `tests/test_serve.py`: a POST carrying only `?t=` is refused and
changes nothing; the page carries both headers.

---

## Added — 2026-09-28 — a Docker image, run as a non-root user

A `Dockerfile` for running jobdork away from the rest of the machine. It is
two stages: the first installs the package with the `pdf` and `ai` extras
into a virtualenv, the second copies only that virtualenv onto
`python:3.10-slim`. It runs as `appuser`, not root, because it parses files
it did not write: a resume PDF through `pypdf`, and job adverts from the
open web. A parser bug reached through either stays inside the container
without root. As first written it could not be reached or started; see the
entry above.

---

## Fixed — 2026-09-28 — distances in km were miles; labels in sentence case

- **A kilometre reader saw miles labelled km.** Distances are stored in
  miles. The dashboard, the Markdown output and the digest printed the
  stored number with the reader's unit after it, so 10 miles showed as
  "10 km"; the static page printed "mi" whatever the unit. All of them now
  convert, through `geo.distance_label`: 10 miles is "16 km".
- **Labels are in sentence case** in every output: "Match", "Fit",
  "Hybrid", "Unconfirmed salary", and each job board as it spells itself
  ("SmartRecruiters", "USAJOBS") rather than its internal key. Company names
  are left as the company writes them.

Tests in `tests/test_international.py`.

---

## Added — 2026-09-28 — countries from a list; tooltips on the settings

- **Countries is a list of names** on the Config page, where it was a text
  box that wanted ISO codes typed and comma separated. Hold Cmd/Ctrl to
  choose several; none accepts everywhere, as before.
- **Hover tips** say what a setting does to a scan where the label cannot:
  a title exclusion drops the post before its advert is read; a job post
  with no salary stated is not hidden by the salary floor; a country left
  out drops its posts at screening, and adding it back and scanning again
  finds them. On an AI verdict, the tip on "Not in the advert or resume"
  says how those claims were found. The first wording of two of these was
  wrong: the country tip said "permanently hidden", and nothing screened out
  is stored, so nothing is permanent; the guard tip said claims were checked
  against "your uploaded documents", when they are checked against the
  advert and your resume.

---

## Added — 2026-09-28 — hallucination over time, by kind of output

A line chart on the Dashboard beside Runs by tool; the Hallucination card
stays. The card is one number for the period. The chart shows **when** the
model says things its sources do not (a jump after changing the model or a
prompt) and **where**: one line per kind of output (verdicts, page reads,
cover letters, resume reviews, claude drafts), each the share of that
day's checked claims that were unsupported.

- **A day with nothing checked is a gap, not 0%.** Zero would claim there
  were no hallucinations on a day nothing was looked at. Every point has a
  dot, so a day with no neighbours is still seen.
- **The tooltip says what a rate stands on:** "17.6% · cover letters · 16 of
  91 claims", and the day's total. One unsupported claim of two is 50%, and
  should read as two claims, not as a trend.
- The legend gives each kind's totals for the period; Show as table lists
  the days with anything checked.
- It is its own chart rather than a second axis on another: a share and a
  count do not share a scale.
- `/api/metrics` returns each day's checked claims per kind (`claims`) and
  the kinds in their fixed order (`kinds`), which is also the colour order.
- The line chart draws gaps, dots, percentages and per-row detail, so both
  time-series charts are one function. Dots are 8px, the dataviz minimum.

Checked in Chrome on a scrubbed copy of the database: three kinds on today,
gaps before, the tooltip on a day with data and on one without, and the
table. The Dashboard screenshot is retaken. Tests in
`tests/test_metrics.py`.

---

## Added — 2026-09-28 — Run fresh scan; runs by tool as a line chart

- **Run fresh scan** on the Dashboard, beside Run a scan, and
  `jobdork scan --fresh` in the terminal. It deletes every job post a scan
  found, with its status, notes, AI verdict and document records, then scans
  from nothing. A red warning tip on the button says so before it is
  clicked. Clicking previews: how many posts, how many of them you are
  pursuing, and a red **Delete N job posts and scan** button that carries N;
  the server refuses if the number moved since, as Clean up does. The
  database is backed up to `data/backups` first. Nothing is remembered as
  deleted, so the scan finds them again; posts you deleted before stay
  deleted, and posts added by hand are kept. In the terminal it previews
  unless given `--yes`.
- **Runs by tool is a line chart**, one line per tool over the days of the
  period, where it was stacked bars. The legend keys are short lines to
  match. A crosshair snaps to the nearest day and the tooltip lists every
  tool there; the arrow keys move it once the chart has focus. A tool with
  no runs in the period stays in the legend with 0 and is not drawn along
  the baseline. Show as table is unchanged.
- **One scan, whoever starts it.** The dashboard's Run a scan had its own
  copy of the scan, which skipped "judge after scan" and wrote only the
  html and json outputs; it now runs the same job as the rest of the page.
  The terminal's scan did not judge after scanning either; it does when
  `llm.judge_on_scan` is on. Both write every format in `output.formats`
  through one function (`render.write_all`).

Checked in Chrome on a copy of the database: the chart, its tooltip and
keyboard, the warning tip, and the confirm step. The tip at first stayed
open over the confirm panel after a click, hiding its delete button; it now
opens on hover or keyboard focus only, and never while the panel is open.
The dashboard screenshot is retaken, from a copy with the log and AI text
removed. Tests in `tests/test_fresh_scan.py`.

---

## Fixed — 2026-09-28 — list --json, and a connection left open

- **`list --json` and `roles.json` wrote JSON inside JSON.** The verdict, the
  score parts and the reasons are stored as JSON text and were written out as
  strings, so a reader had to decode them twice. They are objects and lists
  now, and a verdict stored before its word followed its score reads as the
  score says (the rule is one function, `llm.verdict_for`, used when judging,
  on the dashboard and here).
- **A refused database left its connection open.** When `Store` could not
  open a database (one written by a newer version, a failed migration), the
  connection it had made was never closed. Found by running the tests with
  every warning as an error, which now pass too.

---

## Fixed — 2026-09-28 — rescreen hung; scans failed writing roles.json

Both found while making the demo screenshots.

- **`rescreen` hung, then failed with "database is locked".** It held one
  write open over every post and committed at the end, while each progress
  tick had the run's telemetry write through its own connection and wait up
  to ten seconds for that very lock, on the job's own thread. 588 posts took
  over five minutes and then failed; they now take three seconds. Three
  changes: telemetry never makes the job wait (a flush from the job's thread
  gives up after a quarter of a second, skips if another flush is writing,
  and keeps what it could not write for the next one; only the final state
  waits); the database runs in WAL mode, so a reader never blocks a commit
  (set on open, kept in the file; `-wal` and `-shm` files appear beside it);
  and `rescreen` and `enrich` commit as they go. From the dashboard,
  Re-apply filters had the same problem.
- **Every scan with `json` output failed at the end**, after storing
  everything: `IndexError: No item with that key`, which is the failed scan
  on the Dashboard. `render.rows_to_dicts` iterated `sqlite3.Row` for its
  keys, but that yields the values. It was `row.keys()` until the last
  commit, where a lint simplification (ruff's SIM118) rewrote it; it is
  `dict(row)` now. `out/roles.json` had not been written since 29 August.
  The writer test only checked each format had a function, never ran one;
  a test now writes all four from real database rows.

---

## Changed — 2026-09-28 — no personal details in the repository

- **Name and handle.** `LICENSE`, `pyproject.toml` and the changelog now
  name `jessn-dev`. The project and User-Agent URLs pointed at a
  `jessengolab/jobDork` that is not this repository; they point at
  `github.com/jessn-dev/jobDork`. Git history was left as it is: its
  commits keep their author.
- **Screenshots from a demo.** All five are taken from a copy of the
  database with every status, note, draft, AI output, verdict and log line
  removed, re-scored against a made-up resume ("Alex Rivera"), and judged
  with it. The job posts are public listings. Before, the skill chips came
  from the real resume and the verdict summarised a real career.
- **Resume facts quoted in the docs** (years of experience, the post it was
  tried on) are replaced with neutral examples, in the README, the
  changelog and the cover-letter prompt's own example.
- **Deleted:** `docs/images/generated-cv.jpg` (it showed a name, phone
  number, email and town; never committed), the dork generator's old CSV
  exports, results file, log, and a root `__pycache__` for a `config.py`
  that no longer exists; a second, unused virtualenv (`venv/`, 18 MB); build
  and tool caches; `.DS_Store`; the stale `out/roles.{csv,json,md}`.
- **`.gitignore`: `data/` became `/data/`** (and `out/`, `/out/`). The bare
  pattern also matched `jobdork/data/`, so the dashboard page, the humanizer
  rules and the gazetteer had never been committed and a clone had no
  dashboard; the `!jobdork/data/cities.csv` exception could not work inside
  an ignored directory. Your database stays ignored.

---

## Changed — 2026-09-28 — documentation and screenshots brought up to date

Every doc was read against the code as it now is.

- **Screenshots retaken** (dark, 1440 wide) on the current interface. All
  five were from 29 August and showed the old "Roles / Scan" pages:
  `dashboard.jpg` (the Dashboard with its metrics), new `job-posts.jpg` (the
  list, with match, fit and AI badges), `role-detail.jpg` (a post with the AI
  verdict open: 20 of 20 claims found), `live-run.jpg` replacing
  `live-scan.jpg` (a run reporting itself mid-way; local Ollama, so no job
  board was called), and `static-page.jpg`. All five were taken again the
  same day from a demo, see "No personal details in the repository" above.
- **ARCHITECTURE:** the pipeline diagram now shows enrich, check, judging,
  drafts, the guard between them, and where results go; the database lists
  all ten tables, not five; grouping replaces "same company and title, best
  score wins"; new sections on the AI reader and the guard, and on run history
  and the Dashboard; "What is not built", which contradicted itself, is gone;
  the test counts are gone too, as they had gone stale twice.
- **README:** a section on the AI page (providers, keys in memory, judging,
  page reads, the hallucination check with its HalluLens credit, the resume
  review, feedback); `check` and `prune`; the `viewed` status; the Dashboard,
  Job posts and job post window with their screenshots; draft checks named as
  they are (humanizer rules, not an em-dash count); "48 tests" gone; the
  project tree moved out of the dork generator's section. The dork section
  ran `python main.py` throughout, a file that has not existed since the
  scanner: it is `jobdork dork`, configured in `jobdork/dork/boards.py`.
- **CONFIG:** a full `llm` section (it had none), including that a key in the
  file stops the load; the AI keys in the environment table; Resend is used by
  `scan --email` and `digest`, not only the dork generator; `viewed`; a status
  is per job, and what `prune` never deletes.
- **`config.example.yaml`** had no `llm` block; it has one, which loads.
- **PLATFORMS:** "Not yet implemented: enrich, discover", both shipped months
  ago, is now what they do; Adzuna duplicates are grouped, not collapsed; the
  Lever fallback is no longer described as North American only.
- **SOURCES** and the docs index: `jobdork dork --list-sites`; the new
  screenshots and a pointer to the AI setup.
- Every relative link and anchor in the docs was checked by script.

Also fixed, found on the new screenshots: the Dashboard's run cards said "just
now" for anything under an hour (a judging run 23 minutes old); they say
"23 min ago".

---

## Changed — 2026-09-28 — modules grouped into packages

`jobdork/` was 28 modules side by side. They now sit by what they are for:

| Package | Modules |
|---|---|
| `core/` | `config`, `telemetry`, `textutil` |
| `db/` | `store`, `migrations`, `grouping` |
| `search/` | `scan`, `screen`, `enrich`, `discover`, `listing`, `geo`, `resume` |
| `ai/` | `llm`, `judging`, `guard`, `writer` |
| `writing/` | `generate`, `gates`, `humanize` |
| `web/` | `serve`, `api`, `live`, `session` |
| `output/` | `render`, `digest` |

`cli.py`, `fetch/`, `dork/` and `data/` stay where they were. Nothing
outside `web/` (and `cli.py`) imports from `web/`.

- Every import was rewritten by script, relative as before; module titles
  and logger names follow (`jobdork.ai.llm`, not `jobdork.llm`). Tracked
  files were moved with `git mv`, so their history follows them.
- `data/` is found from the package root in `search/geo.py`,
  `web/serve.py` and `writing/humanize.py`.
- `pyproject.toml` lists the new packages; `pip install -e .`,
  `jobdork --version`, `./run.sh`, `python -m jobdork.dork`, the dashboard
  and `tests/run_all.py` were each run from the new layout.
- No compatibility aliases at the old paths: `from jobdork.store import
  Store` is now `from jobdork.db.store import Store`. Only the tests
  imported by path, and they are updated.
- Docs: ARCHITECTURE's module table is now per package. The README's
  "Project structure" still showed the original `main.py` and `config.py`,
  which have not existed since the scanner; it shows the real tree now.
  SOURCES pointed at a `config.py` for both the source lists (now
  `core/config.py`) and the dork board table (`dork/boards.py`, whose own
  title still said `config.py`). The package docstring said "for North
  America", untrue since 0.3.0.
- A doubled `# noqa` in `fetch/__init__.py` is single again.

---

## Fixed — 2026-09-28 — loose ends from the guardrail work

- **The verdict word follows the score.** gemma scored a post 30 and
  called it "possible", so the badge showed a 30 in amber. The word is now
  set by the prompt's own bands (80+ strong, 50+ possible, else weak), and
  verdicts stored before this are corrected when read, without rewriting
  them: that post now shows 30, weak.
- **Last AI judging** said "recorded before run history · just now" on the
  day a post was judged, because the card skipped single-post runs and fell
  back to a stamp it then described wrongly. A full run is still preferred;
  when single posts are all there has been, the card shows the latest one,
  marked "one job post only". The same applies to Last check.
- **The 90-day metrics could undercount.** Run history kept the last 200
  runs, so a busy quarter lost its oldest. Runs and their model calls are
  now kept for 120 days whatever their number; only the per-run logs, which
  are the bulk, are still limited to the last 200 runs.
- **The thumbs beside the AI badge** said only "Useful"; they now say what
  they rate ("Useful (Was the AI verdict useful)") on hover and to screen
  readers.
- **The feedback chart's lower axis** read "5" for five thumbs down; its
  ticks read ↑5 and ↓5.

Tests in `tests/test_ai.py` and `tests/test_telemetry.py`.

---

## Added — 2026-09-28 — feedback buttons, and the AI letter and review on the page

Last part of the guardrail plan.

- **Thumbs up / down** on every AI output the page shows: beside the AI
  badge in a job post's window (the verdict), under each cover letter,
  resume review and `claude -p` draft tab ("Was this cover letter
  useful?"), and on the Tools page's resume review. Pressing the pressed one
  clears it. Ratings feed the Dashboard's feedback chart. A draft made with
  the guard off can be rated too: its output row is kept in the artifact
  under a hidden `_output` key, which the page never shows as a gate.
- **Job post window:** **Write cover letter (AI)** and **Review resume for
  this post** beside Ask AI. Each runs as a normal run, and the window opens
  on the new tab when it finishes. The tab shows the checks, with the claims
  the guard flagged listed, then the text.
- **Tools → Resume review:** **Review my resume** runs the general review;
  the newest one is shown there whenever Tools is opened, with the model,
  the time, how many of its claims were found in your resume, and anything
  flagged.
- Reviews are shown with their headings and lists rather than as raw
  Markdown. The text is escaped first, so nothing in it becomes markup.
- The review capitalises each point; gemma writes them in lower case.
- Tabs read "resume review" and "CV" rather than `resume_review` and `cv`.

Checked in Chrome: the buttons in the window and the tabs, a thumb pressed
and pressed again (stored as 1, then cleared), and a real general review
from the Tools page (gemma4:26b, 18 of 18 claims found in the resume). Tests
in `tests/test_guard_wiring.py`.

---

## Added — 2026-09-28 — metrics at the top of the Dashboard

Fifth part of the guardrail plan. Above "Last runs", scoped by a **7 / 30 /
90 days** switch (`GET /api/metrics?days=`):

- **Tiles.** Runs; errored runs (failed, died or stopped, with their share
  of runs); AI calls and how many failed; **P50 AI latency** with P95 under
  it; and the **hallucination** rate: unsupported claims over checked
  claims, with coverage (checked outputs over all AI outputs). Hover or
  focus the hallucination tile for the split by kind: verdicts, page reads,
  cover letters, resume reviews, claude drafts.
- **Runs by tool, per day.** Stacked columns in a fixed tool order (scan,
  check, AI judging, AI writing, enrich, other), so a tool keeps its colour
  whatever ran. A job started in the terminal and one started here count as
  the same tool.
- **Feedback on AI output, per day.** Thumbs up above the line, thumbs down
  below, with approval in the heading, counted on the day the output was
  written (when a rating was given is not stored).
- Both charts have a legend with totals, a tooltip listing every series for
  the day under the pointer, and **Show as table**. Colours are the dataviz
  reference palette, validated for colour-blind separation against this
  page's own backgrounds in both themes; three light-theme hues are under 3:1
  contrast, which is what the legend and the table view are for.
- The numbers reload when the Dashboard is opened, when a run finishes, and
  when the period changes; the previous numbers stay (dimmed) while they
  load.

On this database, 30 days: 22 runs, 1 failed (4.5%); 21 AI calls, P50
5.3 s, P95 12.4 s; 20 of 143 claims unsupported (14%) over 7 outputs, all
checked. Model calls and AI outputs are only recorded from today, and a tile
says so ("recorded from 2026-09-28") when that is later than the period's
start. Runs come from run history, which keeps the last 200 runs.

Checked in Chrome at full width with the nav open and folded, in both
themes: tooltips, table view, and the hallucination breakdown, which at
first ran off the right edge and now opens leftwards. The axis rounds a peak
of 22 up to 25 rather than 50. Tests in `tests/test_metrics.py`.

---

## Added — 2026-09-28 — the guard checks verdicts, page reads and drafts

Fourth part of the guardrail plan. Every piece of text a model writes here is
now an `ai_outputs` row, and with the new **`llm.guard`** setting on (the
default; AI page: "Check each verdict and draft…") it is checked against the
advert and your resume.

- **AI judging.** After each verdict, its summary, reasons and concerns go
  through `guard.check`. The result is kept inside the verdict (`guard`,
  `ai_output_id`). The AI badge's tip lists claims neither source supports,
  struck out, under **Not in the advert or resume**, and ends with "N of M
  claims found in the advert or resume" (or "claims not checked"). The score
  is left as the model gave it. The run summary counts verdicts with such a
  claim, and so does the run's Outcomes bar ("unsupported claims").
- **Abstaining.** The judge answers `enough_evidence`. When it says no, the
  badge shows **?** and "Not enough to judge" instead of a score. Verdicts
  stored before this read as having had enough.
- **Page reads.** Each time the model reads an unclear posting page, the
  answer is recorded as a `page_read` output. Its check is the quote rule it
  already had: "open" or "closed" is one claim, supported when its quote is
  on the page; "unknown" claims nothing. No extra model call.
- **`claude -p` drafts** (screen, CV, cover letter). When a model is set on
  the AI page, the draft is checked too and gets a **hallucination check**
  gate. Drafts are recorded as `draft` outputs whether or not they were
  checked, so the Dashboard's coverage counts the unchecked ones.
  `generate.record` does the recording for the terminal and the dashboard
  alike.
- **Failed gates list their items** in the job-post dialog (the flagged
  claims, the unsupported figures), not only a count.
- The AI letter and review honour `llm.guard` as well.

The cost: two more model calls per verdict and per draft. On a 26B local
model that is roughly twice the judging time; the AI page says so. Turning
the guard off still records every output, unchecked.

`guard.advert_source(row)` (title, employer, location, then the advert) and
`guard.settings_for(cfg)` are shared by judging, drafts and `writer.py`.
`cli.gates_summary` is gone; `generate.record` replaced it. Tests in
`tests/test_guard_wiring.py`.

---

## Added — 2026-09-28 — AI cover letter and resume review (`writer.py`)

Third part of the guardrail plan. Both use the model set on the AI page
(local Ollama included), not `claude -p`.

- **`jobdork letter UID`** (dashboard: `POST /api/letter`). At most four
  short paragraphs, facts from the resume and advert only, humanizer rules in
  the prompt and `humanize.clean` after. Gated like a `claude -p` letter
  (length, AI tells, unsupported figures, overlap with `CV.md`) plus a
  **hallucination check** gate from `guard.check`. Saved as
  `cover-letter-ai.md` in the job folder, so a `claude -p` `cover-letter.md`
  is never overwritten, and recorded as a `cover_letter` artifact, so it
  shows in the job-post dialog as the other drafts do. A new or viewed post
  moves to interested, as with any draft.
- **`jobdork review [UID]`** (`POST /api/review`). Without a post: the
  resume's own problems, each quoting the line it is about. With one: also
  what the advert asks for that the resume does not show, what to move up,
  and lines to reword. A suggestion quoting text that is not in the resume
  is dropped by script and the review says how many were. When the model
  says the evidence is too thin, the review opens by saying so. Against a
  post it is saved as `resume-review.md` and a `resume_review` artifact; a
  general review lives in `ai_outputs` only (`GET /api/review/latest`).
- Both record an `ai_outputs` row with the guard result; the artifact's
  hallucination-check gate carries its `output_id`. `GET /api/ai_output`
  reads one, and `POST /api/feedback {output_id, value}` sets 👍 (1), 👎 (-1)
  or clears (0). The buttons come with the UI step.
- A letter or review needs at least 200 characters of advert, as judging
  does.

Guard fixes found on the first live run (gemma4:26b, one job post):

- A claim built from several places ("worked with Spring Boot, React and
  PostgreSQL", each in a different section) failed for want of one quote.
  The verifier may now join excerpts with ` ... `, and every excerpt must be
  found. The extractor splits lists into one claim per item.
- "The candidate is applying for the position" is the letter describing
  itself; such claims are dropped by script, since the model kept writing
  them.
- The advert source now includes the title and employer.

After the fixes the same letter went from 6 of 25 claims flagged to 1 of 25,
and the one left is a real stretch: Docker attached to an employer the
resume does not tie it to. The first letter had claimed the resume's total years of
experience for each language separately; the letter
prompt now says a number of years belongs to what the resume attaches it to.

Also: the overlap gate read "no the CV to compare against yet"; it now reads
"nothing to compare: the CV is not drafted yet".

Tests in `tests/test_writer.py` and `tests/test_guard.py`.

---

## Added — 2026-09-28 — tables for AI outputs and model calls

Second part of the guardrail plan. Two tables, created on open like
`activity` (no migration step, since new tables need none):

- **`ai_outputs`** — one row per text a model wrote (verdict, page read,
  cover letter, resume review, draft): kind, job post, model, the run it came
  from, the text, the guard report with its claim and unsupported counts,
  whether the check ran, and thumbs up/down. `Store.add_ai_output`,
  `ai_output`, `set_feedback` (1, -1 or cleared).
- **`llm_calls`** — one row per model call inside a recorded run: model,
  purpose, seconds, ok. No prompt or answer text. Needed for P50/P95 latency;
  the per-model totals on `activity` cannot give percentiles. Pruned with the
  run it belongs to.

`llm.complete_json` takes a `purpose` (judge, page_read, test,
guard_extract, guard_verify), and `telemetry.current_id()` gives the run an
output belongs to. Nothing writes `ai_outputs` yet; that comes with the
guard wiring. Tests in `tests/test_telemetry.py`.

---

## Added — 2026-09-28 — hallucination guardrail module (first part)

`jobdork/guard.py` implements the HalluLens method (LongWiki task) with our
own prompts: extract atomic claims from an AI output, verify each against
the known source (resume, advert), and count unsupported claims. A model's
"supported" only counts when its quote is found in the named source by
script. A failed check returns `checked=False` and never blocks the output.
Tests in `tests/test_guard.py`.

Not yet wired in. Still to build, per the approved plan: the `ai_outputs`
and `llm_calls` tables, the AI cover-letter and resume-review tools
(`writer.py`), guard checks on judging, page reads and drafts, feedback
buttons, and the observability metrics on the Dashboard.

---

## Changed — 2026-09-28 — the Dashboard is the home page, at full width

- **Home.** The page opens on the Dashboard, and Dashboard is first in the
  nav, above Job posts.
- **Width.** Page content was capped at 1060px, so on a wide screen the
  Dashboard sat in the left part of the window whether the nav was open or
  folded to the rail. The Dashboard now fills the space beside the nav in
  both states. Job posts and the Setup pages keep the 1060px measure, which
  is easier to read for lists and forms.
- **What it shows first.** With nothing picked and nothing running, the
  panels show the latest run over the whole list, not a one-post check
  started from a dialog.

---

## Changed — 2026-09-28 — "Last runs" instead of a history table

The Dashboard's **Recent jobs** table listed 25 past runs and called out
nothing, while the one thing it was for went unnoticed for a month: the
Aug 29 scan got 0 from Adzuna. It is replaced by a **Last runs** strip at
the top of the Dashboard, one card each for the last scan, the last check
and the last AI judging: when (hover for the exact time), the result, and
in amber whatever went wrong. The scan card reads the scan history itself,
so scans from before run history count, and warns when:

- the last scan is over 15 days old;
- a source returned 0 job posts;
- a source that returned posts before did not run at all;
- a scan started and never finished.

On this database it shows all four. Check and judge cards skip single-post
runs from a dialog, and show a run's failure if it failed or died; click one
to show that run above. The full list is folded into **All runs** at the
bottom. "Job" in the sense of a background task is now "run" on this page,
so it no longer reads like a job post.

---

## Added — 2026-09-28 — clean up old and settled job posts

A **Clean up job posts** panel at the bottom of the Dashboard, and
`jobdork prune` in the terminal.

- **By age:** first seen more than 15 or 30 days ago (`--older-than DAYS`),
  whatever the status, except jobs you are pursuing: applied, submitted,
  interviewing and offer are never removed this way. Offer was added to the
  three asked for, since losing one would be worse than losing the others.
  Age is when jobdork first found the post; many posts carry no date of
  their own.
- **By status:** any of rejected, withdrawn, skipped and closed (ticked in
  the panel, `--status` in the terminal).

Deleting takes two steps. **Preview** shows how many of how many, split by
status, with examples, and warns when that is every post you have. The red
**Delete N job posts** button sends that N, and the server refuses if the
number has changed since (a scan finished, a status changed). It also
refuses while a job is running. `prune` only previews unless given `--yes`.

Before every delete the database is copied to
`data/backups/jobdork-<time>-before-cleanup.db` (the last ten are kept). A
deleted post is recorded in a new `deleted` table, and scans leave it out;
otherwise a post still listed by its source would come back as new with
your decision gone. The scan report counts how many it left out. Status,
notes, AI verdicts and document records go with the post; draft files in
Documents stay on disk.

---

## Changed — 2026-09-28 — charcoal nav in dark mode

The dark nav was navy (`#0b1a2e`) against a near-black page (`#0b0b0d`). It
is now a neutral charcoal, `#151518`: a step lighter than the page, so the
two separate without a colour cast. Hover (`#202025`), the active pill
(`#34343c`, white text) and the count badge moved to the same family.
`#101010` was considered and is too close to the page to see.

Also: the AI-tells check skipped text between backticks as code, which is
right for Markdown drafts but hid every JavaScript template string in the
dashboard. `humanize.find(markdown=False)` now reads them, and it found nine
more dashed strings ("advert 500 chars — too short to screen" and others),
now reworded.

---

## Added — 2026-09-28 — humanizer: no signs of AI writing

[humanizer](https://github.com/blader/humanizer) (SKILL.md v3.1.0, MIT) is
bundled at `jobdork/data/humanizer/` with its licence, and applied to every
kind of text a model writes here, including the app's own wording.

- **Drafts (screen, CV, cover letter).** The full guide is written into each
  job folder as `writing-style.md`, and the prompt tells Claude to write by
  it. It governs how to write, never what to claim; the rules on facts and
  figures still hold. Every draft, screens included, then goes through a new
  **AI tells** gate, which lists each tell found with its rule number
  (§1 "not X but Y", §8 dashes, §12 stock AI words, §19 bold labels,
  §22 chatbot residue, and more). It replaces the em-dash count and the
  external linter that was rarely installed.
- **AI verdicts.** The local or cloud model gets a condensed version of the
  rules. Its summary, reasons and concerns are then cleaned of the two tells
  with one right answer (connector dashes and curly quotes), and verdicts
  stored earlier are cleaned the same way when shown. Anything in quotation
  marks is left as written, because it quotes the advert.
- **Page quotes** from the still-open check are never rewritten: they must
  match the page word for word.
- **The app's own wording.** Every message, label, hint, error, report line
  and email subject was written by a model too, and about 90 used a dash as
  a connector; they are rewritten ("Title at Company", "no credential. Get a
  free key at ...", "Server stopped. Reconnecting..."). The Markdown
  report's bold-label list is plain. A test now fails if a tell reappears
  in any string the app shows. Two dashes stay because they are data: the
  gate that counts dashes, and the address parser that splits on them.

`humanize.find()` catches the patterns with fixed wording. Triads, closers
that restate a point, and sentences that add nothing still need a reader.

---

## Changed — 2026-09-28 — duplicate job posts are grouped, not hidden

Copies of one job — an aggregator reposting it, or the same job on an
aggregator and the employer's board — were collapsed on display by company
and title. Three things were wrong with that, and `grouping.py` fixes them.

- **Different places were merged.** "Software Engineer" at one company in
  Chicago and in Austin became one post, and the other vanished. The group
  key now includes the place: resolved city and state, "remote", or the
  location text when it could not be resolved. On this database that
  brings back **25 job posts** that were hidden.
- **Decisions stayed on one copy.** Mark the shown copy applied, and when
  another copy became the shown one (its advert grew), the job came back as
  new. `set_status` now writes every copy in the group.
- **A dead link closed a live job.** The listing check closed a job when one
  copy was gone. Now it closes only when **every** copy is; the last copy
  found closed is the one that closes it. **10** copies had been closed
  while their job was still up elsewhere.

Every copy is kept. The list shows one per group — one not known to be
closed, then the fullest advert, then the best score — with a **+N copies**
chip; the job's dialog lists **Also posted at** with each copy's link and
its own listing state, so a dead link has a working fallback. The counter
adds "· N duplicates grouped".

Schema v6 unifies statuses already split across copies (the latest real
decision wins, its note fills empty notes) and reopens copies the check had
closed while another copy was live.

---

## Changed — 2026-09-28 — quieter status, and what each Setup page is for

- **Connection status only when it matters.** The permanent "live" line is
  gone. When the page loses the server (stopped, crashed, terminal closed)
  an amber **Server stopped — reconnecting…** appears above the theme
  switch, and disappears once it is back. The running-job name under it is
  gone too; the Dashboard dot already says that.
- **ⓘ on every Setup item.** Hover it — or tab to the item — for a short
  explanation of that page (Search, Resume, Sources, AI, Tools). The tip
  floats beside the nav so the nav's scrolling cannot clip it. Native hover
  titles now appear only in the collapsed rail, where the names are hidden.

Caught while testing: the new status notice briefly reused the id `status`,
already taken by the Job posts status filter — the filter's options went
into the notice and the list asked for status "undefined". Renamed, and the
page now has no duplicate ids.

---

## Changed — 2026-09-28 — a new nav, and "job posts" everywhere

### Navigation

The side nav is rebuilt: a logo and name at the top, a solid icon beside
every item, and the page you are on as a filled pill — pale blue with blue
text in light mode, slate with white text in dark, on a deep navy panel.
**Job posts** carries a badge counting new posts; **Dashboard** a dot while
a job runs. At the bottom: connection status, and a **Dark mode** switch
that overrides the system setting in either direction (remembered in this
browser). The chevron beside the logo folds the nav to an icon rail (also
remembered); below 760px wide it is always the rail. Theme tokens now
follow the toggle, so every page, not just the nav, switches.

### "Roles" is "job posts" in everything you read

The dashboard, terminal help and output, error messages, the digest email
(subject included) and the HTML and Markdown reports now say "job post".
Unchanged, on purpose: output file names (`roles.json`, `roles.md`,
`roles.csv`), which scripts may read; the `roles` database table; API paths;
code identifiers, comments; and prompts sent to models.

---

## Changed — 2026-09-28 — "Job posts", and Tools under Setup

The nav's **Roles** is now **Job posts** (with "open job posts" in its
filter and "AI: judge top job posts" on the Dashboard). **Tools** moved
under Setup, after AI, leaving the top of the nav to the two pages used
daily: Job posts and Dashboard.

---

## Changed — 2026-09-28 — Scan and Activity are one Dashboard page

Two pages showed the same jobs twice: Scan had the buttons and a live log,
Activity had the progress, hosts, AI calls and a second log. They are now
one **Dashboard** page (nav: Roles, Dashboard, Tools): the job buttons on
top — run a scan, fetch missing adverts, re-apply filters, check still
open, AI judge — and the activity dashboard below, for any job started here
or in the terminal. One log, read from the database; a job started from the
page appears on it at once. A refused start (another job running, no model
set up) shows beside the buttons. The nav dot for a running job moved to
Dashboard. Tools keeps its own log for discover and digest.

`check` no longer prints a line per listed or maybe-gone role — they come
in hundreds and say the same thing; the summary counts them.

---

## Fix — 2026-09-28 — dead Adzuna links were marked "listed"

Opening many Adzuna roles gave "page not found", while the check called all
652 of them listed. Two causes:

- **Re-scoring counted as seeing.** `rescreen`, `enrich` and a pasted advert
  all went through `upsert`, which set `last_seen` to now — so after any
  rescreen every role looked freshly listed. `upsert(role, seen=False)` now
  leaves `last_seen` alone; only a scan or `add` (a source actually listing
  the role) moves it.
- **A month-old scan vouched for its ads.** The only Adzuna scan that
  returned anything ran 2026-08-28; Adzuna ads mostly expire within about a
  month. Now, for **every source**: when the last scan that returned roles
  from it is over **15 days** old, its roles are `stale`, shown as **maybe
  gone**, with the source, the scan's date and its age on hover. Direct
  evidence read during the check itself — the posting page open or closed,
  or missing from a fresh scan — still wins, because it is newer than any
  scan. After a fresh scan, roles missing from it are `unlisted` as before;
  the timestamps the old bug left behind are older than any new scan, so
  they read correctly without being rewritten.

`jobdork check --platform adzuna` checks one platform only.

---

## Added — 2026-09-28 — Activity page: every job, from any process

The dashboard's live log only ever saw jobs the dashboard started; a scan or
check run from the terminal was invisible to it. Jobs now record themselves
in the database (`telemetry.py`, tables `activity` and `activity_events`),
and the new **Activity** page reads from there, whoever started the job.

- **Header** — job, state (running / done / failed / stopped, plus *quiet*
  when the heartbeat is over 20s old and *died* when its process is gone),
  where it was started, pid, and its latest line.
- **Tiles** — progress (done / total, %), rate per minute, time left or
  time taken, requests (with rate-limited count), AI calls with average time.
- **Outcomes** — a stacked bar of the job's counters (closed / still open /
  maybe gone for a check; strong / possible / weak for judging; kept /
  dropped for a scan), status colours always paired with their labels.
- **Network, by host** — requests, 2xx/3xx, 4xx, 429, failures, average and
  slowest time. **AI calls** — per model: calls, failures, average, slowest.
- **Postings, by listing state** — counted from the roles themselves, with
  how many were checked in the last ten minutes, so work from a process that
  records no telemetry still shows.
- **Log** — the job's last 120 lines. **Recent jobs** — click one to inspect
  it.

Refreshes every 2s while open, every 10s otherwise (to light a dot on the
nav item while anything runs). Recorded: counts, hosts and timings only —
never request bodies, page text, adverts or keys. Writes are batched (one
per second plus a 5s heartbeat) on their own connection, and a telemetry
failure never stops the job. `scan`, `enrich`, `check`, `judge`,
`rescreen` and `generate` are recorded from the terminal too. The last 200
jobs are kept.

Also: `[hidden]` now always hides — `.dot`'s `display` rule had been
overriding it.

---

## Added — 2026-09-28 — an AI reader, and checking postings are still up

### AI page — local or cloud model

New **AI** page under Setup. Pick **Ollama (local)**, **Claude**, **Gemini**
or **ChatGPT**; the model list is read live from the provider (Ollama's
from `/api/tags`, the others from their models endpoints with your key).
**Save and test** makes a one-line round trip. Settings go to the `llm:`
section of the config — provider, model, Ollama address, and two opt-ins:

- **After each scan, judge the top N roles** not yet judged (default 25).
- **When checking postings, read pages that do not say** whether the job is
  open.

What the model does: reads the full advert against your resume and returns
a 0-100 verdict (strong / possible / weak) with a summary, reasons for and
concerns against. It shows as a third badge, `AI 85`, beside match and fit,
with the reasoning on hover. It never drops or hides a role. **Ask AI** in
the role dialog judges one role; **AI: judge top roles** on the Scan page
runs the batch; `jobdork judge` does it from the terminal. A role is judged
again when its advert grows (pasted or enriched).

Adverts are fenced as untrusted data, answers are constrained to a JSON
schema where the provider supports it, and every field is clamped and
clipped before storing. Thinking models on Ollama (gemma4) are asked not to
think — otherwise they spend the token budget reasoning and are cut off
mid-answer.

### API keys — memory only

A key typed on the AI page is held in the server's memory as bytes
(`llm.VAULT`) and never written to the config, database or a log, and never
sent back to the page. It is overwritten and dropped when jobdork stops
(Ctrl-C or `kill`), when you click **Forget**, and after no dashboard tab
has been open for 60 seconds (a running job keeps it until it finishes).
A key put in `config.yaml` under `llm:` is refused at load. The terminal
commands use `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY` or
`OPENAI_API_KEY`. Claude needs `pip install -e '.[ai]'` (the Anthropic
SDK); the others use `requests`.

### Checking a posting is still up

**Check still open** on the Scan page, **Check if still open** in the role
dialog, `jobdork check` in the terminal. Evidence decides, not guesses:

| Evidence | Result |
|---|---|
| HTTP 404 or 410 (Workable answers 410) | closed |
| redirect to `?error=true` (Greenhouse's closed-job redirect) | closed |
| schema.org `validThrough` in the past (USAJOBS) | closed |
| the page says it: "no longer accepting applications", "position has been filled" | closed |
| gone from the employer's Ashby board API | closed |
| page still carries the JobPosting, or still on the Ashby board | open |
| page loads and says nothing | the AI reads it, if allowed — its "closed" counts only with a quote found on the page |

The wording is tight on purpose: every open USAJOBS posting says it "will
no longer be available once the announcement has closed".

A role found closed, and still `new`, `viewed` or `interested`, moves to
`closed` with the evidence as its note; one you applied to or are
interviewing for keeps its status. **Adzuna cannot be checked** — its
pages refuse scripts — so its roles are only `listed` or `unlisted`
(missing from Adzuna's latest results), shown as **maybe gone**, never
closed automatically. Results show on the card (`closed`, `maybe gone`)
and in the dialog, with the evidence on hover. A role checked in the last
12 hours is skipped unless forced.

Schema v5: `roles.llm_score`, `llm_judgement`, `listing_state`,
`listing_note`, `listing_checked_at`, none of which a rescan overwrites.

---

## Added — 2026-09-28 — hover match or fit to see why

Match and fit were two differently styled bits of text with a generic
tooltip. They are now a matched pair of badges — `MATCH 80`, `FIT 5 / 25`,
same size and weight, small-caps label, bold figure — and hovering or
tabbing to either opens a card that explains that role's number:

- **match** lists every rule with its points and the reason: which
  `titles.include` term matched, the arrangement, the distance against your
  radius with the formula (and, at 0 mi, that the posting only gave a city
  so it was measured to the city centre), what the salary was compared
  with, any soft dealbreakers, and resume fit — totalled at the bottom.
- **fit** says how many of the advert's skills you have and how that became
  the number, including when a short advert was counted out of 5, then
  lists the skills on your resume in green and the ones asked for but
  missing.

Screening now records these as `roles.score_parts` (JSON, schema v4). A
role not screened since shows "Tools → Re-apply filters fills this in".

---

## Fix — 2026-09-28 — the score is labelled "match"

A bare number beside `fit 5/25` read as a second, unexplained score. It is
now `match 80` on cards, in the role dialog and in the HTML and Markdown
reports, with a tooltip naming what it adds up: title, arrangement,
distance, salary and resume fit. CSV keeps its `score` column name so
existing spreadsheets still line up.

---

## Fix — 2026-09-28 — fit shown beside the score, and teasers stop scoring 100

Three Adzuna roles sat at exactly 100. Not a cap — every part of the sum had
maxed: title 30, arrangement 10, distance 30 (Adzuna says "Chicago,
Illinois", which resolves to the anchor itself, so 0.0 mi), salary 5 (no
floor set), and resume fit 25 of 25 — because the 500-character teaser named
one skill, and one of one is 100%.

### Changed

- **Fit is stored and shown on its own.** New `roles.fit` column (schema
  v3), shown as `fit N/25` next to the score on each card, in the role
  dialog, and in the HTML, Markdown and CSV reports (`fit` is appended as
  the last CSV column so existing column positions hold). A role with no
  resume or no advert shows `–`, not 0.
- **A thin advert cannot score full fit.** The share is taken of at least
  `MIN_SKILLS` (5) skills, so a teaser naming only "java" scores 5 of 25, not
  25. A full advert you match entirely still scores 25.

### Fixed

- **A rescan overwrote fuller adverts with the teaser.** Scan screened, and
  stored, whatever the source sent this time — so an advert recovered by
  `enrich` went back to 500 characters on the next Adzuna run. Scan now uses
  the stored advert when it is longer, for screening and storage both.
- **`rescreen` skipped duplicate copies.** It walked the list with
  duplicates collapsed, so 127 hidden copies kept their old scores, and
  because the collapse ranks by score, a stale 100 then outranked the
  re-screened 80 and became the copy shown. It now re-screens every row.

### Added — paste the advert

Adzuna cannot be enriched: the API caps adverts at 500 characters, and its
pages answer scripts with a CloudFront `403 Request blocked` (re-checked
today, `robots.txt` included), which this tool does not work around. The
browser can read the page, so the role dialog now has a **Paste the full
advert** box — open by default when the stored advert is 600 characters or
fewer — that stores the text and re-screens the role on it
(`POST /api/advert`). A role that no longer passes is marked skipped with
the reason, as `enrich` does.

---

## Fix — 2026-09-28 — set a role's status from its detail view

The role dialog showed the advert but no way to act on it, so you had to
close it and use the card's dropdown. Its header now carries one button per
status you decide — interested, applied, submitted, interviewing, offer,
rejected, withdrawn, skipped, closed — with the current one filled in its
colour. `new` and `viewed` are left out: those are recorded for you. The
dialog also no longer calls `showModal()` on itself while already open,
which it did every time a status changed with it showing.

A status change keeps the dialog on the tab you were reading — a drafted CV
stays a drafted CV instead of snapping back to the advert. And acting on a
card no longer reopens that role's dialog after you have closed it.

---

## Fix — 2026-09-28 — `run.sh` points at the package

`run.sh` still ran `main.py`, which the package layout removed, so it died
with `can't open file '.../main.py'`. It now runs `python -m jobdork "$@"`,
and with no arguments it runs `serve`, so `./run.sh` opens the dashboard.

---

## 0.15.0 — 2026-08-30 — the page can do everything the terminal can

Eight commands existed only in the terminal, so the dashboard was a viewer
with four buttons. It is now a front end over the same functions — not a
second implementation, the same `scan`, `enrich`, `discover`, `generate`,
`digest` and `add` that `cli.py` calls — so there is nothing to drift.

### Added — every command, in the page

| | |
|---|---|
| **Scan** | already there, now beside enrich and rescreen |
| **Enrich** | fetch the full advert where only a summary arrived |
| **Re-apply filters** | `rescreen`, after changing your search |
| **Add a posting** | paste a link you found yourself |
| **Discover** | find an employer's board and add it, reading the token off their page |
| **Digest** | mail the list, with the CSV attachment option |
| **Generate** | screen, CV and cover letter, per role |
| **Sources** | what runs, what does not, and why |

Every long one reports over the event stream, so drafting a CV is watched
rather than waited for. Still one job at a time, and a refusal now names what
is holding the runner.

### Added — a role detail view

Clicking a title opens the advert in full, with tabs for anything generated
for it. **A document drafted in the terminal is readable in the page**, with
its gate results beside it — which is the parity the two front ends were
supposed to have and did not.

The draft buttons are disabled, with a reason, when the `claude` CLI is not on
PATH. Everything else keeps working; the feature that needs a tool you do not
have says so rather than failing when clicked.

### Added — `viewed`

A new status, between `new` and `interested`, set when you open a role.
Without it a role you have read and not decided on is indistinguishable from
one you never opened, which is the exact thing a scanner is supposed to
remember for you.

### Added — resume upload

Drop a `.pdf`, `.docx`, `.md` or `.txt` in the page; it is parsed immediately
and reports back how many characters, years and skills it found, so a resume
that cannot be read is caught at upload rather than silently scoring every
role at zero.

**The browser's filename is used for exactly one thing — reading its
extension.** The file is written to a name and directory this code chooses.
Verified: an upload claiming to be `../../../.ssh/authorized_keys` is refused
on its extension, and nothing is ever written outside the data directory.

### Security

- **A generated document is fetched by artifact id, never by path.** Only
  files this tool recorded writing can be read, so a bug in the front end
  cannot turn the dashboard into a file browser. A non-numeric id is 400, an
  unknown one 404, and a recorded file that has since been deleted is 410
  rather than a blank page.
- Every new endpoint is behind the same token and Host checks as the rest.

---

## 0.14.0 — 2026-08-30 — a live dashboard, and localhost is not a boundary

Groundwork for whichever way this gets packaged. Every route — a desktop app,
a container, or just running it here — needs this and none of it is wasted.

### Fixed — the server had no authentication at all

`serve` validated the Host header and nothing else. That stops a web page
reaching it under DNS rebinding; it does nothing about another program on the
same machine. **Any process running as you could `curl 127.0.0.1:8765/api/roles`
and read every role, note and status, or POST changes to them.** It was
described as "local only" as though local meant safe.

A token is now minted per run, printed once as part of the URL, held in memory
by the page and sent as a header afterwards, and compared in constant time. It
is not stored and it dies with the process. Verified live: no token 401, wrong
token 401, right token 200.

### Fixed — a hardcoded port

8765 collides, with another jobdork or with anything else that liked the
number. The port is asked for rather than assumed: the preferred one is tried,
a free one is taken if it is busy, and the actual port is printed so a parent
process can read it instead of guessing.

### Added — a scan you can watch

A scan takes minutes, which is exactly when it is worth watching: a rate limit
or a dead board shows up in the middle, not at the end. It now runs on a
background thread and reports through server-sent events — plain HTTP, no
library, no websocket.

```
[status  ] scan started
[progress] ashby: 109 roles, 1 requests
[progress] adzuna: 818 roles, 25 requests
```

**One at a time, refused rather than queued.** Two scans racing would double
every request to hosts that are deliberately paced, and the second would earn
the rate limit the first was avoiding. A second trigger answers
`a scan is already running`.

A subscriber that has stopped reading — a closed tab the server has not
noticed — fills its queue and is dropped, rather than blocking the scan that
is trying to report progress.

### Added — settings in the page

Titles, location, radius, units, countries, arrangements, salary floor and
resume path, edited without opening YAML. The file is written, then re-read
through the normal loader; **an edit that would not survive `jobdork scan`
cannot be saved**, and a rejected edit is rolled back to the file that was
there before. Credentials are not in the payload and are not touched.

### Added — the advert cap, made visible

A role whose advert is 500 characters now says so in the list: *advert 500
chars — too short to screen*. Dealbreakers and fit scoring both read the body,
so that number is the difference between a screened role and a guess.

### Also

- Body limits are per endpoint. A status change is a uid, a word and a note;
  a config save carries every title. Letting the config's limit apply to
  actions meant accepting a quarter-megabyte note, which a test caught.
- A Content-Security-Policy of `default-src 'none'` with `connect-src 'self'`,
  so a script injected through a job title still cannot phone home.
- 21 tests for the server, covering the token, the port, the stream, the
  one-scan rule and config rollback. 142 in total.

---

## 0.13.1 — 2026-08-29 — Workable is back

### Resolved

- **The Workable rate limit expired.** `jobs.workable.com` answers 200 again;
  a `security analyst` search in Chicago returns 512 results. Nothing was
  fixed and nothing needed to be — the circuit breaker read the refusal
  correctly and waited it out, which was the whole design.

  It cost roughly 24 hours of the widest keyless source, and it was earned by
  re-running full scans to test config changes. `scan --limit` exists for that.

- **The backlog is empty.** Every item that has been in *Still outstanding*
  has either shipped or expired. The section is kept as a heading, with the
  standing operational notes that are not work: Adzuna's permanent advert cap,
  SmartRecruiters' ambiguous silence, and Workable's temper.

### Changed

- Ruff's per-file ignores for `jobdork/dork/` extended to `RUF005` and `E741`.
  The generator was moved rather than rewritten, and linting 992 working lines
  to today's style is the change-for-its-own-sake that decision avoided.
  `ruff check .` is clean.

---

## 0.13.0 — 2026-08-29 — the review pass

Six structural problems raised in review. Five accepted as stated, one accepted
with a caveat.

### The dork generator lives in the package now

`main.py` and `config.py` sat at the repository root and were reached by
`runpy.run_path` on a hardcoded path — a hack that worked and would break the
first time the file moved. They are now `jobdork/dork/generator.py` and
`jobdork/dork/boards.py`, and there is a real entry point:
`python -m jobdork.dork`. `jobdork dork ...` still dispatches with the
generator's own flags intact.

**The generator itself was not rewritten.** It works, it is well documented,
and rewriting it would have been change for its own sake.

**Fixed during the move:** it resolved logs, `.env` and result files relative
to its own file, so moving it moved the user's files into the package.
`PROJECT_ROOT` now points where it did before.

### Schema migrations

`CREATE TABLE IF NOT EXISTS` gets a database created and then quietly stops
being enough — it cannot add a column, and a database created before a column
existed keeps opening cleanly and fails on the first write that mentions it.

`jobdork/migrations.py` runs numbered, append-only, forwards-only steps, each
in its own transaction, with the version in `meta.schema_version`. A database
newer than the code is refused rather than opened.

The first step reconciles `roles` against every column the current schema
expects, which closes the gap for good rather than for one column. Your
database migrated in place: **888 roles, 10 artifacts and 6 statuses intact.**

Eight tests build the case that cannot be reached by using the tool — an old
database opened by new code — including a step that fails mid-way and must
leave the version where it was.

### `pyproject.toml` is the only place dependencies are declared

`requirements.txt` now contains `-e .` and a comment explaining why. Two lists
of dependencies drift, and the one that drifts is the one nobody edited.

Same problem, same fix, for the version: `__version__` reads installed package
metadata instead of a second literal. **`jobdork --version` had been reporting
0.2.0 through five releases.**

### ruff, configured and clean

75 issues at the start, zero now. The configuration says which rules are
ignored and why — `BLE001` because catching broadly around one job board is
deliberate and commented at every site, `RUF001` because en dashes in salary
ranges are correct punctuation rather than confusables.

### Screening heuristics are configurable

`BLOCKERS` and the work-mode patterns were hardcoded. They encode a judgement
about one job market — "program" turns an engineering manager into a different
job in the US and may not elsewhere — and a judgement baked into source is one
nobody can disagree with.

```yaml
screening:
  blockers: [product, business, program, sales]
  loose_gap: 2
  office_patterns: ["in the Chicago office"]
```

Extra patterns are **merged** with the built-in ones rather than replacing
them, so adding one never silently loses the defaults. A broken pattern stops
the run, like every other regex in the config. Defaults are unchanged, so a
config that says nothing behaves exactly as before.

### pytest, with the custom runner kept

Accepted with a caveat. The suite is plain functions and asserts, so pytest
already collected all of it — this was configuration, not a rewrite, and
`[tool.pytest.ini_options]` now provides it.

`tests/run_all.py` stays, and is not redundant. It runs the same files **with
nothing installed**, which is what makes a fresh clone testable before
`pip install`, and it exists because CI once ran one test file and reported a
confident pass over the rest. Both are wired up; they run the same 132 tests.

---

## 0.12.2 — 2026-08-29 — documents go in Documents

Generated CVs, cover letters and screens were being written to
`~/job-applications`, dropped straight into the home directory. That is not
where documents belong on any of the three platforms this runs on.

### Changed

The default is now the user's **Documents** folder — `~/Documents/job-applications`
on macOS and Windows, and on Linux whatever `XDG_DOCUMENTS_DIR` or
`~/.config/user-dirs.dirs` says it is, because a localised desktop calls it
`Dokumente` or `Documentos` rather than `Documents`.

If none of those resolves to a real directory the home directory is used
rather than creating a `Documents` folder that the machine had evidently
chosen not to have.

`--dir` still overrides everything.

### Migrated

The seven folders already written to the old location were moved, and **ten
artifact rows in the database were repointed** — moving the files alone would
have left every recorded screen and CV pointing at a path that no longer
existed, which is the sort of breakage that only shows up weeks later when
somebody clicks one.

---

## 0.12.1 — 2026-08-29 — dealbreakers, and a duplicate picking the wrong copy

### Fixed — the dedupe was showing the worse copy

Adding employer boards produced the same Vectra role twice: truncated to 500
characters from an aggregator, and complete at 4,701 from the company's own
Greenhouse board. **The list showed the 500-character one.**

Duplicates were ranked by score alone, and the truncated copy scored *higher* —
a tidier location string, and no advert content on which to lose points.
Nothing about that is visible from the outside; it just quietly hands you the
version that cannot be screened, since dealbreakers and fit scoring both read
the advert body.

The fuller advert now wins, and score only breaks ties between copies that say
as much as each other. Bucketed by thousands of characters, because 4,700 and
4,900 are the same advert and the score should decide between those.

### Added — six dealbreakers, all soft

```
extended client-site travel · unpaid take-home · heavy on-call
active clearance required · contract or staffing agency · relocation required
```

Every one starts `hard: false`, which shows the role with a warning rather
than hiding it. None of these is a preference anybody stated; promoting one to
`hard: true` is a decision for the reader once they are sure.

They caught **29 roles** on the first pass. One of them is the cross-check
worth having: the ITRS role that the `screen` had independently flagged for
buried travel expectations was caught by the regex too — a model reading the
advert and a pattern matching it agreeing about the same sentence.

**Widened while testing:** the travel pattern missed its own motivating
example. The advert reads "consecutive weeks **are spent** full-time at a
client site", and the pattern allowed no intervening words.

Dealbreakers only fire on adverts long enough to contain them, so they are
quiet on the 500-character aggregator rows and useful on the rest — another
place the cap costs something.

---

## 0.12.0 — 2026-08-29 — employer boards, and what they are worth

Not a code change. `sources.companies` had been empty since the scanner was
built, so all five per-employer adapters fetched nothing and every advert came
from an aggregator that truncates at 500 characters. `discover` existed to fix
that and had never been pointed at anything.

### Added

Eight boards, found with `discover` and verified before being written:

| Company | Platform | Token |
|---|---|---|
| Vectra | greenhouse | `vectranetworks` |
| Tenable | greenhouse | `tenableinc` |
| Enova International | greenhouse | `enova` |
| Huntress | greenhouse | `huntress` |
| Dragos | greenhouse | `dragos` |
| Expel | greenhouse | `expel` |
| Vanta | ashby | `vanta` |
| Drata | ashby | `drata` |

`vectranetworks` and `tenableinc` are the argument for reading tokens rather
than guessing them.

### Measured: this is what the aggregator cap costs

| Source | Roles | Average advert | Arrangement unstated |
|---|---|---|---|
| ashby | 17 | **6,375 chars** | 0 / 17 |
| greenhouse | 16 | **5,896 chars** | 0 / 16 |
| workable | 200 | 4,903 chars | 0 / 200 |
| usajobs | 2 | 4,121 chars | 2 / 2 |
| adzuna | 653 | **500 chars** | **517 / 653** |

Resume fit scoring reads the advert body, and the difference is not subtle. The
same feature, on the same resume:

```
adzuna, 500 chars   fit: has security
ashby, 6,375 chars  fit: has compliance, penetration testing, security;
                         wants hipaa, iso 27001, soc 2, vulnerability management
```

The second is a gap analysis. The first is a coincidence.

### Also learned

Most large employers are on Workday, which has no adapter here — `arcticwolf`,
`relativity` and others were located and named as such rather than reported as
"nothing found". Several more, including `rapid7`, `cloudflare`, `datadog` and
`sproutsocial`, render their careers pages in JavaScript and expose no token to
read, so `discover` correctly declined rather than guessing.

Eight boards from nineteen employers tried. The hit rate is the reason
`discover` reports four distinct outcomes instead of found/not-found.

---

## 0.11.1 — 2026-08-29 — what the first live generation found

`generate` shipped in 0.11.0 having never been run. Two runs against real roles
corrected three things, which is the argument for running it rather than
trusting it.

### Fixed

- **The resume was outside the sandbox and therefore unreadable.** `--add-dir`
  names the job folder and nothing else, so a resume at `~/Documents` could not
  be opened. The first screen came back *"file access was not granted"* and
  assessed nothing.

  Widening the sandbox to reach it would undo the point of having one, so the
  resume is **copied into the job folder** instead and referenced by local
  name. The scope stays one directory.

- **A screen was being held to send-time gates.** It flagged
  `"$140,000 - $170,000"` as a figure not in the resume — the advertised
  salary, read correctly off the posting. Those gates guard documents you
  *send*; a screen is notes to yourself and is *supposed* to quote the advert.
  Gates are now per-kind: a screen gets a length check and nothing else.

- **Identifiers inside URLs were read as claims.** A draft quoting
  `https://www.adzuna.com/details/5792028474` had the posting id flagged as an
  unsupported figure. URLs and code spans are stripped before the check.

### What the runs showed

On a role with a **full 4,511-character advert**, the screen was worth having:
it found a title mismatch (advertised "DevOps Engineer", described a Forward
Deployed Engineer), buried travel expectations — "consecutive weeks spent
full-time at a client site" against an advert headlined as 2-days-a-week
hybrid — a currency typo in the salary, and named four requirements not on the
resume.

On a role whose advert had been **truncated to 500 characters by an
aggregator**, it refused: *"cannot screen yet. Advert is a stub. Re-scrape
before spending time."* It did not guess a match from company marketing. That
refusal is the behaviour worth having, and it is the Adzuna cap showing up
where it costs something.

Both runs ended with the model reporting, as instructed, that nothing inside
the advert markers had attempted to issue instructions.

### Also

- **`sources` reported USAJOBS as active for a reader outside the US**, while
  the adapter skipped itself. The report and the behaviour now agree, and the
  reason is printed.
- Screenshots of the dashboard and the static page added under
  `docs/images/`.

---

## 0.11.0 — 2026-08-29 — `generate`

Screens a role, and drafts a CV or a cover letter, by spawning headless
`claude -p`. The last feature on the list, and the only one that spends money.

### Added

```bash
jobdork generate <ref> -k screen         # do this first: seconds, pennies
jobdork generate <ref> -k cv
jobdork generate <ref> -k cover_letter   # refused until the CV exists
jobdork generate <ref> --dry-run         # the prompt and the command, spending nothing
```

The Claude Code CLI rather than the API, deliberately: the agent reads your
resume off disk, writes the draft, and is checked by scripts afterwards.
Through a bare API call all of that would be reassembled out of prompt text,
and the drafting quality lives in the reading and writing. The desktop chat
app ships no command-line entry point and cannot be driven from here.

Documents land in `~/Documents/job-applications/<date>-<company>-<role>/` alongside a
**snapshot of the advert**. Postings are pulled the moment they are filled,
which is usually just before somebody calls you about one.

**Nothing generates unless you ask.** No schedule, no watcher, no speculative
drafting.

### The gates are scripts, not judgement

A model asked to re-read its own draft will say it looks fine. A script
counting em-dashes says how many there are.

| Gate | What it catches |
|---|---|
| **unsupported figures** | any number or scale word in the draft that is not in your resume |
| **phrase overlap** | a cover letter repeating the CV — no run of six words may appear in both |
| **em dashes** | more than two |
| **length** | a draft that came back empty |
| **slop score** | the natural-writing linter, when installed — and it says so when not, rather than passing silently |

`unsupported figures` is the one that matters. A tailored CV is the easiest
place in a job search to acquire a statistic nobody can back up. Tested: a
draft claiming "2.5 million" and "tripled" against a resume that says neither
is caught on all three, while the figures that *are* in the resume are not
flagged. Dates and small integers are ignored — they are list counts, not
claims.

**Nothing is redrafted automatically.** A failed gate means read this before
you send it, not this is broken; a second pass would cost tokens you did not
ask for. Results are recorded against the document either way.

**The cover letter is refused until the CV exists**, so the overlap gate has
something to compare against. The CV carries the facts, the letter carries
judgement, and they should share nothing but your name.

### A job description is hostile input

It comes from thousands of third-party servers, anybody can post a job, and
here that text lands in a prompt *and* in the working directory of a
subprocess that can write files. Each of these is tested:

- **Fenced and labelled**, with the fence markers stripped out of the advert
  first — verified with an advert that tries to close the fence and continue
  as instructions. Exactly one marker of each survives, and the injected text
  remains inside as data. Neutralised by position, not by censorship.
- **Every prompt states** that everything inside the fence is a claim about a
  job, never an instruction, whatever it says or claims to be from.
- **The subprocess is scoped to one folder.** `--add-dir` names that
  directory and nothing else — never `~/.claude/skills`, which would be write
  access to every skill you own. A compromise damages one role's folder.
- **Links are scheme-checked.** `javascript:`, `data:` and `file:` never reach
  a file; the line reads "link withheld: unsafe scheme".

None of this makes an agent immune to persuasion. Prompt injection has no
complete fix, and a determined posting may still get odd wording into a draft
you were going to read anyway. The blast radius is one folder and one
document.

### Recorded

Each run writes an `artifacts` row with the path and the gate results, so
"which roles have a CV but no application" stays one query. Drafting a
document moves a role from `new` to `interested`; screening does not, because
screening is how you decide.

---

## 0.10.0 — 2026-08-29 — SmartRecruiters verified

Two of the three "not fixable here" items turned out to be fixable, once
something answered.

### SmartRecruiters was never broken, only silent

Ten well-known company names in a row returned HTTP 200 with `totalFound: 0`.
On this platform that is also what a throttle and a non-existent board look
like, so none of them proved anything either way — which is why the adapter
shipped marked unverified rather than assumed working.

`Bytedance` finally returned rows, and real data corrected three guesses:

- **`location.fullLocation` is already assembled** — "Mumbai, MH, India".
  Building the string from `city, region, country` produced "Mumbai, MH, in",
  because `country` is a lowercase two-letter code. The assembled version
  geocodes; the built one does not.
- **`location.hybrid` exists alongside `location.remote`.** Reading only
  `remote` filed every hybrid role as arrangement-not-stated.
- **`ref` is the API's own detail URL.** It was winning the URL precedence, so
  clicking a stored role handed you a page of JSON. The human posting page is
  used now, and `enrich` derives the detail URL back from it.

### `enrich` gained a SmartRecruiters reader

Its public posting page carries no schema.org data, so the generic JSON-LD
reader finds nothing there. The advert lives on the detail endpoint, split
across `jobAd.sections` — job description, qualifications, additional
information and company description — and all four are joined, because a
dealbreaker about qualifications sits in a different section from one about
the role.

Verified end to end: two roles stored with empty adverts came back at 1,181
and 1,016 characters.

### Adzuna `au`, `nz` and `sg` are live again

They answered 503 while 0.3.0 was being written and were recorded as such.
Re-probed today: all three return 200. The outage was theirs and it is over —
`au nz sg` join the working indexes, and only `ph id my jp ae ru` have no
index at all.

---

## 0.9.0 — 2026-08-29 — the small gaps

Four things that were each individually minor and collectively the reason the
backlog never emptied.

### Metro names now work outside North America

`Bay Area`, `GTA` and `DMV` resolved; `Kanto`, `Klang Valley` and `Randstad`
did not. About seventy more are recognised across Asia Pacific, Europe, Latin
America, Africa and the Middle East — `Metro Manila`, `BGC`, `Jabodetabek`,
`Greater Tokyo`, `Île-de-France`, `Ruhrgebiet`, `Öresund`, `Gauteng`, `CDMX`,
`Greater Sydney`.

**One name can belong to several countries.** `NCR` is the National Capital
Region in Canada, India *and* the Philippines, and `Bay Area` is San Francisco
to most readers and Hong Kong to some. Those are settled by your configured
countries, exactly as an ambiguous region code is — a country named in the
string itself outranks even that.

**Fixed:** the cleanup turns hyphens into commas, so `Île-de-France` split into
three fragments, the last of which is a country, leaving a city called `Île`.
Metro names are now checked against the untouched string first.

### `locations.exclude` matches what a location resolved to

It was a substring match on the raw string, which is too literal to be useful:
`exclude: [TX]` matched nothing, because postings say "Austin, Texas" and never
"TX" — while `exclude: [Texas]` missed every posting that wrote the code.

An entry is now tried as a region code, then a country, then a city, then a
metro name, and finally as a substring. So `TX`, `Texas`, `Chicago`,
`Bay Area`, `Canada` and an arbitrary phrase all work.

### `jobdork add` takes many URLs

```bash
jobdork add <url> <url> <url>
jobdork add --from-file urls.txt
```

The file is one URL per line, tolerating `#` comments, `- ` bullets and
`title<TAB>url`, because that is how a pasted list actually looks.

**It reads posting URLs, not the dork generator's output.** That file holds
Google *search* URLs, and turning those into postings would mean scraping
Google's results — bot-protected, and a control this tool does not work
around. Click the results, paste the ones worth keeping.

A role that fails your filters is still stored, and says so: you asked for that
one by name, and a filter is not a better judge of that than you are.

### LICENSE

MIT, matching what `README.md` and `pyproject.toml` already declared.
Copyright held under the GitHub handle `jessn-dev`.

---

## 0.8.0 — 2026-08-29 — `enrich`

Fetches the full advert for roles stored as summaries. Dealbreakers read the
advert body, so does work-mode detection, so does resume fit scoring — a role
stored with 200 characters of teaser was waved through rather than screened,
and the flags on it were guesses.

### Added

- **`jobdork enrich`** — reads schema.org `JobPosting` JSON-LD, which posting
  pages publish for Google's benefit and which is therefore both stable and
  meant for machines.

  Measured on live pages: six roles seeded with 180-character teasers came back
  at 1,462 to 4,479 characters. **17,498 characters of advert recovered,
  2,916 average.**

- **A role whose advert grows is re-screened.** A dealbreaker that could not
  match 200 characters may well match 7,000, and leaving the old verdict in
  place would be worse than never having fetched. Three of the six test roles
  stopped passing once the real text arrived, and were marked skipped with the
  reason.

- `--dry-run`, `--limit`, `--platform`, and `--thin N` for what counts as a
  summary rather than a description.

### Adzuna cannot be enriched, and this refuses to try

Its `redirect_url` answers **403 from bot protection**. Getting past that is
breaking a control rather than declining a request, which is a line this tool
does not cross — so Adzuna is skipped by name, with the reason.

**Adzuna's 500-character cap is therefore permanent.** Worth knowing before
writing a dealbreaker that depends on advert text and wondering why it never
fires: on one run that was 653 of 855 roles.

Platforms whose adverts already arrive whole — Workable, Greenhouse, Ashby,
Lever, USAJOBS — are skipped too, rather than spending a request per role to
learn nothing.

---

## 0.7.0 — 2026-08-29 — command-line overrides

Every setting that mattered lived only in `config.yaml`, so trying a different
country meant editing a file you had tuned, or keeping several and passing
`-c`.

### Added

- `--title` · `--exclude-title` · `--anchor` · `--country` · `--radius` ·
  `--units` · `--work-mode` · `--salary-floor` · `--currency` · `--resume` ·
  `--out` · `--db`. The list ones repeat.

  ```bash
  jobdork sources --anchor "Berlin, Germany" --country DE
  jobdork list --title "penetration tester" --work-mode remote --salary-floor 150000
  ```

- **They go after the verb**, where people write them, rather than having to
  precede it — every subcommand inherits the same group.

### Deliberate

- **An override is validated exactly as the file is**, so it cannot be a
  looser way in than the config it replaces. `--country ZZ`, `--currency XYZ`,
  `--radius nonsense`, a resume path that does not exist, and a numeric radius
  with no anchor are all refused the same way they would be in YAML.

- **`--country` moves units and the Adzuna index with it.** Carrying miles
  over from a config written for Chicago into a German search would silently
  cover 2.6x the intended area, and a pinned `adzuna_countries: [us]` would
  otherwise have searched America for a Berlin reader.

---

## 0.6.0 — 2026-08-29 — `serve`

The dashboard with buttons, at `http://127.0.0.1:8765`. The same list `jobdork
list` prints, except that what you click sticks.

### Added

- **`jobdork serve`** — filter by status, scope (open / new since last scan /
  including settled) and a text box; per-role buttons for interested, apply,
  interviewing and skip, a status dropdown carrying all ten states, and a note
  field.

- **It reads and writes the same database the CLI does**, so the two cannot
  disagree. Verified both directions: a status set in the browser shows up in
  `jobdork list`, and one set by `jobdork applied` shows up in the browser
  without a restart.

- **Apply opens the posting and then records it.** Marking a role applied
  without opening it would be recording something that did not happen.

### Local only, deliberately

- **It binds to `127.0.0.1` and there is no `--host`.** A dashboard listing
  where you are applying is not a thing to put on a network, and an option to
  do it is an option somebody uses.

- **The `Host` header is validated against the address actually bound to**,
  not against `Origin`. Under DNS rebinding a page on an attacker's domain
  resolves to 127.0.0.1 and reaches this server from your browser; `Host` and
  `Origin` are both attacker-controlled and agree with each other, and the
  bound address is not. A foreign `Host` gets 421.

- **A uid must be twelve hex characters** — it is the only value from the page
  that reaches the database. Path traversal, SQL and short or long ids are all
  400.

- **`GET` cannot change anything.** A status change is not reachable by
  following a link.

- **Standard library only, no external request.** No CDN, no fonts, no
  framework; a test asserts the page contains no outside URL.

- Unknown paths are 404 rather than an attempt to read something off disk, and
  a body over 8KB is refused.

### Tests

`tests/test_serve.py` runs a real server on a real loopback port for each
case — 12 tests covering the guards above and the read/write parity, bringing
the suite to 74.

---

## 0.5.0 — 2026-08-29 — `discover`

Finds an employer's job board by reading it off their own site, so the five
per-employer adapters have something to fetch. Those boards are the fix for
Adzuna's 500-character advert cap: 653 of 855 roles in one run came back too
truncated to screen.

### Added

- **`jobdork discover <employer>`** — fetches their careers pages and takes
  the board token out of the links they publish themselves.

  ```
  $ jobdork discover vectra.ai
  Looking for vectra.ai...
    greenhouse         16 jobs  [verified]  .../boards/vectranetworks/jobs
                      board names itself 'Vectra'

  Re-run with --add to write these into your config.
  ```

  `vectranetworks` is the point. Tokens are not company names — it is also
  `mymoose` for Rapid7 and `evergreenix` for Garrison — so nothing here
  guesses one from a name.

- **`--add`** writes verified boards into `sources.companies`. The file is
  rewritten as text rather than dumped through the YAML round-trip, because
  a dump strips every comment out of a file that is mostly comments; a test
  asserts the comment count is unchanged and that a second `--add` appends
  rather than clobbering.

### Four outcomes, kept distinct

Verified against live sites while building this, one per case:

| | Example | Meaning |
|---|---|---|
| `[verified]` | vectra.ai, ramp.com | found on their site **and** the board returned jobs |
| `[token not on page]` | stripe.com | the platform is plainly there — 535 mentions of Greenhouse, a `greenhouseId` on every posting — and the board token is named nowhere |
| `[no adapter]` | crowdstrike.com | a Workday board, located and named rather than folded into "nothing found" |
| `[empty board]` | — | answered 200 with no jobs, which on Ashby and SmartRecruiters is also what throttling looks like |

**Only `[verified]` can be added.** An unread board is a guess, and banking a
guess into the source list is worse than leaving it out — a board that answers
is not proof you found the right company. On Ashby, `primer` is a Florida
micro-schools operator; on Greenhouse, `peak` is a Texas physiotherapy chain.
Where the platform states the employer, the board's own claim about itself is
printed next to the result so a mismatch is visible.

### Fixed while building it

- **The `embed/job_board/js?for=` script-tag form was not matched**, which is
  how Vectra publishes theirs. Missing it lost a board whose token is nothing
  like the company name — exactly the case this command exists for.
- **The listing page often carries the token where the landing page does
  not.** `stripe.com/jobs` has no board reference at all; `stripe.com/jobs/search`
  has 535. `/jobs/search` and `/careers/search` are now tried.
- **A company name is refused rather than turned into a domain.** Guessing
  `acme.com` from "Acme Corporation" is the same mistake as guessing a token
  from a name.

---

## 0.4.0 — 2026-08-29 — Email digest

The roles come to you now. A dashboard is something you have to remember to
open; a digest arrives, and what arrived with it is what was not there before.

### Added

- **`jobdork digest`** — mails what the last scan found, without rescanning.

  ```bash
  jobdork digest --email you@example.com          # only what is new
  jobdork digest --all --csv --email you@...      # everything open, CSV attached
  jobdork digest --dry-run                        # print it, send nothing
  ```

- **`jobdork scan --email`** — one command for a cron job: fetch, screen,
  store, write the files, then mail the new roles. The mail is sent *after*
  the files are written and its failure is reported without unwinding the
  scan, because a mail that bounces must not cost you the roles it was about.

- Plain-text and HTML bodies, and an optional CSV attachment written through
  `render.to_csv` rather than a second implementation — so the columns in your
  inbox and the columns in `out/roles.csv` cannot drift apart. A test asserts
  the two headers match.

- Credentials are the two the dork generator already uses, `RESEND_API_KEY`
  and `RESEND_FROM` from `.env`, including its older `JOB_DORK_EMAIL_FROM`
  spelling.

### Fixed

- **"New" meant "first seen on the most recent calendar date."** That looks
  equivalent to "first seen in the most recent scan" and is not: scan twice in
  one day and the second digest resends everything the first one already sent,
  and a day with no scan at all reports yesterday's roles as new. It is now
  anchored to the last completed run in the `runs` table, falling back to the
  date rule only when no run has ever been recorded.

### Deliberate

- **An empty digest is not sent** unless you pass `--even-if-empty`. A mail
  that says "nothing new" every morning trains you to ignore the one that says
  something.

- **Building a digest never needs a credential**, only sending does, so
  `--dry-run` works on a fresh clone and the rendering is testable without a
  key.

- **A missing or wrong credential is named**, with the URL to fix it, rather
  than failing silently or exiting the process out from under a scheduled
  scan.

---

## 0.3.1 — 2026-08-29 — Markdown and CSV output

### Fixed

- **`output.formats` accepted `md` and `csv` and wrote neither.** Config
  validation passed them and `cli.py` only handled `html` and `json`, so
  asking for Markdown produced nothing and reported success — the one silent
  failure left in a config layer built to refuse exactly that.

  Both are now written. `out/roles.md` is the list as text, for pasting into a
  note or an email; `out/roles.csv` is one row per role across 18 stable
  columns, with the advert left out because a 5,000-character description in a
  spreadsheet cell breaks every viewer that opens it. `salary_stated` is its
  own column, because a blank pay range means nobody published one and that is
  not a zero.

  `markdown` is normalised to `md` at load, so the two cannot reach the writer
  as different strings. A test now asserts that every format the validator
  accepts has a writer behind it, and an unknown format still stops the run.

---

## Still outstanding

Nothing. Every item that has been in this section has moved into an entry
above, and the last one — a rate limit that was somebody else's clock —
expired on its own.

It is kept as a heading rather than deleted, because the next gap goes here
and a section that has to be re-invented is a section that gets skipped.

### Operational notes, not work

- **`jobs.workable.com` bans hard.** The ban that ran through 0.6.0 to 0.12.x
  was earned by re-running full scans while tuning a config: fifteen
  consecutive 429s, then a `Retry-After` of 86,130 seconds. Cleared 2026-08-29.
  Use `scan --limit` while experimenting.
- **Adzuna adverts are capped at 500 characters and cannot be enriched** — its
  links answer 403 from bot protection, which this tool does not work around.
  That cap is permanent, and it is the reason employer boards matter.
- **SmartRecruiters answers 200 with `totalFound: 0`** for a throttle and for
  a board that is not there alike. An empty answer from it proves nothing
  either way.
- **Uncommitted:** every entry above "list --json, and a connection left
  open" exists only in the working tree. `b3f5f87` is the last commit.

---

## 0.3.0 — 2026-08-28

Removes the North America assumption. The tool now works from any country.

### Changed

- **`locations.countries` accepts any ISO 3166-1 alpha-2 code.** It was an
  allow-list of `US` and `CA`, backed by a hardcoded list of "foreign"
  countries to drop. That design would have silently deleted a Manila reader's
  entire market. Out of scope now means "not in **your** countries", and the
  same line drops a Berlin posting for a Chicago reader and a Chicago posting
  for a Manila reader. An empty list accepts everywhere.
- **`locations.units`** — `mi` or `km`, defaulting to miles for the US and UK
  and kilometres elsewhere. A `radius: 25` in Berlin was being read as 25
  miles, which is 2.6x the intended area.
- **`radius`** accepts any positive number, not just 5/10/25.
- **`salary.currency`** accepts 45 currencies, up from 2.
- **Adzuna follows `locations.countries`** instead of defaulting to `["us"]`
  for every reader regardless of where they live. Probed live: it serves
  `gb us ca ie in de fr nl at be ch es it pl br mx za`; `au nz sg` answer 503;
  `ph id my jp ae ru` answer 404 and have no index at all. A country it cannot
  serve is named rather than silently skipped.
- **USAJOBS skips itself** when `US` is not in `locations.countries`.
- **The gazetteer covers 245 countries**, 69,933 places, 2.3MB. The builder
  takes country codes, defaults to your config, and accepts `all`.
- **Australian state codes** (`NSW`, `VIC`, `QLD`…) are recognised, and
  `state_name` spells them out — Workable ignores two-letter codes silently,
  so `NSW` returned the whole world.

### Fixed

- **Accents now fold both ways.** `Zurich` finds `Zürich`, `Sao Paulo` finds
  `São Paulo`.
- **English exonyms resolve.** `München` and `Munich` share almost no letters,
  so folding cannot connect them; a curated table covers ~40 cities.
- **`Makati` and `Makati City` are one place.**
- **City-states resolve.** In Singapore the country name is also the city name,
  and a country-only string was being refused.
- **`Remote - Australia` no longer resolves to Cuba.** There is a town called
  Australia there, population three thousand. A country name that is the whole
  string names no city.
- **Alias rows no longer create false ambiguity.** Writing an ASCII alias
  beside every accented name made São Paulo look like two different places, so
  the ambiguity check refused to resolve it. Aliases are now only written when
  they fold differently, and same-coordinate entries are treated as one place.
- **A city ambiguous *within* your own countries** now resolves to the largest,
  marked approximate, instead of being abandoned.

### Measured

Adzuna coverage, probed live with a key, and the reason the Philippines needs
a different answer than Germany:

| Region | Adzuna | Practical coverage |
|---|---|---|
| EU / UK | 10 indexes live | full |
| Australia, NZ, Singapore | 503 | Workable + boards + dorks until restored |
| Philippines, Indonesia, Malaysia, Japan, UAE | 404, no index | Workable + boards + dorks |

---

## 0.2.0 — 2026-08-28

Adds a scanner alongside the existing Google-dork generator. The dork tool is
unchanged in behaviour; everything new is additive and lives in a `jobdork/`
package. Works in any country.

Coverage comes from keyword search rather than a bundled list of employer
boards, so there is no crawl index to maintain and no source file to keep
current. Boards for named employers are added individually when you want them.

---

### Added

**Package `jobdork/`** — 2,700 lines across 20 modules.

| Module | What it does |
|---|---|
| `config.py` | YAML config, validated at load. Secrets read from `.env` only |
| `store.py` | SQLite: roles, role_state, artifacts, runs |
| `geo.py` | Offline gazetteer, radius, state/metro/country normalisation |
| `screen.py` | Title, location, salary, work-mode and dealbreaker filtering |
| `scan.py` | Orchestration, threading, rescreen |
| `resume.py` | Offline resume parsing and skill-overlap scoring |
| `render.py` | Static HTML + JSON output |
| `cli.py` | `scan / list / show / applied / rescreen / add / sources / dork` |
| `textutil.py` | HTML-to-text for advert bodies |
| `fetch/http.py` | Per-host pacing, retries, 429 circuit breaker |
| `fetch/*.py` | Eight source adapters |

**Sources.** Keyless: Workable cross-employer search, plus Greenhouse, Ashby,
Lever, Breezy and SmartRecruiters per employer board. Keyed and dormant until
credentials exist: USAJOBS, Adzuna. A dormant source reports why it skipped
rather than silently not running.

**Radius filtering.** `locations.anchor` plus `radius: exact | 5 | 10 | 25`
(miles). Measured against a bundled gazetteer of 8,879 US and Canadian places
(GeoNames `cities5000`, 321KB, built by `scripts/build_gazetteer.py`). No
geocoding API, no key, no per-role network call.

**Status tracking.** `new → interested → applied → submitted → interviewing →
offer`, plus `rejected`, `withdrawn`, `skipped`, `closed`. The last four are
hidden from results. A status you set outranks a later filter change:
`rescreen --remove` never deletes a role you acted on.

**Resume scoring**, offline and free. Reads `.docx`, `.md`, `.txt` and — via
the optional `pypdf` extra — `.pdf`. Sorts the list by skill overlap and names
the gaps. Never drops a role; it only adds points.

**Static dashboard** at `out/index.html`. Self-contained, light and dark, no
server and no external request.

**Tests.** `tests/run_all.py` discovers every `tests/test_*.py` and needs no
pytest. 30 tests covering the rules that fail quietly.

**Docs.** `config.example.yaml`, `pyproject.toml`, expanded `README.md`.

---

### Fixed — pre-existing

- **`.gitignore` patterns were `.csv` and `.txt`**, which match a file named
  exactly `.csv`. Generated result files were never actually ignored. Now
  `*.csv` / `*.txt`, plus `.env`, `config.yaml`, `config.local.yaml`, `data/`
  and `out/`.
- **Greenhouse dork pointed at the retired domain.** Greenhouse moved to
  `job-boards.greenhouse.io`; the dork searched only `boards.greenhouse.io` and
  missed current postings. Both are searched now.
- **The virtualenv was broken** — `.venv/bin/python` was a dangling symlink to
  a removed pyenv 3.12, so `run.sh` silently fell back to a system Python with
  no `resend` installed. Rebuilt on 3.13.
- **Dork board list skewed to startups.** Added 16 North American mid-market
  ATS domains: Paycom, ADP WorkforceNow, UKG, Paylocity, JazzHR, BambooHR,
  Jobvite, Taleo, SuccessFactors, Oracle Cloud, Recruitee, Teamtailor,
  Eightfold, Dover, Pinpoint, USAJOBS. 33 standard boards, up from 22.

### Fixed — introduced and caught during this work

- **`gh_jid` was stripped as a tracking parameter.** Greenhouse's
  `absolute_url` is often the employer's own domain with the job id in the
  query string (`stripe.com/jobs/search?gh_jid=7532733`), so stripping it
  collapsed 579 Stripe jobs into a single uid. A parameter that identifies the
  posting is not tracking.
- **`screen()` overwrote adapter flags.** It replaced `role.flags` wholesale at
  the end, so anything the fetch layer knew — "adzuna predicted salary
  ignored" — never reached the database. Now merged.
- **Foreign roles leaked through.** "Berlin, Germany" is not in a US/CA
  gazetteer, so it resolved as *unreadable* and was kept under the
  keep-when-unresolvable rule. A named foreign country is now a positive
  statement about where the job is, and drops it. "Atlanta, Georgia" still
  resolves to the US state.
- **`Washington, D.C.` resolved to Washington *state*** — a 2,300-mile error.
  Periods are stripped before the state lookup.
- **Adzuna location parsed from the wrong field.** `display_name` is city plus
  *county* ("Round Rock, Williamson County"), which no gazetteer can place;
  187 of 238 roles were unplaced and the radius was quietly doing nothing. The
  structured `location.area` is now used.
- **USAJOBS pay periods.** `RateIntervalCode` is a two-letter code (`PA`), not
  a word. An unrecognised code fell through to a default of "year", which
  would have stored $50/hour as $50/year and let any salary floor hide the job.
  Unknown codes are now refused rather than assumed.
- **USAJOBS multi-location postings.** A federal role is routinely open in 20+
  cities; taking `PositionLocation[0]` displayed an Austin-matching job as
  "Salt Lake City" and failed a radius it was never outside. The nearest
  location is now chosen using the latitude and longitude USAJOBS supplies.
- **Greenhouse adverts are double-escaped HTML** (`&lt;h2&gt;`). A tag
  stripper matches nothing and returns the entities verbatim, so every
  Greenhouse dealbreaker silently stopped matching. Unescaped first now.
- **`jobdork dork` swallowed its own flags.** `argparse.REMAINDER` treats a
  leading `--flag` as an option to the parent parser. `dork` is now dispatched
  before argparse sees anything.
- **Aggregator duplicates.** One Adzuna vacancy arrives under six or seven
  distinct posting ids. `list` collapses repeats of the same employer and
  title, keeping the best-scoring copy; `list --duplicates` shows them all.
  One run went from 855 rows to 729.

---

### Verified against live APIs

Every adapter was probed before it was written, and several published
behaviours turned out to be wrong.

**Workable** — `GET jobs.workable.com/api/v1/jobs?query=&location=`, no key.
Adverts come back inline, so there is no enrich step. `location` takes exactly
one value; repeating the parameter answers 400. It accepts a city, state or
country spelled out, and silently ignores two-letter codes — `TX` returns the
whole world. `workplace` filters `remote`/`hybrid`/`on_site` server-side.
`pageToken` pages cleanly with no overlap. **There is no salary field at all.**

**Greenhouse** — `boards-api.greenhouse.io/v1/boards/{token}/jobs`.
`content=true` is required or there is no advert. `pay_transparency=true`
returns `pay_input_ranges`, which was empty on every Stripe role.

**Ashby** — `api.ashbyhq.com/posting-api/job-board/{name}`. `isRemote` is a
decoy: Ramp returned `isRemote: true` on a role whose `workplaceType` was
`Hybrid`. `workplaceType` is authoritative. Compensation is well structured.

**Lever** — `api.lever.co/v0/postings/{token}?mode=json`. Bare top-level list.
Separate US and EU deployments; a token on one 404s on the other.

**Adzuna** — verified with a live key. `title_only`, not `what` (`what`
searches the advert body and returns every engineer whose advert mentions
their manager). `distance` is **kilometres**. `salary_is_predicted` is the
string `"1"`, and a predicted figure always has `min == max` — 251 of 292 in
one run were predicted, and predicted figures are discarded rather than
stored, because a guess must never disqualify a job.

**USAJOBS** — verified with a live key. `Radius` is real and in miles: Austin
at 25 returned 23 postings, at 200 returned 52. **An unknown parameter is
ignored silently with HTTP 200** — a search carrying `NotARealParam` returned
the same 501 results — so a misspelled filter does not fail, it just does not
filter. `JobSummary` is truncated to about 500 characters, so all prose fields
are concatenated before a dealbreaker reads them.

**SmartRecruiters** — **unverified.** The envelope is right
(`{offset, limit, totalFound, content}`) but every token tried returned
`totalFound: 0`. That is the platform's known failure mode: it answers 200
with nothing both for a board that is not there and for one that is throttling.
Believe your first successful run over this file.

---

### Measured

One Chicago run, 16 titles, radius 25 miles, 855 roles before dedupe:

| Source | Roles | Avg advert | Arrangement stated | Pay stated |
|---|---|---|---|---|
| adzuna | 653 | **500 chars (hard cap)** | 136/653 | 30% |
| workable | 200 | 4,903 chars | **200/200** | 0 (no field) |
| usajobs | 2 | 4,102 chars | 0/2 | **100%** |

**Adzuna truncates every advert to exactly 500 characters.** Dealbreakers,
work-mode detection and resume fit scoring all read the advert body, so Adzuna
is a discovery-and-salary source and Workable is the one that can be filtered
on. This is the single most important limitation in the tool.

Federal hiring uses a different vocabulary. With private-sector titles USAJOBS
kept 0 of 23 roles; with `IT specialist`, `computer engineer`, `computer
scientist` and `software developer` it kept 17 of 101 — and every one stated
pay.

---

### Known limitations

- **No bundled employer list.** Coverage comes from keyword search plus boards
  you name. `jobdork dork` covers the rest.
- **Adzuna free tier** is 2,500 calls a month, about four scans a day at three
  titles; a second country doubles it.
- **`jobs.workable.com` is strict.** A 16-title config at 0.7 requests/second
  collected 15 consecutive 429s and then a `Retry-After` of 86,130 seconds — a
  24-hour refusal. The rate is now 0.4/s with a 6-page cap. Use
  `scan --limit` while tuning a config rather than re-running full scans.
- **Indeed, Glassdoor, LinkedIn, Dice and ZipRecruiter** have no usable public
  API and remain dork-only.
- **`enrich` is not implemented.** Breezy and SmartRecruiters return a summary
  index; their full adverts need a second request per role.
- **No `discover` command yet.** Board tokens have to be supplied by hand.
- **PDF resumes need `pypdf`**, an optional extra. A PDF that extracts under
  200 characters is refused rather than silently scoring every role zero.

### Not built

`jobdork serve` (interactive dashboard) and `claude -p` document generation —
screen, CV and cover letter with quality gates — are designed but unwritten.
Everything else works without them.

---

### Dependencies

Added `PyYAML` and `requests` as required, `pypdf` as an optional extra for
PDF resumes. `resend` unchanged.
