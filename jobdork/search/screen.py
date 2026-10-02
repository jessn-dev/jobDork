"""
jobdork.search.screen
=====================
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

# Defaults, used when a config does not override them. The live values come
# from `cfg.screening`, because these encode a judgement about one job market
# — "program" changes an engineering manager into a different job in the US
# and may not elsewhere — and a judgement baked into source is one nobody can
# disagree with.
from ..core.config import DEFAULT_BLOCKERS as BLOCKERS
from ..core.config import Config
from ..db.store import Role
from . import freshness, geo

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
    # How `score` was reached, one entry per rule, for the dashboard to show
    # on hover. A number nobody can take apart is a number nobody trusts.
    parts: list[dict] = field(default_factory=list)

    def add(self, part: str, points: float, most: float, why: str,
            **extra) -> None:
        self.score += points
        self.parts.append({"part": part, "points": round(points, 1),
                           "max": most, "why": why, **extra})


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


def _loose_match(tokens: list[str], phrase_tokens: list[str],
                 blockers: tuple[str, ...] = BLOCKERS,
                 gap: int = LOOSE_GAP) -> bool:
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
    if span_end - span_start + 1 > len(phrase_tokens) + gap:
        return False

    inside = set(tokens[span_start:span_end + 1]) - set(phrase_tokens)
    return not (inside & set(blockers))


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

    screening = getattr(cfg, "screening", None)
    blockers = tuple(screening.blockers) if screening else BLOCKERS
    gap = screening.loose_gap if screening else LOOSE_GAP
    for term in cfg.titles_include:
        if _loose_match(tokens, _tokens(term), blockers, gap):
            return True, f"title loosely matches {term!r}", 18.0

    return False, "title matches nothing in titles.include", 0.0


# ── Work arrangement ───────────────────────────────────────────────────────────

def _extra(patterns: list[str]) -> re.Pattern | None:
    """Compile a config's extra arrangement patterns, if it gave any."""
    if not patterns:
        return None
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def detect_work_mode(role: Role, cfg=None) -> tuple[str, list[str]]:
    """Use what the platform said. Only read the advert when it said nothing.

    Workable and Ashby both state the arrangement on every posting, and a
    stated field beats a keyword hunt through prose that mentions "our remote
    team" in a paragraph about culture.
    """
    flags: list[str] = []
    if role.work_mode:
        return role.work_mode, flags

    haystack = f"{role.title}\n{role.location_raw}\n{role.description[:4000]}"

    # A config may add patterns; they are merged with the built-in ones rather
    # than replacing them, so adding one never silently loses the defaults.
    screening = getattr(cfg, "screening", None)
    extra_hybrid = _extra(screening.hybrid_patterns) if screening else None
    extra_remote = _extra(screening.remote_patterns) if screening else None
    extra_office = _extra(screening.office_patterns) if screening else None

    if _HYBRID.search(haystack) or (extra_hybrid and extra_hybrid.search(haystack)):
        return "hybrid", flags
    if _REMOTE.search(haystack) or (extra_remote and extra_remote.search(haystack)):
        if _TETHERED.search(haystack):
            flags.append("says remote but requires living near an office")
            return "hybrid", flags
        return "remote", flags
    if _OFFICE.search(haystack) or (extra_office and extra_office.search(haystack)):
        return "office", flags
    return "", flags


# ── Location ───────────────────────────────────────────────────────────────────

def _excluded_by(banned: str, role: Role, resolved: geo.Resolved, cfg) -> bool:
    """Does one `locations.exclude` entry rule this role out?

    Matched against what the location *resolved to*, not only the raw string.
    Substring alone was too literal to be useful: `exclude: [TX]` matched
    nothing, because a posting says "Austin, Texas" and never "TX", and
    `exclude: [Texas]` missed every posting that wrote the code instead.

    An entry is tried as a region code, then a country code, then a city name,
    and finally as a substring of the raw string — so `NY`, `New York`,
    `Manhattan` and `US` all work, and so does an arbitrary phrase.
    """
    needle = (banned or "").strip()
    if not needle:
        return False

    region = geo.normalise_state(needle, cfg.country_prefs())
    if region and resolved.state and region == resolved.state:
        return True

    country = geo.country_code(needle)
    if country and resolved.country and country == resolved.country:
        return True

    if resolved.city and geo._key(needle) == geo._key(resolved.city):
        return True

    # A metro name excludes the city it stands for: "Bay Area" rules out
    # San Francisco.
    metro = geo._metro(geo._key(needle), cfg.country_prefs())
    if metro and resolved.city and geo._key(metro[0]) == geo._key(resolved.city):
        return True

    return needle.lower() in (role.location_raw or "").lower()


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
        if _excluded_by(banned, role, resolved, cfg):
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
            f"salary in {role.salary_currency}, floor is {cfg.salary.currency}; "
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
            flags.append("no advert text, so dealbreakers were not checked")
        return True, "", 0.0, flags

    from . import dealbreakers

    for rule in cfg.dealbreakers:
        if rule.regex and dealbreakers.find(rule.regex, role.description,
                                            rule.negations_count):
            if rule.hard:
                return False, f"dealbreaker: {rule.name}", 0.0, flags
            flags.append(f"dealbreaker (soft): {rule.name}")
            penalty += 8.0

    return True, "", -penalty, flags


