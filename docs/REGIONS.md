# Regions

Where a scan finds work, region by region: what reaches each one today, what
has been measured, and what is planned. jobdork is built for job seekers in
the United States first, across every industry, and for the rest of the
world second. **Europe, Australia and Oceania, and the Middle East have
been taken through the steps once** (2026-10-23): employers added, Germany's
job sites built, every region measured. Europe outside Germany, New
Zealand and the Gulf are still thin; the sections below say what is left.

Every region goes through the same steps, in this order:

1. **Measure.** `scripts/coverage_benchmark.py` runs a real default scan, as
   a fresh install would (no keys, the built-in employer boards, 50 km), for
   a test user in each of the region's main cities and four titles across
   industries, and counts what each source keeps. Asia has been measured;
   other regions are added to the script's `REGIONS` as they are taken on.
2. **Add the region's large employers** to `scripts/candidates.csv`.
   `scripts/build_boards.py` runs `discover` on each and keeps only the
   boards it can read and verify (see [SOURCES.md](SOURCES.md)).
3. **Add the region's job sites**, where they have a public way in that
   their terms and robots.txt allow: a government job portal, an open API.
   A site that refuses scripts is not worked around; it stays reachable as a
   search link in `jobdork dork`.
4. **Measure again**, and write the numbers in the changelog.

---

## Today

| Region | What reaches it | Measured |
|---|---|---|
| **United States** | 338 built-in employer boards based there across 27 industries, Workable, Himalayas (remote); with keys, Adzuna and USAJOBS | Discover's test list: 30 of 46 employers readable (US 26 of 37) |
| **Canada** | 22 Canadian employers' boards (RBC, BMO, CIBC, Loblaw, Air Canada…) and multinationals hiring there; Workable; with a key, Adzuna | Not yet |
| **Mexico** | Mercado Libre and multinationals hiring there; Workable; with a key, Adzuna | Not yet. Most large Mexican employers refuse scripts or name no board |
| **Asia** | 30 Asian employers' boards (DBS, UOB, AIA, Samsung, TSMC, Coupang…) and multinationals; Kalibrr (Philippines, Indonesia); Workable; Himalayas; with a key, Adzuna (India) | 11 cities, 2026-10-02 (below) |
| **Europe** | Germany's employment agency (Bundesagentur für Arbeit); Arbeitnow (Germany, UK, France, Netherlands, Switzerland…); ING, Santander, Airbus, ASML, Vodafone, Ericsson, Lloyds and other boards; multinationals hiring there; Workable; Himalayas; with a key, Adzuna (gb de fr nl at be ch es it pl) | 11 cities, 2026-10-23 (below) |
| **Middle East** | Emaar, First Abu Dhabi Bank and DP World's boards; multinationals hiring there; Workable; Himalayas | 4 cities, 2026-10-23 (below): thin, and mostly remote. Adzuna has no index there |
| **Australia and Oceania** | Telstra, Commonwealth Bank, Westpac and NAB's boards; multinationals hiring there; Workable; Himalayas | 4 cities, 2026-10-23 (below). Adzuna's `au` and `nz` answered 503 when last tried, and SEEK refuses scripts |

**Asia, measured 2026-10-02**: jobs kept for four titles, and of them not
remote. Manila 386 (238), Bengaluru 405 (333), Singapore 137 (112), Kuala
Lumpur 85 (82), Taipei 79 (57), Bangkok 51 (33), Ho Chi Minh City 49 (29),
Jakarta 48 (27), Hong Kong 35 (16), Tokyo 42 (17), Seoul 28 (7). Tokyo,
Seoul and Hong Kong stay thin: their large employers run careers sites of
their own that link no board, so regional job sites are what is left.

**Europe, measured 2026-10-23** (same four English titles, 50 km): London
222 (166 not remote), Berlin 257 (168), Madrid 172 (73), Warsaw 141 (52),
Munich 121 (41), Paris 116 (53), Amsterdam 110 (58), Milan 106 (45), Dublin
103 (58), Zurich 91 (42), Stockholm 73 (31). The Bundesagentur gave Berlin
121 of its 257; in German ("Pflegefachkraft", "Buchhalter",
"Softwareentwickler", "Kundenservice") it gave Berlin 315 and Munich 217, so
someone in Germany should search in German. Arbeitnow adds about 38 jobs
everywhere (remote, or with no place given) and 7 to 18 more in its own
cities. Outside Germany the region is still Workable, Himalayas' remote jobs
and the multinationals' boards; Adzuna, with a key, covers ten European
countries. Of the 99 large European employers on the list, 23 have boards
jobdork reads; most of the rest name no board or refuse scripts.

