## Added — 2026-11-13 — Three remote job boards for every field: We Work Remotely, Jobicy and Remote OK

Asked for: more job boards for US users in every industry, each checked
against its robots.txt and its terms before it was written (2026-11-13).
Three new sources need no key, carry jobs in sales, customer support,
finance, healthcare, operations and design as well as software, and keep
only the jobs open to your countries:

- **We Work Remotely** (`weworkremotely`): its public RSS, one feed per
  category, about 600 jobs, ten requests a scan (the main feed holds only the
  newest ten of each). A job limited to a region none of your countries is in
  ("Asia Only" for someone in the US) is left out.
- **Jobicy** (`jobicy`): its public Jobs API, the last seven days, 100 a page;
  for a US search, the US filter. Pay on about six jobs in ten. One pass an
  hour at most, as it asks.
- **Remote OK** (`remoteok`): its public API, the newest hundred or so jobs,
  once an hour at most. Some of its text arrives double-encoded ("â€”" for an
  em dash); it is mended.

None of them has a search by many titles, so jobs are kept by your titles.
Each job links to its page on the board that listed it, and shows the board as
its source, as their terms ask. Checked live for a US search with six to
eight titles across those fields: We Work Remotely kept 136 jobs, Jobicy 300
(198 with pay), Remote OK 32. They are in the default `sources.keyless`; a config that
lists its own sources adds them by hand.

Checked and left out, with the reasons in docs/PLATFORMS.md: **Idealist**,
**Snagajob**, **Handshake**, **GovernmentJobs.com** and **Jooble** (their terms
forbid automated reading), **Remotive** (its robots.txt closes its API,
though its documentation invites apps), **The Muse** (its API refuses
jobdork), the **National Labor Exchange's** research data (research use only)
and **Careerjet** (a publisher API for websites that show its listings for
clicks). **CareerOneStop**, the US Department of Labor's job search, has an
API with a free token, but its developer pages refuse scripts: it waits on its
terms being read.
