"""
jobdork.screen
==============
Decides whether a fetched role is one you should see, and why.

Every rule here answers to one principle: only a positive statement by the
employer can disqualify a role. Silence never does. Most postings do not say
what they pay, about half do not say whether they are remote, and a location
string that cannot be parsed is a string this tool failed to read rather than
evidence the job is somewhere else. So the shape of every check is:

    the employer said something, and it fails       -> drop
    the employer said something, and it passes      -> keep, score it up
    the employer said nothing                       -> keep, flag it

A filter built the other way round looks tidy and quietly throws away most of
the market.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import geo
from .config import Config
from .store import Role

# Words that change the job rather than reword it. "Engineering Program
# Manager" is not an engineering manager, however many of the words line up.
BLOCKERS = ("product", "business", "program", "programme", "project",
            "sales", "account")

# How many unrelated words may sit between the words of a title phrase before
# the loose pass stops believing them to be the same title.
LOOSE_GAP = 2

_TOKEN = re.compile(r"[a-z0-9+#.]+")

# Arrangement, read off the advert when the platform did not state one.
_REMOTE = re.compile(
    r"\b(fully[- ]remote|100% remote|remote[- ]first|work from home|wfh|"
    r"telecommut\w*|distributed team|remote)\b", re.IGNORECASE)
_HYBRID = re.compile(r"\bhybrid\b", re.IGNORECASE)
_OFFICE = re.compile(
    r"\b(on[- ]?site|in[- ]?office|in[- ]person|onsite)\b", re.IGNORECASE)

# "Remote (must live within 50 miles of our Austin office)" reads as remote to
# any keyword check and is not remote. Catching it is worth one regex.
_TETHERED = re.compile(
    r"within\s+\d{1,3}\s*(?:mi|miles|km|kilometers?)\s+of\b", re.IGNORECASE)

_NO_SPONSORSHIP = re.compile(
    r"(no|not|unable to|cannot|can't|do not)\s+(?:be\s+)?"
    r"(?:offer|provide|sponsor)\w*\s+(?:visa\s+)?sponsor\w*|"
    r"\bno visa sponsorship\b|\bwithout sponsorship\b", re.IGNORECASE)


@dataclass
class Verdict:
    keep: bool = True
    reasons: list[str] = field(default_factory=list)   # why it was dropped
    flags: list[str] = field(default_factory=list)     # what to know if kept
    score: float = 0.0


# ── Titles ─────────────────────────────────────────────────────────────────────

def _tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def _phrase_in(tokens: list[str], phrase_tokens: list[str]) -> bool:
    """Whole-word contiguous match. The first and strictest pass."""
    n = len(phrase_tokens)
    if not n or n > len(tokens):
        return False
    return any(tokens[i:i + n] == phrase_tokens
               for i in range(len(tokens) - n + 1))


def _loose_match(tokens: list[str], phrase_tokens: list[str]) -> bool:
    """Same words, another order, up to two unrelated words between them.

    This is what finds "Manager, Engineering Platform" for `engineering
    manager` and "Head of Site Reliability Engineering" for `head of
    engineering`. A blocker word inside the span still refuses: the point is
    to accept rewording, not a different job.
    """
    if not phrase_tokens:
        return False
    positions = []
    for word in phrase_tokens:
        found = [i for i, tok in enumerate(tokens) if tok == word]
        if not found:
            return False
        positions.append(found)

    # Cheapest sufficient test: the tightest window containing one occurrence
    # of every word. Titles are short, so the naive span is fine.
    starts = [min(p) for p in positions]
    ends = [max(p) for p in positions]
    span_start, span_end = min(starts), max(ends)
    if span_end - span_start + 1 > len(phrase_tokens) + LOOSE_GAP:
        return False

    inside = set(tokens[span_start:span_end + 1]) - set(phrase_tokens)
    return not (inside & set(BLOCKERS))


def title_verdict(title: str, cfg: Config) -> tuple[bool, str, float]:
    """(matched, how, score_contribution)."""
    tokens = _tokens(title)
    if not tokens:
        return False, "no title", 0.0

    for term in cfg.titles_exclude:
        if _phrase_in(tokens, _tokens(term)):
            return False, f"title excluded by {term!r}", 0.0

    for term in cfg.titles_include:
        if _phrase_in(tokens, _tokens(term)):
            return True, f"title matches {term!r}", 30.0

    for term in cfg.titles_include:
        if _loose_match(tokens, _tokens(term)):
            return True, f"title loosely matches {term!r}", 18.0

    return False, "title matches nothing in titles.include", 0.0


# ── Work arrangement ───────────────────────────────────────────────────────────

def detect_work_mode(role: Role) -> tuple[str, list[str]]:
    """Use what the platform said. Only read the advert when it said nothing.

    Workable and Ashby both state the arrangement on every posting, and a
    stated field beats a keyword hunt through prose that mentions "our remote
    team" in a paragraph about culture.
    """
    flags: list[str] = []
    if role.work_mode:
        return role.work_mode, flags

    haystack = f"{role.title}\n{role.location_raw}\n{role.description[:4000]}"

    if _HYBRID.search(haystack):
        return "hybrid", flags
    if _REMOTE.search(haystack):
        if _TETHERED.search(haystack):
            flags.append("says remote but requires living near an office")
            return "hybrid", flags
        return "remote", flags
    if _OFFICE.search(haystack):
        return "office", flags
    return "", flags


# ── Location ───────────────────────────────────────────────────────────────────

def location_verdict(
    role: Role, cfg: Config, anchor: geo.Resolved, mode: str
) -> tuple[bool, str, float, list[str]]:
    """(keep, reason_if_dropped, score, flags)."""
    flags: list[str] = []
    resolved = geo.resolve(role.location_raw, cfg.country_prefs())

    role.city, role.state = resolved.city, resolved.state
    role.country = resolved.country
    role.lat, role.lon = resolved.lat, resolved.lon
    if resolved.approximate:
        flags.append(resolved.note)

    for banned in cfg.locations.exclude:
        needle = banned.strip().lower()
        if needle and needle in (role.location_raw or "").lower():
            return False, f"location excluded by {banned!r}", 0.0, flags

    # A country the employer named and you did not list is a real refusal.
    # An empty `countries` accepts everywhere, which is what a reader with no
    # geographic constraint means by leaving it empty.
    if (cfg.locations.countries and resolved.country
            and resolved.country not in cfg.locations.countries):
        return False, f"{resolved.country} is not in locations.countries", 0.0, flags

    # Remote has no distance. Measuring one would be inventing a fact.
    if mode == "remote":
        return True, "", 20.0, flags

    radius = cfg.radius_miles()
    if cfg.locations.radius == "exact":
        if not anchor.located and not anchor.state:
            return True, "", 0.0, flags
        if not (resolved.city or resolved.state):
            flags.append(f"location not resolved: {resolved.note or role.location_raw!r}")
            return True, "", 0.0, flags
        if geo.same_place(anchor, resolved):
            return True, "", 25.0, flags
        return False, f"{role.location_raw!r} is not {cfg.locations.anchor}", 0.0, flags

    if radius is None or not anchor.located:
        return True, "", 0.0, flags

    if not resolved.located:
        # Kept on purpose. "We could not read it" is not "it is far away".
        flags.append(f"location not resolved: {resolved.note or role.location_raw!r}")
        return True, "", 0.0, flags

    distance = geo.distance_between(anchor, resolved)
    role.distance_mi = round(distance, 1) if distance is not None else None
    if distance is None:
        return True, "", 0.0, flags
    if distance > radius:
        units = cfg.locations.units or "mi"
        shown = geo.from_miles(distance, units)
        limit = geo.from_miles(radius, units)
        return (False, f"{shown:.0f} {units} away, outside {limit:.0f} {units}",
                0.0, flags)

    # Nearer is better, but only worth a few points: a role 24 miles out that
    # fits is worth more than one next door that does not.
    return True, "", 25.0 * (1.0 - distance / radius) + 5.0, flags


# ── Salary ─────────────────────────────────────────────────────────────────────

def salary_verdict(role: Role, cfg: Config) -> tuple[bool, str, float, list[str]]:
    flags: list[str] = []

    if not role.salary_stated:
        flags.append("unconfirmed salary")
        return True, "", 0.0, flags

    if cfg.salary.floor is None:
        return True, "", 5.0, flags

    if role.salary_currency and role.salary_currency != cfg.salary.currency:
        # Never converted. A wrong exchange rate drops real jobs quietly.
        flags.append(
            f"salary in {role.salary_currency}, floor is {cfg.salary.currency} — "
            "not compared"
        )
        return True, "", 0.0, flags

    top = role.salary_max if role.salary_max is not None else role.salary_min
    if top is None:
        flags.append("unconfirmed salary")
        return True, "", 0.0, flags

    if top < cfg.salary.floor:
        return (False,
                f"pays up to {top:,.0f} {role.salary_currency or ''}".strip()
                + f", below floor {cfg.salary.floor:,.0f}",
                0.0, flags)

    headroom = min((top - cfg.salary.floor) / max(cfg.salary.floor, 1.0), 1.0)
    return True, "", 10.0 + 10.0 * headroom, flags


# ── Dealbreakers ───────────────────────────────────────────────────────────────

def dealbreaker_verdict(role: Role, cfg: Config) -> tuple[bool, str, float, list[str]]:
    """Read against the description, which is where the detail hides.

    A role can look right in a search result and be wrong in the third
    paragraph. That is the whole reason the advert is fetched.
    """
    flags: list[str] = []
    penalty = 0.0
    if not role.description:
        if cfg.dealbreakers:
            flags.append("no advert text — dealbreakers not checked")
        return True, "", 0.0, flags

    for rule in cfg.dealbreakers:
        if rule.regex and rule.regex.search(role.description):
            if rule.hard:
                return False, f"dealbreaker: {rule.name}", 0.0, flags
            flags.append(f"dealbreaker (soft): {rule.name}")
            penalty += 8.0

    return True, "", -penalty, flags


# ── The whole screen ───────────────────────────────────────────────────────────

def screen(
    role: Role,
    cfg: Config,
    anchor: geo.Resolved | None = None,
    resume=None,
) -> Verdict:
    """Apply every rule to one role and mutate it with what was learned.

    `resume` is optional and only ever adds points. It never drops a role:
    a skill you have not listed is a gap in the resume as often as it is a
    gap in you, and neither is grounds for hiding the job.
    """
    if anchor is None:
        anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())

    verdict = Verdict()

    # Adapters set flags of their own — "adzuna predicted salary ignored" is
    # one — and this used to overwrite them wholesale at the end, so anything
    # the fetch layer knew never reached the database.
    verdict.flags.extend(role.flags)

    matched, why, points = title_verdict(role.title, cfg)
    if not matched:
        verdict.keep = False
        verdict.reasons.append(why)
        return verdict
    verdict.score += points

    mode, mode_flags = detect_work_mode(role)
    role.work_mode = mode
    verdict.flags.extend(mode_flags)

    if not mode:
        # Always kept. Roughly half of postings name no arrangement, and
        # reading "we cannot tell" as "not remote" hides more real remote
        # roles than it removes office ones.
        verdict.flags.append("arrangement not stated")
    elif cfg.locations.work_modes and mode not in cfg.locations.work_modes:
        verdict.keep = False
        verdict.reasons.append(
            f"{mode} is not in locations.work_modes "
            f"({', '.join(cfg.locations.work_modes)})"
        )
        return verdict
    else:
        verdict.score += 10.0

    keep, why, points, flags = location_verdict(role, cfg, anchor, mode)
    verdict.flags.extend(flags)
    if not keep:
        verdict.keep = False
        verdict.reasons.append(why)
        return verdict
    verdict.score += points

    keep, why, points, flags = salary_verdict(role, cfg)
    verdict.flags.extend(flags)
    if not keep:
        verdict.keep = False
        verdict.reasons.append(why)
        return verdict
    verdict.score += points

    keep, why, points, flags = dealbreaker_verdict(role, cfg)
    verdict.flags.extend(flags)
    if not keep:
        verdict.keep = False
        verdict.reasons.append(why)
        return verdict
    verdict.score += points

    if role.description and _NO_SPONSORSHIP.search(role.description):
        verdict.flags.append("states it will not sponsor a visa")

    if resume is not None and getattr(resume, "loaded", False):
        from .resume import fit as resume_fit
        match = resume_fit(resume, role.description, role.title)
        verdict.score += match.score
        if match.summary():
            verdict.flags.append(f"fit: {match.summary()}")

    role.score = round(verdict.score, 1)
    role.flags = list(dict.fromkeys(verdict.flags))
    role.reasons = list(verdict.reasons)
    return verdict