**Australia and Oceania, measured 2026-10-23** (same four titles, 50 km):
Sydney 159 (135 not remote), Melbourne 130 (106), Perth 127 (103), Auckland
44 (10). Most of Australia's come from the Workday boards added that day
(Telstra, Commonwealth Bank); New Zealand has no employer board yet, and
Fonterra, Air New Zealand and Spark name none.

**Middle East, measured 2026-10-23:** Dubai 47 (16 not remote), Abu Dhabi
36 (5), Riyadh 43 (19), Doha 28 (6). Of 20 large Gulf employers tried,
three boards could be read (Emaar's hotels, First Abu Dhabi Bank, DP
World); Qatar Airways is on Taleo Enterprise, SABIC on SuccessFactors'
older portal, and the rest name no board or refuse scripts. The job sites
are closed to scripts too, so until one opens a way in, this region is
mostly Himalayas' remote jobs.

---

## Planned

What is left. The names below are where to start looking, not promises:
each has to pass step 3 (terms, robots.txt, a live answer) before it
becomes a source.

### Europe

- **Employers:** 99 of the largest, across industries, are in
  `scripts/candidates.csv`; 23 have boards jobdork reads, 13 of them added
  on 2026-10-23 (ING, Santander, Airbus, ASML, Vodafone…). The rest
  mostly name no board on their site; next is giving their careers pages
  rather than their home pages, as the Asian list needed, and a reader for
  SuccessFactors' older portal (BASF, Novo Nordisk, Heineken, BT, Ryanair).
- **Job sites: two built** (2026-10-23). The Bundesagentur für Arbeit's job
  search (Germany, searched by your titles and place) and Arbeitnow
  (Germany, the UK, France, the Netherlands, Switzerland; no search, read
  newest first). Still to check: Reed (UK, free key), EURES (the EU's job
  portal), France Travail (key). Adzuna covers ten European countries for
  anyone with a key.
- **Already right:** kilometres, accented place names (`Zürich`, `Köln`), and
  the English names of European cities.

### Australia and Oceania

- **Employers:** 24 of the largest are in `scripts/candidates.csv`
  (2026-10-23); Telstra, Commonwealth Bank, Westpac and NAB could be read.
  Woolworths, Coles, BHP, Qantas and every New Zealand employer tried
  could not: no board named, or scripts refused.
- **Job sites to check:** APSJobs (the Australian public service; robots.txt
  allows it, no API found yet), Workforce Australia (the government's job
  board; did not answer a script on 2026-10-23), the New Zealand
  government's jobs site (jobs.govt.nz; robots.txt allows its listings, the
  public service only), Trade Me Jobs (New Zealand). SEEK refuses scripts
  and is not worked around.
- **Already right:** `WA` read as Western Australia for someone in Perth, and
  `Remote - Australia` not taken for the town of Australia, in Cuba.

### Middle East

- **Employers:** 20 of the largest are in `scripts/candidates.csv`
  (2026-10-23); Emaar's hotels, First Abu Dhabi Bank and DP World could be
  read. Qatar Airways is on Taleo Enterprise, SABIC on SuccessFactors' older
  portal, and the rest name no board or refuse scripts.
- **Job sites:** checked 2026-10-23, none usable. GulfTalent's robots.txt
  closes the site to scripts, Bayt has no API and closes its search pages,
  Naukrigulf did not answer. The Gulf states' government job portals are
  still to check.
- **To check:** salaries are often stated monthly and in AED, SAR or QAR,
  and some postings ask for a nationality; the salary rule and dealbreakers
  should be tried on real adverts from the region before it is called
  supported.

### Everywhere

- **Remote job boards** (RemoteOK, Remotive, We Work Remotely, Working
  Nomads), filtered to the countries each job is open to, as Himalayas is.
  Many "remote" jobs are remote within one country, so the filter matters
  more outside the US than in it.
