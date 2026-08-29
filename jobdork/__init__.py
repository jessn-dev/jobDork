"""
jobdork
=======
Job search tooling for North America.

Two ways of finding a role, sharing one database:

  dork    Build Google search URLs you click yourself. Reaches anything Google
          indexed, including the hidden market (public Docs/Sheets, recruiter
          posts) that no applicant tracking system exposes.
  scan    Fetch structured postings straight from ATS APIs, screen them against
          your config, and store what passed.

The dork generator is the original tool and is unchanged. Everything else is
additive: nothing here is required to keep using it.
"""

__version__ = "0.2.0"
