# Config reference

Every setting, what it accepts, and what happens when it is wrong.

The config is read from `config.local.yaml` if present, otherwise
`config.yaml`. Override with `-c PATH` or `JOBDORK_CONFIG`.

**The config is validated when it loads, and a bad value stops the run.** A
broken dealbreaker pattern left alone would match nothing and look like a
clean scan; a résumé path that no longer resolves would produce a document
about a career you did not have. Both fail loudly instead.

**Credentials never go in this file.** They are read from `.env`. A key found
in the YAML is used, but earns a warning, because YAML files get committed and
pasted into issues.

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
  anchor: "Chicago, IL"       # or "Makati, Philippines", "Berlin, Germany"
  radius: 25
  units: mi                   # blank picks by country
  countries: [US]
  work_modes: []
  exclude: []
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `locations.anchor` | string | `""` | `City, ST`, `City, Country`, or a bare region |
| `locations.radius` | `exact` or a number | `25` | Distance in `locations.units` |
| `locations.units` | `mi` \| `km` | by country | Blank picks miles for US/UK, km elsewhere |
| `locations.countries` | list | `[]` | Any ISO 3166-1 alpha-2 code; empty accepts everywhere |
| `locations.work_modes` | list | `[]` | Allow-list of `remote`, `hybrid`, `office` |
| `locations.exclude` | list of strings | `[]` | Region, country, city, metro name, or a substring |

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

`~` is expanded. **The path is checked on every config load**, so a résumé you
moved fails loudly rather than quietly scoring every role at zero.

`.docx`, `.md` and `.txt` are read with the standard library. `.pdf` needs the
optional `pypdf` extra (`pip install pypdf`); without it the scan still runs
and says why scoring is off. A PDF that extracts fewer than 200 characters is
refused — it is a scan or an image export, and scoring against it would rate
every role zero while looking like it worked.

The résumé is used offline, costs nothing, and **only ever adds points**. A
skill you have not listed is a gap in the résumé as often as a gap in you, and
neither is grounds for hiding a job.

Fit is scored on the *share* of the advert's named skills you have, not the
count: an advert listing three technologies you all know is a better fit than
one listing twenty where you know eight. Worth up to 25 points, and recorded
on the role as `fit: has X, Y; wants Z`.

---

## dealbreakers

```yaml
dealbreakers:
  - name: on-call rotation
    pattern: "on.?call rotation|24/7 on.?call"
    hard: false
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | string | required | Shown on the role |
| `pattern` | regex | required | Case-insensitive |
| `hard` | boolean | `true` | `true` hides, `false` warns |

Read against the **job description**, not the title. That is the part that
catches a role which looks right in a search result and is wrong in the third
paragraph.

**A pattern that does not compile stops the run.** Left alone it would match
nothing and look like a clean scan.

A soft match costs 8 points and flags the role. A role with no advert text
cannot be checked, and says so: `no advert text — dealbreakers not checked`.
Note that some sources truncate adverts — see
[PLATFORMS.md](PLATFORMS.md) — and a dealbreaker cannot find what was cut off.

---

## sources

```yaml
sources:
  keyless: [workable, greenhouse, ashby, lever, smartrecruiters, breezy]
  companies:
    - name: Stripe
      platform: greenhouse
      token: stripe
  adzuna_countries: [us]
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `sources.keyless` | list | all six | Which no-credential sources to run |
| `sources.companies` | list of objects | `[]` | Employer boards to read |
| `sources.adzuna_countries` | list | `[]` | Adzuna national indexes; empty follows `locations.countries` |

Each company needs `name`, `platform` and `token`, and the platform must be one
of the per-employer ones. **The token is the board id, not the company name** —
see [SOURCES.md](SOURCES.md#board-tokens).

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
| Résumé skill overlap | 0 to 25 |
| Soft dealbreaker | −8 each |

Nearness is worth only a few points on purpose: a role 24 miles away that fits
is worth more than one next door that does not.

---

## Statuses

```
new → interested → applied → submitted → interviewing → offer
```

plus `rejected`, `withdrawn`, `skipped`, `closed`.

**Those last four are hidden from results** rather than shown again. Use
`list --all` to see them.

**A status you set outranks a filter change.** `rescreen --remove` deletes
roles that no longer match your config, but never one you have acted on: that
status is a decision you made and a rule change does not overrule it.

---

## Environment

Read from `.env` in the project root, which is gitignored. The environment
always wins over the YAML.

| Variable | For |
|---|---|
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna |
| `USAJOBS_API_KEY`, `USAJOBS_EMAIL` | USAJOBS — the email must be the address you registered, and is sent as the User-Agent |
| `RESEND_API_KEY`, `RESEND_FROM` | Email digests from the dork generator |
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
