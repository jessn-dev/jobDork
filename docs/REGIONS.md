# Regions

Where a scan finds work, region by region: what reaches each one today, what
has been measured, and what is planned. jobdork is built for job seekers in
the United States first, across every industry, and for the rest of the
world second. **The Middle East, Europe, and Australia and Oceania are
planned and not built**; the sections below say what that will take.

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
| **United States** | 308 built-in employer boards based there across 26 industries, Workable, Himalayas (remote); with keys, Adzuna and USAJOBS | Discover's test list: 30 of 46 employers readable (US 26 of 37) |
| **Canada** | 19 Canadian employers' boards (RBC, BMO, CIBC, Loblaw, Air Canada…) and multinationals hiring there; Workable; with a key, Adzuna | Not yet |
| **Mexico** | Mercado Libre and multinationals hiring there; Workable; with a key, Adzuna | Not yet. Most large Mexican employers refuse scripts or name no board |
| **Asia** | 26 Asian employers' boards (DBS, UOB, AIA, Samsung, TSMC, Coupang…) and multinationals; Kalibrr (Philippines, Indonesia); Workable; Himalayas; with a key, Adzuna (India) | 11 cities, 2026-10-02 (below) |
| **Europe** | Multinationals hiring there; Workable; Himalayas; with a key, Adzuna (gb de fr nl at be ch es it pl) | Not yet |
| **Middle East** | Multinationals hiring there; Workable; Himalayas | Not yet. Adzuna has no index there |
| **Australia and Oceania** | Multinationals hiring there; Workable; Himalayas | Not yet. Adzuna's `au` and `nz` answered 503 when last tried, and SEEK refuses scripts |

**Asia, measured 2026-10-02**: jobs kept for four titles, and of them not
remote. Manila 386 (238), Bengaluru 405 (333), Singapore 137 (112), Kuala
Lumpur 85 (82), Taipei 79 (57), Bangkok 51 (33), Ho Chi Minh City 49 (29),
Jakarta 48 (27), Hong Kong 35 (16), Tokyo 42 (17), Seoul 28 (7). Tokyo,
Seoul and Hong Kong stay thin: their large employers run careers sites of
their own that link no board, so regional job sites are what is left.

---

## Planned

None of this is built. The names below are where to start looking, not
promises: each has to pass step 3 (terms, robots.txt, a live answer) before
it becomes a source.

### Europe

- **Employers:** the large ones of the UK, Germany, France, the Netherlands,
  the Nordics, Spain, Italy and Poland, across industries, into
  `scripts/candidates.csv`. Many run Workday, SuccessFactors or their own
  sites.
- **Job sites to check:** Arbeitnow (Germany and the EU, no key), the German
  federal employment agency's job search, Reed (UK, free key), EURES (the
  EU's job portal), France Travail (key). Adzuna already covers ten European
  countries for anyone with a key; a keyless install gets far less, which is
  the gap to close.
- **Already right:** kilometres, accented place names (`Zürich`, `Köln`), and
  the English names of European cities.

### Australia and Oceania

- **Employers:** Woolworths, Coles, Telstra, the four big banks, BHP, Rio
  Tinto, Qantas, Fonterra, Air New Zealand and the like, across industries.
- **Job sites to check:** APSJobs (the Australian public service), Workforce
  Australia (the government's job board), the New Zealand government's
  jobs site, Trade Me Jobs (New Zealand). SEEK refuses scripts and is not
  worked around.
- **Already right:** `WA` read as Western Australia for someone in Perth, and
  `Remote - Australia` not taken for the town of Australia, in Cuba.

### Middle East

- **Employers:** Emirates, Etihad, Qatar Airways, ADNOC, Aramco, SABIC,
  Emaar, Majid Al Futtaim, STC, Careem, Noon and the like, across
  industries; the Gulf's large employers, airlines and banks above all.
- **Job sites to check:** Bayt, GulfTalent, Naukrigulf, and the Gulf states'
  government job portals. Whether any of them has a way in that its terms
  allow is the first question.
- **To check:** salaries are often stated monthly and in AED, SAR or QAR,
  and some postings ask for a nationality; the salary rule and dealbreakers
  should be tried on real adverts from the region before it is called
  supported.

### Everywhere

- **Remote job boards** (RemoteOK, Remotive, We Work Remotely, Working
  Nomads), filtered to the countries each job is open to, as Himalayas is.
  Many "remote" jobs are remote within one country, so the filter matters
  more outside the US than in it.
