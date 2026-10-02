# Sources

Where the jobs come from, what that reaches, and what it does not.

---

## Two coverage models

This tool finds work two ways, and they fail in opposite directions.

**Keyword search.** One query, every employer on a platform. Workable's search,
Adzuna and USAJOBS all work this way. No list to maintain, no tokens, no
per-employer setup — you name a job title and the platform answers for its
whole market. This is where nearly all the volume comes from.

**Employer boards.** One company each. Greenhouse, Ashby, Lever, Breezy,
SmartRecruiters, Workday, Oracle Recruiting Cloud, Eightfold and Taleo
Business Edition each publish a company's own openings, and so does an employer's own careers site when it
marks its postings up for search engines. Coverage is the companies jobdork
ships with plus the ones you name, and nothing else.

**Google dorks.** The original generator. Builds search URLs you click
yourself. It reaches anything Google has indexed — including things no
applicant tracking system exposes at all.

The three are complementary, not redundant.

| | Reaches | Data quality | Setup |
|---|---|---|---|
| Keyword search | whole platforms | structured rows | none |
| Employer boards | named companies | best available | none for the built-in list; a token each for your own |
| Dorks | anything indexed | a link | none |

---

## A bundled list of employers, and what it costs

jobdork ships a list of employer boards (see
[below](#employer-boards-jobdork-ships-with)), and a list like that costs
three things. Each is limited rather than ignored:

**Time.** One request or more per employer, paced per host. The list is
hundreds, not thousands, and a scan reads only the boards hiring in your
countries (and, if you say so, your industries). A Workday board is asked
for your countries first and costs one request when it has no jobs there.

**Rot.** Boards migrate between systems, tokens get renamed, companies get
acquired; a stale entry is a company you have silently stopped watching. A
weekly GitHub Action asks every board again, and one that has not answered
with jobs for three weeks is removed by a reviewed pull request.

**A crawler.** Building the list means reading employers' sites. It is done
once a week by the project, not by every install, through `discover`: a few
pages per employer, paced, honouring robots.txt.

Keyword search still does what a list cannot: Workable's search reaches every
employer on Workable without knowing one name, including a company that
joins tomorrow. The list reaches what keyword search cannot: Greenhouse,
Ashby, Workday, Oracle, Eightfold and Taleo have no cross-employer search,
so the only way to read those employers is to name them. Your own
`sources.companies` and dork mode cover the rest.

---

## Board tokens

An employer board is identified by a token, and **the token is rarely the
company's name.**

```
mymoose      is Rapid7
evergreenix  is Garrison
knowbe4      is Egress
```

So tokens are read off the employer's careers page, never guessed from the
name. Guessing is worse than useless because **a board that answers is not
proof you found the right company**: on Ashby, `primer` is a Florida
micro-schools operator; on Greenhouse, `peak` is a Texas physiotherapy chain.
Both look like perfectly working boards until something compares the names.

### Finding one by hand

1. Open the employer's careers page.
2. Follow through to an individual job posting.
3. Read the token out of the URL:

| URL | Platform | Token |
|---|---|---|
| `job-boards.greenhouse.io/**stripe**/jobs/123` | greenhouse | `stripe` |
| `jobs.ashbyhq.com/**ramp**/abc-123` | ashby | `ramp` |
| `jobs.lever.co/**leverdemo**/abc-123` | lever | `leverdemo` |
| `**acme**.breezy.hr/p/abc` | breezy | `acme` |
| `jobs.smartrecruiters.com/**Acme**/123` | smartrecruiters | `Acme` |

Lever tokens are case-sensitive.

Then:

```yaml
sources:
  companies:
    - name: Stripe
      platform: greenhouse
      token: stripe
```

### When the posting is on the employer's own domain

Greenhouse boards are frequently served from the company's site with the job id
in the query string — `stripe.com/jobs/search?gh_jid=7532733`. The platform is
unambiguous but **the board token is not in the URL at all**, so it has to be
supplied:

```bash
jobdork add "https://stripe.com/jobs/search?gh_jid=7532733" --token stripe
```

`jobdork add` detects the platform from the domain, fetches that one posting,
and stores it as a full row. This is the bridge from a Google result to the
database: Google does the finding, the adapter does the reading.

It takes several at once:

```bash
jobdork add <url> <url> <url>
jobdork add --from-file urls.txt
```

The file is one URL per line, tolerating `#` comments, `- ` bullets and
`title<TAB>url`. **These are posting URLs, not the dork generator's output** —
that file holds Google *search* URLs, and turning those into postings would
mean scraping Google's results, which is bot-protected and not something this
tool works around. Click the results, paste the ones worth keeping.

A role added this way is stored **even if it fails your filters** — you asked
for it by name, and a rule is not a better judge of that than you are. The
mismatch is reported rather than silently applied.

### Employer boards jobdork ships with

A fresh install already reads named employers: `jobdork/data/boards.csv`
lists employer boards across industries, US first, and a scan reads the ones
hiring in your countries (`sources.directory`, on by default; see
[CONFIG.md](CONFIG.md#sources)). `jobdork sources` says how many.

None of it is typed in by hand. `scripts/build_boards.py --add` runs
`discover` over `scripts/candidates.csv` (employer, industry, country,
careers page) and writes in only boards found on the employer's own site that
answered with jobs, with the countries they list jobs in. A board found deep
in a site under another name (Marriott's page linking Marriott Vacations
Worldwide's board) is left out for a person to check.

Every Monday a GitHub Action (`.github/workflows/boards.yml`) runs
`build_boards.py --reverify`: a board that answers with jobs is refreshed, one
that has not for three weeks is removed, and the changes arrive as a pull
request whose text lists what changed. To suggest an employer, add a line to
`scripts/candidates.csv`.

### Finding one automatically

```bash
jobdork discover vectra.ai          # look
jobdork discover vectra.ai --add    # and write it into your config
```

It fetches the employer's careers pages and takes the token out of the links
they publish. It does not guess: a company name is refused rather than turned
into a domain, and a token that was not read off their own site is never
written down.

Pages are read in this order, at most twelve, stopping at the first board it
can read:

1. the page you gave, as given (a job search or one posting works best);
2. the site's front page;
3. links on those pages to job pages on the same site (`careers.acme.com`
   counts as `acme.com`), search pages first, six at most;
4. the sitemap, for one or two postings, whose Apply links name the board;
5. a few usual addresses (`/careers`, `/jobs`, `/jobs/search`…).

It honours each site's `robots.txt` (the longest matching rule decides, as
RFC 9309 says) and lists the pages it left unread because of it. A site that
does not answer, or refuses (401, 403), is not asked again.

A board found only on a page it followed, under a name that is not the
site's, comes with a note to check it: `careers.marriott.com` links Marriott
Vacations Worldwide's board from a brand page.

Four outcomes, kept apart because they mean different things:

| | Meaning |
|---|---|
| `[verified]` | found on their site **and** the board returned jobs |
| `[token not on page]` | the platform is visible but the board is never named — Stripe's careers search mentions Greenhouse 535 times and the token none |
| `[no adapter]` | located and named, but no fetcher exists for it |
| `[empty board]` | answered 200 with nothing, which is also what throttling looks like |

**Only `[verified]` can be added.** Where the platform states the employer, the
board's own claim about itself is printed beside the result, so `primer`
returning a Florida micro-schools operator is visible rather than filed.

`--add` rewrites the config as text rather than dumping it through YAML, so the
comments in a file that is mostly comments survive.

---

## The gazetteer

`jobdork/data/cities.csv` — 69,933 places across 245 countries, 2.3MB, shipped
in the repository.

Almost no job source supports a radius. Adzuna does, in kilometres. USAJOBS
does, in miles. Everything else — Workable's search, every employer board, and
every Google result you click — returns a location *string*. So distance is
measured locally.

**No geocoding API, no key, no rate limit, no per-role network call.** The
lookup is a dictionary and a haversine.

### Building it

```bash
python scripts/build_gazetteer.py
```

Downloads GeoNames `cities5000` (CC BY 4.0) and writes the CSV most-populous
first — so a name collision resolves to the city people actually mean. Every
place of 5,000 or more, which is every place a job is advertised in and few
that are not.

With no arguments it builds for the countries in your config. Pass codes to
override (`PH SG`), or `all` for every country.

Without it the tool falls back to about 125 bundled major metros, and the
radius still works in the places most postings name.

GeoNames numbers Canadian and Australian regions rather than lettering them,
so `08` becomes `ON` and `NSW` at build time. Elsewhere the region column is
left blank: a posting says "Makati, Philippines" rather than naming a province,
so the country does the identifying.

`alternatenames` from GeoNames is deliberately not used. It is unordered and
runs to hundreds of scripts per city; taking the first few Latin entries added
four megabytes, made São Paulo look like two different places, and still missed
München. Local spellings are handled by a curated exonym table instead.

### What it normalises

**Regions**, in every form people write them: `CA`, `California`, `Calif`;
`ON`, `Ontario`; `NSW`, `New South Wales`. `D.C.` and `DC` fold to the same key
— without that, "Washington, D.C." falls through to its second word and becomes
Washington *state*, which is 2,300 miles wrong.

**Ambiguous region codes**, settled by your own countries. `WA` is Washington
to a reader in Seattle and Western Australia to one in Perth, and nothing in
the string itself can tell you which.

**Accents, in both directions.** `Zurich` finds `Zürich` and `Sao Paulo` finds
`São Paulo`, because the lookup folds both sides.

**English exonyms.** `München` and `Munich` share almost no letters, so folding
cannot connect them; a curated table does, along with Köln, Wien, Praha,
Warszawa, København, Lisboa, Firenze, Napoli, Roma, Milano, Genève, Bruxelles,
Den Haag, Antwerpen, Göteborg, Moskva, Bucureşti, Beograd, Bombay and Bengaluru.

**The "City" suffix.** `Makati` and `Makati City` are one place, as are
`Quezon` and `Quezon City`.

**City-states.** In Singapore, Monaco and Hong Kong the country name is also
the city name, so a country-only string is looked up as a city before it is
given up on.

**Place-name spellings.** `St. Louis`, `St Louis` and `Saint Louis` are one
city; the gazetteer spells it one way and postings spell it all three. `Ft.`
and `Mt.` likewise.

**Metro names that are not cities**, about a hundred and ten of them
worldwide, each mapped to an anchor point and marked approximate. Where one
name belongs to several countries — `NCR` is the National Capital Region in
Canada, India and the Philippines; `Bay Area` is San Francisco or Hong Kong —
your configured countries settle it:

```
Bay Area · Silicon Valley · SoCal · NYC · Tri-State · DMV · Northern Virginia
Greater Boston · Chicagoland · DFW · Metroplex · Research Triangle · RTP
Twin Cities · PNW · Puget Sound · Front Range · Delaware Valley · South Florida
Tampa Bay · Wasatch Front · Silicon Slopes · GTA · Metro Vancouver
Kanto · Kansai · Metro Manila · BGC · Klang Valley · Jabodetabek · Delhi NCR
MMR · Greater Seoul · Greater Taipei · Pearl River Delta · Greater Sydney
Greater Auckland · Greater London · Randstad · Île-de-France · Ruhrgebiet
Rhein-Main · Öresund · Greater Madrid · Tricity · Gauteng · Greater Cairo
Greater Dubai · CDMX · Greater São Paulo · Greater Buenos Aires
```

**Countries.** A posting naming a country you did not list is dropped — that
is the employer telling you where the job is. `Remote - US` and
`Remote - Philippines` keep their country even though they name no place,
because a remote role still has a legal boundary.

A country name that is the *whole* string names no city, and looking one up
anyway is how `Remote - Australia` resolved to Australia, a town of three
thousand people in Cuba.

Ambiguity is admitted rather than resolved: a bare city name matching several
places returns unresolved with a note, and the role is kept and flagged.

---

## Why keys are never shipped

Keyed sources (Adzuna, USAJOBS) use each user's own free key. A key built
into the public image would be readable by anyone who pulls it, however it
was hidden, and would give every user one shared quota. The full reasoning,
and the key proxy deferred until there is a reason for it, are in
[DECISIONS.md](DECISIONS.md).

---

## What this cannot reach

Stated rather than left for you to find.

**Employers with no board on a platform here.** Coverage is keyword search plus
the companies you name. Dork mode covers the rest.

**Adzuna, in countries it does not index.** It serves `gb us ca ie in de fr nl
at be ch es it pl br mx za`, with `au nz sg` present but currently answering
503. There is no Philippine, Indonesian, Malaysian, Japanese, Emirati or
Russian index. The adapter names the country it cannot serve rather than
returning an empty list.

**USAJOBS, outside the US.** It skips itself when `US` is not in your
countries, rather than searching a market you cannot work in.

**Platforms with no adapter.** iCIMS, Taleo, SuccessFactors, Phenom,
Avature, Oracle Recruiting Cloud, Jobvite, JazzHR, BambooHR, Paycom, ADP, UKG,
Paylocity, Recruitee, Personio, Teamtailor, Pinpoint. All of these are in the
dork board list and none has a fetcher.

**Aggregators with no public API.** Indeed, Glassdoor, LinkedIn, Dice, BuiltIn,
ZipRecruiter, Monster, CareerBuilder, SimplyHired, FlexJobs, Wellfound, Y
Combinator. See [PLATFORMS.md](PLATFORMS.md#not-supported).

**Jobs not posted to an applicant tracking system at all.** Trades, retail
floor work and most care work do not hire this way and are better served
elsewhere.

**Salary, for most postings.** About 12% state a figure. That is the market,
not a bug, and the salary rule is built around it.

**Right to work.** A posting that states its sponsorship position is flagged,
read from the advert. Most state nothing. Treat an unflagged role as unknown
rather than as available.

**Anything an advert did not say.** A source that truncates its adverts —
Adzuna caps at 500 characters — cannot be screened on, because dealbreakers and
work-mode detection have nothing to read.

---

## Dork mode

The Google generator reaches what no API here can.

```bash
jobdork dork --title "security analyst" --location "Chicago, IL" --since 1w --open
```

33 standard boards, plus opt-in strategies that have no structured equivalent
anywhere:

| Key | Finds |
|---|---|
| `google_docs`, `google_sheets` | role lists shared in public Docs before they hit a board |
| `linkedin_posts` | recruiter posts that go live before the official listing |
| `hiring_manager` | people to approach directly |
| `pdf_resumes` | publicly posted resumes, for studying how your field presents |

No applicant tracking system exposes any of that. Adding a board to dork mode
is one line in `jobdork/dork/boards.py`; an API adapter is roughly a hundred plus its
quirks.

Run `jobdork dork --list-sites` for the full board list.

---

## Adding a source

A new adapter is a function that returns a `SourceResult`:

```python
@register("myplatform")
def fetch(fetcher, cfg, token: str = "", company: str = "", **_) -> SourceResult:
    resp = fetcher.get(API.format(token=token))
    if not resp.ok:
        return SourceResult(source="myplatform", requests_made=1,
                            errors=[f"{token}: {resp.error}"])
    roles = [...]
    return _result_for("myplatform", roles, 1, [])
```

Three rules it has to follow.

**Return an account, not a list.** `SourceResult` carries requests made, errors
and a `suspect` flag. An adapter that returned a bare list would be reporting
"no jobs here" for "they stopped talking to me".

**Never decide what an empty answer meant.** That belongs to `_result_for`,
which marks it suspect. This layer reports what happened.

**Fetch through the `Fetcher`.** It owns the pacing, the retries and the
circuit breaker. A direct `requests` call bypasses all three and is how a host
starts refusing.

Then add the name to `KEYLESS_SOURCES` or `KEYED_SOURCES` in `jobdork/core/config.py`, and
a row to [PLATFORMS.md](PLATFORMS.md) documenting what breaks on it.
