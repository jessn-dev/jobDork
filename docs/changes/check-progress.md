## Fixed — 2026-11-12 — Check still open counts what it checks

**Check still open** opened at 54% and counted 729 postings when Job posts
showed 566. Postings checked in the last 12 hours, which it leaves alone,
were counted as done the moment it started; and it counts each copy of a
job found on several sites, since a job closes only when every copy has.
Now the recently checked ones are set aside before it counts, so it starts
at 0%, and its first line says how many postings it checks, for how many
job posts, and how many it left alone.