# ── Explaining the points ──────────────────────────────────────────────────────
# The verdict functions return points and, on a drop, a reason. A kept role
# gets no reason, so these say in words what the points were for.

def _explain_location(role: Role, cfg: Config, anchor: geo.Resolved,
                      mode: str, points: float) -> str:
    where = cfg.locations.anchor or "your anchor"
    units = cfg.locations.units or "mi"
    if mode == "remote":
        return "remote, so distance does not apply: flat 20"
    if cfg.locations.radius == "exact":
        if points:
            return f"{role.location_raw or 'location'} is {where}: 25"
        return f"could not place {role.location_raw or 'the location'} against {where}: 0"
    radius = cfg.radius_miles()
    if radius is None:
        return "no radius set, so distance is not scored: 0"
    if not anchor.located:
        return f"{where} could not be placed on a map: 0"
    if role.distance_mi is None:
        return f"could not place {role.location_raw or 'the location'} on a map: 0"
    shown = geo.from_miles(role.distance_mi, units)
    limit = geo.from_miles(radius, units)
    why = (f"{shown:.0f} {units} from {where}, inside your {limit:.0f} {units} "
           f"radius; nearer scores more: 25 × (1 − {shown:.0f}/{limit:.0f}) + 5")
    if role.distance_mi < 1 and role.city:
        # The case that looked like a bug: "Chicago, Illinois" is the centre
        # of Chicago, which is the anchor, so 0 miles and full points.
        why += (f". Measured to the centre of {role.city}; "
                "the posting gives no street address")
    return why


def _explain_salary(role: Role, cfg: Config) -> str:
    if not role.salary_stated:
        return "no salary published: 0"
    if cfg.salary.floor is None:
        return "salary published, but no salary.floor is set to compare it with: flat 5"
    if role.salary_currency and role.salary_currency != cfg.salary.currency:
        return (f"paid in {role.salary_currency}, floor is in "
                f"{cfg.salary.currency}; not converted: 0")
    top = role.salary_max if role.salary_max is not None else role.salary_min
    if top is None:
        return "salary stated without a figure: 0"
    headroom = min((top - cfg.salary.floor) / max(cfg.salary.floor, 1.0), 1.0)
    return (f"pays up to {top:,.0f} against a floor of {cfg.salary.floor:,.0f} "
            f"({headroom:.0%} above, capped at 100%): 10 + 10 × {headroom:.2f}")


def _explain_fit(match, resume, description: str) -> str:
    from .resume import MIN_SKILLS

    if resume is None or not getattr(resume, "loaded", False):
        return "no resume loaded, so fit is not scored"
    if not description:
        return "no advert text to compare with your resume"
    wanted = len(match.matched) + len(match.missing)
    if not wanted:
        return "the advert names none of the skills jobdork recognises: 0"
    why = (f"you have {len(match.matched)} of the {wanted} "
           f"skill{'' if wanted == 1 else 's'} the advert names")
    if wanted < MIN_SKILLS:
        why += (f"; fewer than {MIN_SKILLS} named, so it is counted out of "
                f"{MIN_SKILLS}, so a short advert cannot earn full fit")
    return why + f": 25 × {len(match.matched)}/{max(wanted, MIN_SKILLS)}"


# ── The whole screen ───────────────────────────────────────────────────────────

