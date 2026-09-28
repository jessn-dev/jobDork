"""
jobdork
=======
Job search tooling, from any country (see docs/ARCHITECTURE.md for the
layout: core, db, fetch, search, ai, writing, web, output, dork).

Two ways of finding a role, sharing one database:

  dork    Build Google search URLs you click yourself. Reaches anything Google
          indexed, including the hidden market (public Docs/Sheets, recruiter
          posts) that no applicant tracking system exposes.
  scan    Fetch structured postings straight from ATS APIs, screen them against
          your config, and store what passed.

The dork generator is the original tool and is unchanged. Everything else is
additive: nothing here is required to keep using it.
"""

# Read from installed package metadata rather than repeated here, so
# `pyproject.toml` stays the single source of truth. Two places to write a
# version number means one of them is wrong, and it is always the one nobody
# remembered to edit — `jobdork --version` reported 0.2.0 through five releases.
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _version
    __version__ = _version("jobdork")
except (ImportError, PackageNotFoundError):       # running from a clone
    __version__ = "0.0.0+source"
