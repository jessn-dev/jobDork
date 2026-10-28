# Changelog

Each finished piece of work gets its own entry here, newest first.
[Still outstanding](#still-outstanding) is the backlog: a bullet moves out of
it and into an entry when the work is done.

---

## Fixed — 2026-10-28 — The secret scan, failing on two made-up keys

The security check's secret scan (gitleaks) reads every branch, and two
made-up keys in the Ollama-key tests of #78 matched its "generic API key"
rule, so the check failed on main and on every pull request opened after.
Both findings are listed in `.gitleaksignore`, the way an earlier test key
is, and #78's tests now name the key once as `_FAKE_KEY`, marked
`gitleaks:allow`, so no new finding comes from them.

## Added — 2026-10-27 — A progress bar when a resume is uploaded

Uploading a resume showed only "Uploading…" or "Reading…" until the answer
came, so a slow upload or a long PDF looked the same as a page that had
stopped. Now a bar under the file picker, on the Resume page and in the
setup wizard, fills as the file goes up, then moves while jobdork reads it,
and goes when the answer arrives. The button (or file picker) waits while
it runs, so the same file is not sent twice, and no answer at all from
jobdork is said, rather than leaving "Reading…" on screen for good.

**Fixed:** a resume whose file name had a character outside Latin-1, such
as a curly apostrophe (`Maria’s Resume.pdf`), an en dash or `履歴書.pdf`,
was never sent: the browser refused it, the error log said "got no answer
from the server: Type error", and setup sat on "Reading…". Found in a
0.15.3 test on an Intel Mac. The name is now sent encoded (the server reads
only its extension), and a refusal by the page is logged as one.

## Changed — 2026-10-27 — version 0.15.3

0.15.3 carries the 3 entries below, everything since 0.15.2 (27 October):

- **A desktop app for Intel Macs**, `jobdork-0.15.3-macos-x86_64.dmg`,
  beside the Apple Silicon one: download, open, drag into Applications.
- **Install on a Mac with one command** in Terminal, which checks the
  download itself and skips the first-open warning; and a WinGet manifest
  written for every release and installed for real on every pull request.
- **What 1.0 promises**, written down in docs/DECISIONS.md.

Updating from 0.15.2 uses the update window 0.15.2 brought. An Intel Mac
has no earlier jobdork to update: it starts at 0.15.3.

## Added — 2026-10-27 — A desktop app for Intel Macs

The desktop app was built for Apple Silicon Macs only; on an Intel Mac the
only ways in were Docker or running from source, too much for someone who
just wants to download and install. From 0.15.3 every release has
`jobdork-X.Y.Z-macos-x86_64.dmg` beside the Apple Silicon one, built and
self-tested on GitHub's Intel Mac machines (`macos-15-intel`) and attested
the same way. macOS 12 or newer.

- The app's **Update** button takes the installer for the Mac it runs on,
  and the one-command install for Macs does too.
- The release page lists it, with how to tell which Mac you have (Apple
  menu → About This Mac).
- **One library is older on the Intel app:** `cryptography` 48.0.1, the
  last version built for Intel Macs; every other build has 50.0.2. Three
  advisories are fixed after 48.0.1: in PKCS#7 decryption (not used), in
  slow certificate-chain building (the update check builds chains only from
  Sigstore's own verified trusted root), and in DNS-name constraints (the
  update check's certificates name a workflow, not a host). CI's dependency
  audit accepts those three for that entry alone, audited separately from
  the rest, which still allows none; the reasons are beside it in
  `.github/workflows/docker.yml`.
- Docs: the desktop guide, run guides, README, SECURITY.md, DECISIONS, and
  the user guide's home page and Getting started.

## Added — 2026-10-27 — Install on a Mac with one command, and a WinGet manifest for Windows

- **One command installs or updates jobdork on a Mac**
  (`packaging/install-mac.sh`), pasted into Terminal:
  `bash -c "$(curl -fsSL https://raw.githubusercontent.com/jessn-dev/jobDork/main/packaging/install-mac.sh)"`.
  It asks GitHub for the newest release, takes the `.dmg` only if GitHub
  Actions uploaded it, checks its SHA-256 against the release's
  `SHA256SUMS.txt` and, when the GitHub CLI is signed in, its build
  attestation; then it quits an open jobdork, puts the new app in
  /Applications (~/Applications when that cannot be written), keeping the
  old one until the new one is in place, and opens it. No password, no
  setting changed; macOS does not show the first-open warning, which is for
  files a browser downloaded. Tested with stand-ins for the network and the
  disk image (tests/test_install_mac.py): it installs, refuses a file that
  does not match its checksum and keeps the old app, and refuses a file
  GitHub Actions did not upload before downloading it.
- **`scripts/winget_manifest.py X.Y.Z`** writes the WinGet manifest for a
  release (three files in the 1.12 schema, in winget-pkgs' folder layout):
  the Windows installer's address and SHA-256 from the release, `inno` and
  per-user, so WinGet runs it silently, and the name Windows lists it under.
  It is what a pull request to microsoft/winget-pkgs adds so that
  `winget install jessn-dev.jobdork` works; that submission is planned
  before 1.0.0.
- **Every release writes its WinGet manifest:** the release workflow's last
  step runs the script on the release's own checksums and keeps the three
  files with the run (`winget-manifest-vX.Y.Z`, 90 days), after the release
  page, so a manifest problem never holds up a release.
- **The manifest is tried for real on every pull request:** a `winget` job
  on Windows writes one for the installer just built, serves the installer
  from the runner, runs `winget validate`, `winget install --manifest`
  (silent, as WinGet's own checks install a submission), checks the name,
  version and publisher Windows lists it under and that `jobdork.exe` is
  there, then `winget uninstall` and checks both are gone. winget marks
  what it downloads as from the internet, and Windows holds an unsigned
  installer with that mark at a security prompt before it starts (tried:
  without the mark it installs silently in a second; with it, it never
  starts on a runner where nobody can answer). So on the runner `.exe`
  files count as low risk; on a person's computer, installing with winget
  shows Windows' prompt for an unsigned installer, as a browser download
  does.
- **The Windows installer names the app "jobdork"** under Installed apps
  (`UninstallDisplayName`), instead of Inno Setup's "jobdork version
  0.15.2": WinGet matches an installed app to its package by that name.
- Docs: the desktop guide, the user guide's Getting started and home page,
  and the README.

## Added — 2026-10-27 — What 1.0 promises, and when it comes

docs/DECISIONS.md now says what a version number promises from 1.0.0 on:
patches fix, minor versions add, and only a major version may break your
settings file, your data, kept keys, the commands, the environment
variables, the installers and Docker image, or what PRIVACY.md rules out,
said in the notes with how to move over. The pages' look, scores, sources
and the database's tables are not promised. 1.0.0 is the public launch,
after 0.15.2's Update is checked, the security review's work, a few people
who do not program have installed it, and jobdork is in WinGet.

## Changed — 2026-10-27 — version 0.15.2

0.15.2 carries the 6 entries below, everything since 0.15.1 (26 October).
The ones a user notices most:

- **Keys, your choice:** asked for again after jobdork closes or updates, or
  kept in your computer's own keychain (macOS Keychain, Windows Credential
  Manager, Secret Service on Linux). Never in a file: the old plain
  `source-keys.env` is moved to the keychain or dropped at the first start,
  and deleted. Start over and removing jobdork always remove kept keys.
- **An update window** that shows each step, from asking GitHub to opening
  the installer, then how to finish installing; a failure says why.
- **Remove jobdork from a computer**, choosing what of yours goes: the
  Windows uninstaller asks, and Settings and `jobdork uninstall` do the same
  on a Mac or Linux.
- **Posts from every aggregator** (Adzuna, Himalayas, Arbeitnow, Kalibrr) are
  checked against the employer's own board, and a post's window can ask that
  board now. **Search Google Jobs** sits above the list.
- **The README** opens on a banner.

Updating from 0.15.1 with its own Update button uses 0.15.1's notice, not
the new window, which shows from the next update on. At the first start of
0.15.2, keys you entered before are gone from memory, as after any restart:
the new **Enter your keys** window asks for them, and asks where an old
`source-keys.env`'s keys should go. On a Mac, keeping keys in the Keychain
means the Mac asks once after each update to let jobdork use it.

## Changed — 2026-10-27 — Keys: asked for again after a restart, or kept in the computer's keychain by choice

After jobdork closed or updated, AI keys held in memory were gone and
nothing asked for them: the AI simply stopped, with a line on the Dashboard.
Adzuna and USAJOBS keys lived in a plain-text file, `data/source-keys.env`.

- **A choice on setup's first page and in Settings, Your keys:** ask for keys
  each time jobdork starts (the default; memory only), or keep them in this
  computer's own encrypted store: the macOS Keychain, Windows Credential
  Manager, or the Secret Service on Linux (`keyring`, core/keystore.py),
  encrypted with your login. Turning it on keeps the keys entered so far;
  off removes the kept copies; **Forget saved keys** removes them all.
- **No key is written to a file any more**, AI or job source. An old
  `source-keys.env` is read for one run while the page asks **Keep them in**
  the keychain or **This time only**; the file is deleted either way.
- **Enter your keys**: when jobdork starts without a key its AI page or job
  sources use, a window asks for them (AI keys, and the Adzuna or USAJOBS
  keys you had given, which are tested before they are kept). **Not now**
  leaves it until the next start. jobdork remembers which job sources you
  gave keys for, by name only (`key_sources`).
- A kept AI key comes back from the keychain after the idle wipe or a
  restart; **Forget** on the AI page removes the kept copy too.
- **Kept keys never outlive jobdork:** **Start over** and removing jobdork
  (Settings, the Windows uninstaller, `jobdork uninstall`) always remove them
  from the keychain, with the scheduled scan; when removing, they are not one
  of the items to choose.
- **On a Mac,** an unsigned app is asked "jobdork wants to use your
  keychain" once after each update (Always Allow); until then a scheduled
  scan runs without the kept keys. Said on both pages and in the guide.
  Containers have no keychain: the page says so, and keys come from the
  environment as before.
- The desktop build carries `keyring` and its backends, and its self-test
  checks the Mac and Windows builds can reach the keychain. Docs: PRIVACY,
  CONFIG (`remember_keys`, `key_sources`), DECISIONS, run guides, README, and
  the guide's Settings, AI, Getting started and glossary pages.

## Changed — 2026-10-27 — Search Google Jobs sits above the list

"Not here? Search Google Jobs for devops engineer, site reliability
engineer, …" was a small grey line after the last job post: seen only by
someone who scrolled to the end of a long list.

- **A bar above the list**, under the count: "Not finding it here? Search
  Google Jobs:" and a button for each of your titles (the first six). With
  nothing matching it says "Nothing here." The same links as before: each
  opens Google's job results in your browser, for that title near you, or
  remote; jobdork sends Google nothing.
- Guide: Job posts, and its picture.

## Changed — 2026-10-27 — Posts from every aggregator are checked against the employer's own board, and the window can ask it now

The flag for a post missing from the employer's own board covered Adzuna
alone, and could almost never fire: of 604 Adzuna posts in one person's
jobs, 2 could be checked. jobdork counted a board as read only when one of
its jobs was stored, so a board that answered with nothing matching (the
very case of a job it does not list) left no trace.

- **Every aggregator:** Adzuna, Himalayas, Arbeitnow and Kalibrr, which
  carry many employers' jobs. Not USAJOBS (federal agencies' own listings)
  nor Workable's search (each post is from the employer's own Workable).
- **Each scan records the employer boards it read** (`board_reads`, schema
  13): the employer, the board, when, and whether to the end. No job data.
  A board read to the end vouches even when nothing on it matched.
- **Only a whole read vouches.** Workday, SmartRecruiters, Eightfold, Oracle
  and Taleo stop at a page limit, and careers sites read the newest few; a
  board cut short, failed, or answering empty (possibly throttled) is not
  read to the end, and a missing job there says nothing.
- **The job post's window says what the board said** (on it, not on it,
  read only partly, not read) and has **Check the employer's own board**:
  it searches that board for the post's own title now and says whether it
  is there, with a link, or why it cannot tell. For a board the scan read
  only partly or not at all, or to look again before applying.
- Guide: Tags and the job post's window.

## Changed — 2026-10-27 — The README opens on a banner

The README's title was the small icon beside "jobDork" in heading type. It
opens now on a banner, as Guardrails AI's does: the icon, the name large,
and "Find the job posts worth your time" beneath, 560 pixels wide, then a
rule and the badges.

- `docs/images/banner-light.svg` and `banner-dark.svg`, drawn from
  `packaging/icon.svg`; GitHub shows the dark one on a dark page.
- Cropped to the artwork, so it sits centred; each line's width is fixed,
  so Windows' wider font cannot run it off the edge.

## Added — 2026-10-27 — Remove jobdork from a computer, choosing what of yours goes

Windows' uninstaller removed the program and left everything else,
including the scheduled scan's task, which went on starting a program that
was gone. On a Mac or Linux there was no uninstall at all: dragging the app
to the Trash left the scheduled scan and every file behind.

- **One way to remove it everywhere** (core/uninstall.py). The scheduled
  scan and the app window's storage always go. Of the person's, each item is
  its own choice and none is chosen: settings, job posts (with their
  backups), the resume, letters and tailored resumes, saved job-source keys,
  logs, and installers Update left in Downloads. Only jobdork's folder, its
  documents folder and its own installers are ever touched; a link pointing
  elsewhere is not followed.
- **Windows:** the uninstaller (Settings, Apps) shows the same items as
  tick-boxes before it removes the program; a silent uninstall keeps
  everything.
- **Settings, "Remove jobdork from this computer"** in the desktop app on a
  Mac or Linux: tick, confirm, and it says what is left to do (Mac: quit and
  drag the app to the Trash).
- **`jobdork uninstall`** from a terminal asks about each item, or
  `--remove jobs,logs` (or `all`).

## Added — 2026-10-27 — An update window that shows each step