def screen(
    role: Role,
    cfg: Config,
    anchor: geo.Resolved | None = None,
    resume=None,
    first_seen: str = "",
    today=None,
) -> Verdict:
    """Apply every rule to one role and mutate it with what was learned.

    `resume` is optional and only ever adds points. It never drops a role:
    a skill you have not listed is a gap in the resume as often as it is a
    gap in you, and neither is grounds for hiding the job.

    `first_seen`, when the post is already stored, dates a post the board
    gave no date for (freshness.age); `today` is for tests.
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
    verdict.add("title", points, 30, why + (
        ": 30" if points == 30 else ": 18, since a loose match scores less than an exact one"))

    fresh = cfg.freshness
    old = freshness.age(role.posted_at, first_seen, fresh, today)
    if old.tier == "ghost":
        verdict.keep = False
        verdict.reasons.append(
            f"{old.text().split(' (')[0]}, past freshness.ghost_days "
            f"({fresh.ghost_days}): likely an evergreen or abandoned listing")
        return verdict

    over = freshness.CLOSED_TEXT.search(role.description or "")
    if over:
        verdict.keep = False
        verdict.reasons.append(f'the advert says the post is over: "{over.group(0)}"')
        return verdict

    mode, mode_flags = detect_work_mode(role, cfg)
    role.work_mode = mode
    verdict.flags.extend(mode_flags)

    if not mode:
        # Always kept. Roughly half of postings name no arrangement, and
        # reading "we cannot tell" as "not remote" hides more real remote
        # roles than it removes office ones.
        verdict.flags.append("arrangement not stated")
        verdict.add("arrangement", 0.0, 10,
                    "the posting does not say remote, hybrid or office: 0")
    elif cfg.locations.work_modes and mode not in cfg.locations.work_modes:
        verdict.keep = False
        verdict.reasons.append(
            f"{mode} is not in locations.work_modes "
            f"({', '.join(cfg.locations.work_modes)})"
        )
        return verdict
    else:
        verdict.add("arrangement", 10.0, 10, f"{mode}, which you accept: 10")

    keep, why, points, flags = location_verdict(role, cfg, anchor, mode)
    verdict.flags.extend(flags)
    if not keep:
        verdict.keep = False
        verdict.reasons.append(why)
        return verdict
    verdict.add("location", points, 30,
                _explain_location(role, cfg, anchor, mode, points))

    keep, why, points, flags = salary_verdict(role, cfg)
    verdict.flags.extend(flags)
    if not keep:
        verdict.keep = False
        verdict.reasons.append(why)
        return verdict
    verdict.add("salary", points, 20, _explain_salary(role, cfg))

    keep, why, points, flags = dealbreaker_verdict(role, cfg)
    verdict.flags.extend(flags)
    if not keep:
        verdict.keep = False
        verdict.reasons.append(why)
        return verdict
    if points:
        soft = [f.split(": ", 1)[1] for f in flags
                if f.startswith("dealbreaker (soft): ")]
        verdict.add("dealbreakers", points, 0,
                    f"soft dealbreaker{'s' if len(soft) > 1 else ''} in the advert: "
                    f"{', '.join(soft)}: −8 each")

    if role.description and _NO_SPONSORSHIP.search(role.description):
        verdict.flags.append("states it will not sponsor a visa")

    if old.known:
        got = freshness.points(old.tier, fresh)
        verdict.add("freshness", got, fresh.new_points,
                    f"{old.text()}: {got:+g}" if got else f"{old.text()}: 0",
                    days=old.days, tier=old.tier, source=old.source,
                    since=old.posted, reposted=old.reposted)
        if old.reposted:
            verdict.flags.append(
                f"reposted: first seen {old.posted}, the board now dates it {old.reposted}")
        if old.tier in ("older", "stale"):
            verdict.flags.append(old.text())
    else:
        verdict.add("freshness", 0.0, fresh.new_points,
                    "the job board gives no posting date: 0", tier="")
        verdict.flags.append("posting date not stated")

    role.fit = None
    if resume is not None and getattr(resume, "loaded", False):
        from .resume import fit as resume_fit
        match = resume_fit(resume, role.description, role.title)
        role.fit = match.score if role.description else None
        verdict.add("resume fit", match.score, 25,
                    _explain_fit(match, resume, role.description),
                    has=match.matched, wants=match.missing)
        if match.summary():
            verdict.flags.append(f"fit: {match.summary()}")
    else:
        verdict.add("resume fit", 0.0, 25, _explain_fit(None, resume, ""))

    role.score = round(verdict.score, 1)
    role.score_parts = verdict.parts
    role.flags = list(dict.fromkeys(verdict.flags))
    role.reasons = list(verdict.reasons)
    return verdict
