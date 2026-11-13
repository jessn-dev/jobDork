## Added — 2026-11-13 — Six remote job boards for every field, every board always on, and Job posts that mix sources

Asked for: more job boards for US users in every industry, each checked
against its robots.txt and its terms before it was written (2026-11-13).
Six new sources need no key, carry jobs in sales, customer support, finance,
healthcare, operations, admin and design as well as software, and keep only
the jobs open to your countries:

- **We Work Remotely** (`weworkremotely`): its public RSS, one feed per
  category, about 600 jobs, ten requests a scan.
- **Jobicy** (`jobicy`): its public Jobs API, the last seven days; pay on
  about six jobs in ten. One pass an hour at most, as it asks.
- **Remote OK** (`remoteok`): its public API, the newest hundred or so. Some of
  its text arrives double-encoded ("â€”" for an em dash); it is mended.
- **Remotive** (`remotive`): its public API, which its documentation offers to
  applications, read four times a day at most. Its robots.txt closes `/api/`;
  for this endpoint the documentation was taken over that line, and the
  decision is written down in docs/PLATFORMS.md. Its free-text pay ("$14 -
  $20/hour", "$25k - $35k") is read when it is plain.
- **Working Nomads** (`workingnomads`): the public JSON feed its site links as
  "API", once an hour at most.
- **Dynamite Jobs** (`dynamitejobs`): no API, so its sitemap and job pages,
  read like an employer's careers site: only pages whose addresses carry one
  of your titles, 40 a scan at most, each checked against robots.txt. Its
  pages list the countries that may apply.

None of them searches by many titles, so jobs are kept by your titles. Each
job links to its page on the board that listed it and shows that board as its
source. A job limited to a region none of your countries is in ("Asia Only",
"EMEA") is left out, and a working-hours time zone counts as a region when
nothing else names one ("Time zone: CET" is Europe's hours). Checked live for a
US search: We Work Remotely kept 136 jobs, Jobicy 300 (198 with pay), Remote OK
32, Remotive 11, Working Nomads 18, Dynamite Jobs 16.

**Every board always on.** A config that listed its own `sources.keyless`
missed every board added after it was written. Now every no-credential source
runs whatever that list says; one is switched off only by naming it in the new
`sources.disabled`.

**Job posts mix sources.** Sorted high to low, posts within 5 points of each
other take turns by source, so one busy board no longer fills the first
screens; the best post still comes first.

Checked and left out, with the reasons in docs/PLATFORMS.md: **Idealist**,
**Snagajob**, **Handshake**, **GovernmentJobs.com** and **Jooble** (their terms
forbid automated reading), **The Muse** (its API refuses jobdork), the
**National Labor Exchange's** research data (research use only) and
**Careerjet** (a publisher API for websites that show its listings for
clicks). **CareerOneStop**, the US Department of Labor's job search, has an API
with a free token, but its developer pages refuse scripts: it waits on its
terms being read.
