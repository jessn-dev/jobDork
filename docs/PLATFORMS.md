# Platforms

What each source actually returns, and what breaks on it.

Every adapter here was probed against the live API before it was written.
Where a published behaviour turned out to be wrong, the run is recorded and
the documentation is not.

---

## Summary

| Platform | Endpoint | Credential | Advert | Salary | Arrangement | Status |
|---|---|---|---|---|---|---|
| [Workable search](#workable-search) | `jobs.workable.com/api/v1/jobs` | none | **full, inline** | **none — no field** | **always stated** | verified |
| [Greenhouse](#greenhouse) | `boards-api.greenhouse.io/v1/boards/{token}/jobs` | none | full | rare | from advert | verified |
| [Ashby](#ashby) | `api.ashbyhq.com/posting-api/job-board/{name}` | none | full | structured | stated | verified |
| [Lever](#lever) | `api.lever.co/v0/postings/{token}` | none | full | rare | stated | verified |
| [Breezy](#breezy) | `{company}.breezy.hr/json` | none | summary | field present | unreliable | partial |
| [SmartRecruiters](#smartrecruiters) | `api.smartrecruiters.com/v1/companies/{token}/postings` | none | detail endpoint | — | stated | verified |
| [Adzuna](#adzuna) | `api.adzuna.com/v1/api/jobs/{cc}/search/{page}` | free key | **500 chars, capped** | 30%, mostly predicted | rarely | verified |
| [USAJOBS](#usajobs) | `data.usajobs.gov/api/search` | free key | full | **100%** | rarely | verified |

---

## Failure usually looks like success

The single most important thing about these APIs.

**Several answer HTTP 200 with an empty array both for a board that does not
exist and for one that is rate-limiting you.** Ashby and SmartRecruiters both
do this. So validation is on job count, never on the status code, and an empty
answer from an employer board is reported as `SUSPECT — answered empty where it
usually does not` rather than as "this company is not hiring". Those are three
different statements and only one of them is honest.

**USAJOBS ignores an unknown parameter silently, with HTTP 200.** A search
carrying `NotARealParam` returned the same 501 results as one without it. A
misspelled filter there does not fail — it just does not filter, and the wide
result set looks like a successful search. Every parameter name used against
USAJOBS has been exercised live for that reason.

**Greenhouse answers 403 to a GET carrying a body.** The HTTP layer only ever
attaches a body to a POST.

---

## Workable search

```
GET https://jobs.workable.com/api/v1/jobs?query={title}&location={place}
```

No key, no token, no account. The widest source available without a
credential, and the only one that reaches employers nobody has added by hand.

**The advert comes back in the search response.** There is no enrich step for
Workable, which saves one request per role and is unusual enough to be worth
stating.

| Parameter | Behaviour |
|---|---|
| `query` | The job title |
| `location` | **Exactly one value.** Repeating the parameter answers **400** |
| `workplace` | `remote` \| `hybrid` \| `on_site`, filters server-side |
| `pageToken` | Opaque, pages cleanly with no overlap, 20 per page |

`location` accepts a city (`Austin, Texas`), a state (`Texas`) or a country
(`United States`) — **spelled out**. Two-letter codes are ignored *silently*,
which is worse than an error: `TX` returns the whole world and looks like it
worked.

**There is no salary field at all.** Not empty — absent from the schema. Every
Workable role is `unconfirmed salary`, and no floor can ever disqualify one.

`workplace` is set on every posting, so the arrangement is read from the field
rather than hunted for in prose that mentions "our remote team" in a paragraph
about culture. A remote posting frequently carries `location: null`; that is
the employer saying the job has no address, not a field to repair.

Workable has no radius parameter. A radius search asks for the whole state and
measures locally.

### Rate limiting

**Paced at 0.4 requests/second, with a 6-page cap per search.**

This host is stricter than its per-board sibling. A 16-title config at 0.7/s
collected 15 consecutive 429s, tripped the circuit breaker, and then earned a
`Retry-After` of **86,130 seconds — a 24-hour refusal**.

A search runs once per title per place plus a remote pass, so titles multiply
requests fast. Use `scan --limit` while tuning a config rather than re-running
full scans.

---

## Greenhouse

```
GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs
    ?content=true&pay_transparency=true
```

One employer per board token.

`content=true` is required or the response is a list of titles with no advert
to read a dealbreaker against.

**The advert arrives HTML-escaped** — `&lt;h2&gt;`, not `<h2>`. A tag stripper
run against it matches nothing and returns the entities verbatim, so every
dealbreaker silently stops matching. It is unescaped before it is stripped.

`pay_transparency=true` returns `pay_input_ranges`, which was empty on every
role of a large sample board. Salary from here is the exception.

`absolute_url` is frequently the employer's own domain with the job id in the
query string — `stripe.com/jobs/search?gh_jid=7532733`. **`gh_jid` identifies
the posting and must not be stripped as tracking**; doing so collapses an
entire board to a single id.

Greenhouse migrated from `boards.greenhouse.io` to `job-boards.greenhouse.io`.
Both still serve.

Paced at 5/s.

---

## Ashby

```
GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true
```

**`isRemote` is a decoy.** A board returned `isRemote: true` on a role whose
`workplaceType` was `Hybrid`. `workplaceType` is authoritative — `Remote`,
`Hybrid`, `Onsite` — and `isRemote` is read only when it is missing.

Compensation is the best-structured of any source here:
`compensation.compensationTiers[].components[]` carries `compensationType:
"Salary"`, an `interval` like `"1 YEAR"`, a `currencyCode` and min/max values.

`location` is a display string that may carry decoration — `"New York, NY
(HQ)"`. `address.postalAddress` is the structured fallback.

Answers 200 with an empty array when throttled. Paced at 5/s.

---

## Lever

```
GET https://api.lever.co/v0/postings/{token}?mode=json
GET https://api.eu.lever.co/v0/postings/{token}?mode=json
```

**Two separate deployments.** A token that exists on one 404s on the other. A
North American search reads the US host and falls back to the EU host, so a
company that moved does not read as a dead board.

The response is a **bare top-level list**, not an object with a `jobs` key.

The title lives in `text`. Location is in `categories.location`, with every
location in `categories.allLocations`. The advert is split across
`descriptionPlain`, `descriptionBodyPlain` and `additionalPlain`, any of which
may be absent; all three are joined.

`createdAt` is milliseconds since the epoch.

Tokens are case-sensitive. Paced at 3/s.

---

## Breezy

```
GET https://{company}.breezy.hr/json
```

Bare list. Title is in `name`.

**`location.is_remote` is not what it sounds like** — it is set on hybrid roles
as well as remote ones. Reading it as remote would tell you a hybrid role has
no office, which is the kind of wrong that wastes an application. It is treated
as remote only when there is also no city.

Countries arrive as ISO alpha-2 in `location.country.id` and the state as a
code in `location.state.id`, so the location string is assembled rather than
taken from one field.

The index carries no advert body; the posting page does. Paced at 3/s.

---

## SmartRecruiters

```
GET https://api.smartrecruiters.com/v1/companies/{token}/postings
```

**Verified, eventually.** Ten well-known company names in a row returned
`totalFound: 0`. On this platform that is also what a throttle and a
non-existent board look like, so an empty answer proves nothing either way —
which is the single most important thing to know about it.

What live rows corrected:

- **`location.fullLocation`** is "Mumbai, MH, India", already assembled.
  Building from `city, region, country` gives "Mumbai, MH, **in**" — the
  country is a lowercase code — and that does not geocode.
- **`location.hybrid`** exists beside `location.remote`. Reading only `remote`
  files every hybrid role as arrangement-not-stated.
- **`ref` is the API's own detail URL.** Storing it as the role's link hands
  you JSON when you click through; the human page is
  `jobs.smartrecruiters.com/{token}/{id}`.

**The advert is not in the index and not on the posting page either** — that
page carries no schema.org data. It lives on the detail endpoint, split across
`jobAd.sections`: `jobDescription`, `qualifications`, `additionalInformation`
and `companyDescription`. `jobdork enrich` joins all four.

Paced at 8/s.

---

## Adzuna

```
GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
```

Free key from `developer.adzuna.com`. The only source that watches more than
one country from the same config — the country is two letters in the URL path.

Probed live. **Serving:** `gb us ca ie in de fr nl at be ch es it pl br mx za`.
**Previously 503, live again since 2026-08-29:** `au nz sg`.
**Answering 404:** `ph id my jp ae ru` — no index exists at all.

`sources.adzuna_countries` left empty follows `locations.countries`, so a
Berlin reader gets `de` without knowing the code. A country with no index is
reported by name rather than silently skipped.

**Getting the key:** the portal's own *API Access Details* sidebar link is
broken; it points at `/admin/access_details`, which 404s. The working page is
`/admin/applications`, which is linked from nowhere. Create an application
there and the `app_id`/`app_key` pair is issued.

| Parameter | Note |
|---|---|
| `title_only` | **Use this, not `what`.** `what` searches the advert body, so "engineering manager" returns every engineer whose advert mentions their manager, and you pay a call per page of it |
| `where` | City and state, spelled out |
| `distance` | **Kilometres.** Your radius is normalised to miles internally and converted here; sending 25 where 40 was meant shrinks the search to a third of its area |
| `results_per_page` | 50 maximum |

### The 500-character cap

**Every advert is truncated to exactly 500 characters.** Measured across 653
roles: average 500.0, maximum 500.

This is the most consequential limitation in the whole tool. Dealbreakers read
the advert body. Work-mode detection reads the advert body. Résumé fit scoring
reads the advert body. On the same run, **517 of 653 Adzuna roles had no
detectable arrangement, against 0 of 200 on Workable.**

Adzuna is a discovery-and-salary source. It is not one you can screen on.

### Predicted salary

`salary_is_predicted` is the **string `"1"`**, not an integer and not a
boolean. A predicted figure always has `salary_min == salary_max`.

**Predicted figures are discarded rather than stored**, and the role reads
`unconfirmed`, flagged `adzuna predicted salary ignored`. A guess must never be
allowed to disqualify a job. 251 of 292 roles in one run were predicted.

### Location

**Use `location.area`, not `location.display_name`.** `display_name` is city
plus *county* — "Round Rock, Williamson County" — which no gazetteer can
place. `area` is structured:

```json
"area": ["US", "Texas", "Travis County", "Austin"]
```

Country, state, county, city. Parsing `display_name` instead left 187 of 238
roles unplaced with the radius quietly doing nothing.

### Duplicates

Adzuna aggregates, so one vacancy arrives under six or seven distinct posting
ids. Each is a legitimately different uid and cannot be merged at store time
without risking the loss of the only copy. `list` collapses repeats of the same
employer and title on the way out; `list --duplicates` shows them all.

### Quota

25 calls/minute, 250/day, 1,000/week, **2,500/month**. One scan is one call per
title per page, so a 7-title config runs about 21 calls and the monthly cap
works out at roughly four scans a day. A second country doubles it. Paced at
1/s.

---

## USAJOBS

```
GET https://data.usajobs.gov/api/search
```

US federal only. Free instant key from `developer.usajobs.gov`. The adapter
skips itself when `US` is not in `locations.countries`.

Requires three headers: `Host`, `Authorization-Key`, and **`User-Agent` set to
the email address you registered with**. It refuses the request otherwise.

| Parameter | Note |
|---|---|
| `PositionTitle` | The title search |
| `LocationName` | `City, State` spelled out |
| `Radius` | **Miles.** Verified: Austin at 25 returned 23 postings, at 200 returned 52 |
| `ResultsPerPage` | Up to 500 |

**Unknown parameters are ignored silently with HTTP 200.** See
[above](#failure-usually-looks-like-success).

### Pay periods

`RateIntervalCode` is a two-letter code, not a word — `PA` for per annum, `PH`
per hour, `PD` per day, `PW` per week, `PM` per month, `BW` biweekly, `WC`
without compensation.

**An unrecognised code must not default to yearly.** Doing so turns $50 an hour
into $50 a year and lets any salary floor hide the job. An unknown code is
refused and the salary recorded as unstated.

### Multiple locations

A federal posting is routinely open in 20 or more cities at once. Taking
`PositionLocation[0]` displayed an Austin-matching role as "Salt Lake City" and
failed a radius it was never outside.

USAJOBS carries `Latitude` and `Longitude` on every location, so the nearest to
your anchor is chosen directly and the gazetteer is not needed. The role is
flagged `open in N locations; nearest shown`.

### Vocabulary

**Federal hiring uses different job titles.** `software engineer` barely exists
there. On one run:

| Titles | Fetched | Kept |
|---|---|---|
| `software engineer, backend engineer, platform engineer` | 23 | **0** |
| `IT specialist, computer engineer, computer scientist, software developer` | 101 | **17** |

Every one of those 17 stated pay. This is the only source where a salary floor
does most of its work.

`JobSummary` is truncated to about 500 characters, so all prose fields are
concatenated before a dealbreaker reads them.

Paced at 3/s.

---

## Pacing

Concurrency governs how many **different** boards are read at once. It is not
how hard any one host is hit: each host has its own clock, and requests to
different hosts are interleaved so a long run of one platform does not park the
pool on a single host.

| Host | Requests/sec |
|---|---|
| `api.smartrecruiters.com` | 8.0 |
| `boards-api.greenhouse.io`, `api.ashbyhq.com` | 5.0 |
| `api.lever.co`, `data.usajobs.gov`, default | 3.0 |
| `api.adzuna.com` | 1.0 (quota, not politeness) |
| `apply.workable.com` | 0.7 |
| `jobs.workable.com` | 0.4 |

### The circuit breaker

A host answering three consecutive 429s, having used its retries, is treated as
saying no rather than asking for a pause: **blocked outright for five minutes
rather than retried into.**

A `Retry-After` under a minute is honoured as a pause. **Over a minute it is
read as a refusal** for the rest of the run.

These are other people's servers, and a job board that starts blocking
automated readers makes the market worse for everyone. The user agent
identifies the tool.

---

## Not supported

No usable public API exists for these; they remain reachable only through
`jobdork dork`:

**Indeed** (publisher API retired 2020) · **Glassdoor** (partner-only) ·
**LinkedIn** (the public guest endpoint carries no description and no salary,
and is disallowed by its robots.txt) · **Dice** · **BuiltIn** ·
**ZipRecruiter** · **Monster** · **CareerBuilder** · **SimplyHired** ·
**FlexJobs** · **Wellfound** · **Y Combinator**

Adding a board to dork mode is one line. An API adapter is roughly a hundred
plus its quirks — which is most of this document.

---

## Not yet implemented

**`enrich`.** Breezy and SmartRecruiters return a summary index; their full
adverts need a second request per role.

**`discover`.** Board tokens are supplied by hand. See
[SOURCES.md](SOURCES.md#board-tokens).