Updating from 0.15.0 to 0.15.1, Update showed a notice, "Downloading the
update. The installer opens when it has been checked.", and nothing after
it: the job had failed three times on its first request ("could not ask
GitHub for the release (URLError)"), and that was written only to the
activity list. Nothing said it had stopped, or that it was still going.

- **Update opens a window** that follows the job: asking GitHub for the
  release, downloading the installer with a bar and how much is done ("44% ·
  52 of 118 MB"), checking it against the release's checksums, checking its
  build attestation, opening it. Each step is ticked off as it passes.
- **Then how to finish.** Mac: **Quit jobdork**, drag jobdork onto
  Applications in the Finder window that opened and choose Replace, open it
  again. Windows: follow the installer, which closes jobdork and offers to
  open the new version.
- **A failure is shown in the window**, with its reason and **Release page**
  to download it by hand. A download that drops part way now says so ("the
  download stopped (could not reach GitHub; is this computer online?)")
  rather than a Python error.
- The app can quit itself when asked (`quit_app`, the page's one new call to
  the app); the guide's Settings page describes the window.

## Changed — 2026-10-26 — version 0.15.1

0.15.1 carries the 13 entries below, everything since 0.15.0 (25 October),
and the employer boards re-verified on 26 October (417 of 420 answering).
The ones a user notices most:

- **AI verdicts you can rely on.** With `gemma4:26b` reading and
  `qwen3.8:27b` checking, 2.9% of a verdict's claims were unsupported,
  measured on seven resumes in six fields; eight local models compared in
  docs/AI-MODELS.md. A skill the AI called missing that your resume lists
  now counts for you, and the score is redone.
- **Resumes read whole:** current jobs written "Up to present", jobs at a
  university, PDFs that came out one word per line or with broken letter
  pairs ("construcƟon"), and resumes up to 20,000 characters.
- **Setup fixes:** "Other: type a model name" shows its box, Groq has its
  mark, Save and test shows it is working, and the Where step says what it
  needs.
- **Check now says when it could not reach GitHub**, instead of calling
  your version the newest.
- **A guide for the AI on two computers**, with what to do about AMD cards
  on Windows.

Updating from 0.15.0 with its own Update button uses 0.15.0's check: the
release's checksums and its build attestation. On some computers 0.15.0's
Check now cannot reach GitHub and says you have the newest (fixed here); if
it does, download 0.15.1 from the release page and install it over 0.15.0.

## Added — 2026-10-26 — Choosing an AI model, measured

Which local model to recommend was a guess from one resume. Eight readers
were measured the same way, on seven resumes in six fields (software,
marketing, sports writing, copywriting, pharmacy, construction quality
control), 56 job posts each from real boards, all checked by `qwen3.8:27b`.

- **docs/AI-MODELS.md:** the results and what they mean. `gemma4:26b`
  2.9% unsupported claims, no resume above 4.5%; `qwen3:14b` 9.9%,
  `gemma3:12b` 10.0%, `phi4:14b` 13.0%, `mistral-small3.2:24b` 13.9%,
  `llama3.1:8b` 14.3% (and 27 of 56 verdicts failed), `gpt-oss:20b` 14.9%,
  `qwen3:30b` 18.4%. Seconds per job post on a Mac M4 and on a PC with a 12
  GB card, what to run on which computer, local against hosted, and that
  the rules were tuned on `gemma4:26b`'s mistakes. Linked from the README and
  the user guide's AI page.
- **scripts/hallucination_benchmark.py:** the measurement, for anyone's own
  resumes and models, hosted ones included (`--reader gemini:<model>` with
  the key in the environment). Works on a copy of the database; keeps the
  verdicts so a second run re-checks without asking the reader;
  `--case RESUME DATABASE COUNT` pairs a resume with jobs in its own field;
  `model@http://host:11434` runs a model on another computer.

## Changed — 2026-10-26 — A missing skill the resume lists counts for you, and the score is redone

Models wrote "the resume does not mention Linux" over a skills line listing
Linux, and "lacks specific experience with Azure DevOps" over "Azure DevOps
Pipelines" (`phi4:14b`: 39 of its 45 gap flags). Shown as a reason against
the job, and it pulled the score down.

- Before a verdict is stored, each concern calling something missing is
  checked against the resume by script, past filler words ("specific
  experience with", "familiarity with", "explicitly", "required for the
  role") and through lists ("CI/CD tools like Jenkins, GitHub Actions or
  GitLab CI": any one found fills it).
- When one is found, the reader scores again, told what the resume has; the
  concern becomes a reason, "The resume lists Linux.", which the claim check
  confirms like any other. One more call, only for such a verdict.
- The verdict says so: "The model first called Linux missing; your resume
  lists it, so it scored again (first 60)." The guide's Scores page explains
  it.

## Changed — 2026-10-26 — The AI reader says only what the resume says

The reader prompt, from what the claim check flagged most across seven
resumes:

- A skill the resume only lists is named as listed, never with what it was
  used for or where ("used Docker for deployment workflows" over a skills
  line), and never tied to an employer unless one bullet names both.
- No depth or amount ("extensive", "deep", "expertise in", "lacks depth
  in"), and nothing a background is "centered on" or "in".
- A gap names one thing as the advert does, after looking for it in the
  skills lines too; citizenship, clearance or a licence the resume does not
  state is "the resume does not state US citizenship".
- An old post's concern gives its age as measured ("posted 45 days ago"),
  not that it "may already be filled", which no source can support.
- The claim check leaves out judgements of fit ("does not match the role",
  "is a strong fit"), which are opinions, and reads more gap wordings ("does
  not provide", "background is not in"); a short name such as ".NET" or "Go"
  must be a whole word ("Go" was found in "Google"); and a claim that only
  says the resume lists a skill is confirmed by script when it does.

## Fixed — 2026-10-26 — "<<MEASURED>>" in verdicts, and the total years given to one field

Told to take years of experience only from the <<MEASURED>> block, a model
wrote "has <<MEASURED>> of experience" into 11 of 29 verdicts, and the page
showed it. And "7 years 8 months as a DevOps Engineer" gave the total of
every role to one title.

- The prompts for verdicts, letters and tailored resumes ask for the length
  written out; any block name left is replaced before it is stored, the
  measured block with its length ("7 years 8 months"), the others with
  plain words.
- Where the measured length is given to one field or title, the sentence
  says what it is: "7 years 8 months of work in all".

## Fixed — 2026-10-26 — Resumes read whole, and work told from study

Seven resumes read against what their PDFs hold:

- **"Up to present"** and "to date" end a current job: a pharmacist's two
  current jobs were not counted.
- **Study or work is decided by the section** the dates sit in (Education,
  Experience, Employment), not by the employer's name: a faculty job at a
  university and an internship at another were dropped as study, while a
  degree's dates on a line of their own were counted as work, and so were an
  award's. A resume without such headings is read as before.
- **A certificate's term** ("cycle Feb 2024 to Jan 2027") is not work, and
  no month after today is counted.
- **PDFs that come out one word per line** are read by layout instead, every
  word kept (290 of 290).
- **Letter pairs a font draws as one shape** come out as their letters:
  "construcƟon", "submiƩals", "MicrosoŌ" (156 in one CV) read
  "construction", "submittals", "Microsoft", so a quote of them matches;
  ﬁ, ﬀ and ﬂ are spelled out.
- **A resume is read up to 20,000 characters**, from 12,000: four pages
  came to 11,597. Past it, the log says it was cut.

## Fixed — 2026-10-26 — The README's logo sits level with its title

The README's title had the logo with `align="center"`, which an image does
not take, so the logo sat on the text's baseline and "jobDork" rode high
beside it. It is `align="absmiddle"` now, which GitHub keeps and browsers
centre on the line; checked in GitHub's own rendering of the heading.

## Added — 2026-10-26 — The AI on two computers: a guide

The reader and the checker the AI page recommends (`gemma4:26b` and
`qwen3.8:27b`) are about 18 GB each, and one 32 GB Mac could not hold both:
they pushed each other out of memory and calls failed. jobdork already lets
every model have its own Ollama address; nothing said how to use that.

- **docs/run/ai-on-two-computers.md:** the reader on a PC with a graphics
  card, the checker on the laptop jobdork runs on, joined by Tailscale. It
  covers checking the card is used (`ollama ps`, and AMD cards Ollama does
  not list), Windows' settings and a firewall rule that lets in Tailscale's
  addresses only, keeping the PC awake, a test from the laptop, the AI page
  and `config.yaml`, security and what to do when it does not connect.
  Written from a working setup: a MacBook Pro (M4) checking, a Windows 11
  PC with an RX 6700 XT reading, 78% of the model on the card, about 50
  seconds a job post over Tailscale.
- **AMD cards on Windows:** Flash Attention with the `q8_0` cache, the usual
  advice for fitting more on a card, made every job post on the RX 6700 XT
  fail (Vulkan device faults, about 210 seconds each before the crash). The
  guide gives those two settings for NVIDIA only, and has a section with the
  signs (HTTP 500 "forcibly closed", `device fault` in Ollama's log), the fix,
  and what was not the cause (shared GPU memory in use).
- **Which computer runs what:** by the strong computer's graphics memory,
  where the reader and checker go; with 40 GB or more both go there and
  jobdork's own computer needs no Ollama. And how to keep a smaller card
  free for other work between scans (`OLLAMA_KEEP_ALIVE 2m`).
- Linked from the user guide's AI page, docs/run/README.md and the NAS
  guide.

## Fixed — 2026-10-26 — The hallucination check reads more ways of saying something is missing

Reported from 0.14.4 with Gemini judging and Ollama (gemma4:26b) checking:
the hallucination rate reached 36% (181 of 497 claims). 119 of the 181 were
gaps ("the candidate lacks Kafka"), which 0.14.4 always counted as made up;
0.15.0 settles a gap by script, against the resume, and run on the same
claims that alone leaves about 17%. Some gaps were still not read as gaps,
because of how they were worded:

- **"does not explicitly list", "is not clearly documented", "does not
  confirm", "has not worked with", "has not held"** now count as claims that
  something is missing, and get the same script check: supported when the
  thing is nowhere in the resume, contradicted when it is there.
- "The candidate's experience with Argo CD is not clearly documented" is
  checked for "Argo CD", not for the words around it, which are never in a
  resume and would have settled any such gap as true.

On those 497 claims the script now settles 114 of the 181 flags, which
leaves about 13%. What remains is mostly the checker not finding what the
resume does say (Kubernetes and Helm, which it lists) and the reader's own
judgements ("a fragmented work history"); a stronger checker model helps
with the first (the guide's AI page compares checkers; qwen3.8:27b did best).

## Fixed — 2026-10-26 — Check now says when it could not ask GitHub

Reported from 0.14.4: Settings, Updates, **Check now** answered "You have
jobdork 0.14.4, the newest" with 0.15.0 out. A check that failed (offline,
GitHub limiting requests, a certificate that could not be verified) looked
the same as no newer release; the app's data folder had no
`version-check.json`, which is written only when GitHub answers, so no check
had ever reached it.

- **Check now says it could not check, and why**, and offers **Release
  page** to look by hand. Opening Settings stays quiet about a failed check,
  as before; the reason also goes to Warnings and errors.
- **The update check and Update's downloads use certifi's certificates**,
  the bundle every other request in jobdork already uses. They went through
  urllib with the certificates of the Python they run in, which in the
  desktop app may be looked for where the build machine kept them. Not
  confirmed as the cause on the reporting Mac; the message now names it if
  it is.

## Changed — 2026-10-26 — Setup's Where step says what it needs

Reported from 0.14.4: with a country chosen, the state left at "Any state"
and the city empty, **Continue** said "Choose your country and city first",
which read as if the state were the problem, and nothing on the page said
the city was required.

- The step says up front that your country and city are required, and that
  the state can stay at "Any" and the rest as it is.
- **Continue** names the one field still empty ("Choose your country.", or
  "Type your city and pick it from the list."), outlines it in red and puts
  the cursor in it.

## Changed — 2026-10-26 — Save and test shows it is working

Reported from 0.14.4: after **Save and test** nothing on the page changed
until the model answered, which for a local model can be a minute, so the
click looked lost.

- While it runs the button reads **Testing…** with a spinning circle, Save
  and Save and test cannot be clicked again, and the message names the
  models being asked. The result replaces it as before.

## Added — 2026-10-26 — Groq's mark on its provider button

Groq became a provider in 0.15.0 without the mark the other providers show
beside their names on the AI page and in setup. It has its own now (from Lobe
Icons, MIT), in Groq's orange.

## Fixed — 2026-10-26 — "Other: type a model name" shows the box to type in

Reported from 0.14.4 with Gemini, and true of every provider: choosing
**Other** in the model list hid the text box instead of showing it, and
filled in a garbled name, so a model the list did not have could not be
entered. The option's value began with a NUL character, which HTML turns
into U+FFFD, so it never matched the value the page compared it with. It is
plain text now, and a test keeps NUL out of the page.

## Changed — 2026-10-25 — version 0.15.0

0.15.0 carries the 33 entries below, everything since 0.14.4 (24 October).
The ones a user notices most:

- **Safer updates and builds.** Update opens an installer only once its
  build attestation verifies, and the installers are built from
  hash-pinned packages after the tests and scans pass. A job post's link
  can no longer run script in the dashboard or send the app into your
  network.
- **New:** a Search Google Jobs link, a flag for Adzuna posts missing from
  the employer's own board, Groq as an AI provider, and AI usage on the
  Dashboard.
- **Fixed:** the desktop app opens PDFs, saves files, opens links and lets
  you copy; DuPont, TJX and Disney are back; a busy AI provider is asked
  again before the call fails.
- **A new icon and logo**, a website that opens on a landing page, and
  documentation checked against the code.

Updating from 0.14.4 with its own Update button uses 0.14.4's check, the
release's checksums; from 0.15.0 on, every update is checked for its
build attestation as well.

## Added — 2026-10-25 — A landing page; the README's title with the logo

The website opened straight onto the user guide, which explains how to use
jobdork to someone who has already decided to. Someone arriving from a
search or a shared link had nothing telling them what it is, who it is for,
or why to try it.

- **https://jessn-dev.github.io/jobDork/ is now a landing page:** what
  jobdork does, that it covers every kind of job (27 industries among the
  built-in boards, federal jobs through USAJOBS), the three steps, how it
  compares with a job board, answers to the first questions (cost, applying,
  LinkedIn, your data, the first-open warning), and Download, the guide and
  GitHub as the next steps, with how to hear about new versions. It carries
  a description, link previews and the app's details for search engines;
  every figure on it is one the README and docs already state. The guide's
  front page moved to `/overview/`; no other address changed, so the app's
  links into the guide still land.
- The site has the jobdork logo in its header and as its tab icon.
- **README:** the title is centred with the logo beside it, and the badges
  are centred beneath. Its links to the guide, those in docs/run/README.md
  and the release notes go to the guide's front page.

## Changed — 2026-10-25 — The documentation checked against the code; a shorter README

Every page was read against the code that it describes; what was wrong or
out of date was corrected, and what could not be backed up was removed.

- **README:** from 849 lines to 252: what jobdork is and where to start,
  with the documentation named in its introduction by what each page is
  for; then what it does, how it differs from a job board, install, privacy
  and security, limits, development. The detail it carried (sources, regions,
  the salary rule, drafting, the AI page, the scanner's internals) already
  had a home in `docs/` and the user guide, and is linked. Its pictures were
  five from September with the old layout and logo (`docs/images/`,
  removed); it uses the user guide's current ones.
- **Install from source no longer says to run `build_gazetteer.py`.** The
  full place list (70,026 places, 245 countries) ships in the package, and
  that script run with no country rebuilds it for your config's countries
  only, replacing the full list (README, docs/run/source.md, SOURCES.md).
- **Counts:** US boards 338, not 340; Canada 22, not 19; Asia 30, not 26
  (REGIONS.md). Out-of-date line counts per package removed from
  ARCHITECTURE.md, whose module table now names every module.
- **Update** is described as it works now, with its attestation check, in
  docs/run/desktop.md, the guide's Settings page and PRIVACY.md, which also
  lists the two addresses it asks (GitHub's attestations and Sigstore's
  signing keys); so does the Windows installer's privacy page.
- **CONFIG.md** gains `llm.context`, the `screening` section (title
  blockers, the loose match's gap, extra arrangement patterns) and where
  keys typed in the app are kept, `source-keys.env`.
- **PLATFORMS.md** gains Germany's employment agency and Arbeitnow, Workday's
  second address and a site named Jobs, and how a careers-site posting with
  no markup yields its board; Mayo Clinic, now read through Oracle, is no
  longer the careers-site example.
- **DECISIONS.md:** the job-source key cards and the Google Jobs link are
  built, not planned; the OS keychain for those keys was considered and
  not adopted, with why.
- macOS 12 or newer named as the desktop app's requirement; "no installer
  yet" for Intel Macs and Linux is "no installer"; the build instructions
  install from the hash-pinned lock; CONTRIBUTING.md says a dependency
  change updates both lock files.
- Every link and section anchor in the repository's Markdown resolves, and
  the user guide builds with `--strict`. Every picture in the guide was
  taken again from the demo.
- **The Settings picture shows what people see:** notifications on and the
  daily update check on. It said "off, because JOBDORK_UPDATE_CHECK=off is
  set", the switch the screenshots used to stay offline; the demo now
  starts with its version check already answered, so nothing goes online.
- The package description and keywords (`pyproject.toml`) say what jobdork
  is now: a local-first scanner of employers' job boards with a screening
  filter and resume matching, not a Google dork search.

## Security — 2026-10-25 — Repository settings locked down before distribution

- **Immutable releases:** a published release's files can never be changed
  or replaced, so an installer cannot be swapped after people have it.
- **Actions:** only GitHub's own and the six the workflows name (five
  `docker/*`, `sigstore/cosign-installer`) may run, each pinned to a full
  commit SHA, which GitHub now enforces rather than leaving to habit.
- **Outside contributors:** every workflow from one waits for approval, not
  only a first-time contributor's.
- Wiki and Projects off (unused, and each is something to watch); merged
  branches are deleted.
- **Not available here:** secret scanning's generic patterns and validity
  checks need GitHub's paid Secret Protection; provider patterns and push
  protection stay on. SECURITY.md's owner checklist records all of it, with
  the two items it listed as still to do (SHA pinning, `BOARDS_PR_TOKEN`)
  done.

## Security — 2026-10-25 — Drafts by Claude Code ignore your own Claude Code settings

- `claude -p`, which writes CVs and letters from a job post anyone could
  have written, already ran in the job's folder with file tools only and
  none of your MCP servers. It still read your `~/.claude` settings: your
  permission rules (which could let it read or write beyond the folder),
  your hooks and your plugins.
- It now runs with `--setting-sources project`: settings from the job's
  folder only, which has none. Signing in is not a setting and still works
  (tried with a real run). Test: the command carries it.

## Security — 2026-10-25 — The desktop installers are built from hash-pinned packages

- **The hole:** the Docker image installed every package by exact version
  and SHA-256, but `desktop.yml` ran `pip install -e '.[pdf,ai,app,package]'`:
  whatever PyPI served that day went into installers GitHub then attests as
  this project's, and `pip-audit` never looked at them.
- **`requirements-desktop.lock`:** all 65 packages for macOS and Windows at
  once (Python 3.13), with hashes, made by `uv pip compile --universal`
  (the command is at its top; `packaging/desktop-build.in` adds setuptools,
  so installing jobdork itself fetches nothing). `desktop.yml` installs it
  with `--require-hashes`, then jobdork with `--no-deps --no-build-isolation`,
  in bash on Windows too, where PowerShell would carry on past a failed
  first line.
- **Audited:** CI's security job runs `pip-audit` on it with the platform
  markers dropped first, since pip-audit skips packages for other systems
  and CI is Linux: all 65 checked, none with a known vulnerability.
- **Built only after the checks pass:** the desktop job now waits for the
  tests and the security scans, as the image already did. On a tag the
  installers are attested as they are built, and an attestation should
  never vouch for code that failed a scan.
- Tried: a fresh Python 3.13 installs it with every hash checked, and the
  macOS app builds from it and passes its self-test.

## Security — 2026-10-25 — Update opens an installer only once its build attestation verifies

- **The hole:** Update downloaded the installer and `SHA256SUMS.txt` from
  the same release, compared them, and opened the installer (on Windows,
  ran it). Anyone with the owner's GitHub login or a token could have
  uploaded another installer with a matching checksum file, skipping CI,
  and every Windows user pressing Update would have run it.
- **Only files the release workflow uploaded** are offered now: one uploaded
  by a person (a stolen login shows as that person) is not listed. The
  release is asked for again when Update is pressed, not read from the
  day-old cache.
- **The build attestation must verify.** After the checksum, GitHub's
  attestation for the file's SHA-256 is checked with Sigstore
  (`sigstore-python`, in the desktop app only): signed by GitHub Actions for
  this repository's `desktop.yml` at exactly that version's tag, logged in
  the public transparency log, and naming this file and digest. Another
  workflow, branch, fork or tag, other bytes, no attestation, or GitHub not
  answering: the file is deleted and nothing opens.
- The trust root is refreshed online, or taken from the copy inside the app.
  The app's `--self-test` verifies 0.14.4's real macOS attestation offline
  (`jobdork/data/attestation-check.json`), so a build that could not check
  fails before release; a local macOS build from the new lock passed it.
  The `.dmg` grows from about 30 MB to 36 MB.
- Tests (no network): a hand-uploaded file is not offered; a matching
  checksum with no attestation, another tag's, another file's or other
  bytes' is deleted; GitHub unreachable is a refusal; the real 0.14.4 bundle
  verifies offline for its tag and file only. SECURITY.md: "How the app
  checks an update before opening it".

## Changed — 2026-10-25 — CodeQL results are required on main

- The rules for `main` now include "Require code scanning results": a pull
  request that brings a new CodeQL security alert of high severity or
  above, or a new error, cannot be merged until it is fixed or dismissed.
  Alerts already on `main` do not count; there were none open (20 sorted
  the same day: 8 fixed, 12 dismissed with their reasons).
- Off the Still outstanding list. A different scanner stays an option if
  CodeQL proves weak.

## Added — 2026-10-25 — An Adzuna post missing from the employer's own board is flagged

- **A yellow tag**, "Not on Northbridge Health's own board, which jobdork
  read: may be filled, or not a real opening", on an Adzuna post whose job
  the employer's own board does not list. Adzuna keeps showing some posts
  after the job is filled or withdrawn, and some were never real; its pages
  cannot be read to ask (enrich.py), so the employer's board is asked.
- **Only when jobdork read that board** in the same scan: one of its jobs,
  kept or dropped by your filters, was seen within a day of the Adzuna post.
  An employer whose board jobdork does not read is never flagged; absence
  there proves nothing.
- **Compared loosely**, to keep real jobs unflagged: the employer name
  without case, punctuation, "The" or company suffixes ("The Home Depot,
  Inc." is "The Home Depot"); the title anywhere on the board, one inside
  the other counting ("Registered Nurse" in "Registered Nurse - ICU"),
  places not compared, as the two write them differently. A board copy
  dropped by your filters still vouches for the job.
- Worked out when the list or a post is shown (`search/ownboard.py`), so it
  follows the latest scan with nothing stored. The post stays listed: a
  reason to check the employer's site, not proof. "Ghost" on its own stays
  the age tag. Guide: Tags. Tests: the matching rules, a dropped copy, the
  list and the post's window, and that every board platform discover reads
  counts as an employer's own.

## Fixed — 2026-10-25 — The macOS build makes its disk image without hdiutil's deprecation warning

- macOS 27 warns that `hdiutil create -volname -format` is deprecated in
  favour of `diskutil image create from`. The build now uses that where it
  exists, giving the same compressed (UDZO) image, as APFS: it takes no
  filesystem, and every macOS the app runs on (12 and later) reads APFS.
- Where it cannot name the volume, `hdiutil` is used as before: CI's
  macOS 15 has `diskutil image create from` but no `--volumeName`, and
  refused it (the first CI build of this change failed there), so the
  build asks the command's help for `--volumeName` rather than whether it
  runs. Tried on macOS 27.0.1 with the build's own `dmg()` on a stand-in
  app: no warning, the Applications link kept; the CI build checks the
  `hdiutil` path.

## Fixed — 2026-10-25 — Folding the menu no longer pushes it down

- Folded to its icons, the menu put the arrow under the logo: the top grew
  from 38 to 74 pixels and every item below moved down by the difference.
  The top now stays one row: the arrow lies over the logo, shows on hover or
  keyboard focus, and a click on the logo opens the menu again. Measured in
  Chrome: the first item stays at the same height open and folded.

## Changed — 2026-10-25 — A new icon and logo, one design everywhere

- **The mark:** a briefcase with a loupe and a `>_` prompt, cyan and green
  on a near-black tile, in place of the white briefcase on blue. The same
  drawing is the app's icon (macOS and Windows), the logo at the top of the
  menu and on setup's welcome, and the browser tab's icon.
- `packaging/icon.svg` is the master, on the macOS icon grid (an 824-pixel
  rounded square in 1024); `packaging/icon.png` is rendered from it, so
  the two cannot drift apart. The build turns the PNG into the `.icns` and
  `.ico` files as before.
- **The tab icon** is a `data:` URI inside the page. The page's
  Content-Security-Policy gains `img-src data:` for it: images still come
  from nowhere on the network (tested, with remote images still refused).
- Guide: every full-page picture retaken with the new logo.

## Changed — 2026-10-25 — The Dashboard shows the run before the AI charts

- The run in progress (or the last one) came after every chart: the
  period tiles, runs over time, hallucination, feedback, and the whole of
  AI usage, so a first scan's progress was a long scroll down. Now, under
  the buttons: the last run of each kind, then the run in full (progress,
  rate, time left, requests, AI calls, outcomes, network by host, AI calls
  by model, postings by listing state), then the charts. The log, warnings
  and errors, and all runs stay at the bottom.
- A last-run card says it shows its run **below** now. Guide: the
  Dashboard page follows the same order (a run in detail, the numbers, log
  and history), with the picture retaken.

## Added — 2026-10-25 — Search Google Jobs from the job posts list

- **"Not here? Search Google Jobs for …"** under the job posts list, and in
  its place when nothing matches, names up to six of your job titles. Each
  opens Google's job results (`udm=8`) in your browser for that title near
  your location, or "remote jobs" when remote is the only arrangement you
  want. In the desktop app it opens in your browser, like any outside link.
- It is the way on for posts jobdork cannot read (LinkedIn, JobStreet,
  employers on systems with no reader yet). The results stay in Google;
  **Add a Job Post** on the Sources page keeps one in jobdork.
- jobdork sends Google nothing: it is a link, and your browser makes the
  request when you click (PRIVACY.md says so, under scanning). Reading
  Google's results itself would break Google's terms; JSearch or SerpApi,
  which sell them as data, stay deferred with the key proxy.
- The title and place are encoded into the search (a "Charge Nurse & RN"
  stays one search), and the link goes through `webHref` like every built
  link. Guide: Job posts, with a picture. Test: the page builds it that way.

## Changed — 2026-10-25 — Setup's welcome no longer says answers are saved as you go

- The line under **Get started** ("Each answer is saved as you go, so you
  can stop any time and carry on later") is gone from the page: it is said
  in the guide (Getting started), the README and the run guides, and the
  welcome was long enough. `jobdork setup` in a terminal still says it,
  where there is no page to come back to.

## Changed — 2026-10-25 — Ruff pinned, so CI lints with the version you have

- **#43 failed CI on a rule the local ruff did not have.** `pyproject.toml`
  asked for `ruff>=0.6`, so CI installed the newest (0.17.2) and flagged
  RUF059 that 0.16.5 here passed. Ruff adds rules in its releases, so an
  open range means `main` can go red with no change to the code.
- The `dev` extra now pins `ruff==0.17.2`. Dependabot's weekly pip update
  reads `pyproject.toml` and proposes the next ruff as a pull request,
  after its week of cooldown, where CI shows whether new rules fire.
- CONTRIBUTING.md says so: after a Dependabot update, `pip install -e
  '.[dev]'` again.

## Checked — 2026-10-25 — Desktop installers, the crontab line, Feedback Send, the weekly board PR

Off the Still outstanding list, tried by hand:

- **The Windows installer** on a Windows machine: install, the scan
  schedule's Task Scheduler entry, the close-mid-scan question, toasts.
  (The Windows build had already passed in CI: v0.14.4 shipped
  `setup.exe`.)
- **The release notes' steps past the unsigned warnings** on a downloaded,
  quarantined `.dmg` (macOS "Open Anyway").
- **The scan schedule's crontab line** on Linux.
- **The Feedback page's Send** in a browser against the live relay.
- **The weekly board re-verify** opens its pull request: the
  `BOARDS_PR_TOKEN` secret is set, and its first run found the re-verify
  bugs fixed in #40 (#39 closed, #41 merged).

Still outstanding from that bullet: only `hdiutil`'s deprecation notice.

## Fixed — 2026-10-25 — Code scanning: the alerts CodeQL raised on main

CodeQL (default setup, on since 2026-10-23) had 20 open alerts. Seven are
fixed in code, one hardened; ten are its guesses from names, and are
dismissed on GitHub with the reason written there.

- **Slow regex on text from a job post** (#7, `geo.py`): `\s*[-–—]\s*`
  tried every space of a long run with no dash after it: 1.4 s on 20,000
  spaces. A split on the dash, each side stripped, gives the same result
  in no measurable time.
- **Resume upload** (#3, #4, `api.py`): the file was already written as
  `resume` plus an extension from a fixed list; the extension written is
  now the list's own string, not the browser's that matched it.
- **The guide's screenshot script** (#1, #2, `guide_shots.mjs`): a role's
  uid read from the page went into the script run there unescaped; every
  value now goes in as JSON with `<`, `>`, `/` and the line separators
  escaped. Answers from Chrome find their callback in a Map, not by a
  property name taken from the message. Run end to end on the demo data.
- **Tests that checked an address with `in`** (#18-#20): by host instead.
- **The dork tool's `.env`** (#9): created owner-only (0600), where it was
  written first and narrowed after, readable to others for a moment.
  Tested for the permissions it ends with.
- **Dismissed as false positives:** "sensitive data" logged or stored
  (#8, #10-#17) is a board's token (its public name on Greenhouse, Workday
  and the rest), a job's uid, an employer's name or a report; the paths
  (#5, #6) are the resume file you named yourself, read by the app you run.

## Fixed — 2026-10-25 — A busy AI provider is asked again before the call fails

- **Gemini answered 503 on a real check of #38** (`gemini-3.5-flash`,
  "This model is currently experiencing high demand ... Please try again
  later") and the call failed at once, with the provider's raw JSON as the
  message. Only Claude retried, through Anthropic's own client
  (`max_retries=2`); Gemini, ChatGPT, Groq and Ollama go through `_post`,
  which asked once.
- `_post` now asks again on **502, 503 and 504**, twice, after 2 and then
  5 seconds, or after the provider's own `Retry-After` when it is 30
  seconds or less. Still busy after three tries: "HTTP 503, asked 3 times:
  This model is currently experiencing high demand ...", still a
  **Provider error** on the Dashboard.
- **Not retried:** 500 (Ollama's out of memory, which seconds do not fix),
  429 (the next reader in `llm.readers` takes it; out of quota stays out
  of quota), a refused key, a model not found, a timeout.
- A failure now reads in the provider's own words: Gemini, OpenAI and Groq
  all answer `{"error": {"message": ...}}`, and that message is shown
  instead of the first 200 characters of the JSON around it.
- Guide: the Dashboard page says so under AI errors. Tests: a 503 then a
  502 then an answer, three 503s, a short and a long Retry-After, and
  500/429/401/404 asked once; nothing waits or goes online.

## Fixed — 2026-10-25 — DuPont, TJX and Disney back, through their Workday boards

- The re-verify of 2026-10-25 (#41) dropped six careers-site boards unread
  since 2026-10-01. Looked at one by one:
  - **DuPont and TJX** moved to Phenom: their sitemaps still list every
    posting (203 and 2,599), but the pages carry no JobPosting markup. The
    job is in Phenom's own page data, and its `applyUrl` is a Workday
    board, which jobdork reads through its API.
  - **Disney**: its address in `scripts/candidates.csv`
    (jobs.disneycareers.com) now leads to its Workday board.
  - **Deloitte** (apply.deloitte.com does not connect), **Progressive** and
    **Telus Digital** (403 to robots.txt, to a browser's user agent too)
    stay out.
- **A posting page with no markup is read for the board it applies
  through.** Discover already reads two postings to prove a careers site;
  when neither is marked up, the board links on those pages are taken
  instead (no extra requests).
- **Workday's other address** is read: `wd1.myworkdaysite.com/recruiting/tjx/TJX_EXTERNAL`
  gives the usual token, `tjx/wd1/TJX_EXTERNAL`.
- **A Workday site named Jobs** (DuPont's `dupont/wd5/Jobs`) is no longer
  skipped as a posting path when a posting path follows it.
- Added with `build_boards.py --add`: DuPont `dupont/wd5/Jobs` (203 jobs),
  TJX `tjx/wd1/TJX_EXTERNAL` (11,160), Disney `disney/wd5/disneycareer`
  (377). 420 built in, 338 of them US (README). Tests: both addresses and
  the Jobs site read off a page; discover finds the Workday board on an
  unmarked Phenom posting, offline.

## Fixed — 2026-10-25 — The weekly board re-verify dropped working careers sites

- **The first weekly re-verify that could open its pull request** (#39,
  once `BOARDS_PR_TOKEN` was added) would have removed 93 boards and
  listed 42 more as failing, all of them careers sites or Eightfold
  boards. They were not failing; re-verify never asked them.
- **Careers sites** (`site`): `_verify` counted a site board from what
  discovery's `_site_board` had already read off its sitemap. A board
  re-checked from `boards.csv` starts from its address alone, so every one
  came back "empty" without a request. A board with nothing read yet is
  now read again; one whose sitemap lists no marked-up posting says so.
- **Eightfold on the employer's own host** (Applied Materials, Dexcom,
  Ericsson, Vodafone) and **outside .com** (National Australia Bank,
  nab.com.au): the domain the token already carries was not among the
  guesses, so only the host's first label with .com was tried ("careers.com").
  It is now tried first after the page's own.
- Both since the boards came in (2026-10-02); the hand runs used
  `--add`, which reads through discovery. Checked live: AMD, Applied
  Materials, Duke University, National Australia Bank, Chevron and Vodafone
  re-verified with jobs. Tests: a site board and an Eightfold board on its
  own host re-checked from a bare token, offline. PR #39 should be closed
  unmerged and the workflow run again.

## Fixed — 2026-10-25 — Gemini "did not answer in JSON" on Save and test

- **Save and test failed three times on `gemini-3.5-flash`** (2026-10-23)
  with "the model did not answer in JSON". The test allows 50 tokens for
  `{"ok": true}`, and Gemini's thinking models (2.5 and 3.x) think by
  default with the thinking counted against `maxOutputTokens`: the
  thinking used the budget and the answer was cut off mid-object.
- Gemini now gets `REASONING_TOKENS` (4,000) of room on top of each
  call's own budget, as GPT-OSS on Ollama does. No thinking setting is
  sent: the names differ between 2.5 (`thinkingBudget`) and 3.x
  (`thinkingLevel`), and a wrong one is refused with a 400.
- An answer stopped at the limit (`finishReason: MAX_TOKENS`) is reported
  as that: "the answer was cut off at the 4050-token limit, N of them
  thinking", a new error kind **Answer cut off** on the Dashboard's AI
  errors chart (`cut_off`, matched before the status codes, since its
  token counts could read as one).
- Not tried against Gemini itself: no key here, and tests do not go
  online. Tests: Save and test sends the larger limit and passes; a
  MAX_TOKENS answer gives the cut-off message and kind.

## Added — 2026-10-24 — AI usage on the Dashboard: requests, errors, tokens per model

- **What every AI call costs, on the Dashboard.** Below the hallucination
  chart, for the period chosen (7, 30, 90 days):
  - **Total AI requests**: calls per day as columns, and the share
    answered as a line on its own 0-100% scale (`columns()` takes a `line`).
  - **AI errors, by kind**: failed calls per day, stacked by kind: rate
    limited (429), key refused (401/403), model not found (404), provider
    error (5xx), timed out, could not reach, answer not JSON, declined,
    other. The five most frequent get colours; the rest fold into Other.
  - **Usage per model**: input tokens, output tokens and requests per day,
    one line per model, in the colour order the hallucination chart uses
    (first called, first colour; past six, "other models").
  - **Provider** narrows all of it (one key each, so it is "all API keys"
    or one); **Model** narrows the per-model charts. Every chart has its
    table.
- **Tokens as the provider counted them**, from each reply: Ollama's
  `prompt_eval_count`/`eval_count` (streamed calls included), OpenAI's and
  Groq's `usage`, Gemini's `usageMetadata` (thinking counted as output, as
  it is billed), Claude's `usage` (cached input included). A call that
  failed after the model answered, such as an answer that was not JSON,
  keeps the tokens it spent.
- **Schema 12**: `llm_calls` gains `input_tokens`, `output_tokens` and
  `error` (`llm.error_kind`, from the failure's message). Calls before it
  have 0 tokens and their failures show as "Kind not recorded"; the
  per-model charts say from which day tokens were counted. A database at
  12 is refused by an older jobdork, as every schema step is.
- `/api/metrics` returns `usage` (models with provider and colour slot,
  error kinds by frequency, the day tokens start) and each day's usage
  per model.
- Guide: Dashboard has an **AI usage** section and picture
  (`dashboard-usage.png`, demo data with a reader, a local checker and a
  rate-limited hosted model); README's Dashboard paragraph names it.
- Tests: tokens read from each provider's reply, a failure's kind and its
  spent tokens kept, failure messages sorted into kinds, usage per day
  and model with kinds and the period respected, the schema step.

## Fixed — 2026-10-24 — Letters and tailored resumes flagged true years, and a tailored resume could list a skill you do not have

- **A tailored resume listed Django on a resume that says Flask.** The
  check caught it (one of 4 flagged claims of 25), but the PDF already had
  it. Skills now get the script check employers, schools and
  certifications have: one not in the resume or the Resume page's notes,
  as written or word by word ("Python (Flask)"), is left out and listed in
  the "employers and schools from your resume" gate.
- **"Over seven years of experience" was flagged on a resume with 7 years
  8 months of dated roles.** Only the judge was given the work history
  counted from the resume's dates; the letter and the tailored resume added
  up dates themselves, and the check had no total to quote. Both now get
  the same `<<MEASURED>>` block, their prompts say to use only it (the
  tailored summary's years "as the resume states them" became "as
  <<MEASURED>> gives them"), and the check and the figures gate read the
  resume with that line beside it.
- **"The candidate is seeking a Software Engineer role" was counted as made
  up.** It is the resume summary saying what role is wanted, which the
  prompt asks for and no source can support, like a letter's "I am applying
  for". The check's self-description filter (`guard._SELF`) now drops it:
  seeking, looking for, wanting, pursuing or targeting a role, position,
  job or opportunity, unless a person is named between ("seeking a
  candidate for the role" is the advert, and still checked).
- Of the 4 flagged on that resume, the fourth ("full-stack development")
  stays flagged: the resume does not say it.
- README, guide (AI, Job window) updated. Tests: the letter and the tailored
  resume are sent the measured block and checked with it; a skill not in
  the resume is dropped and listed; self-description is left out while a
  company seeking someone is kept.

## Fixed — 2026-10-24 — The desktop app could not open a PDF, save a file or open a link

- **"Could not open the PDF: desk().open_file is not a function"**, for a
  cover letter and a resume alike, and the same for saving a file or
  opening a job's link: none of the app's calls existed in its window.
  pywebview builds `window.pywebview.api` in the page with `new Function`,
  and the dashboard's Content-Security-Policy has no `'unsafe-eval'`, so
  the first one threw (the `EvalError` in `logs/app.log` at every start)
  and the page was left with an empty api it took for the app's. Answers
  come back from Python through `eval` too, so even calls built another
  way would never have resolved.
- **The page now asks the app through its own server**, which runs in the
  app: `POST /api/desk` with the page's token, answered by the same Bridge
  (`open_url`, `save_file`, `open_file`; `jobdork/web/app.py`,
  `jobdork/web/serve.py`). The window gets no `js_api`, so pywebview builds
  nothing and the EvalError is gone. `'unsafe-eval'` was not added: it
  would let script injected through a job post build code from strings,
  in the one window that can write and open files.
- **`open_file` shows PDFs only.** It opened whatever it was named with the
  system's handler, where a `.command` file runs. It now refuses anything
  that does not start as a PDF does, and always saves its copy as `.pdf`.
- Tried in the real app in a WebKit window (a throwaway home): opening a
  PDF and a link reached the Bridge and their answers reached the page,
  with no error from the page. tests/test_serve.py covers the route (404
  in a browser, the token, the size limit, unknown calls);
  tests/test_app.py the Bridge's calls, PDF-only, and that the page names
  exactly the Bridge's calls without eval. SECURITY.md says what the page
  can ask of the app.

## Changed — 2026-10-24 — SignPath signing dropped: the installers stay unsigned

- **SignPath Foundation did not grant free code signing**, so everything
  written for the application is gone: the README's "Code signing policy"
  (SignPath's required wording, team roles, MFA on SignPath) is now
  **Unsigned installers**, saying the installers are not signed, how to
  open them, and what can be checked instead (built by Actions from a tag,
  approved by hand, an attestation per download). The release notes link
  there instead of claiming signing "once granted"; docs/run/desktop.md no
  longer says signing was applied for; the installer script's comment
  gives its own reason for the privacy page, which stays.
- docs/DECISIONS.md's desktop-app entry records the refusal: a paid
  certificate is the next option if the warnings stop people installing.

## Fixed — 2026-10-24 — The hallucination rate counted the check's own mistakes

- **The Dashboard said 15-20% of what the AI wrote was made up.** Half of
  that was the check. Of the 130 claims flagged in the two databases on
  this machine, 68 were gaps ("the resume does not mention Django"), which
  the check could only fail, since nothing can be quoted for what is not
  there; about 13 were true claims ("has Java") lost because the checker
  echoed the claim back without its full stop, or quoted with punctuation
  the source did not have; one was the post's age, which the checker was
  never shown. About a third were real: "large-scale", "over 5 years",
  "distributed", "primarily GCP", none of them in the resume.
- **The check (`ai/guard.py`):** a gap is settled by script: the claim must
  be worded as one ("does not mention", "lacks", "no … experience"), name
  the thing, and the thing must be nowhere in the source it names, or the
  gap is contradicted. Checkers answer gaps "supported" with the missing
  thing as the quote, or with no quote; both get the same script check,
  the thing taken from the claim's own words when not quoted. Claims are
  matched to the checker's answers by their words, then by number when
  recognisably the same claim. Quotes match by words: a single word whole
  ("java" is not in "javascript"), several with their spaces dropped, since
  PDF text runs words together ("remotefreelance"). A source named the way
  the model sees it ("JESSE NGOLAB resume" in 403 of 420 answers) is that
  source. Flagged claims are stored with their source and quote.
- **The verdict (`ai/judging.py`, `ai/llm.py`):** years of experience are
  counted by `resume.work_span` from the resume's dated roles, overlaps
  once and study left out, and given to the model as `<<MEASURED>>`
  ("January 2016 to September 2023, 7 years 8 months in all: every role
  together, not any one field"), which the check can quote. The prompt
  forbids scale, seniority, "primarily", "focused on", and adding up dates,
  and asks for gaps worded as gaps. The post's dates go to the check too.
  A rule asking for role titles instead of "recent roles are in…" was
  tried and taken out: 7.4% against 6.4% without it.
- **Measured** on a copy of the database, local models only, the same 30
  job posts: 20.0% flagged before; 10.4% with the new check on the old
  verdicts; 6.4% with the new verdicts, gemma4:26b checking itself.
- **The checker matters most.** Eight local models checked the same 574
  claims; where they disagreed (233 claims) the truth was decided by hand
  against the resume and advert. qwen3.8:27b: 99.3% right, 70% of its flags
  real, 87.5% of real errors caught, 1.7% flagged. mistral-small3.2:24b
  97.2%; gemma4:26b on its own work 94.2% (16% of its flags real);
  gpt-oss:20b 91.6%; bespoke-minicheck 87.0%; llama3.1:8b 85.3% (37.5% of
  real errors caught); qwen3:30b 75.7%; phi4:14b
  and llama3.2:3b unusable (phi4's 16K context drops the sources;
  llama3.2 flags almost everything). One resume and one person's labels:
  a direction, not a benchmark. The guide's checker section says so.
- **GPT-OSS on Ollama answered nothing as a checker**: it ignores "think":
  false, reasoned through the whole token budget and returned an empty
  answer; at "low" it answered wrongly. It now gets "medium" and 4,000
  tokens on top of the answer's.
- This machine's configs now check with qwen3.8:27b (the desktop app's then
  with Gemini); the app's fallback checker had been llama3.2:3b.
- **CodeQL found a slow pattern (py/redos, high)** in reading what a gap
  claim says is missing: a run of filler words ("no any  any  any …") could
  split its spaces many ways and take exponential time on a claim built
  that way, and claims come from models reading job posts. Each filler word
  now owns the spaces after it, and only a claim's first 300 characters are
  read; tests/test_guard.py times a hostile claim.
- README, docs/CONFIG.md, docs/run/nas.md, config.example.yaml and the
  guide's AI page name qwen3.8:27b as the checker to pull.
- tests/test_guard.py and tests/test_ai.py cover gaps (including a made-up
  claim using gap words to pass), matching, glued text, the work span and
  the measured block.

## Fixed — 2026-10-24 — Nothing could be copied in the desktop app

- **No text in the app window could be selected**, on macOS or Windows:
  not a log line on the Activity page, an error, a letter or an advert.
  pywebview makes a page unselectable unless the window is created with
  `text_select=True` (it adds `user-select: none` to the body), and
  `jobdork app` did not ask. It does now; Cmd+C and Ctrl+C copy what is
  selected (pywebview handles the shortcut on macOS, WebView2 on Windows).
  The browser dashboard (`jobdork serve`) was never affected.
- tests/test_app.py checks the window is made with it. Not yet tried in a
  built app.

## Added — 2026-10-24 — Groq as an AI provider

- **Groq** is a fifth provider on the AI page, beside Ollama, Claude,
  Gemini and ChatGPT: open models (Llama, GPT-OSS, Qwen and others) on
  Groq's own servers, fast, paid by use with a free tier whose limits are
  low (about 8,000 tokens a minute for GPT-OSS 20B), so a second reader
  helps. Its key is held in memory like the others, or read from
  `GROQ_API_KEY` in the terminal.
- `openai/gpt-oss-20b` and `-120b` are asked for the answer's exact shape
  (strict JSON schema), with brief reasoning and the reasoning left out of
  the reply, since it counts against the answer's length. Every other
  Groq model gets JSON mode, with the shape in the prompt as for Gemini.
- **Load models** lists Groq's chat models only: not speech (Whisper),
  voices (Orpheus), the classifiers (Prompt Guard, Safeguard), or
  Compound, which searches the web and runs code with what it is sent.
- As for every hosted model, contact details are removed from the resume
  first. PRIVACY.md links Groq's policy and its data page: by default it
  keeps no requests, apart from logs of up to 30 days for abuse and
  reliability, which its Zero Data Retention setting turns off.
- A key typed into feedback text is scrubbed by its `gsk_` prefix too, and
  a run that fails for a missing `GROQ_API_KEY` points at the AI settings.
- No logo on its button yet (the page carries the others' marks inline,
  and Groq's could not be fetched while building this).
- Guide, README, CONFIG, the run guides and privacy notes name Groq; the
  AI page and setup pictures are retaken. tests/test_ai.py checks the
  calls and the model list with the network stubbed.

## Fixed — 2026-10-24 — A job post could send the app into your network

- **Addresses from job posts were fetched as given.** An apply link, a
  careers page or "Check if still open" could name `192.168.1.1`,
  `localhost` or `169.254.169.254`, and the app would send a request into
  the user's own network: a router's page, a printer, a NAS, or a cloud
  machine's metadata. The dashboard refuses such a request itself (token
  and Host checks); the other devices on a home network mostly do not.
- `fetch/http.py` now mounts an adapter on the fetcher's session that
  refuses any request, and any redirect it follows, whose host is not a
  public address: private, loopback, link-local, carrier NAT (100.64/10,
  Tailscale too), multicast, and IPv6's equivalents including
  `::ffff:127.0.0.1`. A name is refused if any address it resolves to is
  one of those. A refusal is not retried, and reads "refused: … is in this
  machine or its network". The AI models, Ollama among them, go through
  `ai/llm.py`, so a local model still works.
- Not caught: a server built to answer with a public address and then a
  private one (DNS rebinding), since the name is resolved again to connect.
- tests/test_fetch_guard.py checks the addresses, a name with one private
  address among public ones, and a redirect into the network from a local
  server; nothing in it goes online.

## Fixed — 2026-10-24 — A drafting agent with your own tools

- **`claude -p` ran with every tool your own Claude Code settings allowed**,
  and with all your MCP servers. It drafts from a job advert, which anyone
  can write, so a posting that talked the agent round could have run a
  shell command your settings allow (`Bash(python:*)`, say), fetched a web
  page, or used a mail or drive server, with your resume in its folder.
  The folder limit covered the file tools, not those.
- `build_command` now passes `--tools Read,Write,Edit,Glob,Grep` (no shell,
  web, subagents) and `--strict-mcp-config` with no config (no MCP
  servers). Checked that the installed CLI (2.1.309) accepts both, without
  calling it. tests/test_generate.py checks the command has no risky tool.

## Fixed — 2026-10-24 — A job post's link could run script in the dashboard

- **The Apply button put a post's address inside its `onclick` string**,
  escaped with `esc()`. The browser decodes `&#39;` back to `'` before the
  handler runs, so an address with a `'` in it (an employer's own site can
  give any) ended the string and ran what followed, in the page that holds
  the dashboard's token: it could read your resume and settings through the
  API. The address now rides in `data-url`, as Open advert's already did.
- **"Also posted at" links used a post's address as their `href`** as given,
  so a `javascript:` one ran when clicked. Every built link now goes
  through `webHref()`, which keeps only `http:`/`https:`; those links open
  through `openOut` like the rest (in the desktop app, in your browser).
- tests/test_page_safety.py reads the page's source and fails on both
  patterns; it failed on the old page.
- SECURITY.md has a new section, "What a job post cannot do".

## Changed — 2026-10-24 — Dependabot waits a week for a new version

- `.github/dependabot.yml` sets `cooldown: default-days: 7` for the actions,
  the base image and pip. `requirements.lock`'s checksums stop a tampered
  copy of a pinned version, not a malicious new release, and those are
  usually found and pulled within days. Updates for a published advisory
  are not held back.
- SECURITY.md says so, records CodeQL default setup (turned on 2026-10-23,
  not yet a required check) and the owner's passkeys on GitHub and Docker
  Hub, and drops those two from the owner's to-do list.

## Changed — 2026-10-24 — A release page opens with its downloads

- **The installers were at the bottom of the page.** GitHub lists a
  release's files after its text, always, and 0.14.4's text is its whole
  changelog, about 110,000 characters: the `.dmg` and the Windows setup
  were a long scroll away. That order cannot be changed on GitHub's side.
- So the page now opens with a **Download** table linking each file
  directly (Mac, Windows, the Docker command, the checksums), then the
  first-open warnings, then how to check a download is the real one, and
  last **What changed**, folded under a line you click to open ("114
  changes in this release"). The files are reached first either way.
- The whole page is built by `scripts/release_notes.py --page <tag> <image>
  <digest>`, which the release job runs, instead of 60 lines of `echo` in
  `docker.yml`; tests/test_release_notes.py checks the order and the links.
- The v0.14.4 page was rebuilt this way by hand (`gh release edit`), with
  its real image digest; its three download links answer.
- 0.14.4 itself was released on 2026-10-24 (tag on the merge of #28): the
  first release with installers, and with its notes from the changelog.

## Fixed — 2026-10-23 — Two dependencies with known vulnerabilities

- **pypdf 6.21.1 had three advisories** (CVE-2026-115572, -115580,
  -115585): a crafted PDF could make reading it run for a very long time.
  jobdork reads PDF resumes, so a malicious one could hang an upload.
  `requirements.lock` now pins 6.21.2, and the `pdf` extra asks for 6.21.2
  or newer.
- **setuptools 84.0.0** (GHSA-xmj3-9gf7-h52w), used only to build: on
  Windows, a crafted wheel could write outside its folder. Now 84.1.0.
- Both were published after the lock was last made, so the security job's
  `pip-audit --strict` would have failed the next push to main. Found while
  measuring the new vulnerability badge. Only those two lines of the lock
  changed, with PyPI's own hashes; `pip-audit` on the lock now finds none.

## Added — 2026-10-23 — Release pages carry the changelog

- **A release page now says what changed**: the `docs/CHANGELOG.md` entries
  written since the release before it, in full, newest first
  (`scripts/release_notes.py`, run by the release job in `docker.yml`).
  Before, GitHub generated the notes from pull request titles, so a release
  said "chore: release 0.14.1 (see docs/CHANGELOG.md) by @jessn-dev in #11"
  and nothing else.
- A release's entries are the ones above the newest entry the previous
  release's changelog had, read from the two tags with git, so nothing has
  to be marked by hand. A page holds 125,000 characters: entries are given
  in full while they fit, and the rest are listed by title, linked to their
  place in the changelog (0.14.4's 110 entries come to about 113,000).
- tests/test_release_notes.py: only the new entries, the first release
  taking all, the overflow linked, GitHub's heading links.

## Added — 2026-10-23 — Badges: build, coverage, vulnerabilities, version, licence, contributing

- The README opens with three rows of badges: **health** (the build, test
  coverage, known vulnerabilities), **ecosystem** (latest release, the
  Docker image's version, Python, the licence) and **community** (pull
  requests welcome, code style, the user guide).
- **Coverage and vulnerabilities are measured here, with no outside
  service or account**: the guide workflow runs the tests under `coverage`
  and `pip-audit` on `requirements.lock` (exactly what the image and the
  installers carry), and `scripts/badges.py` writes two small files that
  shields.io reads from the GitHub Pages site. They are measured on every
  push to main and every Monday, since new advisories appear without any
  change here. Coverage today: 75%.
- **CONTRIBUTING.md**, new, which "PRs welcome" links to: setting up, what a
  pull request needs (tests, changelog, the guide and its pictures, the
  docs), and that contributions are under the GPL. A pull request template
  carries the same checklist.

## Added — 2026-10-23 — A user guide, published on GitHub Pages

- **https://jessn-dev.github.io/jobDork/**: how to use jobdork, page by
  page, for people who will never read the code. Getting started and setup;
  the Dashboard; Job posts; the job post window and every AI tool in it;
  **Match, Fit and AI** explained, with how each is worked out; every
  **status** and tag (age, still open, recruiter, the yellow tags); Search,
  Resume, Sources, AI (readers, checkers, the hallucination check) and
  Settings; **sending feedback**, with screenshots and what is and is not
  sent; and a glossary.
- **22 pictures from the real dashboard**, taken by
  `scripts/guide_screenshots.py` on a made-up person's data
  (`scripts/guide_demo.py`: a nurse in Chicago, invented employers, links to
  example.com), scored by jobdork's own rules. The guide is public, so no
  real resume, search or employer list is ever photographed. Headless Chrome
  over the DevTools protocol (`scripts/guide_shots.mjs`); needs Chrome and
  Node.
- **It cannot fall behind the app**: `tests/test_guide.py` fails when the
  dashboard shows a button or heading the guide never names, a status has
  no row, a menu page has no guide page, or a picture is missing, unused, or
  not taken by the script (so it would go stale). The build is strict: a
  link to a missing page or section fails the pull request.
- Built with MkDocs and Material (pinned in `guide/requirements.txt`; MkDocs
  stays on 1.x) by `.github/workflows/guide.yml`, which publishes from main.
  How to keep it current: `guide/README.md`. The repository's Settings →
  Pages → Source has to be set to GitHub Actions once.

## Added — 2026-10-23 — The pages follow the version, in one step

- **Every page that tells you which release to copy names the current one,
  set in one step.** `python scripts/set_version.py 0.14.5` writes the
  version into `pyproject.toml` and into every page where a reader copies
  it: the image tag (`jessengolab/jobdork:…`), the installers' names
  (`jobdork-…-macos-arm64.dmg`, `…-windows-x64-setup.exe`), and the tag
  command in SECURITY.md. Before, `compose.yaml` and the NAS guide named
  0.14.4 by hand while `pyproject.toml` said 0.14.3, and nothing would have
  noticed either going stale; the run guides wrote `<version>` instead, which
  a reader had to look up.
- Found by shape, in every page (README, SECURITY.md, PRIVACY.md,
  `compose.yaml`, all of `docs/`), so a new page is covered without being
  listed. The changelog and the history are left out: they name past
  versions on purpose. A version stated as a fact ("0.14.4 or newer",
  "0.14.3 and older") has none of these shapes and never changes.
- **A stale page fails the checks**: `tests/test_version.py` runs
  `set_version.py --check`, so a pull request that sets a new version
  without the pages cannot merge, and the release tag's check in
  `docker.yml` runs it again before anything is built. SECURITY.md's release
  steps start with the script.
- `pyproject.toml` set to 0.14.4 with it, as the next release (step 1 of
  SECURITY.md's release; tag `v0.14.4` after merging).
- README: a release badge that shows the newest release by itself.
- tests/test_version.py: every page on the pyproject version, new pages
  included and the changelog left out, what to copy changed and facts kept,
  a malformed version refused.

## Changed — 2026-10-23 — Licence: GNU GPL v3 or later

- **jobdork is now under the GNU General Public License v3.0 or later**
  (strong copyleft), replacing MIT. `LICENSE` is the FSF's text unchanged,
  `pyproject.toml` says `GPL-3.0-or-later`, and so does the image's
  `org.opencontainers.image.licenses` label; the README badge and License
  section say what it means in a line.
- **The installers now carry `LICENSE`**, as the GPL asks of anything
  distributed built: CI installs jobdork editable, whose metadata names the
  licence file without holding it, so the MIT text was never in the app
  either. `packaging/jobdork.spec` adds it to the bundle, and the app's
  `--self-test` fails a build without it.
- Both authors of every commit are the owner, so no one else's permission
  was needed.
- The vendored humanizer rules keep their own MIT licence, which the GPL can
  carry. HalluLens is CC BY-NC, which it could not: none of its code,
  prompts or data was ever included, only its method, and the README's new
  Credits section says so.

## Fixed — 2026-10-23 — The hallucination check had one checker and no fallback

- **Readers could fall back through six models; the check could not.** The
  second model (`llm.checker_*`) was one model: when it was down, out of
  credit or rate limited, the claim check failed and the output was recorded
  unchecked, lowering coverage, though other ready models were listed. With
  no second model chosen, the check ran on the same reader chain that wrote
  the output, so with several readers the first still checked its own work.
- **`llm.checkers` is now a list, up to six, tried in order** like
  `llm.readers` (setup offers three). The old `checker_provider` and
  `checker_model` still read as a one-entry list, and are written as the
  first checker's, as `provider` and `model` are for readers.
- **Who checks, in order** (`guard.checking`): the chosen checkers, then the
  other readers, then the model that wrote it, only when nothing else is
  ready. The writer is the reader that answered (`Settings.answered`), so
  when the second reader wrote because the first was down, the first may
  check. One chain, so `complete_json` hands over to the next on any failure.
  The report's `second` is now whether the model that answered is not the
  writer.
- The guard checks on a copy of the settings: its calls no longer change
  which model a verdict is recorded under (`ai_outputs.model`), which they
  could when the guard and the writer shared one chain.
- A checker that is the same model as the writer is passed over for that
  output (and for the judged post's second score), instead of the config
  refusing a checker equal to the first reader: with fallback, the first
  reader can be the right checker for what the second wrote.
- **The AI page** shows checkers as cards, like readers: Earlier, Remove,
  **Add another checker**, a key and models per card; hidden while no reader
  is set. **Save and test** asks every checker. The second score on judged
  posts tries the checkers in order too (`Settings.checker_chain`).
- docs/CONFIG.md (`llm.checkers`), docs/ARCHITECTURE.md, README.
  tests/test_guard.py (a checker that cannot answer hands over, reader
  fallback with the writer last, a checker equal to the writer passed over),
  tests/test_readers.py (config list and old keys, the page's save, setup's
  limit of three). Checked on the AI page against a scratch config: two
  checker cards, saved back as `llm.checkers`.

## Changed — 2026-10-23 — Documentation: one guide per way to run it

- **docs/run/**, new: [README.md](run/README.md) puts the ways to run
  jobdork side by side (what each gives, what it needs, where it keeps your
  files, how to move between them), then one guide each:
  [desktop.md](run/desktop.md) (installers, the first-open warning,
  verifying a download, schedule, notifications, updates, uninstalling,
  `--debug`, building the installers), [source.md](run/source.md) (install,
  the extras, the dashboard, the window on Linux, updating),
  [cli.md](run/cli.md) (every command, keys from the environment, cron and
  Task Scheduler by hand), [docker.md](run/docker.md) (the image on your own
  computer, the data folder, Ollama from a container, updating) and
  [nas.md](run/nas.md) (docs/DEPLOY.md, moved; DEPLOY.md now points there).
- **What was missing:** no guide for the desktop app beyond a paragraph,
  none for Docker on your own computer apart from the NAS, no list of the
  commands for terminal-only use, no uninstall or update steps, nothing on
  Linux needing GTK or Qt for the window.
- **What was outdated:** the README installed through one path and mixed in
  the others; `jobdork dork --help` showed `python main.py`, a file that has
  not existed since the move into `jobdork/dork/` (now `jobdork dork`, with
  its own usage name); `jobdork --help` said "North American job boards";
  `jobdork/data/humanizer/README` named `jobdork/humanize.py`.
- **The README** is shorter: an Install and run table pointing to the guides,
  and the dork generator's 360-line flag reference moved to
  [docs/DORK.md](DORK.md). New Credits section for humanizer, HalluLens,
  GeoNames and Lucide. Links to DEPLOY.md in SECURITY.md, CONFIG.md,
  compose.yaml, the Dockerfile and `core/schedule.py` updated.

## Added — 2026-10-23 — Update from the app: download, check, install

- **Settings → Updates** says which version you have and whether a newer one
  is out, with **Check now** (asks GitHub at once, whatever the daily
  check's timing) and the daily check switched by a button, **Turn off the
  daily check** / **Turn on**, instead of a checkbox.
- **Update to 0.x.y**, in the desktop app on macOS (Apple Silicon) and
  Windows: downloads that release's installer for this computer from the
  project's own GitHub release downloads (nothing else is fetched) into
  Downloads, checks it against the release's `SHA256SUMS.txt`, deletes it if
  it does not match, and opens it: the Windows installer replaces the app,
  the Mac disk image opens for the new app to be dragged into Applications.
  It runs as a job, with its progress under the Dashboard's log
  (`updates.download_installer`, `POST /api/update/install`). Elsewhere (pip,
  Linux, Docker) the section says how to update that copy and links the
  release page.
- The Dashboard's banner for a new version now has **Update**, which opens
  Settings, and the first time a version is seen, a notification says so,
  once (`updates.first_notice`).
- tests/test_notify.py: the checksum match and mismatch, downloads only from
  this repository's releases, Check now, the once-only notice.

## Added — 2026-10-23 — Notifications, with a bell

- **Your computer's own notifications** (`core/notify.py`) when a scan finds
  new job posts (one you start or a scheduled one: "3 new job posts. The
  scheduled scan found 3 new job posts (40 kept in all)"), when a scan fails,
  and when a newer jobdork is out. Never for a scan that found nothing new.
  - **macOS**: Notification Center. The desktop app posts as itself through
    the system's notification framework (UserNotifications, a new macOS
    dependency of the `app` extra, carried by the build and checked by its
    self-test), after macOS asks once for permission; run any other way,
    through `osascript`. Sound: "Glass", a bell. Checked on this Mac: a test
    notification appeared, with its sound.
  - **Windows**: a toast in the Action Center under jobdork's name: the
    installer gives the Start menu and desktop shortcuts the app's
    AppUserModelID (`io.github.jessn-dev.jobdork`), which is how Windows ties
    a toast to an app; the toast's text goes to PowerShell through the
    environment, not the script. Not tried on Windows yet.
  - **Linux**: `notify-send`, with the bell sound hint.
  - **Docker**: no desktop, so the page shows a notice and rings a bell made
    in the browser (Web Audio, nothing loaded) while it is open.
- **Settings → Notifications**: on or off, sound on or off, and **Send a
  test notification**. `notifications: {enabled, sound}` in config.yaml
  (docs/CONFIG.md); `JOBDORK_NOTIFY=off` turns them off for a run, and the
  tests set it, so no test pops anything up. A notification that fails is
  logged and never fails a scan.
- PRIVACY.md and the Windows installer's privacy page say so.
  tests/test_notify.py (each system's command, escaping, the settings, a
  failing command), tests/test_serve.py.

## Changed — 2026-10-23 — A Settings page, behind a gear where Dark mode was

- **Settings**, at the bottom of the menu with a gear icon, replaces the Dark
  mode switch there, and holds what is about how jobdork runs rather than
  what you are looking for:
  - **Appearance**: Dark mode.
  - **Schedule a run** (was the Dashboard's "Scan by itself"), with **Run a
    scan now** beside it.
  - **Notifications** and **Updates** (above).
  - **Built-in employer boards**: how many a scan reads, and **Turn off** /
    **Turn on**; industries and single boards stay on the Sources page,
    which it links.
  - **Where your files are** and **Clean up job posts**, moved from the
    Dashboard, which is now the runs and their numbers.
- Checked in headless Chrome on a copy (the browser extension was not
  connected): every section draws, the sound button wrote
  `notifications.sound: false` and changed its label, and the Sources link
  opens Sources. README, PRIVACY.md, docs/CONFIG.md and docs/DEPLOY.md name
  the new places.

## Changed — 2026-10-23 — Adzuna and USAJOBS keys are saved only once they work

- **A key is kept only when the source accepted it.** Saving already tried
  each key with one search and refused a key the source refused; a key it
  could not be asked about (offline, the service down) was saved with "Saved,
  but not tried". Now that is refused too: "Not saved: USAJOBS could not be
  asked (timed out), so the key could not be tested. Try again when it
  answers" (HTTP 503), so a key that does not work never sits in the keys
  file. A key that works says "Tested: USAJOBS accepted the key, and it is
  saved." In setup and on the Sources page alike (`api.setup_keys`).
  tests/test_core.py.

## Added — 2026-10-23 — Up to six AI readers, each taking over when the one before cannot answer

- **`llm.readers`**: the AI readers in the order they are asked, up to six,
  each a provider and model (and for Ollama its own address, if not the
  usual one). The same provider can be listed again with another model, not
  the same model twice. A config from before, with one `provider` and
  `model`, is that one reader, and the first reader is always also written
  as `provider` and `model`, so an older jobdork still reads it.
- **Fallback, at every model call** (`llm.complete_json`): the first reader
  that is ready (a key held, a model chosen) is asked; when it cannot answer
  (not reachable, rate limited, a refused key, an error) the next is, in
  order. What it produced is recorded under the reader that answered, so a
  verdict or letter names the model that wrote it. When none can, the error
  lists each reader's reason. The second model, which checks the first's
  claims, is unchanged and separate.
- **The AI page lists them as cards**, one per reader, each with its
  provider, Ollama address or key, and model list; **Add another reader**
  below, **Earlier** to move one up, **Remove**. A key is per provider, so
  two readers on Claude share one. **Save and test** asks each reader on its
  own and says which answered and how fast, and which could not and why.
- **Setup's AI step** shows one reader and **Add another reader**, up to
  three there; the AI page allows six. The server holds to both (400 "at
  most 3 AI readers in setup; add more later on the AI page").
- Checked over HTTP on a copy (the browser extension was not connected): the
  existing config read as one reader, two Ollama readers saved and read
  back. Not yet seen in a browser. tests/test_readers.py (fallback, order,
  limits, the old form), docs/CONFIG.md, config.example.yaml, README.

## Added — 2026-10-23 — The version check can be switched off in the app, and the installer says what goes where

SignPath Foundation's terms ask that software which goes on the network by
itself shows its privacy policy when installed and lets you turn that off.
jobdork's one such request is the daily version check, which only an
environment variable could stop.

- **"Updates" on the Dashboard**: a box, ticked by default, "Check once a
  day whether a newer jobdork is out". Unticking it writes
  `update_check: false` to config.yaml (new setting, docs/CONFIG.md) and the
  check asks nothing; ticking it again checks at once. When
  `JOBDORK_UPDATE_CHECK=off` is set, the box is unticked and greyed, and says
  the environment wins. Saving it starts no scan or re-screen.
- **The Windows installer shows a privacy page before installing**
  (`packaging/privacy.txt`, Inno Setup's `InfoBeforeFile`): what jobdork
  keeps and where, what it sends where and when, the version check and how to
  turn it off, what an uninstall leaves, and a link to PRIVACY.md.
  `.gitignore` drops every `*.txt` (the dork tool's output), so it names
  this file as an exception; without it CI's installer build would have
  failed on a missing file.
- PRIVACY.md says how to turn the check off in the app. Checked over HTTP on
  a copy (the browser extension was not connected): the card is on the page,
  saving writes the setting, and the version check then answers without
  asking. Not seen in a built Windows installer yet. tests/test_schedule.py,
  tests/test_serve.py.

## Added — 2026-10-23 — A privacy policy and a code signing policy

For the application to SignPath Foundation's free code signing, whose terms
ask for both, and because jobdork never said in one place what it sends where.

- **[PRIVACY.md](../PRIVACY.md)**: what jobdork keeps and in which folders
  (settings, database, backups, resume, keys file, documents, logs; AI keys in
  memory only), how to delete it (Start over; uninstalling leaves the data
  folder), and every place it goes on the network: job boards and employers'
  sites (your titles and place as search terms), Adzuna and USAJOBS with your
  keys, the AI provider you choose (adverts and your resume, under that
  provider's policy), the Feedback relay (only on Send; a public issue, an
  email with screenshots and your reply address, your IP kept an hour for the
  rate limit), the once-a-day version check (`JOBDORK_UPDATE_CHECK=off`), and
  email digests through your own Resend key. And what it does not do: no
  analytics, accounts or tracking, the Dashboard on 127.0.0.1 behind a token,
  no system changes beyond its folders and the optional scan schedule.
- **"Code signing policy" in the README**, in SignPath's required wording:
  what is signed (the Windows installer and program, built by
  `desktop.yml` from a tag), that each release is approved by hand, the team
  roles (committers, reviewers and approvers, with multi-factor
  authentication), and a privacy statement linking PRIVACY.md. It says
  signing has been applied for and the installers are unsigned until it is
  granted. The README's documentation table and licence line link both.
- **Release notes** (`docker.yml`) link the code signing policy and the
  privacy policy at the release's own tag.

## Added — 2026-10-23 — Europe, Australia and the Gulf: employers added and measured

- **119 large employers of Europe, Australia, New Zealand and the Gulf**,
  across industries, are in `scripts/candidates.csv` (996 candidates in
  all), and 18 of their boards were found and verified (423 built in): ING,
  Santander, Airbus, ASML, Vodafone, Ericsson, Lloyds Banking Group,
  Equinor, Boots, Ocado and Delivery Hero in Europe; Telstra, Commonwealth
  Bank, Westpac and NAB in Australia; Emaar's hotels, First Abu Dhabi Bank
  and DP World in the Gulf. Six held back by the check for a sister
  company's board (found deep in a site, under a name that is not the
  employer's) were checked by hand and accepted with reasons in
  `scripts/boards_review.csv`: DP World's adverts name DP World, Airbus's
  Workday tenant is `ag`, Westpac's jobs are at its Barangaroo head office.
- **The other 101 found nothing readable**: most name no board on their
  site (Tesco, Siemens, Allianz, Woolworths, BHP, Emirates), some refuse
  scripts (BNP Paribas, Nestlé, Qantas, Aramco), and some use systems with
  no reader (iCIMS at AXA and Booking.com, SuccessFactors' older portal at
  BASF and Novo Nordisk, Taleo Enterprise at Qatar Airways).
- **Measured** with `scripts/coverage_benchmark.py`, which now has
  `--region europe | oceania | middleeast` (and counts a title's hits in
  any case, so German titles are counted). A fresh keyless install, four
  titles, 50 km, jobs kept (of them not remote): London 222 (166), Berlin
  257 (168), Madrid 172 (73), Paris 116 (53), Amsterdam 110 (58), Stockholm
  73 (31); Sydney 159 (135), Melbourne 130 (106), Auckland 44 (10); Dubai 47
  (16), Riyadh 43 (19), Doha 28 (6). Every city is in docs/REGIONS.md, with
  what is left: Europe outside Germany and the Gulf above all.
- Found on the way: Accenture's Workday board answers 429 when several
  scans run back to back, as the benchmark's do; one scan is unaffected.

## Added — 2026-10-23 — Two sources for Europe: Germany's employment agency and Arbeitnow

A keyless install reached Europe through Workable, Himalayas' remote jobs and
the multinationals on the built-in list; Adzuna only with a key.

- **The Bundesagentur für Arbeit's job search** (`arbeitsagentur`):
  Germany's largest list of jobs, searched by your titles from your place
  with your radius in km (all of Germany when you are elsewhere). Places go
  by their German names: "Munich" and "Cologne" found nothing, "München"
  and "Köln" hundreds, so Munich's German-title benchmark went from 46 to
  263 jobs. Titles in
  German, as the adverts are ("Pflegefachkraft"). The advert is fetched for
  the titles your filter keeps, 60 a scan at most; pay comes as a range per
  hour, month or year in euros. The agency marks temporary staffing and
  private placement itself, and those posts are tagged as a recruiter's
  ("the Bundesagentur für Arbeit lists it as temporary staffing"). The
  interface is the one its own site uses, documented by the bundesAPI
  project; robots.txt allows it. Its v4 search answers 403 now, so the
  search is v6 and the advert v4. Runs only when Germany is one of your
  countries.
- **Arbeitnow** (`arbeitnow`): a free public API of jobs in Germany, the UK,
  France, the Netherlands, Switzerland and the rest of Europe, many in
  English. It has no search, so the newest pages (300 jobs each, about 600
  new a day) are read, 10 at most (about five days of jobs), one every two
  seconds, and kept by your titles: at one a second, the benchmark's scans
  of several cities in a row met a 429 at the fifteenth page. A bare city
  ("Amsterdam") is given its country ("Amsterdam, Netherlands"): screening
  places a bare city only in your own countries and keeps one it cannot
  place, so on a first measure someone in Stockholm kept 84 of Arbeitnow's
  143 matches, Amsterdam's and London's among them; with countries added,
  38 (remote jobs, and ones that give no place, which are kept from every
  source). Its terms ask for a link back: the stored link is the Arbeitnow
  page. Runs when a European country is yours, or none is.
- **"Still open" asks the agency**: its job page is drawn by script and says
  nothing to a reader, so the check asks the job's own record, and a job the
  agency no longer lists (404, `STELLENANGEBOT_NICHT_GEFUNDEN`) is closed on
  its word. **Fetch missing adverts** reads the same record for a job kept
  without its advert. Arbeitnow's adverts arrive whole and are not fetched
  again.
- Both are in the default `sources.keyless`; a config that lists its own
  sources adds them by hand (docs/CONFIG.md).
- Checked live, for Berlin with three titles: the agency 420 jobs (60 with
  their adverts) in 35 seconds, Arbeitnow 221 matching jobs across Europe in
  54. tests/test_europe.py (offline).
- **Looked at and not built:** Remotive's public API now lists 9 jobs;
  Working Nomads' 41; GulfTalent and Bayt close themselves to scripts;
  Workforce Australia did not answer. Details in docs/REGIONS.md.

## Added — 2026-10-23 — SAP SuccessFactors career sites are read: 37 more employers

- **SuccessFactors was the largest system with no reader** (13 misses on the
  test lists, and on a fresh probe of the 528 candidates without a board, 40
  employers' careers pages pointed at it, 33 in the US). Most front it with
  SAP's Career Site Builder, and the careers-site reader (`fetch/site.py`)
  now reads those sites both ways they publish jobs:
  - **A sitemap that is a feed.** `/sitemap.xml` is an RSS feed of every open
    job with its title, place, closing date and whole advert (American
    Airlines, XPO, Sephora, Colgate, ExxonMobil). Jobs are taken straight
    from it, every one whose title matches yours: one request per employer,
    no posting page read. A closing date past today leaves a job out.
  - **Microdata.** Posting pages that mark the job up with `itemprop`
    attributes instead of a JSON-LD block (Duke, JetBlue, Aflac) are read
    into the same shape (`microdata_posting`); any careers site doing the
    same now reads too. A site's own name as employer ("Duke Careers") is
    trimmed to the employer's.
  - The feed is read with patterns, as every sitemap here is, not an XML
    parser: it comes from someone else's server (CI's code scan, bandit
    B314, caught the first version).
  - Not used: the same sites' `/services/rss/` search feed, which their
    robots.txt closes. Nothing that answered with a bot challenge (SAP's own
    jobs.sap.com) is worked around.
- **Discover takes these as careers-site boards**: a feed sitemap is its own
  proof, with no posting page read, and the SuccessFactors "no adapter" note
  is no longer added beside a site board that reads it.
- **37 boards added** (405 in all, 340 of them US): American Airlines,
  JetBlue, Amtrak, Royal Caribbean, Wyndham; ExxonMobil, Phillips 66,
  Westinghouse, NextEra, Dominion, DTE, Entergy; XPO, GXO; Duke and Purdue
  universities; Aflac, Lincoln Financial; Colgate-Palmolive, Hershey,
  McCormick, Under Armour, Sephora, Tractor Supply; AGCO, LyondellBasell,
  Mohawk; Huntington Ingalls; Cintas, Foundever, EY, Paramount; in Canada
  Scotiabank, Rogers, the University of Toronto; Singtel; the Hong Kong
  Jockey Club. Tractor Supply's was held back because `tractorsupply.jobs`
  leads to `tractorsupply.careers`; that is its own site, accepted in
  `scripts/boards_review.csv` with the reason. Edison, NRG and Wipro use
  only SuccessFactors' older portal, which has no public listing, and are
  still not read.
- Checked live: the feed gave 39 American Airlines and 54 XPO jobs for three
  titles in one request each; microdata gave Duke 40 and JetBlue 13.
  tests/test_site.py (offline, shapes from those sites).

## Changed — 2026-10-23 — The resume's skills cover every field, not only tech

- **596 skill terms in 13 fields** (`FIELDS` in `search/resume.py`), up from
  about 250 that were all tech: healthcare (patient care, med-surg, IV
  therapy, Epic, ACLS, BLS, medical coding…), finance and banking (month-end
  close, reconciliation, GAAP, NetSuite, KYC, underwriting…), sales and
  marketing, customer service, retail and hospitality, logistics (forklift,
  RF scanner, Class A CDL…), manufacturing and trades, construction and
  engineering, education, human resources, legal, and office and business.
  A nurse's resume used to show almost no skills, and fit scores outside tech
  rested on next to nothing.
- **An advert's terms count only from the fields your resume is in**
  (`fields_of`, `near`). A word is a skill in one field and plain English in
  another: a nurse's advert says "rest breaks" and "able to go up stairs",
  which were counted as REST and Go. A field is yours when your resume names
  two of its skills that are not common to every field (`WEAK`: Excel,
  scheduling, customer service, HIPAA…); one passing mention ("built a
  patient care app") does not make a programmer's resume a nurse's. Your own
  skills are kept to your fields too, so "go-to preceptor" is not the
  language. A resume in no field yet counts every term, as before.
- **Tech is one field**, so a tech resume scores as it did: on your own
  resume and the 2,251 stored adverts with text, nothing it counted before
  stopped counting; Jira and Confluence, now listed, count.
- **FAIR, REST, SOC, R, POS and CEN match only in capitals**: "fair chance
  employer" had counted FAIR, the risk model, as missing in 219 of those
  2,251 adverts.
- **Five times faster**: the patterns are compiled once (there are more of
  them than Python's own pattern cache holds) and each is tried only when a
  plain substring test finds the term. Scoring those 2,251 adverts took 4.3
  seconds instead of 20.5.
- The resume review's skills line (`ai/tools.py`) uses the same fields.
  tests/test_skills.py.

## Added — 2026-10-23 — The built-in employer boards on the Sources page

- **"Built-in employer boards" on Sources** lists all 368 that come with
  jobdork: employer, industry, countries, jobs at the last weekly check, and
  the system it runs on, with whether this setup reads it and, when not, why
  ("hires outside your countries", "not one of your industries", "switched
  off"). Before, the only view was `jobdork sources` and editing
  `sources.directory` in config.yaml by hand. A find box, and All / Read /
  Not read.
- **Switched there**: the whole directory on or off, the industries (each
  with its number of boards; none ticked reads every one), and **single
  boards**, by a new `sources.directory.skip`, a list of employer names, for
  one that keeps listing jobs you never want (`directory.select`,
  `directory.why_not`, `GET /api/directory`, `setup.rewrite`).
- **Boards newly read start a scan**, as an added title does: a save is
  compared by the boards it reads (`serve.search_changes`), so switching the
  directory on, clearing the industries back to every one or reading a
  skipped board again all scan for them. Before, only an industry added
  counted, and clearing the list read every industry without a scan.
- Checked in a browser on a copy: 191 of 368 read for its settings;
  switching Boeing off wrote `skip: [Boeing]`, made it 190, and started no
  scan. tests/test_directory.py, tests/test_serve.py.

## Security — 2026-10-23 — A newer Python base image

- **Both `FROM` lines in the Dockerfile** move to the current
  `python:3.14-alpine` (`sha256:601e99e0…`, read from Docker Hub today),
  newer than the one Dependabot's pull request #22 proposed on 2026-10-14,
  which therefore supersedes it (#22 closed). Not built here (Docker is not running on
  this machine); CI's `image` job builds it and runs the suite in it.

## Added — 2026-10-23 — The desktop app asks before closing mid-scan

- **Closing the window while a scan or another job runs asks first**: "Scan
  is still running. Closing jobdork stops it, and what it has not saved yet
  is lost", with **Close anyway** and Cancel. The red button, Ctrl-F4 and
  Cmd-Q all ask; with nothing running, the window closes at once as before.
  The server hands the app a `busy()` along with its address
  (`serve(on_ready=…)`), and the window's `closing` handler only decides
  whether pywebview asks and what it says (`app.ask_before_closing`): a
  dialog shown from inside that handler would wait on the main thread it is
  running on. tests/test_app.py. Not tried on Windows.

## Added — 2026-10-23 — Where your files are, on the Dashboard

- **A "Where your files are" card** lists the folders worth knowing about:
  settings and data (config, keys file, database, resume), backups (made
  before every delete), logs, and letters and resumes. Before, the desktop
  app's folder was named only in the README. Each has **Open**, which shows
  it in Finder, Explorer or the file manager (`/api/folders`,
  `/api/folders/open`). Only the four, by name: the page cannot ask for any
  other path. Open is offered only when the server is on the machine the
  page is on: not in a container, and not when `JOBDORK_ALLOW_HOSTS` opens
  the dashboard to other machines, where it would open a window on the NAS.
  A folder nothing has been written to yet says so. tests/test_serve.py.

## Added — 2026-10-23 — The Dashboard says when a newer version is out

- **A banner at the top**, "jobdork 0.14.4 is out. You have 0.14.3", with a
  link to the release and what to do for this install: the installer for the
  desktop app, the image tag for Docker, `git pull` and `pip install -e .`
  for a clone. **Not now** hides it until the next release.
- **`core/updates.py`** asks GitHub's releases API for the latest release, at
  most once a day (kept in `version-check.json` beside the database), and only
  when the page asks: never at start, so an offline start waits for nothing.
  Pre-releases are ignored, and a copy with no version (a clone never
  installed) asks nothing. What is sent is the request itself and a
  User-Agent naming jobdork and its version. `JOBDORK_UPDATE_CHECK=off` turns
  it off (docs/CONFIG.md); `tests/conftest.py` and `tests/run_all.py` turn it
  off for every test. tests/test_schedule.py. Checked in a browser on a copy
  with a stored answer, so nothing went online: the banner shows, and Not now
  keeps it away after a reload.

## Added — 2026-10-23 — Scans that run by themselves; one scan at a time

- **"Scan by itself" on the Dashboard**: never, every day, every weekday, or
  once a week, at a time you pick. It is written into the computer's own
  scheduler (`core/schedule.py`), so it runs whether or not jobdork is open:
  a LaunchAgent on macOS (a time missed while the Mac slept runs when it
  wakes), a Task Scheduler task on Windows, made from XML so it can say "run
  a missed time when the PC is next on" and "on battery too", which
  `schtasks /Create` alone cannot, and a crontab line on Linux. The scheduler
  is the only record: the card reads back what is there, so an entry removed
  by hand reads as off, one set by hand reads as "other", and one that starts
  another copy of jobdork (the app moved, a second install) says to save
  again. In a container the card says to schedule `docker exec` on the host
  instead (docs/DEPLOY.md).
- **It starts this install, not a path inside it.** The dork tool's `--cron`
  writes `sys.executable` and `generator.py`, which in the desktop app is a
  file inside the app that nothing can run. The schedule runs the app's own
  program with `--scan` (`app.scheduled_scan`: a scan in the app's folder, no
  window), or `python -m jobdork -c <config> scan --scheduled` (pythonw on
  Windows, so no console window opens at 8 a.m.).
- **`scan --scheduled`**: no progress lines, output to
  `logs/scheduled-scan.log` beside the config (in the data folder in a
  container), kept to about 512 KB by dropping its older half; listed under
  All runs as from the "schedule". It does nothing, and says why, before
  setup has given it titles.
- **Only one scan at a time, across processes.** The dashboard already ran
  one job at a time, but a scan from a terminal or the schedule is another
  process, and two at once double every request to hosts that are paced on
  purpose. `scan.run` now holds an operating-system lock on `scan.lock`
  beside the database (`flock`, or `msvcrt.locking` on Windows), which the
  system lets go of however the process ends, so a crashed scan cannot leave
  the next one refused. A second scan stops with "another scan is already
  running": `jobdork scan` exits 3, a scheduled one steps aside and exits 0,
  and its run says "not started: another scan was running".
- Checked on this Mac: launchd loaded the entry and `launchctl print` showed
  its times and paths; a `kickstart` ran `scan --scheduled` from the repository
  while another process held the scan lock, and it logged the refusal and was
  listed from the "schedule"; then removed. In a browser on a copy: Save
  wrote a weekly entry, a reload read it back, Off removed it. Not tried on
  Windows or Linux. tests/test_schedule.py (with every scheduler given a
  stand-in, so the suite installs nothing), tests/test_serve.py.

## Added — 2026-10-23 — Warnings and errors lists every error the app meets

So that whatever goes wrong can be reported from the Feedback page, which
attaches this list. Before, only what jobdork's own code logged was there.

- **A page request that crashes** (an error the server did not expect) is
  logged as "a request to the dashboard failed: <the error>". It was only
  printed to the terminal, or to `logs/app.log` in the desktop app.
- **Errors from the libraries jobdork uses** (the HTTP client, the PDF
  reader, the app's window), which log under their own names. Errors only:
  their warnings are mostly noise about other people's files. Each is listed
  once; jobdork's own are not copied twice.
- **A background task that dies of an exception**, which Python only prints
  to a terminal: "a background task stopped (<name>): <the error>".
- **Problems in the page itself**: a script error, a request the server
  failed (HTTP 5xx) or did not answer, and every error message shown to you
  as a toast, prefixed "in the page:". The page sends them to
  `/api/page-problem` (token required, warnings and errors only, 600
  characters, no query strings since they can hold what you typed); each
  text once a minute and at most 30 a page load.
- Checked in a browser on a copy: a script error and an error toast appear
  under Warnings and errors and in the Feedback report's preview.
  tests/test_telemetry.py, test_serve.py (which now runs jobdork's own
  server class, as the app does).

## Changed — 2026-10-23 — The AI verdict reads your projects and education

- **"Ask AI" and the verdicts after a scan now read the projects and
  education added on the Resume page**, not the resume file alone: fit
  scores and tailored resumes already did. They go to the model in their
  own block after the resume (`<<ADDED>>`), so a long resume cannot push
  them past its 12,000-character cap, and the prompt says they count as
  part of the resume. The second model gets them too, and the claim check
  counts them as your record, so a reason that quotes a project is not
  struck out as unsupported.
- Verdicts made before a project was added are not redone by themselves;
  "Ask AI again" on a post, or the next scan's AI run for new posts, uses
  them. tests/test_guard.py.

## Security — 2026-10-23 — pypdf 6.21.1

- `requirements.lock`: pypdf 6.19.0 → 6.21.1 for eight advisories
  (CVE-2026-113786 and CVE-2026-113789 to -113795; fixed by 6.21.1 at the
  latest), which failed CI's dependency audit on pull request #25. Hashes
  from PyPI, and the downloaded wheel matched. The `pdf` extra now asks for
  `pypdf>=6.21.1`, so a fresh `pip install '.[pdf]'` cannot pick a
  vulnerable one. `pip-audit --strict` passes; the suite and a real resume
  PDF read the same.

## Added — 2026-10-23 — Feedback is sent: the relay is live

- **The feedback relay is deployed** on Cloudflare Workers at
  `https://jobdork-feedback.jessengolab-dev.workers.dev` (from
  `relay/feedback/`, `npx wrangler@4.150.0 deploy`). Its keys and both email
  addresses are Worker secrets, sent from `relay/feedback/.env` with
  `wrangler secret bulk`; that file is git-ignored and not the repository's
  own `.env`, which jobdork loads at start. Preview URLs are off.
- **Every copy sends there**: `RELAY_URL` in `core/feedback.py` is the
  relay's address, so the Feedback page's **Send** works in pip, Docker and
  desktop installs alike. `JOBDORK_FEEDBACK_URL` replaces it for one copy,
  and `off` turns Send off (leaving "Open as a GitHub issue" and "Save as a
  file"). docs/CONFIG.md and the relay README say so. The test that checks
  sending with no relay now blanks the address first: with one built in, it
  would have filed a real issue.
- **Five reports an hour per address**, in a KV namespace bound in
  `wrangler.toml`. It counts every request, invalid ones too.
- Checked: a test report through jobdork's own `feedback.send` opened issue
  #24 with `question` and `from-app`, its screenshot kept off the issue and
  emailed, and the email arrived (closed afterwards); the deployed relay
  refuses a GET and an unknown kind; the sixth request in an hour gets 429.
  Not checked: the Feedback page's Send button in a browser.

## Changed — 2026-10-23 — The feedback relay deploys from the repository

Groundwork for deploying it; not deployed yet.

- **`relay/feedback/wrangler.toml`**: `npx wrangler@4.150.0 deploy` from
  that folder, with no generated project to copy the Worker into. Only the
  repository name is in it; the keys and both email addresses are Worker
  secrets, so no address of yours lands in this public repository. A
  commented block turns on the five-an-hour rate limit.
- **Works without a verified domain**: with no `FEEDBACK_FROM` the relay
  sends as Resend's test sender (`onboarding@resend.dev`), which may mail the
  Resend account's own address, enough for reports to the maintainer.
- **A missing label no longer loses the issue**: GitHub refuses an issue
  naming a label the repository lacks (422), and the relay now files it
  without labels instead of giving up on it. The `from-app` label was also
  created on the repository.
- **`relay/feedback/test.mjs`** runs the Worker against stand-ins for GitHub
  and Resend (`node relay/feedback/test.mjs`, 5 checks): the issue and the
  email, the reporter's address and the screenshots kept off the issue,
  either service down, and what is refused before anything is sent.
- README rewritten for this; `.wrangler/` and `node_modules/` ignored.

## Changed — 2026-10-23 — "Add a Job Post" on the Sources page

- The form for adding a job post from its link moved from the Search page
  to Sources, under the keys, and is called **Add a Job Post**: Search is
  what you look for, Sources is where posts come from. Sources' menu
  description says so.

## Added — 2026-10-23 — The search applies itself

- **A change on the Search page re-screens your job posts by itself**: a
  job title removed, an exclude or dealbreaker added, the place, distance,
  work arrangement or pay changed. Posts that no longer pass, and which you
  have not acted on, are removed from Job posts and remembered under
  "Dropped by your filters" with the rule and reason, where they can be kept
  anyway; a later scan that matches one again brings it back
  (`scan.rescreen` now records what it removes). Re-apply filters, pressed
  by hand, still only re-scores.
- **Adding a job title, a country or an industry also starts a scan**, or a
  new place to search from: posts for those were never fetched.
  `serve.search_changes` tells the two apart; the age limit and other
  display settings start nothing. During setup nothing starts: setup runs
  its own first scan.
- **A change made while a job runs waits for it** instead of being refused:
  `Runner.queue` keeps one waiting job of each kind, built when its turn
  comes so it uses the settings as they are then. Several quick edits are
  one re-screen. The toast says what started ("Re-applying your search to
  the job posts. Scanning for what you added.") or what it waits for.
  Saving or deleting a project or an education entry queues its re-score
  the same way, instead of telling you to press Re-apply filters later.
- Checked on a copy of the live database: removing "infrastructure
  engineer" re-screened 2,262 posts in about 35 seconds and moved 94 to
  Dropped; 80 page requests during it all answered. tests/test_serve.py
  (the queue; what a change starts; remove re-screens, add scans, the age
  limit starts nothing), test_agency.py (removed posts are remembered as
  dropped, acted-on posts stay). The test server records queued jobs rather
  than running them: a saved title in one test had started a real scan
  that went online.

## Fixed — 2026-10-23 — "database is locked" behind a re-screen

- **A page request during a re-screen could fail with "database is
  locked"**: every request opens the database, and opening wrote a row to
  `meta` (an insert that does nothing still waits for the write lock),
  while the re-screen held the lock for fifty posts at a time, which could
  outlast SQLite's five-second wait. Opening now reads first and writes only
  when the row is missing, and the re-screen commits at least twice a
  second. Found by the browser check of the automatic re-screen.

## Added — 2026-10-23 — Education added on the Resume page

- **Education your resume does not show yet** (a degree finished since, a
  course under way) is added on the Resume page below Projects, the same
  way: a list, and "Add education" opening a form with the qualification,
  school or provider, location, started, finished or expected, and details
  (honours, GPA, courses). Schema 11 adds the `education` table (in the
  same, not yet released, step as projects' kind and part).
- **Every entry goes into a tailored resume** under Education, newest first
  (still studying first), replacing the model's line for the same school
  and a matching qualification ("BS Computer Science" and "B.S. in Computer
  Science"), added when the resume lacks it (`writer.with_own_education`).
  The model is told about these lines, and the facts check accepts schools
  and qualifications from them. The `claude` CLI path gets them in
  `projects.md` with the same instruction.
- **Fit scores count them**, with the projects: a "Data Analytics
  Certificate" whose details name SQL is SQL you have. Saving or deleting
  one re-scores the job posts.
- Checked in a browser on a copy of the live database (saved, listed with
  its dates, re-score queued behind a running re-screen).
  tests/test_writer.py, test_agency.py.

## Changed — 2026-10-23 — One README

- **docs/README.md is gone.** It was the docs folder's index, not a second
  copy, but it repeated the root README's table of documents and its
  screenshots. Its two parts found nowhere else, "Start here" and "The five
  things worth knowing before you trust the output", are now in the root
  README under Documentation, with their links pointing into docs/.

## Added — 2026-10-23 — Projects of any kind, counted in fit scores and always in a tailored resume

- **Any kind of project.** A project on the Resume page now has a kind (app
  or software, writing or articles, design, research, campaign or event,
  business or operations, teaching, volunteer, personal, other) and your
  part in it ("Lead writer", "one of four developers"), beside the tools,
  the link and the STAR fields. The page's wording no longer assumes
  software. Schema 11 adds the two columns (`projects.kind`, `role`).
- **Fit scores count your projects.** A skill shown only in a project is a
  skill you have: scans and re-screens read the resume and the projects
  together (`scan._load_resume(cfg, store)`).
- **Saving or deleting a project re-scores the job posts** (the same job as
  Re-apply filters), and the toast says so; while a scan runs it says to use
  Re-apply filters afterwards instead. On a copy of 2,262 posts the re-score
  ran well past 20 seconds, like Re-apply filters.
- **Every project you added goes into a tailored resume**, the most relevant
  to the job first (skills, then words, the advert and the project share),
  at most three or four by career stage; the projects gate names any of
  yours left out for room. One the resume only names or links to, which
  the model gave no more than a name or a URL, is described from your own
  STAR fields, with your part, tools and link on the line under its name.
  Someone experienced now gets a projects section after the jobs holding
  only these; the resume's other projects still go in the jobs. Decision
  in docs/DECISIONS.md. The `claude` CLI path's guide says the same.
- Checked in a browser on a copy of the live database: the kinds list, a
  writing project saved with its kind and part, the toast, and the re-score
  starting on the copy. tests/test_writer.py (an experienced person's own
  project after the jobs, a bare link described from the notes, the most
  relevant first), test_agency.py (fit), test_serve.py (re-score on save, an
  unknown kind refused), test_migrations.py (schema 11).

## Added — 2026-10-23 — Recruiters' posts marked, filtered, and warned about

- **Who posted it.** Each job post is called the employer's or a
  recruiter's (`search/agency.py`): a known staffing or search firm (Robert
  Half, Kforce, TEKsystems, Aya Healthcare and about 80 more, US first, all
  industries), a name that says so ("… Staffing", "… Recruiting", "…
  Personnel"), an advert that speaks for a client ("our client", "on behalf
  of our client", "one of our clients"), or a built-in board listed as
  staffing. Names that are also employers' are not on the list (Atrium
  Health, HaysMed, Kelly-Moore), and "our client base", "our client teams"
  and "our clients" are not a recruiter. A recruiter's post shows
  "Recruiter", with the reason on hover and in the post's window.
- **Filter: Posted by anyone / the employer / a recruiter**, on Job posts
  beside the other filters.
- **"May be a job you have already applied to."** A post that may be the
  same job as one you are pursuing (applied, submitted, interviewing or
  offer) reached the other way, through a recruiter and directly or through
  two recruiters, says so on its card and in its window, which explains why
  it matters: a duplicate candidate is often dropped. Same job means the
  recruiter's advert names the employer as its client (within 150
  characters after "client" or a "Company:" label), or the same title words
  in the same city. Remote posts match by name only, and a name anywhere
  else in an advert does not count: on the live data "Oracle", "Google
  Cloud", "Snowflake", "Okta" and "Target" were products and plain words.
  Several applications at one named employer are one line. **Apply** on such
  a post asks once more ("Apply anyway?") before opening it.
- Grouping is unchanged: it keys on the company, and a recruiter's post
  carries the recruiter's name, which is why these were never joined.
- Computed when the list is read, not stored, so it follows your statuses
  at once: 212 ms for 1,997 posts on a copy of the live database, where 115
  were recruiters'. Checked in a browser on that copy: the filter, the tag,
  the warning on a card and in the window, Apply asking again.
  tests/test_agency.py.

## Changed — 2026-10-23 — Fewer wasted reads of boards with no jobs for you

- **An Oracle board whose countries add up to every job it has is
  trusted.** A board was trusted to say where its jobs are only when its
  location list named three countries or more; Alorica's named one, Egypt,
  for its one job, so a US scan searched it once per title (11 requests)
  and found nothing. Now, when the countries listed account for every job
  on the board (`oracle.covers_every_job`), a board with none in yours is
  skipped after one request: "Alorica lists no jobs in US".
- **A first scan's quick part passes over boards with fewer than 10 jobs**
  (`directory.QUICK_MIN_JOBS`): they are fast but show nothing, and the
  quick part is there to show posts soon. They come after the others in
  their industry, and boards whose count is unknown still come last.
- **Alorica re-verified**: 1 job (was 53, from 2026-10-01). It keeps US as
  its home country, as every re-verified board does.
  `scripts/build_boards.py --reverify --name <board>` now re-verifies only
  the boards named, as `--name` already did for `--add`. The rest of the
  list has not been re-verified; the weekly workflow still needs
  `BOARDS_PR_TOKEN` (Still outstanding).

## Fixed — 2026-10-23 — "returned 0 job posts" only when something is wrong

- **The Last scan card said "Oracle returned 0 job posts"** after a first
  scan's quick part, whose only Oracle board answered every request and
  had nothing matching the titles, while the rest of the scan, still
  running, had found 66 Oracle posts. Any kind of board with 0 posts was a
  warning. A scan now records which kinds had an error (`failed` in the
  run's counts, merged across a first scan's two parts), and a 0 is a
  warning only when that kind failed ("…: it failed. Why is under Warnings
  and errors on the Activity page") or when earlier scans found posts from
  it ("…, where earlier scans found some"). A scan recorded before today
  has no `failed`, and every 0 in it is reported as before.

## Fixed — 2026-10-23 — Keys are checked and tried when saved, and can be replaced

- **A key is tried before it is saved.** Saving an Adzuna or USAJOBS key
  makes one search with it (`api.try_source_keys`, `usajobs.try_key`,
  `adzuna.try_key`); one the source refuses is not saved and the page says
  so: "USAJOBS refused this key and email. Copy the key again from
  USAJOBS's email, and use the email you signed up with". If the source
  cannot be asked (offline, down), the key is saved and the page says it
  was not tried. Removing a key asks nothing. Found when an error message,
  pasted into the key box by mistake, was saved as the USAJOBS key and
  every scan failed with HTTP 401.
- **What cannot be a key is refused before anything is sent**: a space,
  line break or quote anywhere in it ("which a key never has. Copy it
  again"; the message never repeats what was typed), and an email that is
  not an email address. All values are checked before any is kept, so one
  bad box no longer leaves the other half-saved in memory
  (`config.check_source_key`).
- **Show / Hide** beside each key box, so what was pasted can be read
  before saving; the box goes back to hidden after Save.
- **Keys on the Sources page.** The key cards were only in setup, so a key
  that turned out wrong could only be fixed by starting over. Sources now
  has them under the source table, with **Replace** and **Remove** for a
  key the app holds; a key from `.env` or the environment says so, since
  the app does not change those. Setup's Pay step uses the same cards.
- **A refused key is one warning, not one per title.** A scan whose key
  USAJOBS or Adzuna refuses (HTTP 401 or 403) stops that source at the
  first request and logs "USAJOBS refused the API key or email (HTTP 401).
  Check both on the Sources page…" instead of "'devops engineer': HTTP 401;
  'software engineer': HTTP 401; …".
- Checked in a browser on a scratch copy: the cards on Sources, Show
  revealing a pasted sentence, Save refusing it for the space without a
  request, and a well-formed fake key refused by USAJOBS itself and not
  saved; setup's Pay step draws the same cards. `jobdork setup` in the
  terminal tries the key too and prints the outcome.

## Fixed — 2026-10-23 — A real USAJOBS key was refused

- **Saving a USAJOBS key said "USAJOBS_API_KEY has characters a key does
  not"** for the key exactly as USAJOBS sends it. USAJOBS keys are base64,
  which ends in `=` padding, and `=` was on the refused list
  (`config.write_source_keys`, 2026-10-02). It is allowed now: the keys
  file and `.env` are both read by splitting a line at its first `=`, so
  the rest of the line comes back whole. Line breaks and quotes are still
  refused. tests/test_core.py saves a padded key and reads it back after a
  restart.

## Fixed — 2026-10-23 — Start over and the stale-post clean-up failed at their first step

- **Clicking Start over answered "bad request body"**, and so did the
  preview of removing risky and stale posts (both 2026-10-14, never tried
  in a browser until now). The page asks for each preview with an empty
  form, which a browser sends as no body at all, and the server read a
  body before looking at which request it was. The previews now read none;
  the delete itself still needs its fields (the typed words, the count).
  tests/test_serve.py sends the empty form the way a browser does.
- **A "missing or wrong token" line in the browser's network log on every
  page load.** The browser asks for `/favicon.ico` on its own, without the
  token, and was refused. It is now answered with nothing (204), still only
  for a Host the dashboard accepts.

## Added — 2026-10-23 — CI builds the desktop app and attaches it to the release

Third part of the desktop app.

- **`.github/workflows/desktop.yml`** builds the macOS `.dmg` (macos-15,
  Apple Silicon) and the Windows installer (windows-2025, which has Inno
  Setup 6) with `packaging/build.py`, on Python 3.13. It is called from
  docker.yml, so it runs on every push and pull request next to the other
  checks, and can be run by hand for any branch; each run keeps its
  installers as artifacts for a week. It is not one of the checks `main`
  requires.
- **A release waits for both installers.** `publish` now needs `desktop`
  as well as `image`, so a tag whose app does not build is stopped before
  the approval step rather than producing a release page with no downloads.
  After approval, `release-page` attaches the `.dmg`, the setup `.exe` and
  `SHA256SUMS.txt`, and the release notes say which file is for which
  machine and how to get past each system's unsigned warning (macOS:
  Privacy & Security → Open Anyway; Windows: More info → Run anyway).
- **Unsigned, but attested.** On a tag each installer gets a build
  provenance attestation, so `gh attestation verify <file> --repo
  jessn-dev/jobDork` shows it was built by this repository's workflow from
  the tagged commit. SECURITY.md lists the new check and the release step.
- **The built app checks itself.** `jobdork.app/Contents/MacOS/jobdork
  --self-test <report>` (or `jobdork.exe`) imports the window's backend for
  the platform (Cocoa, or WinForms with WebView2), the Claude provider, the
  PDF reader and the server, looks for the data files (dashboard, boards,
  cities, regions, humanizer rules) and the package version, writes what
  is missing to `<report>` (a Windows app has no stdout) and exits 1,
  without opening a window. `build.py` runs it after PyInstaller and stops
  before packaging if it fails: a missing module would otherwise show only
  when a user opened the app. `app.self_test()`, two tests.
- Checked: a local macOS build passes the self-test, and fails it naming
  `cities.csv` when that file is taken out of the built app; the release
  notes rendered with sample values. Not checked: the workflow itself has
  not run yet (it will on the pull request; `actionlint` is not installed
  here), so the first Windows build is still to come.

## Added — 2026-10-21 — Building the macOS app and the Windows installer

Second part of the desktop app. The macOS build is made and tried; the
Windows one is written but has not been built yet (it needs a Windows
machine, which CI will be).

- **`python packaging/build.py`** builds for the machine it runs on, with
  PyInstaller from `packaging/jobdork.spec`, one folder rather than one
  file (a one-file build unpacks itself on every start, which is slow and
  is what antivirus tools flag). macOS: `jobdork.app` in a `.dmg` beside a
  link to Applications, drag to install; 29 MB, ad-hoc signed as Apple
  Silicon requires, not notarised. Windows: an Inno Setup installer
  (`packaging/jobdork.iss`) for the current user, no administrator prompt,
  Start-menu entry, optional desktop icon; uninstalling leaves the user's
  data in `%LOCALAPPDATA%\jobdork`. New `'.[package]'` extra: PyInstaller
  and Pillow. The Claude provider and the PDF reader are always bundled: an
  app user cannot add an extra afterwards.
- **An icon**: `packaging/icon.png`, the dashboard's briefcase on its blue,
  on the macOS icon grid; `icon.svg` is its source.
- **`jobdork app --debug`**: the window's developer tools (right-click,
  Inspect) and debug logging. The installed app takes `--debug` too.
- **Output of an app with no terminal goes to `logs/app.log`** in its
  folder. Found by running the built app: on macOS its stdout is not
  missing, as on Windows, but leads nowhere, so the first check never fired.
- **The token is not written to that log.** In the app the server prints
  its address without the token, which the window already has; the 0.14.0
  rule is that the token is never stored.
- **The user's own tools are found.** An app opened from Finder gets the
  system's bare PATH, so the `claude` CLI that drafts letters would not be
  found; the app adds `~/.local/bin`, `~/.claude/local`, `/opt/homebrew/bin`
  and `/usr/local/bin` where they exist.
- Checked: the `.dmg` mounted read-only shows the app and the Applications
  link; the app opened from it with `open` writes its log, serves setup,
  refuses a request without the token. Not checked: what a downloaded
  (quarantined) copy shows on first open, and anything on Windows.

## Added — 2026-10-21 — `jobdork app`: the dashboard in its own window

First part of the installable desktop app (decision in docs/DECISIONS.md).
Runs from source today; the macOS and Windows builds come next.

- **`jobdork app`** (web/app.py) opens the dashboard in a window (pywebview,
  the new `'.[app]'` extra) instead of a browser tab. The server runs on a
  thread, the window on the main thread as macOS requires; closing the
  window stops the server the way Ctrl-C does, so held API keys are
  forgotten and temporary files emptied as before. `serve()` takes an
  `on_ready(url, stop)` hook for this; `jobdork serve` is unchanged.
- **Its own folder.** Everything else in jobdork is relative to the folder
  it starts in, and an app opened from the Dock starts in none in
  particular, so the app moves into a per-user one first: Application
  Support on macOS, `%LOCALAPPDATA%` on Windows (local, not roaming: a
  roaming profile copying a live SQLite database breaks it),
  `~/.local/share` elsewhere. `--home` or `$JOBDORK_HOME` picks another.
  Without a terminal, output goes to `logs/app.log` there.
- **Links and files go through the app.** The window ignores
  `window.open` on macOS and has no downloads folder of its own, so the page
  now uses `openOut()` and `saveFile()`: in the app, job posts, Apply, the
  feedback issue link and any other web address open in your own browser;
  letters, resumes, PDFs and the feedback file are saved through a save
  dialog; "Open PDF" shows it in the system's viewer from a temporary copy
  deleted when the app closes. In a browser all of these behave as before.
  The bridge (`Bridge`) opens only http(s) addresses, strips folders from a
  file name, and refuses a file over 25 MB or one that arrives damaged.
- tests/test_app.py: the folder per platform, the bridge's checks, and a
  whole run with the window stood in for (setup page served with the token,
  nothing written before setup's first answer, clean stop).

## Changed — 2026-10-21 — Same "stop any time" line in both setups

- The welcome screen of `jobdork setup` (terminal) and of the browser setup
  now say the same thing: "Each answer is saved as you go, so you can stop
  any time and carry on later", then how: run `jobdork setup` again, or
  open the page again.

## Security — 2026-10-21 — certifi 2026.10.19

- `requirements.lock`: certifi 2026.7.22 → 2026.10.19 for advisory
  PYSEC-2026-4320, which failed CI's dependency audit. Hashes from PyPI;
  `pip-audit --strict` passes again.

## Added — 2026-10-21 — Send feedback from the Dashboard

- **Tools is now Feedback.** The unfinished "Email a digest" form is gone
  from the page (`jobdork digest` and `scan --email` are unchanged). In its
  place: a problem, an idea or a question, with a title, details, an
  optional reply address, up to three screenshots (PNG, JPEG, WebP, 2 MB
  each) and two ticks: the last 7 days' warnings and errors, and the app's
  version and system.
- **Preview first.** The page shows the report word for word before
  anything leaves the machine. Keys, tokens, `key=` values, email
  addresses, network addresses and your home folder are taken out of the
  logs and the text (core/feedback.py `scrub`). Never the resume, job posts
  or config. The reply address is kept off the public issue.
- **Send** posts it to a relay (`JOBDORK_FEEDBACK_URL`, or `RELAY_URL` set
  by a packaged build). The app holds no Resend or GitHub key. The relay
  in `relay/feedback/` (a Cloudflare Worker, not deployed yet) opens the
  GitHub issue and emails the maintainers with the screenshots and Reply-To.
  Without a relay, **Open as a GitHub issue** opens a prefilled issue in the
  browser (cut to fit an address), and **Save as a file** downloads it.
- New endpoints `/api/report/preview` and `/api/report`; tests in
  tests/test_feedback.py.

## Fixed — 2026-10-21 — Shorter scan summary; board counts summed

- A scan's summary had one line per employer board, so a full scan's ran
  to hundreds of entries on the Activity page. It now has one line per kind
  of board ("greenhouse: 45 roles from 120 boards, 2 skipped, 1 with
  errors"). Each board's own line still shows in the run's log as it
  finishes.
- The scan history kept only the last board's count for each kind, so
  Greenhouse could show "returned 0 job posts" on the Dashboard while other
  Greenhouse boards had found posts. Counts are now summed.

## Added — 2026-10-15 — Job posts: see what your filters dropped

- **"Dropped by your filters"** in the Job posts menu lists the posts a scan
  left out, each with the rule (title, too old, closed, work arrangement,
  place, pay, dealbreaker) and the reason in words. A menu filters by rule,
  with counts. **Keep anyway** stores one in Job posts, marked interested
  with a note; your filters are not changed.
- Scans now remember dropped posts in a `dropped` table (schema 10): the
  card's fields only, never the advert, kept 14 days and at most 20,000.
  A post a later scan keeps, or one you deleted, is not listed.

## Added — 2026-10-15 — Job posts: place, distance and pay filters

- A second row under the Job posts menus: work arrangement (remote, hybrid,
  on-site, not stated), a place box (matches the post's location), "within
  N mi/km" (remote posts always pass), "pay at least" and "pay stated only".
  Pay in another currency is never converted, so it is not compared. They
  narrow the list on the page, for stored and dropped posts alike; "Clear
  filters" resets them. Nothing about scanning changes.

## Added — 2026-10-15 — How old a job post you still want to see

- New setting `freshness.show_days`. Job posts hides posts older than it
  that you have not acted on, never deletes them, and the count line says
  how many are hidden with a **show them** link. Change it from the menu on
  Job posts. Setup's last step (and `jobdork setup`) asks, suggesting one
  month; an existing config keeps every age (0).

## Changed — 2026-10-15 — "Add a posting" is under Search

- Moved from Tools to the bottom of the Search page. Tools now holds only
  the email digest, which is still under development.

## Fixed — 2026-10-15 — Failed AI calls say why

- The Dashboard counted failed AI calls but nothing said why. Each failure
  is now logged as a warning with the model, what the call was for and the
  reason, so it shows under Activity's warnings and errors (a refused or
  missing key is labelled as a key problem). Calls that failed before this
  change have no reason recorded.

## Added — 2026-10-14 — `./run.sh clean` clears local test data

- **`./run.sh clean`** deletes this folder's local test data: `config.yaml`,
  `config.local.yaml`, `data/` (database, uploaded resume, source keys),
  `out/`, `logs/`, `dork_results.txt` and `job-applications/`. It lists
  what it found and needs `yes` typed; `./run.sh clean --yes` skips the
  question. A dashboard started from this folder is stopped first, since
  it holds the database open. `.env` and anything else is kept, and nothing
  outside the folder is touched. The next `./run.sh` opens onboarding.

## Fixed — 2026-10-14 — AI page: every loaded model is offered

- "Load models" said "46 available" but the list showed one. The model box
  was a text box with a suggestion list, and a browser only suggests what
  matches the text already in it, so once the first model was filled in it
  was the only one offered. Now a loaded list is a real dropdown of every
  model, with "Other: type a model name" for one it does not have. The
  same for the second model.

## Added — 2026-10-14 — Dashboard: Start over (setup again, from nothing)

- **A red "Start over" button on the Dashboard**, with a hover warning like
  the other deletes. Pressed, it lists exactly what goes: the settings, the
  number of job posts (with statuses, notes, AI verdicts and run history),
  the uploaded resume by name, the documents written for job posts, the
  report files, and the job-source and AI keys.
- **Confirmed twice**: type "start over", then press "Delete everything and
  start setup". Cancel leaves everything as it was. Refused while a scan or
  any other job is running.
- **"Keep a backup copy first"**, ticked by default: the settings, the
  database and the resume are copied to `data/backups/start-over-<time>/`.
  Keys are never copied.
- **Only what jobdork wrote is deleted**: a resume the settings point at
  elsewhere, an output folder outside the config's folder, and anything
  else in your folders are left alone. The AI keys in memory are forgotten.
- Then the page reloads into setup at Welcome, and setup writes the new
  settings where the old ones were.
- `POST /api/start-over/preview` and `/api/start-over` (`words`, `backup`).

## Added — 2026-10-14 — AI: a second model checks the first

- **AI page: "Second model, to check the first".** Off unless chosen. Pick
  its provider (Ollama, Claude, Gemini, ChatGPT), hold its key in memory if
  it needs one, and pick its model. Saved as `llm.checker_provider` and
  `llm.checker_model`; the same model as the first is refused. "Save and
  test" asks both to answer.
- **It runs the claim checks** (`ai/guard.py`) on everything the first
  model judges, writes and suggests: verdicts, cover letters, tailored
  resumes, resume reviews and the AI tools (ATS keywords, highlights,
  tailored edits, feedback, revisions). One model marking its own work
  misses what it got wrong the same way twice. Every result says which
  model checked ("checked by …"). A chosen second model that cannot be
  called (no key held) falls back to the first, and the result says why.
- **It scores each judged job post itself.** Its score, verdict and summary
  are shown in the AI badge's tooltip; 20 or more points apart, the badge
  shows "≠ N" and the tooltip "Models disagree". Judging runs and the
  Activity counters count disagreements. The first model's score stands.
- Never blocks or hides anything. Costs about three more calls per output
  on its key; a local Ollama model costs nothing. Setup's title and
  industry suggestions are not checked: they are choices, not claims.

## Changed — 2026-10-14 — Tools: "Email a digest" off, under development

- **Every control is disabled**: the address, both boxes and Send. The
  heading says "(under development)", and hovering the block, or reaching
  it with Tab, shows a tooltip: not ready yet, turned off for now, your
  job posts are under Job posts. Send is no longer re-enabled when a job
  finishes. The Tools menu's description says so too.
- `jobdork digest` in the terminal and `/api/digest` are unchanged.

## Added — 2026-10-14 — Activity: warnings and errors from the app and every scan

- **Warnings and errors reach the dashboard.** What jobdork logged as a
  warning or error (a host blocked for rate limiting, a source that raised,
  a resume it could not read, a prompt too long for the model) went to the
  terminal only. Now each one lands in the running job's log, marked, or,
  outside a job, in a new `app_events` table (schema 9): the server, setup,
  a config that stopped loading, and the config's own warnings at start.
  Scans run from the terminal are included.
- **A failed or stopped job says so in its log**, as an error or a
  warning line, not only in its summary. A source that returned errors is
  logged as a warning with the first three.
- **Activity page: "Warnings and errors".** The last 7 days, newest first,
  each tagged ERROR or WARN and with its job (or "app"); pick a job's line
  to show that run. The job log colours warnings amber and errors red.
- **A missing or refused key is a warning that says so.** "Missing or
  refused key (job source): adzuna: skipped (no key …). You see this
  because the job source key is not set or was not accepted; see
  docs/CONFIG.md, sections "sources" and "Environment"." The AI's points at
  the "llm" section or the AI page. A keyed source chosen without its key
  is now logged each scan; skips by design (a country a source does not
  serve) are not.

## Added — 2026-10-14 — Remove risky and stale job posts, on your say-so

- **After a scan, and in Job posts, jobdork offers to remove them.** When
  any job post you have not acted on (status new or viewed) is risky
  (posted 8 to 21 days ago), stale (over 21 days) or a ghost listing (over
  90, already hidden), a box says how many of each, with "Remove N job
  posts" and "Not now". Remove shows examples and asks once more; the
  delete carries the previewed count and is refused if it moved, as Clean
  up is. The database is backed up to `data/backups/` first, and removed
  posts stay removed: later scans leave them out.
- **Counted per job, copies included.** The number is the posts you see in
  Job posts; each one's grouped copies go with it, or the next copy would
  take its place in the list.
- **Never touched:** posts marked interested, applied, submitted,
  interviewing or offer. Nothing is removed without the button: screening
  still keeps old posts, marked and ranked lower.
- "Not now" holds until the number changes. The day limits are the
  `freshness` settings (`week_days`, `older_days`, `ghost_days`).
- `POST /api/cleanup/aged/preview` and `/api/cleanup/aged` (`expect`). A
  job's "done" event now names the job, so the page knows a scan finished.

## Changed — 2026-10-14 — Job posts: the count says how many copies were found

- **The list's count matches the scan's "kept".** A scan counts every copy
  it stores; the list shows one post per job. "19 of 19 · 19 duplicates
  grouped" read as if 19 had been lost against a scan that kept 38. It now
  says "19 of 19 · 38 copies found, 19 grouped".

## Changed — 2026-10-06 — Setup: a designed welcome screen

- **The welcome screen says what jobdork does and what setup asks.** It used
  to be a heading, one paragraph, a bare list of step names and a small
  Start button. Now: the logo and "Find the job posts worth your time";
  three cards (reads the boards for you, checks every job post, stays on
  your computer — only the AI you choose reads it); each of the six steps
  numbered with one line on what it asks and a Required or Optional tag;
  "Have your resume ready" above a large "Get started" button, which has
  focus, and "Each answer is saved as you go" below it.
- Wider than the other steps (46rem), one card per row on a phone, works in
  light and dark, a short fade-in that is off when the system asks for
  reduced motion. The button's blue (#2563eb) keeps white text readable
  (5.2:1). A step added to `core/setup.py` later still shows, by its title.

## Changed — 2026-10-03 — Setup: pay and job sources in one step; your credentials

- **Six steps after Welcome, not seven.** Pay and "What will be searched"
  are one step, "Pay and job sources": the salary floor, then what every
  scan reads. A config saved at the old `sources` step resumes at this one.
- **The keyed sources are a question, and only where they can work.**
  "Use Adzuna? It searches many job boards at once, in 20 countries." with
  "Yes, add a free key" opening its boxes; with the US among your countries
  also "Use USAJOBS? It lists US federal government jobs."; outside the US
  only Adzuna, and neither where Adzuna covers none of your countries (the
  Philippines alone). The sentence on where a pasted key is kept is gone.
  The terminal asks the same.
- **Your certifications and licenses.** Step 3 asks for them, with the ones
  your resume names already ticked (BLS, ACLS on a nurse's), and the Search
  page has the list to edit (`credentials:` in the config). An opened job
  post checks its advert against them as well as the resume, and one of
  yours that the built-in list does not know still counts when the advert
  names it ("IAT I"). The terminal's step 3 asks too, keeping capitals.
- **Tests no longer reach the repository's database.** The dashboard tests'
  config had no `db:`, so a test that saved settings left the server
  pointing at `data/jobdork.db` in the repository, the live one while you
  test (they only read from it). Their config now names its own.
- Three new tests.

---

## Added — 2026-10-03 — Certifications and licenses an advert asks for

- An opened job post shows, above the advert, the certifications and
  licenses it asks for, each marked Required or Preferred and with the
  credentials it names as chips, green with a check when your resume has
  them; the same lines are highlighted in the advert.
- Read from the advert's lines (`search/credentials.py`): a line that talks
  about one ("certification", "licensed", "board certified"), or names one
  of about 80 across healthcare, finance, technology, trades, law and
  teaching (RN, BLS, ACLS, CPA, PMP, CISSP, CDL, Series 7…) and says it is
  required or preferred or sits under a requirements heading, since "RN"
  alone is in every line of a nurse's advert. Every line under a
  "Certifications" heading counts, named or not ("IAT I"). Left out: a line
  saying none is needed, the employer's own ("a certified B-Corp", ISO
  27001), and long boilerplate. Short names match case and whole words, so
  "RN" is not found in "learn".
- On a test database it found credentials in 361 of 1,346 adverts long
  enough to read (CISSP 54, Security+ 28, AWS Certified 22 in a tech-heavy
  search). Display only: screening and the AI read the advert as stored.
- Six new tests.

---

## Changed — 2026-10-03 — Setup turns on AI judging after each scan

- When the AI test passes in setup, Continue also turns on "After each scan,
  judge the top 15 job posts not yet judged" (`llm.judge_on_scan`,
  `llm.judge_top: 15`), so the AI reads the best new posts against your
  resume from the first scan on; the screen says so, and it can be changed
  on the AI page. Skip for now leaves it off. `jobdork setup` in a terminal
  does the same after its test.

---

## Changed — 2026-10-03 — The first scan is watched on the Dashboard

- Setup's last step no longer keeps you on its screen while the quick part
  runs. "Start the first scan" ends setup and starts the scan in one go, and
  the Dashboard opens at once, where the scan is shown as any other: a
  notice says the first scan is running and job posts appear within a few
  minutes, then that the rest of the employer boards are being read.
  The setup screen's own log and source counter are gone. `jobdork setup`
  in a terminal still runs the quick part in front of you.

---

## Changed — 2026-10-03 — Every lambda says why it is a lambda

- Each of the 33 lambdas in `jobdork/` and `scripts/` has a comment above it
  starting `# lambda:` that says why: a sort or max key, a `default_factory`
  that must make a fresh list per instance, a call deferred until later (a
  timer, a writer run only for its format), a path read at each use so a
  config change is followed, or an adapter between two call shapes. New
  code follows the same rule.

---

## Changed — 2026-10-03 — Setup step 3 shows a real progress bar

- "Reading your resume…" was a line of text for as long as the model took.
  It is now a bar that moves with the model's answer: a local model's reply
  is streamed (`llm.complete_json(on_text=…)`, Ollama only), and since the
  schema fixes the order of the answer's keys, reaching each one is real
  progress: reading your resume, choosing job titles (moving with each
  title written), titles to keep out, industries, dealbreakers, done
  (`suggest.stage`). The page polls `/api/setup/suggest/progress`; when the
  answer arrives the bar gives way to "Suggested from your resume. Untick
  what does not fit." The terminal prints each stage as it is reached.
  Hosted models answer in one piece and in seconds, so their bar shows the
  reading stage until then.
- Removed from the Welcome screen: "Each answer is saved as you go…".
- One new test (stages never go backwards; a streamed answer is read and
  cleaned as before).

---

## Changed — 2026-10-03 — An opened job post, reorganised and readable

- **Opening a job post no longer opens Match's explanation.** The dialog
  put focus on the first thing it could, the Match badge, whose tip a focus
  shows; the dialog now takes the focus itself.
- **The header holds still.** Badges and the title on the left, wrapping as
  far as a long title needs; Open posting (now a button) and Close at the
  top right, where a 130-character title used to push them down a line.
- **No job post ids** in the list or the dialog (`4aadaa36db52`). `jobdork
  list` still prints them for the terminal.
- **The advert tab is the advert.** Drafting and the AI buttons (Ask AI,
  write a cover letter or tailored resume, review the resume) moved to the
  AI tools tab; the advert keeps Check if still open and a Replace the
  advert button, which opens the paste box (Paste the full advert, and a
  note, for one too short to screen).
- **The advert is formatted for reading:** short lines without a full stop
  become headings ("Key Responsibilities", "Required:"), runs of short lines
  under a heading become a list (the boards' text loses its bullets),
  bullets and numbered lines become list items, and stray spaces and blank
  lines go. Display only: screening and the AI read the text as stored.

---

## Added — 2026-10-03 — Job posts sort by match or fit, or show the unscored

- A menu beside the Job posts filters: Match high to low (the order they
  came in) or low to high, Fit high to low or low to high, and Unscored
  only, the posts with no match or no fit score (on a test database, 9 of
  1,810, all with no fit). A post with no score goes last whichever way
  round, and equal ones keep their order (best match, then newest). It
  works with search, status and "posted within" together.

---

## Fixed — 2026-10-03 — AI calls made outside a job are counted

- Setup's "Save and test" and its suggestions from the resume called the
  model (Gemma on Ollama), yet the Dashboard's AI calls and P50 latency
  tiles said 0: a model call was recorded only inside a job (a scan, a
  judging run, a letter), and these run in no job. Such a call is now
  written to `llm_calls` with no job, wherever `jobdork serve` or
  `jobdork setup` runs (`telemetry.record_calls_to`), so the tiles count
  it; a failed write is ignored rather than breaking the call. The scan's
  own "No AI calls in this job" was right: a scan judges with AI only when
  "After each scan, judge the top…" is on, which it is not by default.
- **The path is made absolute when it is set.** Tests that ran `jobdork
  setup` set a relative `data/jobdork.db`, and the tests after them, run
  from the repository, wrote their fake calls into the real database there
  (16 rows of "test, 1.0 s" and "model m"). The tests now also clear the
  setting after each such test; a full run adds nothing to it.
- One new test.

---

## Changed — 2026-10-03 — Network, by host: five a page, sortable

- The Dashboard's per-host table listed every host a run touched: 140 after
  a first scan with the built-in boards. It now shows five, with Previous
  and Next ("6 to 10 of 140"), the same pager as the Search page's lists
  (now one `paged()` helper for both). Showing another run starts again at
  page one.
- Every column sorts by a click on its heading: Requests (the default,
  busiest first), 2xx/3xx, 4xx, 429, Failed, Avg, Slowest and Host. A new
  column starts biggest first (A to Z for hosts); the same heading again
  turns it round, with ▼ or ▲ beside it.

---

## Added — 2026-10-02 — Setup step 7: the first scan, quick then in the background

- **Quick first, then the rest.** "Start the first scan" reads the keyword
  sources, your own boards and 8 of the built-in boards, the smallest in
  each of your industries first (`directory.quick`), then marks setup done
  and opens the Dashboard. The rest of the built-in boards are read straight
  after as a scan of their own, "full scan", while a notice on the Dashboard
  says so. No board is read twice (`scan.run(part="quick" | "rest")`).
  Measured on a US healthcare search: 52 s and 110 job posts before the
  Dashboard opened. Taking the first 20 boards instead took 3.5 min, because
  one 2,000-job Workday board alone needed 180 paced requests.
- **The runner chains jobs** (`Runner.start(..., then=[...])`): each is its
  own job in the event stream and on the Activity page, the runner stays busy
  between them so nothing else starts, and a failed part stops the rest.
- **The setup screen** streams each source as it is read and counts
  "6 of 13 sources read"; a failure offers "Try again", and coming back to
  the page mid-scan does not offer a second start.
- **Opening the Dashboard after setup kept the token.** The page reloaded to
  a bare address and got "missing or wrong token", since the token lives
  only in the page; it now passes it for that one load.
- **Terminal:** `jobdork setup` runs the quick part with its progress, says
  setup is done, and offers the rest now or later with `jobdork scan`.
- **Fixed on the Dashboard's Last scan card** (seen during this): a scan
  still running was reported as "never finished", and a source skipped for
  want of a key or outside your countries as "returned 0 job posts". A run
  now records which sources were skipped, and a scan with a live heartbeat
  is "still running". The skip messages for Adzuna and USAJOBS say the key
  can be pasted in setup, not only put in `.env`.
- **The card reads a first scan's two parts as one scan.** Read alone, the
  background part (employer boards only, by design) made the card say
  Adzuna, USAJOBS, Himalayas and Workable "did not run", though the quick
  part had read 1,700 posts from them. A run now records its part, and a
  rest run is added to the quick run before it. A source also counts as
  skipped only when every board of it skipped: one Workday board skipping
  had marked all of Workday skipped, which would have hidden a real
  "returned 0".
- **README Install** now starts with `jobdork serve` and the setup it opens;
  copying `config.example.yaml` is the alternative.
- Six new tests (the sample and the split, smallest first, the chain, the
  route, the terminal step, the Last scan card).

---

## Added — 2026-10-02 — Setup step 6: what will be searched

- **A plain summary** of what every scan reads: Workable's search,
  Himalayas' remote jobs, Kalibrr where the Philippines or Indonesia is in
  your countries, and the built-in employer boards with their count for
  your industries and countries (38 for healthcare in the US), above the
  titles they are searched for.
- **Adzuna and USAJOBS keys can be pasted in the app**, as decided on
  2026-09-30 ("users paste their own in the app, stored in data/"). They go
  to `data/source-keys.env`, beside the database (the kept volume in
  Docker), created readable by its owner alone, never into `config.yaml`,
  and are never sent back to the page: it says "Ready", where the key came
  from, and offers Remove for one saved in the app. `.env` and the
  environment still win. Only the four job-source names are accepted, and
  half a pair is refused. A source that cannot apply says why (USAJOBS
  without the US in your countries, Adzuna outside its countries).
- **Terminal:** the same summary; for each keyed source that applies,
  "Add a key now? [y/N]", with the key typed hidden.
- `_yes()` in the CLI takes a default, so an optional question defaults
  to no. One new test (saved, file mode 0600, read back after a restart,
  never in the report or the config, removed, foreign names refused); the
  terminal flows now run through this step to the first scan.

---

## Added — 2026-10-02 — Setup step 5: pay (optional)

- **Dashboard:** the same form as Where, showing only the salary floor and
  its currency, which the Where step already set from the country (pesos
  for the Philippines). The screen says it is optional, that a post with no
  salary is always kept, and that the floor is yearly: hourly and daily
  rates are annualised before comparing, and an hourly rate times 2,080 is
  the figure to type. Empty hides nothing for pay.
- **Terminal:** the yearly floor (commas allowed, a non-number asked
  again), then the currency, defaulting to the country's; blank is no
  floor. The terminal Where step now sets that currency too, as the page
  does.
- One new test; the Where test now runs on through Pay with no answer.

---

## Added — 2026-10-02 — Setup step 4: where

- **Dashboard:** the Search page's own place picker, radius, work
  arrangements and countries list, shown inside setup (the salary floor
  waits for the Pay step). Nothing is filled in: a new user chooses a
  country and city, rather than starting from the Naperville the picker
  offers a config without a place. Continue saves through the same code as
  the Search page's Save, which also lists the chosen country under
  countries to keep when none are listed; with no city it says so.
- **New configs start with no place and every country.** Before, a config
  without `locations` was measured from Naperville, IL and limited to the
  United States. A place is required to finish the step.
- **Units follow the country** chosen in the picker, here and on the Search
  page: kilometres for the Philippines, miles for the United States, as
  the currency already did.
- **Terminal:** a country by name, code or the start of its name; a region
  the same way, or any; the city from the place list (a short numbered list
  when several match); radius, arrangements, and other countries by code.
- One new test (Baguio, Cordillera, Philippines; remote; PH and US); the
  setup test also checks the new config's empty place and the refusal.

---

## Added — 2026-10-02 — Setup step 3: what you are looking for

- **With AI set up**, the model reads the resume and fills in four lists:
  job titles as employers write them, titles to keep out (similar words, a
  different job), the industries whose built-in employer boards to read, and
  dealbreakers the resume gives a reason for. Titles, excludes and industries
  come ticked; a suggested dealbreaker is only marked, since it is a
  preference the resume cannot settle. Industries and dealbreakers are
  chosen from jobdork's own lists, and anything else the model says there is
  dropped (`ai/suggest.py`). On a nurse's sample resume a local 26B model
  answered in 4 s with "registered nurse", "icu nurse", "critical care
  nurse"… and kept out "nurse practitioner"; a 3B model was weaker.
- **Without AI**, or when the model fails, the same screen asks for the
  titles to be typed.
- Each list takes additions; nothing is saved until Continue, and at least
  one job title is required to go on. Industries are saved to
  `sources.directory.industries` (none ticked reads every industry).
  Coming back shows what was saved instead of asking the model again.
- **Terminal:** the same lists, numbered: Enter keeps them, numbers drop
  entries, and more can be typed; dealbreakers are turned on by number.
- Four new tests.

---

## Added — 2026-10-02 — Setup step 2: AI (skippable)

- **Dashboard:** the AI page itself, inside setup: Off, Ollama, Claude,
  Gemini or ChatGPT; the Ollama address or a key held in memory; a model,
  filled in with the first one offered so nobody stalls on an empty box; and
  Save and test. Continue appears once the model has answered; "Skip for
  now" is always there, because scanning works without AI. The screen says
  a typed key is forgotten when jobdork stops and to keep one in `.env` (or
  the container's environment), and in Docker gives the address Ollama on
  the same computer is reached at. The when-to-use options keep their
  defaults; they stay on the AI page.
- **Terminal:** `jobdork setup` lists the four, asks for the Ollama address
  or reads the key from `.env` or the environment (a terminal run has no
  memory to hold one in, so it says where to put it), lists models to pick
  from, saves, and asks the model to answer; blank skips.
- One new test (no key, then Ollama, a model, a passing test, moved on).

---

## Fixed — 2026-10-02 — A new database no longer fails the first page load

- The dashboard's first load opens the database from several requests at
  once. When the file did not exist yet, two of them creating it together
  could fail with "database is locked", so a new user's first screen came up
  with errors. Opening a database is now one at a time within a process
  (`db/store.py`). One new test; it failed 6 runs in 30 before the fix.

---

## Added — 2026-10-02 — Setup step 1: your resume (required)

- **Dashboard:** choose a PDF, Word, Markdown or text file. It is read at
  once and the screen shows what was read: characters, years of experience
  claimed, skills recognised, and the full text, so a resume that lost half
  of itself on the way in is seen before anything is scored against it.
  Under 800 characters it says so and suggests another export. Choosing
  another file replaces it; Continue moves on to AI. Coming back shows the
  resume already uploaded.
- **Terminal:** `jobdork setup` asks for the file path (a dragged-in, quoted
  path works), prints the same summary and the start of the text, and asks
  "Use this resume?"; blank stops, and the next run carries on there.
- **Required:** no step after it can be saved without a resume file, from
  the page, the terminal or a hand-edited request (`core/setup.py`).
- Two new tests (the step cannot be skipped; the terminal flow, stopped and
  resumed).

---

## Changed — 2026-10-02 — A first run opens setup, the same in Docker and on your machine

- **`jobdork serve` starts with no config** and the dashboard opens on a
  setup screen (no menu) instead of exiting with "No config found". The
  welcome step lists the questions to come and saves as you go; closing the
  page and coming back resumes at the same step. The other steps are still to
  build, one per screen.
- **`jobdork setup`**, the command the old error message already named, now
  exists: the same steps in the terminal, resuming from the same place as the
  browser.
- **Docker no longer copies the example config** into `data/config.yaml`. A
  new user there was searching for software engineer jobs nobody asked for,
  and the container behaved differently from a local install. Now both wait
  for setup; the config is written on the first answer (`data/config.yaml` in
  a container, `config.yaml` otherwise, `$JOBDORK_CONFIG` if set). A config
  already in `data/` is read as before.
- Progress is kept in the config as `setup: {step: …}`, removed when setup
  ends; configs without it count as set up. Until then other commands refuse
  with "Setup is not finished", and the dashboard refuses a scan with no job
  titles.
- The code that writes the config moved from `web/serve.py` to
  `core/setup.py`, shared by the dashboard and the terminal. Three tests
  replace the seeding ones, plus one for the dashboard's first run.

---

## Added — 2026-10-02 — How jobdork got here, and how it differs from a job board

- **docs/HISTORY.md**: from a 900-line Google search builder in March to
  today, era by era, with the decisions that turned around and why (no
  bundled list → 368 built-in boards; AI optional → required → not blocking
  a scan; Docker's temporary resume → kept; regex dealbreakers → plain
  words).
- **README: "How is this different from a job board, or an AI job app?"**,
  a table on where the jobs come from, what decides what you see, copies and
  ghost jobs, what the AI writes, where your resume lives and what it costs,
  and what jobdork is not good at.

---

## Changed — 2026-10-02 — Documentation checked against the code

Every document was read for claims the last three days made untrue, and
fixed:

- **README:** sources now name Kalibrr, Himalayas, the nine employer-board
  platforms and the 368 built-in boards (it said five platforms, "exactly
  the companies you name"); what it cannot do no longer says retail floor
  and care work never reach a hiring system (Dollar Tree, Lowe's, Starbucks
  and the hospital systems do), and names the systems without a reader; the
  AI is described as needed for judging and writing, not as "optional"; the
  docs table and project structure list REGIONS, DEPLOY, DECISIONS,
  SECURITY, `compose.yaml`, `scripts/` and the workflows.
- **docs/ARCHITECTURE.md:** the module table (storage, robots, dealbreakers,
  directory, freshness; line counts), `boards.csv` in the pipeline and in
  `data/`, pacing by domain and `Fetcher.pace`.
- **docs/SOURCES.md:** tokens for Workday, Oracle, Eightfold, Taleo and
  employer sites; Discover reading a given address as a board and falling
  back to the site itself; Oracle and Taleo no longer listed as having no
  adapter; the gazetteer's real size (70,026 places, 2.6 MB); what an
  employer-board reader needs to be added.
- **docs/PLATFORMS.md:** Kalibrr is asked for a country by name (it said
  results mix both countries); employer systems with no reader listed.
- **docs/CONFIG.md:** `JOBDORK_ALLOW_HOSTS`, `JOBDORK_DOCS_DIR` and
  `JOBDORK_TEMP_DOCS`.
- **docs/DEPLOY.md:** what "No config found" restarts and the red data
  notice mean.
- **SECURITY.md:** the weekly boards workflow and its write token; the
  Docker Hub token and username ticked as set (confirmed by the owner), the
  username described as a `release` environment variable, where it is.
- **docs/DECISIONS.md:** the keys decision's list of shipped sources brought
  up to date, marked as such.
- **config.example.yaml:** the AI comment and the built-in boards' reach.
- This changelog: a note that work was uncommitted since `b3f5f87`, long
  untrue, removed.

---

## Added — 2026-10-02 — docs/REGIONS.md: coverage by region, and the plan for the rest

What reaches a user outside the US was spread over the README, SOURCES and
this changelog, and the README still said a Philippine user had Workable and
little else. `docs/REGIONS.md` puts it in one place: what reaches each
region today (the US, Canada, Mexico, Asia, Europe, the Middle East,
Australia and Oceania), what has been measured, and the plan for **Europe,
the Middle East, and Australia and Oceania, which are planned and not
built**: measure first with the coverage test, add each region's large
employers, add its job sites where their terms allow, measure again. The
README links to it in place of the old line.

---

## Added — 2026-10-02 — compose.yaml for a NAS, and where each setting goes on each one

docs/DEPLOY.md named the image `<dockerhub-user>/jobdork` (it is
`jessengolab/jobdork`), gave click-by-click steps for UGREEN only, and had no
compose file, though Synology, QNAP, UGREEN, TrueNAS and Portainer all take
one pasted in, which fills every setting at once.

- **`compose.yaml`** at the top of the repository: the image with a version
  tag, the port, `JOBDORK_ALLOW_HOSTS`, `./data` mounted at `/app/data`,
  automatic restart, 1 GB of memory, and the opt-in temporary folder and
  `.env` commented out. Checked with `docker compose up` on an image built
  from this branch: it starts, writes `data/config.yaml` into the folder
  beside it, and the dashboard answers through an allowed address.
- **docs/DEPLOY.md** says where a compose file goes on Synology, QNAP,
  UGREEN, TrueNAS SCALE and Portainer, and where each setting goes on Unraid,
  which takes them one by one.
- The real image name in README, DEPLOY and SECURITY.

**The published 0.14.3 does not work this way.** It was built before the
container learnt to create its own `data/config.yaml`, and with no config
mapped in it restarts over and over ("No config found"). The compose file
and the docs name 0.14.4, which has to be released before they are true.

---

## Fixed — 2026-10-02 — Kalibrr found almost nothing in Indonesia

Kalibrr's search answers with Philippine jobs unless it is asked for a
country by name, and jobdork never asked, so an Indonesian search filtered
three pages of Philippine jobs down to nothing: 2 jobs for three titles.
Each country you want is now asked for (`country=Indonesia`): 380 jobs for
the same titles. On the coverage test, Jakarta's Kalibrr results went from 0
kept to 10. One new test.

---

## Added — 2026-10-02 — 26 Asian, 19 Canadian and 1 Mexican employer board in the built-in list

The built-in list was US first and reached Asia, Canada and Mexico only
through multinationals hiring there: one board was Canadian, none Mexican,
and the Asian ones could be counted on one hand.

- **`scripts/candidates.csv` gains 232 employers** (877 in all): 154 across
  11 Asian markets (banks, telecoms, airlines, conglomerates, hospitals, IT
  services), 48 Canadian and 30 Mexican.
- **46 boards came of it** (368 in all, was 322): DBS, UOB, AIA, Prudential, MUFG,
  Samsung, TSMC, Coupang, Agoda, AirAsia, AIS, Maxis, Razer, Takeda and
  Dr. Reddy's in Asia; RBC, BMO, CIBC, Desjardins, Loblaw, Canadian Tire, Air
  Canada, Bell, Enbridge, Canadian Natural Resources and McGill in Canada;
  Mercado Libre for Mexico. Six held back for a name the check could not
  match were accepted in `scripts/boards_review.csv`, with reasons.
- **Fixed on the way:** Discover read boards only off pages, never off the
  address it was given (Razer's own Workday address became a "site" board);
  a Workday site named "Careers" was refused as if it were a path word; a
  SmartRecruiters link through `my-applications/` gave that word as the
  token (Dr. Reddy's). SuccessFactors addresses on `sapsf.com` and
  `career…successfactors.com`, and TurboHire, Darwinbox and PeopleStrong,
  are now named rather than reported as nothing.
- **`build_boards.py` says why each employer found nothing**: a system with
  no reader, blocked, or nothing named. Of the misses: Asia 93 named nothing
  (after 37 careers addresses guessed wrong were replaced by the employers'
  home pages), CA/MX 35; blocked 14 and 13; SuccessFactors 13 in all. Most
  big Asian employers run careers sites of their own that link no board.

**Asia coverage test, jobs kept (local, not remote), before → after,
with the Kalibrr fix:** Manila 316 → 386 (168 → 238), Bengaluru 354 → 405
(281 → 333), Taipei 47 → 79 (26 → 57), Jakarta 37 → 48 (16 → 27), Singapore
129 → 137, Kuala Lumpur 78 → 85, Bangkok 43 → 51, Ho Chi Minh City 45 → 49,
Hong Kong 32 → 35, Tokyo 40 → 42, Seoul 26 → 28. Tokyo, Seoul and Hong Kong
stay under 20 local jobs: regional job sites, not more employers, are what
is left there.

---

## Added — 2026-10-02 — A warning when Docker is keeping your data inside the container

Started without `-v <folder>:/app/data`, the container keeps job posts,
settings, the resume and letters in its own layer, and `docker rm` (or
`--rm` on stop) deletes them with it. Nothing said so; the documented
commands mount a folder, but a quick `docker run jobdork` does not.

- **At startup**, when `/app/data` (the folder holding the database, or one
  above it) is not a mount point in the kernel's mount table, the log says
  so and gives the `-v` to add.
- **On the Dashboard**, a red notice says the same, until the container is
  started with a mounted folder.
- Outside a container nothing is checked.

Checked with the image built locally: without `-v` the log warns and
`/api/state` reports `/app/data`; with `-v` there is no warning and the
seeded config lands in the mounted folder. One new test.

---

## Changed — 2026-10-02 — Docker keeps your resume and letters across restarts

In the container the uploaded resume and every document written from it
went to a temporary folder, emptied whenever the dashboard started and
stopped. Every restart meant uploading the resume again, and a cover letter
not downloaded was gone. For a tool whose next step is a resume-first
onboarding, that is a step to redo after every update.

- **The image now keeps them in `data/documents`**, inside the volume that
  already keeps scan results and settings (`JOBDORK_DOCS_DIR`, set to
  `/app/data/documents`).
- **Temporary stays available, by choice:** `-e JOBDORK_TEMP_DOCS=/tmp/jobdork`
  restores the old behaviour for a shared machine where nothing personal
  should outlive a run, and wins when both are set.
- On your own machine nothing changes: `data/` and
  `~/Documents/job-applications`.

README and docs/DEPLOY.md say so. One new test.

---

## Added — 2026-10-02 — Remove all, for job titles, titles never shown, and dealbreakers

Starting a search over (a nurse's titles instead of an engineer's) meant
removing every row by hand, two clicks each.

- **Remove all N**, under Job titles, Never show these titles and
  Dealbreakers on the Search page, opens a red confirm like Delete all
  scanned posts, with a Cancel; it is hidden when the list is empty.
- **Job titles are replaced, not emptied.** A scan needs at least one title
  and the config refuses an empty list, so the confirm asks for the new
  titles (separated by commas) and saves them in place of the old in one
  go.

Checked in the browser on a copy: 14 job titles replaced by two, and three
never-shown titles removed.

---

## Changed — 2026-10-02 — Remove asks with a check and an x

On the Search page's lists (titles, countries, dealbreakers) the first
click on Remove turned the button into "Remove?" for three seconds, and a
second click on the same spot removed the row. Now the first click puts a
check (remove) and an x (keep) in its place; the check has the focus, the x
puts the Remove button back, and with neither clicked it comes back by
itself after four seconds. Checked in the browser on a copy.

---

## Added — 2026-10-02 — Delete all scanned job posts, without scanning again

The only way to empty the list was Run fresh scan, which deletes every
scanned job post and starts a scan straight away. Starting over with other
settings, or just clearing the list, meant a scan you did not want yet.

- **Delete all scanned posts**, on the Dashboard next to Run fresh scan:
  the same preview ("This deletes all 662 scanned job posts…", with how
  many you are pursuing), the same red button carrying the count, the same
  backup to `data/backups` first, and no scan after. Posts added by hand are
  kept; posts you deleted before stay deleted.
- It runs as a job (`POST /api/scan/delete`), so it shows in the run log and
  is refused while a scan is running; a count that moved since the preview
  deletes nothing.

Checked in the browser on a copy: 662 deleted, backup written, run logged.
Two new tests.

---

## Added — 2026-10-02 — A coverage test for users in Asia

How much a fresh install finds outside the US had never been measured.
`scripts/coverage_benchmark.py` runs a real default scan, no keys, the
built-in boards, 50 km, for a test user in each of 11 Asian cities and four
titles across industries (software engineer, accountant, nurse, customer
service), and counts what each source keeps.

**First result (jobs kept, of them not remote):** Bengaluru 354 / 281,
Manila 316 / 168, Singapore 129 / 104, Kuala Lumpur 78 / 75, Taipei 47 / 26,
Ho Chi Minh City 45 / 25, Bangkok 43 / 25, Tokyo 40 / 15, Jakarta 37 / 16,
Hong Kong 32 / 13, Seoul 26 / 5. Outside Manila, Bengaluru and Singapore
most of what is found is remote work from Himalayas; the local jobs come
from multinationals' boards in the built-in list. Kalibrr found nothing for
Jakarta, though it covers Indonesia.

---

## Added — 2026-10-01 — Taleo Business Edition boards

Costco hires through Taleo Business Edition, and Discover reported it as
"taleo, no adapter" (and named the host only, `tbe.taleo.net`, which is
everybody's). Taleo Business Edition has no JSON at all; its pages are the
interface.

- **`fetch/taleo.py`**, source `taleo`, token `host/path/org/cws`
  (`phf.tbe.taleo.net/phf02/COSTCO/41`). The search results page lists ten
  jobs at a time, paged by `rowFrom` with no session; only titles your title
  rules keep are opened, and each job's page carries a schema.org
  `JobPosting`, read as an employer site's is. Measured: Costco, "engineer"
  and "analyst", US: 11 jobs with full adverts, 13 requests, 13 seconds.
- **Discover reads the token** with `org` and `cws` in either order; Costco's
  sit in a script, cws first, joined by `\u0026`, and a `\b` before them
  found nothing because `\u0026cws` has no word edge. The board is counted
  by paging its results, and is no longer also reported as "no adapter".
- **Still open:** a removed job answers 200 with "This job has moved or is no
  longer available", now read as closed; the page check alone said
  "unknown".
- **Dates in Java's form** ("Thu Jul 02 00:00:00 GMT 2026", from Costco's
  pages) are read as 2026-07-02 for every employer site; they were stored
  as "Thu Jul 02".
- The check that holds a board back for a person compares Taleo's `org`
  with the employer, not the host's first label (`phf`).
- Paced at one page a second for every `*.taleo.net` host. Taleo Enterprise
  (`careersection`) is a different product with no reader; Kaiser
  Permanente and UnitedHealth Group, which use it, are read through their
  own sites.

**Test list: 30 of 46 (was 29), US 26 of 37 (was 25).** New: Costco.

**Built-in boards: 322 (was 319), 308 of them US.** Costco is the only
Taleo Business Edition employer among the 645 candidates; BNSF Railway and
Trinity Health came in on the same build through their own sites, which
answered this time.

`taleo` was added to the local config's sources; the example lists it.
Six new tests in `tests/test_taleo.py`.

---

## Changed — 2026-10-01 — Dealbreakers in plain words; regular expressions under Advanced

A dealbreaker was a regular expression. To rule out jobs that need a
clearance, you wrote `security clearance|TS/SCI|top secret|polygraph`, and
the dashboard explained `\b`, `(?:a|b)` and `\d{2}` to get you there. Most
people looking for work should not have to learn that to say "no security
clearance".

- **Type the words**: `security clearance`, `us citizen`, `client-site
  travel`. Capitals, hyphens, dots and plurals do not matter ("us citizen"
  finds "U.S. citizenship", "client-site travel" finds "client site"), and
  only whole words match ("us" never matches inside "focus").
- **Common dealbreakers include their other wordings.** 17 of them, US
  first and across industries: "security clearance" also finds TS/SCI, top
  secret and polygraph; "no visa sponsorship" finds "unable to sponsor"; "heavy
  travel" finds "travel up to 75%" and not "up to 10%"; "heavy lifting" finds
  "lift up to 50 lbs". On the dashboard they are one-click buttons.
- **A negation is not a match.** "No security clearance is required" and "you
  do not need to be a US citizen" said the opposite and, as patterns, matched
  anyway. A no, not, without or never in the few words before a match, in the
  same sentence, now skips it. A dealbreaker that is itself a negation ("no
  visa sponsorship") counts its matches as they are, and so does a pattern.
- **Try it asks the server**, so a pasted sentence is tested by the same
  Python a scan uses (`POST /api/dealbreakers/try`), not by the browser's
  regex engine.
- **Regular expressions stay**, under Advanced on the dashboard and as
  `pattern:` in config.yaml; every existing dealbreaker works as before.
- In config.yaml a dealbreaker can be a bare phrase (`- security
  clearance`), named and weighted as the common list has it, or `words:`
  with `name` and `hard`. One with nothing to look for stops the load.

`jobdork/search/dealbreakers.py` holds the matching and the list. Checked in
the browser on a copy: typing "us citizen" and pasting "Applicants must be
U.S. citizens" shows `Found: "U.S. citizens"`; Add and a one-click
suggestion both save words. Seven new tests (`tests/test_dealbreakers.py`
and one in `tests/test_serve.py`, which replaces the check of the old
regex samples).

---

## Added — 2026-10-01 — Eightfold boards

Starbucks and Lockheed Martin hire through Eightfold, and Discover reported
each as "eightfold, no adapter". Eightfold's robots.txt closes its sites
and opens two paths to tools, `/careers` and `/api/pcsx`; the second is the
JSON the careers site reads.

- **`fetch/eightfold.py`**, source `eightfold`, token `host/domain`
  (`starbucks.eightfold.ai/starbucks.com`): the careers host, a tenant's or
  the employer's own (`careers.lumen.com`), and the employer domain the API
  is asked for.
- **Pages are ten results, ranked by relevance**, so as with Oracle a
  listing is kept only when your title rules keep its title, each title is
  read at most five pages deep, and a page with none of yours ends it.
  Measured, US: Starbucks, store manager, 50 jobs; Lockheed Martin,
  software engineer, 50.
- **Your countries are asked by name**; a country with no jobs costs one
  request (Starbucks lists none in the Philippines).
- **The advert is one detail request per kept job.** A posting's address
  carries `?domain=`, which its page accepts, so the still-open check and
  `enrich` can ask again; a removed posting answers 404.
- **Discover settles the domain** by asking: a wrong one answers 404, so a
  `domain=` the page names is tried first, then the site the tenant was
  read on, then the tenant's name with .com. An Eightfold careers site on
  the employer's own host is tried as a board when it names no tenant.
- **A vendor's test copy is not a board.** HP's page linked
  `hp-sandbox.eightfold.ai`, which answered with 135 jobs; tenants named
  sandbox, staging, test, demo, uat or dev are ignored, and that one is
  rejected in `scripts/boards_review.csv`.
- **The check that holds a board back for a person** compared the tenant
  with the site's name, and on an employer's own host the tenant is
  "careers"; for Eightfold it compares the employer domain.
- **An employer is read through one kind of board.** FedEx's careers page
  stopped linking its Workday boards on 2026-10-01, and the build would
  have added its site next to them; a site board is no longer added for an
  employer that has their own board.

**Test list: 29 of 46 (was 27), US 25 of 37 (was 23).** New: Starbucks,
Lockheed Martin.

**Built-in boards: 319 (was 304), 305 of them US.** 16 Eightfold boards,
among them Citigroup, Morgan Stanley, Northrop Grumman, Micron, Qualcomm,
PayPal and AstraZeneca; six employers moved from their site to their
Eightfold board.

**Measured on the same copy, US only, 15 titles:** a scan of the 319
boards took 23 minutes (21 before), about 10,700 requests. The 16 Eightfold
boards cost 874 of them and fetched 524 jobs for your titles; that copy keeps
only Naperville and remote jobs, so 11 were kept.

`eightfold` was added to the local config's sources; the example lists it.
Eight new tests (`tests/test_eightfold.py`, and one in
`tests/test_directory.py`).

---

## Added — 2026-10-01 — Oracle Recruiting Cloud boards

JPMorgan Chase, Kroger, Hilton and Marriott hire through Oracle Recruiting
Cloud, and Discover reported each as "oraclecloud, no adapter". Marriott's
was worse: with its own board unreadable, the only board Discover could
offer was a link on a brand page to Marriott Vacations Worldwide.

- **`fetch/oracle.py`**, source `oracle`, token `host/site`
  (`jpmc.fa.oraclecloud.com/CX_1001`): the JSON the employer's Candidate
  Experience site reads. robots.txt on these hosts answers 403.
- **The keyword search is loose** ("software engineer": 1,659 results at
  JPMorgan, by relevance), so a listing is kept only when your title rules
  keep its title, each title is read at most four pages of 25 deep, and a
  page with none of yours ends it. Measured: JPMorgan, software engineer,
  US: 88 jobs in 32 seconds; Kroger, pharmacist: 100.
- **Your countries are asked of the board** through its location filter;
  several are one finder value joined by `%3B`, since a bare `;` ends the
  finder's name. A board with none of yours costs one request.
- **The advert is one detail request per kept job**; a removed posting
  answers with no items, which the still-open check counts as closed.
  `enrich` reads Oracle adverts the same way.
- **Discover reads the token** off the careers link, or, where the page only
  loads Oracle's assets (Kroger), off a `siteNumber=` in their addresses. One
  board under two site numbers with the same count (Hilton's `CX_1` and
  `CX_1009`) is kept once, and an Oracle host read as a board is no longer
  also reported as "no adapter".
- **`build_boards.py` drops an employer's site board when it finds their own
  board**, so nobody is read twice: Mayo Clinic, Ascension, Tenet and five
  more moved from their site to their Oracle or Workday board.
- Paced at two requests a second for every `*.oraclecloud.com` host.

**Test list: 27 of 46 (was 24), US 23 of 37 (was 20).** New: JPMorgan
Chase, Kroger, Hilton; Marriott's find is now its own board (12,912 jobs)
rather than Marriott Vacations Worldwide's.

**Built-in boards: 304 (was 273), 291 of them US.** 32 Oracle boards,
among them American Express, Dollar General, Macy's, Honeywell, Texas
Instruments, Northwell Health and Providence. Alorica's and Penske's were
held back (Oracle host names are codes, so the name check cannot match
them) and accepted in `scripts/boards_review.csv`.

**Measured on the same copy, US only, 15 titles:** a scan of the 304
boards took 21 minutes (19 before), about 9,800 requests in all. The 32
Oracle boards cost 1,212 of them and kept 41 jobs; Workday's 162 boards
still cost the most, 7,053.

`oracle` was added to the local config's sources; the example lists it.
Eight new tests in `tests/test_oracle.py`.

---

## Added — 2026-10-01 — An employer's own careers site as a source

Discover found Kaiser Permanente and UnitedHealth Group on Taleo, Mayo
Clinic on Oracle Recruiting Cloud, State Farm on iCIMS, UPS behind a Phenom
front end, and Wells Fargo and General Motors not at all: none of them
readable. But their careers sites list every
posting in a sitemap and mark each posting page up for Google as a
schema.org `JobPosting`, with title, places, dates, the full advert and pay
when stated. That is readable, whatever system sits behind it.

- **`fetch/site.py`**, source `site`, token the careers site's address
  (`https://jobs.mayoclinic.org`). Sitemap first (robots.txt `Sitemap:`,
  then the index's jobs children), then the posting pages.
- **Only postings whose address names one of your titles are read**
  (`/job/rochester/registered-nurse/33647/…`), one request each, at most 40
  a site per scan, one a second. Addresses that are ids only
  (`jobs.statefarm.com/jobs/46295`) are read newest first, 20 a scan.
- A posting address has a jobs word and an id; category and blog pages in
  the same sitemap have none and are skipped. One posting in five languages
  counts once.
- `validThrough` in the past leaves a posting out. Pay of 0 to 0 (State
  Farm, on every post) is no pay stated. `address` may be a list (Wells
  Fargo).
- **Discover offers the site** when it finds no board jobdork can read and a
  posting there is marked up: "site 3097 jobs [verified]" for Kaiser.
- robots.txt is honoured for sitemaps and pages; the reader moved from
  `discover` to `fetch/robots.py` so both use it. `Fetcher.pace()` slows one
  host, for sites no rate table can name in advance.

**Test list: 24 of 46 (was 16), US 20 of 37 (was 12), healthcare 4 of 5
(was 1).** New: Kaiser Permanente, UnitedHealth Group, Mayo Clinic, Wells
Fargo, State Farm, UPS, General Motors, Stripe.

**Built-in boards: 273 (was 183), 261 of them US.** Rebuilding the list
with the site reader added 88 employers' own sites: Walgreens, Chipotle,
Ford, Disney, PepsiCo, Procter & Gamble, Tenet, Ascension, Sutter Health,
Johns Hopkins Medicine and the rest. The check that holds a board back for
a person compared the employer's name with the token's first part, which
for a site is "https:", so it held back all 91; for a site it now asks
whether the address led to another domain. Six did; five were the
employer's own (Cedars-Sinai at `cshs.org`, Whole Foods at
`wholefoods.com`) and were accepted in `scripts/boards_review.csv`, and
Hanesbrands, whose address leads to Gildan's site, was rejected.

**Measured on the same copy, US only, 15 titles:** a scan of the 273 boards
took 19 minutes (18 without the sites). The 86 site boards read in it cost
1,564 requests and kept 82 jobs, while Workday's 159 boards cost 6,973.

`site` was added to the local config's sources; the example lists it.
Nine new tests in `tests/test_site.py`.

---

## Added — 2026-10-01 — Employer boards jobdork ships with: 183 employers, on by default

A fresh install read keyword sources and nothing else until someone ran
`discover` employer by employer. Workday, Greenhouse and Ashby have no
cross-employer search, so the employers most people name (retailers,
hospital systems, banks) were out of reach by default.

- **`jobdork/data/boards.csv`: 183 boards, 175 of them US employers, across
  23 industries.** Healthcare 20, banking 19, tech 18, retail 13,
  insurance 12, pharma 11 and the rest; 158 are Workday. Each was found by
  `discover` on the employer's own site and answered with jobs, and records
  the countries it lists jobs in.
- **`sources.directory`**, on by default: reads the boards hiring in your
  countries (`locations.countries` unless it names its own), optionally
  only some industries. A board also in `sources.companies` is read once.
  `jobdork sources` says how many boards your config reads.
- **`scripts/build_boards.py`** builds the list: `--add` runs `discover`
  over `scripts/candidates.csv` (645 employers, 615 US); `--reverify` asks
  every board again and removes one with no jobs for three weeks. A board
  found deep in a site under another name is held back for a person.
- **`scripts/boards_review.csv`** holds those decisions, each with its
  reason, and the build applies them every run. From the first build: 9
  held-back boards accepted (Cencora is `myhrabc`, Corewell Health is
  `spectrumhealth`, Southwest is `swa`), and 4 rejected: Marriott's link to
  Marriott Vacations Worldwide, UPMC's to GoHealth Urgent Care, a 38-job SAP
  affiliate, and a 3-job Breezy board under Duolingo's name.
- **A weekly GitHub Action** (`.github/workflows/boards.yml`) re-verifies the
  list and opens a pull request whose text says what changed. It needs a
  `BOARDS_PR_TOKEN` secret: a pull request opened with the workflow's own
  token does not start the checks main requires.
- `discover` now records the countries a board lists jobs in: Workday's
  country facet, or the places of the jobs another platform returned.
- `.gitignore` ignored every `*.csv`, so `jobdork/data/boards.csv` and the
  build's `scripts/candidates.csv`, `scripts/boards_review.csv` and
  `scripts/employers.csv` would have been left out of a commit; they are
  now listed as exceptions, like the gazetteer.

**Measured on a copy, US only, 15 titles:** the 183 boards cost 18 minutes
and about 7,000 requests, nearly all Workday (one search per title per
board, then one request per matching job), and kept 523 jobs out of 8,000
fetched. The other platforms' 17 boards took 48 requests.

Reading the built-in Workday boards without each job's advert was tried and
dropped. Skipping it outright took 10 minutes but kept 1,013 jobs, 825 of
them with no known country: "2 Locations" names nowhere, and passed the
location filter unread. Reading the advert only for those took 14 minutes
and kept 480, 43 fewer than a full read, most likely remote jobs listed
under a city, since only the advert says remote. Four minutes did not pay
for losing those, so every board is read in full.

- **`enrich` reads Workday adverts** from the same record the scan uses;
  the posting page is drawn by script and carries none. Checked on live
  postings: 7,000 to 8,000 characters each.

From the first build, 467 of 645 candidates had no board jobdork can read:
Oracle Recruiting Cloud, Taleo, iCIMS and Eightfold above all, which is the
order platform readers come next. docs/SOURCES.md's "Why not a bundled list
of employers" is rewritten to say how the list limits each of its costs.
Ten new tests.

---

## Fixed — 2026-10-01 — Discover could hang on a page with a long run of letters

`jobdork discover` looked for a job system's address (`kp.icims.com`,
`acme.wd5.myworkdayjobs.com`) with patterns like `[A-Za-z0-9_-]+\.icims\.com`,
which retry from every letter of a run that never matches. A page with 40,000
letters of inline data in a row cost 87 seconds per pattern; a page with a
megabyte of it never finished. Found when a build over 645 employers sat at
full CPU for 26 minutes.

A host name label is now matched only where it starts, and at most 63
characters long (the DNS limit). Two million letters take a third of a
second, and every board found before is still found. One new test.

---

## Changed — 2026-09-30 — Discover follows the site's own job links and sitemap

Discover tried one page and then a fixed list of seventeen addresses
(`/careers`, `/jobs/search`, `/join-us`…). A board linked from anywhere
else on the site was missed. On the test list below it found a board for 10
of 46 employers and took 20 minutes.

- **Reading order:** the page you gave, the front page, then that site's
  own links to job pages (same site, search pages first, six at most), then
  its sitemap (one or two postings, whose Apply links name the board), then
  six usual addresses. Twelve pages at most; it stops at the first board.
- **robots.txt is honoured**, read the way RFC 9309 says: the longest
  matching rule decides. Python's `urllib.robotparser` takes the first
  match, and read `jobs.nvidia.com`'s `Disallow: /` ahead of its
  `Allow: /careers`, closing the page the site opens to tools. Pages left
  unread for it are listed.
- **A site that does not answer, or refuses (401, 403), is not asked
  again.** Unreachable and blocked are reported apart.
- **A board found only on a page Discover followed, under a name that is
  not the site's, carries a note to check it.** `careers.marriott.com` links
  Marriott Vacations Worldwide's board (`mymvw`) from a brand page; Marriott's
  own jobs are on Oracle Recruiting Cloud.

**Result on the test list: 16 of 46 (was 10), US 12 of 37 (was 8), in 7½
minutes (was 20).** New: CVS Health, FedEx, Airbnb, Spotify, Grab; Costco
now names its platform (Taleo) instead of nothing. Marriott's find is the
sister company above, so the honest count is 15.

Fourteen new tests in `tests/test_discover.py`. The Adobe test now expects
robots.txt to be read before the page.

---

## Added — 2026-09-30 — A test list for Discover: 46 real employers

There was no measure of how often Discover finds a board for the employers
people name. Every change to it was checked against the one site that
prompted it.

- **`scripts/employers.csv`**: 46 employers, 37 in the US across retail,
  banking, healthcare, logistics, manufacturing, hospitality, government
  contracting, education and tech, and 9 elsewhere.
- **`scripts/discover_benchmark.py`** runs Discover on each, real requests
  paced as every jobdork request is, and writes
  `out/discover_benchmark.json`: the outcome per employer, the hit rate
  overall, for the US and by industry, and every platform seen by how many
  employers use it. Run on purpose, not in CI.

**First result: 10 of 46 (21%), US 8 of 37.** All ten were Workday. No
reader for Oracle Recruiting Cloud (5: Kroger, JPMorgan, Marriott, Hilton,
Mayo Clinic), Eightfold (3), Taleo (2), iCIMS (1); blocked by 4; healthcare
0 of 5, hospitality 0 of 4. That order is the order platform readers get
built in.

---

## Added — 2026-09-30 — Workday boards, found by Discover and filtered to your countries by the board

Discover on NVIDIA's careers page (`jobs.nvidia.com`) listed three platforms
with "no adapter" and added nothing: Workday, where NVIDIA's jobs are, and
two lines for Eightfold, which were `app.eightfold.ai` and
`vs-errors.eightfold.ai`, Eightfold's own service hosts and nobody's board.
Most large employers hire through Workday; without it a scan reached
startups and missed the companies people most often name.

- **`fetch/workday.py`**: an employer's board through the JSON its careers
  site reads. The token is three parts, `tenant/dc/site`.
- **Discover reads the three parts** off the employer's page and verifies
  the board with one empty search, its own count of open jobs:
  "workday 2000 jobs [verified]" for NVIDIA.
- **Your countries are asked of the board itself** through its country
  filter, whatever the employer named it. NVIDIA has no Philippine jobs, so
  for the real config the board costs one request and says "NVIDIA lists no
  jobs in PH"; before the filter, two titles took 145 requests and 2½
  minutes to find the same nothing.
- **Only titles you keep are fetched in full** (one request each), and
  Workday hosts are paced at one request a second.
- **Still open** asks the posting's own record: 404 or `posted: false` is
  closed, and counts as hard evidence.
- **Discover ignores a platform's service hosts** (`app`, `vs-errors`, `cdn`
  and the like), so they are no longer reported as boards.

Also fixed on the way: a closing date passed (Kalibrr, Himalayas) was
recorded as closed but not as hard evidence, so the post was never moved to
closed. It is now.

`workday` was added to the local config's sources; the example lists it.
Nine new tests; two older ones that named Workday as the example of a
platform with no adapter now name iCIMS.

---

## Added — 2026-09-30 — Himalayas: remote jobs open to your country and your hours

Remote work is most of what a scan can find for someone outside Manila, and
most "remote" jobs on the big boards are remote within the US. Himalayas'
public search (no key) says, per job, which countries it accepts and which
UTC offsets, so those can be filtered rather than shown.

- **`fetch/himalayas.py`**, in `sources.keyless`: each title searched once
  per country in `locations.countries`, three pages of 20, newest first, one
  request a second. Skipped when `locations.work_modes` leaves out remote.
- **Your country:** asked of the search itself, which returns jobs open to it
  and jobs open worldwide; the post says which ("remote, open to
  Philippines", "remote worldwide").
- **Your hours:** a job whose accepted offsets are all more than an hour from
  yours is left out. Your offset is read from the anchor's longitude
  (Baguio: UTC+8), with no time-zone database to ship.
- Posting and expiry dates as for Kalibrr: freshness tiers apply, an expired
  post is not returned, and "still open" (job pages answer 403 to scripts)
  goes by the expiry, then by the latest search.
- Their terms ask that a job links back and names Himalayas as its source:
  the link is the Himalayas page, and the source reads Himalayas.

Tried live with the real config's first two titles: 6 requests in 5 seconds,
89 posts, 7 kept, all open to the Philippines, four posted that day. Five new
tests, none touching the network. `himalayas` was added to the local
config's source list by hand, and the example lists it.

---

## Added — 2026-09-30 — Kalibrr as a source, and Discover knows a job site from an employer

Discover was given `https://ph.jobstreet.com/jobs` and answered "refused the
request; nothing here works around that, no job board found". True, and no
help: Discover looks for one employer's board on that employer's own site,
and JobStreet is a job site, not an employer. It answers 403 to anything but
a browser, its robots.txt closes its search API, and SEEK's API is for
partners only. Kalibrr, tried next, is different: its site reads a public
JSON search that answers scripts, and robots.txt allows it.

- **Kalibrr is a scan source** (`fetch/kalibrr.py`, in `sources.keyless`).
  Each title is searched four pages deep, 50 a page, at one request a
  second. Philippine and Indonesian jobs; skipped when `locations.countries`
  names neither PH nor ID. Its dates are the best of any source:
  - `activation_date` is the posting date, so the freshness tiers apply;
  - a post past its `application_end_date` is not returned, and the "still
    open" check marks a stored one closed after it;
  - a recruiter not seen in 30 days (`es_recruiter_last_seen`) is flagged,
    "applications may not be read": the clearest ghost signal a board gives.

  Pay counts only when the employer shows it; remote and hybrid are read
  from Kalibrr's own fields. Its job pages answer 403 to scripts, so "still
  open" otherwise goes by whether the post was in the latest search, as for
  Adzuna (the two now share that path), and `enrich` skips it.
- **Discover recognises job sites by address** (JobStreet, JobsDB, SEEK,
  Kalibrr, LinkedIn, Indeed, Glassdoor, OnlineJobs.ph) and says what to do
  instead, before sending anything: for Kalibrr, add it to
  `sources.keyless`; for the rest, search links, or Discover the employer's
  own site from a posting.
- **Dork mode** has JobStreet, JobsDB, Kalibrr and OnlineJobs.ph on request
  (`jobdork dork --sites jobstreet kalibrr --since 1w`), opened in your
  browser, which those sites allow. Not in the default set, which stays as
  it was.

A config that lists its sources keeps its list: `kalibrr` was added to the
local one by hand, and the example config lists it.

Tried live with the real config's first two titles: 8 requests in 8
seconds, 240 posts; 231 dropped on the title (Kalibrr's search is loose), 3
as more than 25 miles from Baguio, 1 as a ghost 247 days old; 2 remote posts
kept, one posted two days before. Ten carried the idle-recruiter flag. Seven
new tests, none touching the network.

---

## Added — 2026-09-30 — stale and ghost job posts: aged by date, ranked, and dropped past 90 days

Nothing looked at how old a post was. Of the 29 posts in the database, 17
were posted more than 60 days before and 9 more than 180, the oldest on
2023-09-05: mostly Workable listings still "published" years on, the classic
ghost job. The model that judges fit was given no dates at all, and
Greenhouse's date fell back to `updated_at`, which an edit or an automatic
repost bumps, so an old post could read as this week's.

**The age is measured in code, never asked of a model** (`search/freshness.py`).
A model has no clock and can take the dates in a resume or an advert for the
posting date. Tiers, all settings under [freshness](CONFIG.md#freshness):

| Tier | Age | Effect |
|---|---|---|
| New | up to 2 days | +5, green badge |
| First week | up to 7 | 0 |
| Older, risky | up to 21 | −5, amber, flagged |
| Stale, may be filled | beyond 21 | −15, red, flagged |
| Ghost | beyond 90 | dropped at screening |

Stale posts stay listed: the job you want most may still be worth a try. A
ghost you have not acted on is left out of the list, and counted ("13 ghost
listings hidden"); a post you applied to is never hidden for its age.

- **Dates, best first:** the board's posting date; the posting page's own
  `datePosted`, or its "Posted 3 weeks ago" (read by `enrich` only after the
  word "posted", so "5 years of experience" or "a 12-month contract" is never
  taken for a date); failing both, the day jobdork first saw the post, as a
  lower bound once it is more than a week old; failing that, "posting date
  not stated", kept.
- **Reposts** date from the first sighting: a job seen in July, under this
  URL or any other copy of it (grouping.py), that the board now dates
  September, is flagged "reposted" and aged from July.
- **Greenhouse** no longer falls back to `updated_at`.
- **At the source:** Adzuna is asked for nothing older than `ghost_days`, so
  ghosts cost no quota. USAJOBS can be asked for 60 days at most, so with the
  default 90 screening does it.
- **An advert that says the post is over** ("this position has been filled",
  "this job has been archived", "no longer accepting applications") is
  dropped at screening. The words are the listing check's, now shared, and as
  tight as before: USAJOBS' "will no longer be available once the
  announcement has closed", printed on every open job, does not match, nor
  does "archived records management".
- **The model is told the dates in their own block** (`<<POSTING DATES>>`):
  today, the posting date and its age, and that the resume's dates are the
  candidate's history. It scores fit on substance only and, for an older or
  stale post, adds a concern that it may be filled.
- **The page** shows each post's age as a badge worked out when the page
  loads, not when it was screened (a post screened as new is not new a month
  later), and has a "Posted within" filter: 2 days, a week, 3 weeks, any
  time.

Tried on a copy of the real database: 13 of 29 posts past 90 days, the rest
ranked with their age ("posted 29 days ago (stale, may be filled): −15").
Thirteen new tests.

Not done: flagging an Adzuna post that is not on the employer's own careers
board. Adzuna's pages cannot be read, and matching it to the employer's board
needs that board found first (`discover`); it is left for its own change.

---

## Changed — 2026-09-30 — a container needs no config.yaml prepared by hand

Setting jobdork up in a NAS's Docker app took a file made outside the
image first: download `config.example.yaml`, rename it, upload it, and map it
to `/app/config.yaml`. Map it before it exists and Docker makes a *folder*
of that name; leave it out and the container stopped at start with "No config
found". The image already carries the example.

- **In a container with no config**, the first start copies the image's
  `config.example.yaml` to `data/config.yaml` and uses it, with a warning in
  the log saying so. `data/` is the volume that is kept, so the dashboard's
  settings are saved there and survive a new container. Later starts read
  the kept copy and never overwrite it.
- **`data/config.yaml` is the last place looked**, after `config.local.yaml`
  and `config.yaml`, so a `config.yaml` already mapped to `/app/config.yaml`
  is still the one used.
- **Only in a container:** the same test as for listening beyond loopback,
  the `JOBDORK_IN_CONTAINER` variable *and* a container marker file, so a
  checkout with no config still stops with "No config found" rather than
  writing one. The test's constants moved from `web/serve.py` to
  `core/config.py`, which both now use.
- If `data/` is not writable by user 1000, the error says so and gives the
  `chown`.

A NAS now maps one folder, `data` → `/app/data`. `docs/DEPLOY.md` and the
README say so. Three new tests: seeding and keeping the copy, a mapped
`config.yaml` winning, and nothing written outside a container.

---

## Fixed — 2026-09-30 — 0.14.3 is published; the signature check no longer races Docker Hub

`v0.14.3` is the first release. The image is on Docker Hub as
`jessengolab/jobdork:0.14.3` (also `0.14` and `latest`), exactly
`sha256:6ec0dc1f092423b4cc2edcbbdff86387095ffe53864188c17b7405e00dc4da2f`,
signed by this repository's workflow.

The run still ended red. cosign 3 stores the signature as an OCI referrer of
the image, and Docker Hub lists a new referrer a few seconds after it is
pushed; the verify step ran three seconds after signing and got "no
signatures found". The signature was there: it is listed under the image's
referrers, and `cosign verify` (v3.0.6) passes against it from outside. But
the failed step skipped the job that writes the GitHub Release page, so that
page was created by hand with the same notes the job writes, plus a line
saying so.

Re-running the failed job was not an option: it rebuilds, the build time is
in the image's labels, so the digest changes and `0.14.3` and `latest` would
move to an image other than the one signed and approved.

The verify step now tries up to six times, ten seconds apart, before it calls
a signature missing.


---

## Fixed — 2026-09-30 — no traceback when the browser hangs up

With the dashboard running, reloading the page, closing its tab or
restarting the server printed a full traceback ending in
"ConnectionResetError: [Errno 54] Connection reset by peer". A browser keeps
a connection open for its next request and drops it when the page goes
away; Python's standard server reports that as an error. Nothing had
failed, but it read as a crash every time. The server (`serve.Server`) now
passes over a reset, a broken pipe, an aborted connection and a timeout, and
still prints anything else.

---

## Fixed — 2026-09-30 — the resume review showed its title twice

The Resume page read "Resume review", then straight under it "Resume review"
again: the section's heading, then the review's own first line, `# Resume
review`, which the page drew as a heading. It looked like two reviews. A job
post's Resume review tab had the same doubling. The page now leaves that
first line out; `resume-review.md` in the job folder keeps it, since there it
is the only title.

---

## Added — 2026-09-30 — the projects section adapts to the person, and projects can be described STAR-style

A projects section is a student's evidence and a senior engineer's padding;
the tailored resume had one rule for both (a PROJECTS section at the end,
whenever the model listed any).

- **The model judges the career stage** from the resume and the post
  (student or entry level, career changer, freelancer, experienced) and the
  post's industry, with a one-line reason. **Code decides the layout** from
  that (`resume_doc.ORDER`):

  | Stage | Projects section |
  |---|---|
  | Student, entry level | right below Education, which moves above the jobs; at most three |
  | Career changer | above the jobs; at most three |
  | Freelancer | right after the jobs, as "Selected Client Projects" ("Consulting Highlights" in business); at most four |
  | Experienced | none: a project belongs in a job's bullets, where the resume ties it to that job |

  A stage the model makes up counts as experienced, the one that adds
  nothing. The heading follows the industry: "Technical Projects",
  "Portfolio Highlights", "Key Initiatives", otherwise "Projects". A new
  gate, "projects section", says which stage was judged, why, and what that
  did to the section.
- **Projects on the Resume page**, with STAR fields (situation, task, action,
  result) plus tools and a link, kept in the database (schema version 8, a
  new `projects` table). They are part of the record: the tailored resume and
  the `claude -p` drafts may use them (as `projects.md` in the job folder),
  and the figure and hallucination checks accept what they say. A project
  the resume and the notes do not name is left out and listed. Each project
  is written as one to three STAR bullets.
- **The tutorial filter:** a to-do list, tic-tac-toe, a weather app, a
  calculator, a clone of a well-known site and the like are flagged as you
  type the name, on the saved project, and as a gate on a tailored resume
  that shows one. Flagged, not hidden: it may be all a student has. The page
  and the server use one pattern (`resume_doc.TUTORIAL`).

Tried with `gemma4:26b` on the real resume for an internship post: judged
"experienced (over 7 years of professional experience)", so no section, and
the one saved project left out and counted. Seven new tests. A database at
schema 8 is refused by an older jobdork, as every schema bump is.

---

## Added — 2026-09-30 — a tailored resume in the ATS template, as a PDF named for the role

"Tailor my resume" suggested edits to tick, and downloaded the result as a
`.txt`; a whole resume rewritten for a post came only from `claude -p`, as
Markdown, which a NAS container does not have. Now **Write tailored resume
(AI)** in a job post's window (or `jobdork tailor UID`) has the AI-page model,
Ollama or a hosted one, rewrite the resume for that post and saves it as
`FirstName_LastName_JobTitle_Resume.pdf`, with its Markdown beside it.

- **The layout is the
  [AI-friendly template](https://resumeoptimizerpro.com/blog/ai-friendly-resume-template)**,
  and it is code, not a request: the model returns fields (summary, skills,
  jobs, education, certifications, projects) and `writing/resume_doc.py` lays
  them out, so every provider gives the same document. One column; the name,
  then "City, State | Phone | Email | LinkedIn"; PROFESSIONAL SUMMARY, SKILLS,
  PROFESSIONAL EXPERIENCE, EDUCATION, CERTIFICATIONS, PROJECTS, each left out
  when empty; skills comma-separated; each job as title, then
  "Company | City, State | Month YYYY - Month YYYY", then bullets. A date the
  resume gives as a year stays a year: a month nobody wrote is not invented.
- **The contact line is copied from the resume by script.** A hosted model
  never sees the email, phone or profile links (they are redacted), and a
  name a model typed is one it could get wrong.
- **Checked like everything else a model writes:** figures, AI tells, the
  hallucination check, and a new gate: an employer, school or certification
  the resume does not name is left out and listed, and a title worded
  differently from the resume is listed to check.
- **The PDF is written by jobdork** (`output/pdf.py`): real selectable text in
  reading order, Helvetica (the template's Arial), no new dependency, so
  nothing new in the image to lock or scan. Text outside Western European
  letters is spelled with the nearest ones ("Łódź" as "Lodz"). A heading is
  kept on the same page as the lines under it.
- **`claude -p`'s CV follows the same template**, keeps titles, employers and
  schools as the resume writes them (it could retitle before), and gets the
  same PDF beside `CV.md`.
- **The page** shows the tailored resume formatted, with Open PDF and
  Download PDF. The PDF is rendered from the document's own Markdown when
  asked for, so it always matches what the page shows.

Tried on the real resume with `gemma4:26b` over Tailscale: written in about 40
seconds, all 25 claims supported, every employer found, one AI tell
("Enhanced") flagged. Nine new tests.

---

## Changed — 2026-09-30 — View resume shows the resume, not only its text

View resume showed the text the tools extract, which for a PDF is broken
lines and no layout: it was hard to tell whether that was the file or the
reading of it. Now a PDF opens in the browser's own viewer inside the dialog,
and a Word file or Markdown is shown with its headings, bullets and bold. The
extracted text, with the skills found in it, is still there, folded under
"The text the fit score and the AI read".

The page may now frame a `blob:` it made itself (`frame-src blob:` in the
content security policy); it still loads nothing from anywhere else, and
nothing may frame the page.


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

- **The app in your own language** (asked 2026-10-28). A language chosen on
  setup's first screen, before anything else, and changeable in Settings:
  every page, setup step, message and the guide in it. The most-used
  languages first (Spanish, Chinese, Hindi, Arabic, Portuguese, French,
  Filipino, among others), and a way to ask for one that is missing (a
  feedback kind). With it, a **resume written in another language**: its
  skills read (today the skill list is English), and the AI asked to read
  and answer in it. A resume's file name in any script already works
  (0.15.4).
- **More job boards** (asked 2026-10-28, the big US list). Indeed, LinkedIn,
  ZipRecruiter, Monster, SimplyHired, CareerBuilder, Dice, Built In and
  FlexJobs are out for the reason in PLATFORMS.md (no public API; their
  terms and robots.txt refuse scripts) and stay reachable through
  `jobdork dork` and **Search Google Jobs**. Stack Overflow Jobs closed in
  2022; USAJOBS is read already. Worth checking, each against its terms and
  robots.txt before anything is built: **We Work Remotely** (a public RSS
  feed; already planned in REGIONS.md), **Idealist** (nonprofits),
  **Snagajob** (hourly work) and **Handshake** (students; behind a school
  login, so likely out). The licensed way to the big boards is a keyed
  reseller of Google's job results (JSearch, SerpApi), a decision in
  DECISIONS.md.

- **Europe outside Germany, the Gulf, and New Zealand** stay thin (measured
  2026-10-23): their large employers mostly name no board, and their job
  sites are closed to scripts or need a key (Reed, France Travail). What is
  left to try is in [REGIONS.md](REGIONS.md#planned).
- **Regional job sites in Asia**, where employers' boards cannot reach.
  Probed 2026-10-23: **MyCareersFuture** (Singapore's government portal)
  answers its site's own search API with whole adverts and pay, and its
  robots.txt allows it, but its terms of use (read in a browser, last
  updated 15 Oct 2026) forbid it without written permission from SWDA:
  caching of and links to its content are "strictly prohibited" (§11), and
  no part may be "stored in a retrieval system" (§15). jobdork stores each
  advert and links to it, so it is not built; written permission from SWDA
  is the way in; 104 (TW) and
  GaijinPot (JP) answer 403 to scripts; Saramin and Worknet (KR) need a key
  each, as Adzuna does. Glints (SEA) closes its search to scripts in
  robots.txt (`/opportunities/jobs/explore?…`); its job pages are open, so
  a sitemap reader like the careers-site one is the way in, not yet tried.
  Mexico has the same gap.
- **More built-in boards.** 420, 338 of them US; 996 candidates. More
  candidates help where employers name their boards; where they do not (most
  large Asian and Mexican employers), regional job sites are the lever.
  SuccessFactors behind its older portal only (Edison, NRG, Wipro) is still
  unread.
- **An interactive demo for the launch** (Product Hunt recommends one; the
  tools it names include Arcade, Storylane, Supademo, Hexus, Layerpath,
  Guideflow and ScreenSpace). Two ways, not yet chosen: record one with
  Arcade or Supademo, on a dashboard running made-up demo data
  (`scripts/guide_demo.py`) from a written click script with a caption per
  step (resume, suggested titles, scan, scored job posts, an AI verdict with
  its claim check, a tailored letter); or a demo build of the dashboard
  itself on the website, the real page on fixed demo data with no server.
  The recording is done in the maintainer's own browser and account.
- **AI page, an Ollama address on another computer** (found 2026-10-27, a
  tester using the owner's Ollama over Tailscale). A line with no address of
  its own shows the page-wide one, `http://localhost:11434` by default, in
  its box, so someone without Ollama of their own keeps an address that
  cannot work, and every **Load models** fails. Say when the address is
  this computer's own and nothing answers there, and leave the box empty
  rather than pre-filled when the page-wide address is only the default.
- **The first scan's two parts, told apart** (asked 2026-10-27). Setup's
  last step runs a quick scan ("first scan": the keyword job sites, your own
  boards and 8 built-in ones) and then a "full scan" of every other
  built-in board, in the background. The Dashboard should say which is
  running and that it started: "Quick scan: reading job sites and 8
  employer boards" then "Full scan started: reading the other N employer
  boards; job posts keep arriving". When the full scan ends, tell the
  person their job posts are ready to view: a notice on the page with a
  **View job posts** button, and the computer's notification when
  notifications are on, including when the window was closed meanwhile.
- **The hallucination rate in colour** (asked 2026-10-27): the Dashboard
  tile and the "Hallucination, over time" chart green at 5% or below (the
  2-5% target in docs/AI-MODELS.md), amber above 5% up to 10%, red above
  10% (where every other local model measured). Said in words too, not by
  colour alone ("within target", "watch it", "too high: see AI-MODELS.md").
- **A scan queue you can see and cancel** (asked 2026-10-27). A change to
  Search, Projects, Education or Sources starts a scan or re-screen; one
  that arrives while another runs waits (web/live.py `Runner.queue`), but
  only one of each kind, the newest replacing the one waiting, and the page
  never shows it. Instead: first in, first out, every request kept, with
  what started it ("Search: added Nurse Practitioner"); the number waiting
  on the Dashboard; a list where any waiting one can be cancelled; and
  **Stop** for the scan running now, keeping what it found so far. Shown in
  the Dashboard panel now titled "Feedback on AI output, per day", renamed
  for it (where the feedback chart goes instead is decided when it is
  built).
- **Hosted models measured before recommending them** (asked 2026-10-27):
  run scripts/hallucination_benchmark.py with Gemini and Groq models as
  reader and as checker, as was done for Ollama, and count requests and
  tokens per verdict against each free tier's daily and per-minute limits,
  so the guide can say which free models to pick and how many job posts a
  day a free key covers before it is capped.
- **An Ollama address with a key** (for beta testers using someone else's
  Ollama without Tailscale, 2026-10-27): an optional key on an Ollama line,
  sent as `Authorization: Bearer`, kept like every other key (memory or the
  keychain, never a file), so jobdork can use an Ollama behind a
  gatekeeper that checks keys; and one pasted connection code that fills
  the AI page.
- **Add a job post from any link** (found 2026-10-27, a UnitedHealth Group
  post on `uhg.taleo.net/careersection/10000/jobdetail.ftl?job=2389918`
  refused with "cannot tell which platform that URL is on. Supported:
  greenhouse, ashby, lever, breezy, smartrecruiters"). Adding by link
  (`add_by_url`, `cli._platform_for`) knows 5 systems, fewer than a scan
  reads, and nothing else. Recognise every system jobdork reads (Workday,
  Oracle, Taleo Business Edition, Eightfold and the rest); for any other
  link, read the page itself (schema.org `JobPosting`, as fetch/site.py
  does); and a reader for **Taleo Enterprise** (`*.taleo.net/careersection/`):
  its job page carries the title, job number, place, department, type,
  posting date and description in the page's `initialHistory` field, with
  no `JobPosting` data. When nothing can be read, say so and offer to paste
  the advert's text instead.
- **The error log names the reason, not only the status.** A model list
  that could not be loaded is recorded as "GET /api/llm/models failed on
  the server (HTTP 502)", although jobdork knows the reason ("Ollama is not
  answering at …"). Record the server's own message; and treat a 502 that
  only reports another service not answering as a warning about that
  service, not as an error in jobdork.
- **Linux installers: an AppImage and a .deb** (chosen 2026-10-27, both),
  built and attested by the release workflow beside the Mac and Windows
  ones, with removal (`jobdork uninstall`, Settings) and Update for each.
- **Guardrails, from Guardrails AI's ideas** (guardrails-ai/guardrails, used
  as reference, not as a dependency): measure `bespoke-minicheck` (4.7 GB,
  already in Ollama) as the checker with scripts/hallucination_benchmark.py,
  so smaller computers can run reader and checker together; a rewrite pass
  that asks the reader once to fix only the claims the check flagged ("reask"),
  the biggest lever for smaller models (10% to 18% in docs/AI-MODELS.md); and
  matching claims to the resume by meaning (an Ollama embedding model), for
  true claims worded differently from the resume.
- **Sources: say why no employer boards are read.** With `sources.keyless`
  narrowed to sources that are not employer-board platforms (no workday,
  greenhouse…), `jobdork sources` says "0 built-in employer boards" without
  saying that the platforms left out are the reason (seen 2026-10-26).

### Waiting on a decision

- **A key proxy, deferred** until the Discover test list shows whether
  keyless sources leave real gaps: zero-setup access to keyed sources
  (Adzuna, USAJOBS, Google Jobs resellers) through a server the project runs.
  The reasoning, its costs, and the conditions for revisiting it are in
  [DECISIONS.md](DECISIONS.md#deferred-a-key-proxy).
- **JSearch (RapidAPI) or SerpApi as an optional keyed source**: Google for Jobs data,
  which reaches Philippine posts on JobStreet and LinkedIn by legitimate
  means, with full adverts, apply links and dates. Waits on three things:
  a RapidAPI key to verify the live answer against (Adzuna's documentation
  was wrong on three fields until the first live run); how many requests
  to allow, as the free tier is 200 a month and one scan of 16 titles would
  spend most of it; and its current terms and free tier, read on RapidAPI.
  `python-jobspy` was considered and refused: it scrapes LinkedIn and Indeed
  against their terms and robots.txt.
- **Code signing.** The installers are unsigned, so macOS and Windows warn
  before the first open ([how past
  it](run/desktop.md#the-first-open-warning)). macOS: Apple's developer programme, then notarising in CI.
  Windows: SignPath Foundation's free certificate was refused (2026-10-24);
  the options left are a certificate authority's certificate or Azure
  Trusted Signing (no certificate file to keep; check whether it signs for
  an individual). Sign with a trusted timestamp (RFC 3161): `codesign
  --timestamp` on macOS (notarising requires it), signtool `/tr` or Azure
  Trusted Signing on Windows; without one, installers stop being trusted the
  day the certificate expires. When to revisit is in
  [DECISIONS.md](DECISIONS.md#a-desktop-app-a-pywebview-window-unsigned-at-first--2026-10-21).

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
