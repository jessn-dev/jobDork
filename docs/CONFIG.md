# Config reference

Every setting, what it accepts, and what happens when it is wrong.

The config is read from `config.local.yaml` if present, otherwise
`config.yaml`. Override with `-c PATH` or `JOBDORK_CONFIG`.

**The config is validated when it loads, and a bad value stops the run.** A
broken dealbreaker pattern left alone would match nothing and look like a
clean scan; a resume path that no longer resolves would produce a document
about a career you did not have. Both fail loudly instead.

**Credentials never go in this file.** They are read from `.env`. A key found
in the YAML is used, but earns a warning, because YAML files get committed and
pasted into issues. An AI key is stricter: `llm.key`, `llm.api_key` or
`llm.token` in the file stops the load (see [llm](#llm)).

---

## titles

```yaml
titles:
  include:
    - software engineer
    - security analyst
  exclude:
    - sales engineer
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `titles.include` | list of strings | **required** | What to search for |
| `titles.exclude` | list of strings | `[]` | Never show these |

An empty `include` is refused. Every keyword source expands one search per
entry, so with nothing here there is nothing to ask for.

### How a title is matched

Twice, strictest first.

**Pass one — whole words, contiguous, case-insensitive.** `software engineer`
matches "Senior Software Engineer" and "Software Engineer II". It does not
match "Engineering Director", because `engineer` is not `engineering`; a
partial word never matches.

**Pass two — same words, any order, up to two words between.** This is what
finds "Engineer, Software Platform" for `software engineer`, and "Head of Site
Reliability Engineering" for `head of engineering`.

**Blockers refuse pass two.** A word that changes the job rather than rewording
it, appearing between your words, blocks the match:

```
product   business   program   programme   project   sales   account
```

So `engineering manager` does not match "Engineering **Program** Manager" —
that is a different job however well the words line up. Blockers apply only to
the loose pass: if you actually want that role, list it exactly and pass one
will match it.

`exclude` is checked before either pass and wins outright.

### What a title match is worth

Pass one is worth 30 points, pass two 18. Everything else adds to that; see
[Scoring](#scoring) below.

---

## locations

```yaml
locations:
  anchor: "Naperville, IL"    # or "Makati, Philippines", "Berlin, Germany"
  radius: 25
  units: mi                   # blank picks by country
  countries: [US]
  work_modes: []
  exclude: []
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `locations.anchor` | string | `"Naperville, IL"` | `City, ST`, `City, Region, Country`, `City, Country`, or a bare region |
| `locations.radius` | `exact` or a number | `25` | Distance in `locations.units` |
| `locations.units` | `mi` \| `km` | by country | Blank picks miles for US/UK, km elsewhere |
| `locations.countries` | list | `[US]` | Any ISO 3166-1 alpha-2 code; `[]` accepts everywhere |
| `locations.work_modes` | list | `[]` | Allow-list of `remote`, `hybrid`, `office` |
| `locations.exclude` | list of strings | `[]` | Region, country, city, metro name, or a substring |

On the dashboard, **Where you are** is a picker: a country, then its first
level of region under that country's own name for it (State in the US,
Province in Canada, Region in the Philippines, Prefecture in Japan, hidden
where there is none, such as Singapore), then a city suggested from the
bundled place list as you type. It saves the anchor as `City, Region,
Country` (`Baguio, Cordillera, Philippines`; `Austin, TX, United States`), and
refuses a city that is not in the list, because an anchor that cannot be
placed turns the radius off. A region named in the anchor picks between
same-named cities in a country: `San Fernando, Ilocos` and `San Fernando,
Central Luzon` are 180 km apart. A trailing "City" is tried without it, so
`Baguio City` finds Baguio.

The defaults apply only to a key that is missing: `anchor: ""` is no anchor,
and `countries: []` keeps job posts from every country.

A numeric `radius` with no `anchor` is refused — a radius needs somewhere to
measure from. A country code the geocoder does not know is refused by name
rather than quietly matching nothing.

**There is no built-in region.** Out of scope means "not in **your**
`countries`", and the rule runs in every direction: a Berlin posting is dropped
for a Chicago reader by the same line that drops a Chicago posting for a Manila
reader. An empty `countries` accepts everywhere, which is what somebody with no
geographic constraint means by leaving it empty.

### units

`mi` or `km`. Left blank it picks miles when your countries include the US or
UK, and kilometres otherwise — so `radius: 25` means 25 km in Berlin and 25
miles in Chicago. Getting this wrong is not cosmetic: 25 miles is 2.6 times the
area of 25 km. Distances are computed in miles internally and converted back
for anything you read.

### radius

`exact` means the posting's city and state must match the anchor after
normalisation. A posting that states only a state matches an anchor in that
state, because the state is the most precise thing the employer said.

Any positive number is measured with the bundled gazetteer, in your units.
See [SOURCES.md](SOURCES.md#the-gazetteer).

**Remote roles skip the radius entirely.** Distance from your house to a job
with no office is not a number that means anything.

**A location that cannot be resolved is kept and flagged**, never dropped.
"We could not parse it" is not evidence the job is somewhere else. The role
carries `location not resolved: ...`.

### exclude

An entry is tried as a region code, then a country, then a city, then a metro
name, and finally as a substring of the raw string. So `TX` and `Texas` both
drop a role in Austin, `Bay Area` drops one in San Francisco, and an arbitrary
phrase still works. A plain substring match was too literal to be useful:
postings write "Austin, Texas" and configs write `TX`, and neither matched the
other.

**A country you did not list is dropped**, because that *is* the employer
telling you where the job is. With `countries: [US]`, "Berlin, Germany" goes
and "Atlanta, Georgia" stays; with `countries: [DE]` it is the other way
round.

### work_modes

An allow-list. Empty — the default — keeps all three.

This is the setting a `remote_ok` boolean cannot express. "I don't want to work
from home" and "I won't take anything else" are different questions;
`work_modes: [remote]` says the second.

**A posting that names no arrangement is kept whatever you set**, and flagged
`arrangement not stated`. Roughly 60% name none, and reading "we cannot tell"
as "not remote" hides more real remote roles than it removes office ones.
`unstated` is refused as a value for the same reason: it is not a working
arrangement anybody chooses.

Where the arrangement comes from, in order:

1. The platform's own field, when it has one. Workable and Ashby state it on
   every posting.
2. The advert text otherwise — `hybrid` wins over `remote` wins over `office`.
3. Nothing, in which case it is unstated.

`Remote — must live within 50 miles of our Chicago office` reads as remote to
any keyword check and is not remote. It is detected and recorded as hybrid,
flagged `says remote but requires living near an office`.

---

## salary

```yaml
salary:
  floor: 120000
  currency: USD
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `salary.floor` | number or `null` | `null` | Annual minimum |
| `salary.currency` | ISO 4217 code | `USD` | Your floor's currency; 45 are accepted |

### The rule

- A posting whose **stated** pay is below the floor is **hidden**.
- A posting with **no stated pay** is **shown**, marked `unconfirmed salary`.

**Only a number the employer published can disqualify a role.** About 12% of
postings state one. A floor that also hid the silent ones would throw away most
of the market.

Day, hourly, weekly and monthly rates are annualised before the comparison —
$600 a day is $156,000 a year, not $600. Annualisation uses 2,080 hours, 260
days, 52 weeks or 12 months. A pay period that cannot be read is treated as
unknown and the salary is recorded as unstated, rather than assumed yearly.

**A salary in another currency is never converted.** It is shown and marked
`not compared`. A wrong exchange rate drops real jobs quietly.

**Predicted salaries are discarded, not stored.** Some sources estimate pay
where the employer published none. An estimate must never be allowed to
disqualify a job, so it is dropped and the role reads `unconfirmed`.

---

## resume

```yaml
resume:
  path: ~/Documents/cv.pdf
```

| Key | Type | Default |
|---|---|---|
| `resume.path` | path | `""` |

`~` is expanded. **The path is checked on every config load**, so a resume you
moved fails loudly rather than quietly scoring every role at zero.

`.docx`, `.md` and `.txt` are read with the standard library. `.pdf` needs the
optional `pypdf` extra (`pip install pypdf`); without it the scan still runs
and says why scoring is off. A PDF that extracts fewer than 200 characters is
refused — it is a scan or an image export, and scoring against it would rate
every role zero while looking like it worked.

The resume is used offline, costs nothing, and **only ever adds points**. A
skill you have not listed is a gap in the resume as often as a gap in you, and
neither is grounds for hiding a job.

Fit is scored on the *share* of the advert's named skills you have, not the
count: an advert listing three technologies you all know is a better fit than
one listing twenty where you know eight. Worth up to 25 points, and recorded
on the role as `fit: has X, Y; wants Z`.

---

## dealbreakers

```yaml
dealbreakers:
  - security clearance              # a phrase is the whole dealbreaker
  - us citizen
  - name: Client travel
    words: [client-site travel, extensive travel]
    hard: false
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| (a phrase) | string | | The words to look for; named and weighted as the list of common ones has it |
| `name` | string | the first word | Shown on the role |
| `words` | list, or text with commas | | Phrases to look for, in plain words |
| `pattern` | regex | | Advanced: a regular expression instead of words |
| `hard` | boolean | `true` | `true` hides, `false` warns |

Read against the **job description**, not the title. That is the part that
catches a role which looks right in a search result and is wrong in the third
paragraph.

**Words are matched the way adverts write them.** Capitals never matter;
words may be joined by a space, a hyphen or nothing ("client-site travel",
"client site travel"); a short word in capitals may have dots ("US" finds
"U.S."); the last word may end in s, es, ed, ing or ship ("us citizen" finds
"U.S. citizenship"); and only whole words match ("us" never matches inside
"focus").

**Common dealbreakers come with their other wordings.** Type one of these
and the usual ways adverts phrase it are looked for too:

| Dealbreaker | Also finds | Effect |
|---|---|---|
| security clearance | TS/SCI, top secret, polygraph, secret clearance, public trust | hides |
| us citizen | U.S. citizenship, United States citizen, must be a citizen | hides |
| no visa sponsorship | unable to sponsor, cannot sponsor, without sponsorship | hides |
| relocation required | must relocate, required to relocate | hides |
| client-site travel | travel to client sites, client site, at client locations | 8 points |
| heavy travel | extensive travel, frequent travel, travel up to 30 to 100% | 8 points |
| on-call | on call rotation, 24/7 support, pager duty | 8 points |
| night shift | overnight shift, graveyard shift, third shift | 8 points |
| weekend work | weekends required, weekend shifts | 8 points |
| fully on-site | 100% on site, five days in office | 8 points |
| drug test | drug screen, drug-free workplace | 8 points |
| driver's license | drivers license, CDL | 8 points |
| heavy lifting | lift up to 40 lbs or more | 8 points |
| contract or agency | C2C, corp to corp, staffing agency, 1099 | 8 points |
| commission only | 100% commission, quota | 8 points |
| unpaid take-home | take-home test or project, unpaid trial | 8 points |
| bilingual required | must be bilingual | 8 points |

The full list is `CATALOG` in `jobdork/search/dealbreakers.py`. A phrase not
in it is matched as written.

**A negation is not a match.** "No security clearance required" and "you do
not need to be a US citizen" are the opposite of the dealbreaker, so a match
with no, not, without or never in the few words before it, in the same
sentence, is skipped. A dealbreaker that is itself a negation ("no visa
sponsorship") counts its matches as they are.

**A pattern that does not compile stops the run**, and so does a dealbreaker
with nothing to look for. Left alone either would match nothing and look like
a clean scan.

A soft match costs 8 points and flags the role. A role with no advert text
cannot be checked, and says so: `no advert text — dealbreakers not checked`.
Note that some sources truncate adverts — see
[PLATFORMS.md](PLATFORMS.md) — and a dealbreaker cannot find what was cut off.

On the dashboard they are on the Search page: a table you remove rows from,
a box to type the words in, the common ones as one-click buttons, and a box
that tries the words against a sentence you paste. Regular expressions are
under Advanced.

### Advanced: writing a pattern

For anything plain words cannot say. A pattern is a Python regular
expression, taken as written (a "no" before a match does not cancel it),
matched anywhere in the advert with capitals ignored. Plain words are a pattern already: `polygraph` finds
"Polygraph" in any sentence. A few symbols cover almost every dealbreaker:

| Write | Means | Example | Finds | Does not find |
|---|---|---|---|---|
| `\|` | Or | `TS/SCI\|top secret` | "TS/SCI", "Top Secret" | "Secret Santa" |
| `.` | Any one character | `on.call` | "on-call", "on call" | "oncall" |
| `?` | The thing before it is optional | `on.?call` | "on-call", "on call", "oncall" | "on the call" |
| `\b` | Edge of a word | `\bC2C\b` | "C2C only" | "B2C2C" |
| `\d` | Any digit | `\d\d%` | "50%" | "5%" |
| `{2}` | Exactly that many of the thing before | `\d{2}%` | "25%" | "5%" |
| `(?:a\|b)` | A group, to put an "or" inside words | `unpaid (?:trial\|project)` | "unpaid trial", "unpaid project" | "unpaid leave" |
| `\s?` | An optional space | `\d{2}\s?%` | "25%", "25 %" | |

To match one of `. ? | ( ) [ ] { } + * ^ $ \` itself, put a backslash before
it: `C\+\+` finds "C++". In YAML, wrap a pattern in double quotes and double
every backslash (`"\\bC2C\\b"`), or use single quotes and write it as is
(`'\bC2C\b'`).

Samples, the same ones the dashboard offers:

```yaml
dealbreakers:
  - name: Security clearance
    pattern: 'security clearance|TS/SCI|top secret|polygraph'
    hard: true
  - name: Relocation required
    pattern: 'must relocate|relocation (?:is )?required'
    hard: true
  - name: Heavy travel
    pattern: 'travel up to \d{2}\s?%|(?:extensive|frequent) travel'
    hard: false
  - name: On-call
    pattern: 'on.?call|24/7 support|pager ?duty'
    hard: false
  - name: Contract or agency
    pattern: '\bC2C\b|corp.?to.?corp|staffing (?:agency|firm)'
    hard: false
  - name: Unpaid take-home
    pattern: 'take.?home (?:test|project|assignment)|unpaid (?:trial|project)'
    hard: false
  - name: Sales quota
    pattern: '\bquota\b|commission.?only'
    hard: false
```

To learn more, Python's own
[Regular Expression HOWTO](https://docs.python.org/3/howto/regex.html) is a
gentle introduction, and the
[syntax reference](https://docs.python.org/3/library/re.html#regular-expression-syntax)
lists everything. [regex101](https://regex101.com/?flavor=python&flags=i)
tests a pattern against a whole advert and explains each part; choose the
Python flavour, which is what a scan uses.

---

## sources

```yaml
sources:
  keyless: [workable, greenhouse, ashby, lever, smartrecruiters, breezy, kalibrr, himalayas, workday, oracle, eightfold, taleo, site]
  companies:
    - name: Stripe
      platform: greenhouse
      token: stripe
  directory:
    enabled: true
    countries: []        # empty: follow locations.countries
    industries: []       # empty: every industry
  adzuna_countries: [us]
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `sources.keyless` | list | all thirteen | Which no-credential sources to run. A config that lists them keeps its own list: add `kalibrr`, `himalayas`, `workday`, `oracle`, `eightfold`, `taleo` and `site` to it by hand |
| `sources.companies` | list of objects | `[]` | Employer boards to read |
| `sources.directory.enabled` | bool | `true` | Read the employer boards jobdork ships with. `directory: false` also switches them off |
| `sources.directory.countries` | list | `[]` | Only boards hiring in these countries; empty follows `locations.countries` |
| `sources.directory.industries` | list | `[]` | Only these industries (`healthcare`, `banking`, `retail`…); empty is all |
| `sources.adzuna_countries` | list | `[]` | Adzuna national indexes; empty follows `locations.countries` |

Each company needs `name`, `platform` and `token`, and the platform must be one
of the per-employer ones. **The token is the board id, not the company name** —
see [SOURCES.md](SOURCES.md#board-tokens).

The directory is a list of employer boards that ships with jobdork, in
`jobdork/data/boards.csv`, every one found by `discover` on the employer's own
site and verified with jobs. A board you also list in `companies` is read
once. Only boards on a platform in `keyless` are read, and each costs
requests: `jobdork sources` says how many your config reads. See
[SOURCES.md](SOURCES.md#employer-boards-jobdork-ships-with).

Leave `adzuna_countries` empty and it follows `locations.countries`, so a
Berlin reader gets the `de` index without needing to know Adzuna calls it that.
Adzuna serves `gb us ca ie in de fr nl at be ch es it pl br mx za`, and `au nz
sg` exist but currently answer 503. Naming a country it has no index for — the
Philippines, for one — is reported rather than silently ignored. Each extra
country is a full extra set of calls against a monthly quota.

USAJOBS skips itself entirely when `US` is not in `locations.countries`.

Keyed sources are registered whether or not you have credentials. Without them
they report why they skipped, rather than silently not running — a source that
disappears looks exactly like a source that found nothing.

---

## output

| Key | Type | Default | Meaning |
|---|---|---|---|
| `output.dir` | path | `out` | Where files are written |
| `output.formats` | list | `[html, json]` | `html`, `json`, `md`, `csv` |

| Format | File | What it is |
|---|---|---|
| `html` | `out/index.html` | Self-contained page. No server, no external request, light and dark |
| `json` | `out/roles.json` | Full rows, minus the advert body |
| `md` | `out/roles.md` | The same list as text, for pasting into a note or an email |
| `csv` | `out/roles.csv` | One row per role, 18 stable columns, for a spreadsheet or a script |

`markdown` is accepted as a spelling of `md` and normalised at load, so the two
cannot reach the writer as different strings.

The CSV leaves out the advert deliberately — a 5,000-character description in a
cell breaks every viewer that opens it, and `jobdork show` is where the advert
belongs. `salary_stated` is its own column because a blank pay range means
nobody published one, which is not a zero.

Every accepted format has a writer, and a test asserts it: a format that
validates and then writes nothing is exactly the silent failure the rest of
this file exists to prevent.

---

## fetch

| Key | Type | Default | Meaning |
|---|---|---|---|
| `fetch.concurrency` | int | `8` | Boards read at once, capped at 64 |
| `fetch.timeout` | int | `20` | Seconds |
| `fetch.retries` | int | `2` | Per request |
| `fetch.user_agent` | string | identifies the tool | Sent on every request |

**Concurrency governs breadth, not intensity.** How hard any one host is hit is
set per host and is not configurable — see
[PLATFORMS.md](PLATFORMS.md#pacing). Raising this reads more different boards
at once; it does not make any single board answer faster.

---

## freshness

How a job post's age counts. Measured in code from the job board's own dates,
never by a model.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `freshness.new_days` | int | `2` | Up to this: brand new, top of the pile |
| `freshness.week_days` | int | `7` | Up to this: first week |
| `freshness.older_days` | int | `21` | Up to this: older, risky; beyond it, stale |
| `freshness.ghost_days` | int | `90` | Beyond this: a ghost listing, dropped. `0` never drops for age |
| `freshness.points` | map | `{new: 5, older: -5, stale: -15}` | Score points per tier |

**Only a ghost is dropped.** A stale post may be filled or reposted by a
script, but the job you want most may still be worth a try, so it is marked
and ranked lower. A post you have applied to is never hidden for its age.

**Where the date comes from:** the board's posting date; failing that, the
posting page (`datePosted`, or "Posted 3 weeks ago", read by `enrich`);
failing that, the day jobdork first saw the post, once that is more than a
week ago, as a lower bound. None of those: "posting date not stated", kept.

**Reposts** are dated from the first sighting. A job jobdork saw on 1 July,
under this URL or another copy of it, that the board now dates 29 September
was reposted, and is as old as 1 July says.

Adzuna is asked for nothing older than `ghost_days`. USAJOBS can only be
asked for up to 60 days, so with a longer limit screening does it.

---

## llm

The AI reader. Off unless `provider` is set. The dashboard's AI page writes
this section for you.

**What a hosted model is sent.** Claude, Gemini and ChatGPT get every prompt
with email addresses, phone numbers and LinkedIn, GitHub and GitLab profile
links removed (`llm.redact`). Year ranges, figures and standards such as
"NIST 800-53" are left alone. A local Ollama model gets the text as it is,
because nothing leaves the machine. A street address is not removed; leave
it off a resume you use with a hosted model if that matters to you.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `llm.provider` | string | empty (off) | `ollama`, `anthropic` (Claude), `gemini` or `openai` (ChatGPT) |
| `llm.model` | string | empty | The model's name, e.g. `gemma4:26b`; the AI page lists what is available |
| `llm.ollama_url` | URL | `http://localhost:11434` | Where Ollama answers. Must be `http(s)://host:port` |
| `llm.judge_on_scan` | bool | `false` | After each scan, judge the best job posts not yet judged |
| `llm.judge_top` | int | `25` | How many a judging run reads, 1 to 500. Bounds what a scan can spend on a paid API |
| `llm.read_pages` | bool | `false` | When checking postings, ask the model about pages that do not say whether the job is open |
| `llm.guard` | bool | `true` | Check each verdict and draft for claims the resume and the advert do not support. Two more model calls per output |

**Keys are never read from this file.** `llm.key`, `llm.api_key` or
`llm.token` stops the load with an error rather than a warning. Type a key on
the AI page, where it is held in memory only and wiped when the server stops,
or set it in the environment for the terminal (see [Environment](#environment)).
Ollama needs no key.

**Judging needs a resume and at least 200 characters of advert.** A post with
less is skipped and counted, not guessed at. The verdict is shown beside the
rule-based score and never replaces it.

**With `guard` off**, verdicts and drafts are still recorded, unchecked; the
Dashboard's hallucination coverage says how many that is.

---

## db

| Key | Type | Default |
|---|---|---|
| `db` | path | `data/jobdork.db` |

Gitignored. Your history stays yours.

---

## Scoring

Points, so you can tell why one role is above another.

| Signal | Points |
|---|---|
| Title, exact match | 30 |
| Title, loose match | 18 |
| Work mode stated and wanted | 10 |
| Remote role | 20 |
| Exact-radius location match | 25 |
| Within radius | 5 to 30, nearer is higher |
| Salary stated, no floor set | 5 |
| Salary above floor | 10 to 20, by headroom |
| Resume skill overlap | 0 to 25 |
| Soft dealbreaker | −8 each |
| Posted in the last 2 days | +5 |
| Posted 8 to 21 days ago | −5 |
| Posted more than 21 days ago | −15 |

Nearness is worth only a few points on purpose: a role 24 miles away that fits
is worth more than one next door that does not.

---

## Statuses

```
new → viewed → interested → applied → submitted → interviewing → offer
```

plus `rejected`, `withdrawn`, `skipped`, `closed`. `viewed` is set for you when
you open a post on the dashboard.

**Those last four are hidden from results** rather than shown again. Use
`list --all` to see them.

**A status you set outranks a filter change.** `rescreen --remove` deletes
roles that no longer match your config, but never one you have acted on: that
status is a decision you made and a rule change does not overrule it.

**A status belongs to the job, not the link.** Copies of one job posted in
several places share it, and `check` closes the job only when every copy is
gone.

**`prune` never deletes a job you are pursuing:** applied, submitted,
interviewing and offer are kept whatever their age.

---

## Environment

Read from `.env` in the project root, which is gitignored. The environment
always wins over the YAML.

| Variable | For |
|---|---|
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna |
| `USAJOBS_API_KEY`, `USAJOBS_EMAIL` | USAJOBS — the email must be the address you registered, and is sent as the User-Agent |
| `RESEND_API_KEY`, `RESEND_FROM` | Email: `scan --email`, `digest`, and the dork generator |
| `ANTHROPIC_API_KEY` | Claude, from the terminal (the dashboard takes keys on its AI page) |
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Gemini, from the terminal |
| `OPENAI_API_KEY` | ChatGPT, from the terminal |
| `JOBDORK_CONFIG` | Config path override |

---

## Minimal working config

```yaml
titles:
  include: [software engineer]
locations:
  anchor: "Chicago, IL"
```

Everything else has a default.
