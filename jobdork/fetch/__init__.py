"""
jobdork.fetch
=============
Adapters that turn one board's API into a list of `store.Role`.

Every adapter is a callable with the same shape:

    fetch(fetcher, cfg, **kwargs) -> SourceResult

and returns roles plus an honest account of what happened. That second part is
not decoration. Several of these APIs answer HTTP 200 with an empty array both
for a board that does not exist and for one that is rate-limiting you, so an
adapter that returned a bare list would be reporting "no jobs here" for
"they stopped talking to me". `SourceResult.suspect` is how a source says it
does not know.

Registered but keyless-dormant sources (USAJOBS, Adzuna) are listed here all
the same. They report that they have no credential rather than disappearing,
because a source that silently does not run looks exactly like a source that
found nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from ..db.store import Role

log = logging.getLogger("jobdork.fetch")


@dataclass
class SourceResult:
    """What one source did. Never just a list of roles."""

    source: str
    roles: list[Role] = field(default_factory=list)
    requests_made: int = 0
    skipped: str = ""            # why it did not run at all
    errors: list[str] = field(default_factory=list)
    suspect: bool = False        # answered, but the answer is not trustworthy

    @property
    def ran(self) -> bool:
        return not self.skipped

    def summary(self) -> str:
        if self.skipped:
            return f"{self.source}: skipped ({self.skipped})"
        parts = [f"{self.source}: {len(self.roles)} roles"]
        if self.requests_made:
            parts.append(f"{self.requests_made} requests")
        if self.suspect:
            parts.append("SUSPECT: answered empty where it usually does not")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts)


# Populated by the adapter modules at import time.
REGISTRY: dict[str, Callable] = {}


def register(name: str):
    def wrap(fn: Callable) -> Callable:
        REGISTRY[name] = fn
        return fn
    return wrap


def get(name: str) -> Callable | None:
    return REGISTRY.get(name)


# Import for side effects: each module registers itself.
from . import (  # noqa: E402,F401
    adzuna,
    ashby,
    breezy,
    eightfold,
    greenhouse,
    himalayas,
    kalibrr,
    lever,
    oracle,
    site,
    smartrecruiters,
    taleo,
    usajobs,
    workable,
    workday,
)

__all__ = ["REGISTRY", "Role", "SourceResult", "get", "register"]
