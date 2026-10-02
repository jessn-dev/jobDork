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
| [Kalibrr](#kalibrr) | `www.kalibrr.com/kjs/job_board/search` | none | full, inline | when shown | stated | verified |
| [Workday](#workday) | `{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | none | detail endpoint | — | rarely | verified |
| [Himalayas](#himalayas) | `himalayas.app/jobs/api/search` | none | full, inline | with a currency | **always remote** | verified |
| [Oracle Recruiting Cloud](#oracle-recruiting-cloud) | `{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions` | none | detail endpoint | — | rarely | verified |
| [Eightfold](#eightfold) | `{host}/api/pcsx/search` | none | detail endpoint | — | stated | verified |
| [Taleo Business Edition](#taleo-business-edition) | `{host}/{path}/ats/careers/v2/searchResults` | none | on the job's page | when stated | when stated | verified |
| [Employer site](#employer-site) | its sitemap, then each posting page | none | full, on the page | when stated | when stated | verified |

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

**Two separate deployments.** A token that exists on one 404s on the other. The
adapter reads the US host and falls back to the EU host, so a company whose
board lives in Europe does not read as a dead board.

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
the advert body. Work-mode detection reads the advert body. Resume fit scoring
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
without risking the loss of the only copy. They are grouped instead, by
employer, title and place: one post on screen, one status for all copies
(see [ARCHITECTURE.md](ARCHITECTURE.md#deduplication-in-two-places));
`list --duplicates` shows them all.

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

## Kalibrr

    GET https://www.kalibrr.com/kjs/job_board/search?text=...&country=Indonesia&limit=50&offset=0

The search Kalibrr's own site reads. Philippine and Indonesian jobs, many of
them from employers whose careers page Kalibrr hosts, so it reaches
Philippine employers that run no Greenhouse or Lever board. `robots.txt`
closes only `/root` and `/candidate/profile`. Skipped when
`locations.countries` names neither PH nor ID.

- **Dates are the best of any source:** `activation_date` (posted),
  `application_end_date` (applications close; a post past it is not
  returned) and `es_recruiter_last_seen`. A recruiter not seen in 30 days is
  flagged: applications may not be read.
- `text` matches loosely: "software engineer" put a marketing internship
  first. Screening's title match does the real filtering (231 of 240 in the
  first live run).
- **Ask for the country by name.** Without `country`, the search answers with
  Philippine jobs only: an Indonesian search found 2 jobs for three titles
  where `country=Indonesia` finds 380. Each country you want is searched
  separately (`country=Philippines`, `country=Indonesia`); a two-letter code
  is ignored. The radius is measured locally, from each job's address.
- Pay counts only when `salary_shown` is true.
- `is_work_from_home` / `is_hybrid` give the arrangement; both false is left
  unstated.
- **Job pages answer 403 to scripts.** The link works in a browser. The
  "still open" check goes by the closing date, then by whether the post was
  in the latest search, as for Adzuna; `enrich` skips it (the search already
  carries the whole advert).

---

## Workday

    POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    GET  https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/...

Most large employers hire through Workday. The JSON is what the careers
site's own pages read; robots.txt allows the public site path. The token is
three parts, `tenant/dc/site` (`nvidia/wd5/NVIDIAExternalCareerSite`), read
off the employer's careers page by `discover`.

- **Your countries are asked of the board.** Its country filter has a name
  each employer picks (NVIDIA: `locationHierarchy1`) and is recognised by its
  values being country names. One empty search per board reads it; a board
  with none of your countries is skipped after that one request ("NVIDIA
  lists no jobs in PH"). With no such filter, a listing whose location names
  another country is skipped before its detail is fetched.
- **A detail is one request per job**, so only titles your title rules keep
  are fetched in full. NVIDIA for two titles, worldwide: 145 requests and
  2½ minutes; for India alone, 71.
- The list states `total` on its first page only.
- `startDate` is the posting date; a relative "Posted 30+ Days Ago" when it
  is missing.
- **Still open:** the detail answers 404 for a removed posting and
  `posted: false` for one taken down; the page itself is a script and says
  nothing.
- Paced at one request a second for every `*.myworkdayjobs.com` host.

---

## Himalayas

    GET https://himalayas.app/jobs/api/search?q=...&country=PH&sort=recent&page=1

Remote jobs worldwide, about 93,000. No key; robots.txt allows the API. Their
terms ask that a job links back to Himalayas and names it as the source: the
stored link is the Himalayas page, and the source shows as Himalayas.

- **`country`** returns jobs open to that country, including worldwide ones.
  Most "remote" jobs from US employers are remote within the US; asking by
  country is what keeps those out. One search per title per country.
- **Working hours:** `timezoneRestrictions` lists the UTC offsets a job
  accepts. One more than an hour from yours is left out. Your offset comes
  from the anchor's longitude (Baguio, 120.6° east: UTC+8); with no anchor,
  hours are not checked.
- 20 jobs a request at most, three pages a title, newest first.
- `pubDate` / `expiryDate` are Unix seconds. Past expiry, a post is not
  returned, and a stored one is closed by the "still open" check.
- Pay counts when it comes with a currency.
- **Job pages answer 403 to scripts** although robots.txt allows them.
  "Still open" goes by the expiry, then by the latest search; `enrich` skips it.
- Skipped when `locations.work_modes` leaves out remote.

---

## Oracle Recruiting Cloud

    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true&finder=findReqs;siteNumber={site},keyword="…",limit=25,offset=…
    GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails
        ?onlyData=true&expand=all&finder=ById;Id="{id}",siteNumber={site}

JPMorgan Chase, Kroger, Hilton, Marriott and Mayo Clinic hire through it.
The JSON is what the employer's Candidate Experience site reads; robots.txt
on these hosts answers 403, so there is no file to honour. The token is two
parts, `host/site` (`jpmc.fa.oraclecloud.com/CX_1001`), read off the careers
page by `discover`: from the careers link, or, where the page only loads
Oracle's assets (Kroger), from a `siteNumber=` in their addresses.

- **The keyword search is loose.** "software engineer" finds 1,659 jobs at
  JPMorgan, ranked by relevance. A listing is kept only when your title
  rules keep its title; each title is read at most four pages of 25 deep,
  and paging stops at the first page with none of yours. Kroger, for
  "pharmacist" in the US: 100 kept, the four-page cap.
- **Your countries are asked of the board.** Its location filter mixes
  countries, states and cities; the entries named as a country are the
  country filter. Several are one finder value joined by an encoded `;`
  (`%3B`): a bare `;` ends the finder's name. A board with none of yours
  costs one request.
- **The advert is a detail request**, one per kept job:
  `ExternalDescriptionStr`, responsibilities and qualifications.
- **One board, two site numbers.** Hilton's `CX_1` and `CX_1009` answer with
  the same 4,225 jobs; `discover` keeps one.
- **Still open:** the detail answers with no items for a removed posting.
- Paced at two requests a second for every `*.oraclecloud.com` host.

---

## Eightfold

    GET https://{host}/api/pcsx/search?domain={domain}&query=…&location=…&start=…
    GET https://{host}/api/pcsx/position_details?domain={domain}&position_id={id}

Starbucks and Lockheed Martin hire through it. robots.txt on these hosts
closes the site and opens `/careers` and `/api/pcsx` to tools; this is that
path. The token is two parts, `host/domain`
(`starbucks.eightfold.ai/starbucks.com`): the careers host, `{tenant}.eightfold.ai`
or the employer's own (`jobs.nvidia.com`), and the employer domain the API
is asked for.

- **A wrong domain answers 404** and none at all 422, so `discover` checks
  the one it guesses: a `domain=` the page names, then the site it read the
  tenant on, then the tenant's name with .com. Lockheed's page names
  `lockheedmartin.eightfold.ai` and no domain; `lockheedmartin.com` answers.
- **Pages are ten results**, whatever `num` asks for, ranked by relevance.
  Each title is read at most five pages deep, a listing is kept only when
  your title rules keep it, and a page with none of yours ends it.
- **Your countries are asked by name** (`location=United States`); a
  country with no jobs costs one request and is skipped. Starbucks lists
  none in the Philippines.
- **The advert is a detail request**, one per kept job; a removed posting
  answers 404. A posting's address carries `?domain=`, which its page
  accepts, so the still-open check and `enrich` can ask again.
- `workLocationOption` is `onsite`, `hybrid` or `remote`.
- Paced at two requests a second per host. Starbucks answers slowly: 56
  requests took 107 seconds, Lockheed's 57.

---

## Taleo Business Edition

    GET https://{host}/{path}/ats/careers/v2/searchResults?org={org}&cws={cws}&rowFrom=…
    GET https://{host}/{path}/ats/careers/v2/viewRequisition?org={org}&cws={cws}&rid={id}

Costco hires through it. There is no JSON: the search results are a page
listing ten jobs at a time, paged by `rowFrom` with no session needed, and
each job's own page carries a schema.org `JobPosting`, read as an employer
site's is. robots.txt on these hosts answers 404, which allows everything.
The token is four parts, `host/path/org/cws`
(`phf.tbe.taleo.net/phf02/COSTCO/41`), read off the careers page by
`discover`.

- **Only titles your title rules keep are opened**, one page each.
  Costco's board, "engineer" and "analyst" in the US: 11 jobs, 13 requests,
  13 seconds. At most 300 jobs are listed per board.
- `org` and `cws` come in either order, and Costco's sit in a script joined
  by `\u0026`, so `discover` matches both.
- **`datePosted` may be Java's form**, "Thu Jul 02 00:00:00 GMT 2026"; it is
  read as 2026-07-02, here and for every employer site.
- **Still open:** a removed job answers 200 with "This job has moved or is
  no longer available", which counts as closed.
- Paced at one page a second for every `*.taleo.net` host.

Taleo Enterprise (`*.taleo.net/careersection/…`) is a different product and
has no reader; Kaiser Permanente and UnitedHealth Group, which use it, are
read through their own careers sites instead.

---

## Employer site

    GET {site}/robots.txt → Sitemap: …
    GET {site}/sitemap.xml (and its jobs children)
    GET {posting page}   → <script type="application/ld+json"> JobPosting

For employers whose applicant tracking system has no reader here. Their
careers site lists every posting in its sitemap and marks each posting page
up for Google as a schema.org `JobPosting`: title, places, posting date,
closing date, the full advert, and pay when stated. Kaiser Permanente,
UnitedHealth Group, Mayo Clinic, Wells Fargo, State Farm, UPS and General
Motors all do. The token is the careers site's address
(`https://jobs.mayoclinic.org`); `discover` offers it when it finds no board
it can read and a posting on the site is marked up.

- **A posting address has a jobs word and an id** (`/job/irvine/nursing-
  attendant/641/10035`, `/jobs/R-1075582`); category and blog pages in the
  same sitemap have no id and are left out. The same posting listed once
  per language counts once.
- **Only postings whose address names one of your titles are read**, one
  request each, at most 40 per site per scan, newest first. A site whose
  addresses are ids only (`jobs.statefarm.com/jobs/46295`) is read newest
  first, 20 a scan.
- `jobLocation.address` is one address, a list of them (Wells Fargo), or
  text. `jobLocationType: TELECOMMUTE` is remote.
- **Pay of 0 to 0 is no pay stated** (State Farm sends that on every post).
- **Still open:** a `validThrough` in the past is closed, and is left out
  of a scan; the page answering 404 is closed.
- robots.txt is honoured for the sitemaps and every page. Paced at one page
  a second per site.

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
| `www.kalibrr.com`, `himalayas.app`, `*.myworkdayjobs.com` | 1.0 (no published limit) |
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
**FlexJobs** · **Wellfound** · **Y Combinator** · **JobStreet** and
**JobsDB** (SEEK; answer 403 to scripts, robots.txt closes the search API, the
API is partner-only) · **OnlineJobs.ph**

Discover recognises these by address and says so before sending anything,
rather than reporting a refusal as if an employer had blocked it. JobStreet,
JobsDB, Kalibrr and OnlineJobs.ph are in dork mode on request:
`jobdork dork --sites jobstreet jobsdb kalibrr onlinejobs`.

**Employer systems with no reader yet.** Discover names these when an
employer's page links one, as "no adapter", rather than reporting nothing:
SAP SuccessFactors (the largest group on the test lists: 13 employers),
iCIMS, UKG, Taleo Enterprise (`careersection`), Jobvite, JazzHR, BambooHR,
Paycom, ADP, Paylocity, Recruitee, Teamtailor, and in India TurboHire,
Darwinbox and PeopleStrong. Several of those employers are read anyway,
through their own careers site (State Farm on iCIMS, Kaiser Permanente on
Taleo Enterprise), when the site marks its postings up for search engines.

Adding a board to dork mode is one line. An API adapter is roughly a hundred
plus its quirks — which is most of this document.

---

## Reading the full advert

**`enrich`** fetches the advert where a source sent only a summary: through
SmartRecruiters' posting API, and for the others from the schema.org
`JobPosting` data on the posting page. Adzuna is refused by name: its links
answer 403 from bot protection, which this tool does not work around.

**`discover`** reads an employer's board token off their own careers page. See
[SOURCES.md](SOURCES.md#finding-one-automatically).
