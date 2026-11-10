## Fixed — 2026-11-10 — Fewer true claims flagged by the hallucination check

On a real resume, after the checker could read all of it, ten of 169 claims
were still flagged. Five were real mistakes by the AI (skills only the
advert names, such as gRPC and NoSQL). The other five were the check's own:

- **The work history given to a field.** jobdork rewrites "10 years 10
  months of experience in DevOps" to "10 years 10 months of work in all",
  because the total is every role together. A list was cut at its first
  comma ("of work in all, DevOps, and security"), and "of software
  engineering experience" was missed; the checker read the field back in
  and flagged it. `llm.total_only` now covers the whole clause, and the
  claims the checker splits out of a verdict get the same rewrite
  (`guard.check`, `work`).
- **A true gap the checker could not quote.** "The candidate lacks
  leadership experience" came back "unsupported", as most gaps do. A gap
  answered so is now settled by script against the resume, as one answered
  "absent" already was: true when the resume never names the thing,
  contradicted when it does. Only a short, named thing: a long one stays
  with the checker. The thing is read without "experience", "expertise"
  and "required for a … role" after it, which made "Python experience"
  impossible to find.
- **An overall opinion of fit.** "Meets the seniority and technical
  requirements" and "is overqualified for the role" are the score in words,
  which no source can back; they are no longer taken as claims. One that
  names something checkable ("meets the requirement for 10+ years", "the
  core requirements for Java") still is.

tests/test_guard.py covers each one, with the wordings seen in real
verdicts.
