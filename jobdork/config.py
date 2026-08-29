"""
jobdork.config
==============
Loads and validates `config.yaml`.

Rules this file exists to enforce:

  - The config is validated when it loads. A broken dealbreaker regex or a
    resume path that no longer exists stops the run, rather than silently
    filtering nothing and looking like a quiet day on the market.
  - Secrets never live in `config.yaml`. API keys are read from the
    environment or `.env`, which is gitignored. A key written into the YAML
    is accepted but warned about.
  - Every key has a default. A config that only sets `titles.include` works.

`config.local.yaml` is read in preference to `config.yaml` when present, so a
machine-specific override never has to be merged back.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Accepted values ────────────────────────────────────────────────────────────

WORK_MODES = ("remote", "hybrid", "office")

# Any ISO 3166-1 alpha-2 country the geocoder recognises. There is no built-in
# region: a reader in Manila, Munich or Melbourne configures their own
# countries and everything else follows from that.
def _known_countries() -> tuple[str, ...]:
    from .geo import ALL_COUNTRY_CODES
    return tuple(sorted(ALL_COUNTRY_CODES))


# "exact" means the posting's city and region must match the anchor after
# normalisation. Anything else is a distance in `locations.units`.
RADIUS_EXACT = "exact"
UNITS = ("mi", "km")

# Accepted spellings, mapped to the one the writers actually key on. Every
# entry here needs a writer in cli.py; a format that validates and then writes
# nothing is exactly the silent failure the rest of this file exists to stop.
OUTPUT_FORMATS = {
    "html": "html",
    "json": "json",
    "md": "md", "markdown": "md",
    "csv": "csv",
}

# Statuses a role can hold. The last four are settled: a role in one of them
# is hidden from results rather than shown again.
STATUSES = (
    "new", "interested", "applied", "submitted", "interviewing", "offer",
    "rejected", "withdrawn", "skipped", "closed",
)
SETTLED_STATUSES = ("rejected", "withdrawn", "skipped", "closed")

# Sources that need no credential. These are what a fresh install runs.
KEYLESS_SOURCES = (
    "workable",         # jobs.workable.com keyword search, no token needed
    "greenhouse",       # per-employer board, needs a token in sources.companies
    "ashby",
    "lever",
    "smartrecruiters",
    "breezy",
)

# Sources that are registered but dormant until a key is present.
KEYED_SOURCES = ("usajobs", "adzuna")

ALL_SOURCES = KEYLESS_SOURCES + KEYED_SOURCES

CONFIG_CANDIDATES = ("config.local.yaml", "config.yaml")

# Currencies a floor can be stated in. A salary in any other currency is kept
# and flagged "not compared", never converted.
CURRENCIES = (
    "USD", "CAD", "EUR", "GBP", "AUD", "NZD", "SGD", "PHP", "INR", "JPY",
    "CNY", "HKD", "TWD", "KRW", "MYR", "IDR", "THB", "VND", "CHF", "SEK",
    "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "ILS", "AED", "SAR",
    "ZAR", "NGN", "KES", "EGP", "BRL", "MXN", "ARS", "CLP", "COP", "PEN",
    "TRY", "UAH", "PKR", "BDT", "LKR",
)

# ── Errors ─────────────────────────────────────────────────────────────────────


class ConfigError(Exception):
    """Raised when the config cannot be trusted. Always fatal."""


# ── .env ───────────────────────────────────────────────────────────────────────

def load_dotenv(path: str | Path = ".env") -> None:
    """Read KEY="value" lines into os.environ without overwriting real ones.

    Deliberately tolerant: a malformed line is skipped rather than fatal,
    because a broken .env should not stop a keyless scan that never needed it.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass
class Dealbreaker:
    """A regex read against the job description, not the title.

    `hard` hides the role. Otherwise it is shown with a warning, because
    plenty of things that would put you off are worth seeing anyway.
    """
    name: str
    pattern: str
    hard: bool = True
    regex: re.Pattern | None = None


@dataclass
class Locations:
    anchor: str = ""                                # "Chicago, IL", "Makati, Philippines"
    radius: str | float = 25                        # "exact" or a distance
    units: str = ""                                 # mi | km; blank picks by country
    countries: list[str] = field(default_factory=list)
    work_modes: list[str] = field(default_factory=list)   # empty means all three
    exclude: list[str] = field(default_factory=list)


@dataclass
class Salary:
    floor: float | None = None
    currency: str = "USD"


@dataclass
class Company:
    """One employer board to read. `token` is the board id, not the name.

    Tokens rarely match company names, so this is written by
    `jobdork discover` rather than guessed.
    """
    name: str
    platform: str
    token: str


@dataclass
class Sources:
    keyless: list[str] = field(default_factory=lambda: list(KEYLESS_SOURCES))
    companies: list[Company] = field(default_factory=list)
    usajobs_key: str = ""
    usajobs_email: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    # Empty means "follow locations.countries". Defaulting this to ["us"]
    # made every reader search the American index no matter where they live.
    adzuna_countries: list[str] = field(default_factory=list)

    def usajobs_ready(self) -> bool:
        return bool(self.usajobs_key and self.usajobs_email)

    def adzuna_ready(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)


@dataclass
class Output:
    dir: str = "out"
    formats: list[str] = field(default_factory=lambda: ["html", "json"])


@dataclass
class Fetch:
    concurrency: int = 8
    timeout: int = 20
    retries: int = 2
    user_agent: str = (
        "jobdork/0.2 (+https://github.com/jessengolab/jobDork) "
        "personal job search"
    )


@dataclass
class Config:
    titles_include: list[str] = field(default_factory=list)
    titles_exclude: list[str] = field(default_factory=list)
    locations: Locations = field(default_factory=Locations)
    salary: Salary = field(default_factory=Salary)
    dealbreakers: list[Dealbreaker] = field(default_factory=list)
    resume_path: str = ""
    sources: Sources = field(default_factory=Sources)
    output: Output = field(default_factory=Output)
    fetch: Fetch = field(default_factory=Fetch)
    db_path: str = "data/jobdork.db"
    path: str = ""          # where this config was read from

    # Warnings collected during load. Not fatal, but worth printing once.
    warnings: list[str] = field(default_factory=list)

    def radius_miles(self) -> float | None:
        """The radius in miles, whatever units it was written in.

        None means 'exact match only', not 'no limit'. Distances are computed
        in miles internally and converted back for anything you read.
        """
        if self.locations.radius == "exact":
            return None
        from .geo import to_miles
        return to_miles(float(self.locations.radius), self.locations.units)

    def country_prefs(self) -> tuple[str, ...]:
        """Configured countries, used to settle ambiguous region codes.

        WA is Washington to a reader in Seattle and Western Australia to one
        in Perth, and only this can tell them apart.
        """
        return tuple(self.locations.countries)

    def active_sources(self) -> list[str]:
        """Keyless sources, plus keyed ones whose credentials are present."""
        active = [s for s in self.sources.keyless if s in ALL_SOURCES]
        if self.sources.usajobs_ready():
            active.append("usajobs")
        if self.sources.adzuna_ready():
            active.append("adzuna")
        return active

    def dormant_sources(self) -> list[str]:
        """Keyed sources that are registered but have no credential yet."""
        dormant = []
        if not self.sources.usajobs_ready():
            dormant.append("usajobs")
        if not self.sources.adzuna_ready():
            dormant.append("adzuna")
        return dormant


# ── Loading ────────────────────────────────────────────────────────────────────

def find_config(explicit: str = "") -> Path | None:
    """Resolution order: --config, $JOBDORK_CONFIG, config.local.yaml, config.yaml."""
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise ConfigError(f"No config at {p}")
        return p
    env = os.environ.get("JOBDORK_CONFIG", "")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            raise ConfigError(f"JOBDORK_CONFIG points at {p}, which does not exist")
        return p
    for name in CONFIG_CANDIDATES:
        p = Path(name)
        if p.is_file():
            return p
    return None


def load(explicit: str = "", require: bool = True) -> Config:
    """Read, validate and return the config. Raises ConfigError on anything wrong."""
    load_dotenv()
    path = find_config(explicit)
    if path is None:
        if require:
            raise ConfigError(
                "No config found. Run `jobdork setup`, or copy "
                "config.example.yaml to config.yaml and edit it."
            )
        return Config()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must be a mapping at the top level")

    cfg = _build(raw)
    cfg.path = str(path)
    _apply_env_secrets(cfg)
    _validate(cfg)
    return cfg


def _build(raw: dict[str, Any]) -> Config:
    cfg = Config()

    titles = raw.get("titles") or {}
    cfg.titles_include = _str_list(titles.get("include"), "titles.include")
    cfg.titles_exclude = _str_list(titles.get("exclude"), "titles.exclude")

    loc = raw.get("locations") or {}
    countries = [c.upper() for c in
                 _str_list(loc.get("countries"), "locations.countries")]
    cfg.locations = Locations(
        anchor=str(loc.get("anchor") or "").strip(),
        radius=loc.get("radius", 25),
        units=str(loc.get("units") or "").strip().lower(),
        countries=countries,
        work_modes=[m.lower() for m in _str_list(loc.get("work_modes"), "locations.work_modes")],
        exclude=_str_list(loc.get("exclude"), "locations.exclude"),
    )

    sal = raw.get("salary") or {}
    floor = sal.get("floor")
    cfg.salary = Salary(
        floor=float(floor) if floor not in (None, "") else None,
        currency=str(sal.get("currency") or "USD").upper(),
    )

    for i, entry in enumerate(raw.get("dealbreakers") or []):
        if not isinstance(entry, dict):
            raise ConfigError(f"dealbreakers[{i}] must be a mapping with name and pattern")
        cfg.dealbreakers.append(
            Dealbreaker(
                name=str(entry.get("name") or f"dealbreaker {i}"),
                pattern=str(entry.get("pattern") or ""),
                hard=bool(entry.get("hard", True)),
            )
        )

    resume = raw.get("resume") or {}
    cfg.resume_path = str(resume.get("path") or "").strip()

    src = raw.get("sources") or {}
    companies = []
    for i, entry in enumerate(src.get("companies") or []):
        if not isinstance(entry, dict):
            raise ConfigError(f"sources.companies[{i}] must be a mapping")
        companies.append(
            Company(
                name=str(entry.get("name") or "").strip(),
                platform=str(entry.get("platform") or "").strip().lower(),
                token=str(entry.get("token") or "").strip(),
            )
        )
    cfg.sources = Sources(
        keyless=[s.lower() for s in _str_list(src.get("keyless"), "sources.keyless")]
        or list(KEYLESS_SOURCES),
        companies=companies,
        usajobs_key=str(src.get("usajobs_key") or ""),
        usajobs_email=str(src.get("usajobs_email") or ""),
        adzuna_app_id=str(src.get("adzuna_app_id") or ""),
        adzuna_app_key=str(src.get("adzuna_app_key") or ""),
        adzuna_countries=[c.lower() for c in
                          _str_list(src.get("adzuna_countries"),
                                    "sources.adzuna_countries")],
    )

    out = raw.get("output") or {}
    cfg.output = Output(
        dir=str(out.get("dir") or "out"),
        formats=[f.lower() for f in _str_list(out.get("formats"), "output.formats")]
        or ["html", "json"],
    )

    fet = raw.get("fetch") or {}
    cfg.fetch = Fetch(
        concurrency=int(fet.get("concurrency", 8)),
        timeout=int(fet.get("timeout", 20)),
        retries=int(fet.get("retries", 2)),
        user_agent=str(fet.get("user_agent") or Fetch().user_agent),
    )

    cfg.db_path = str(raw.get("db") or "data/jobdork.db")
    return cfg


def _apply_env_secrets(cfg: Config) -> None:
    """Environment wins over YAML, and a key in the YAML earns a warning.

    `config.yaml` is a file people commit or paste into issues. The
    environment is the right home for a credential, so a key found in the
    YAML is used but called out.
    """
    pairs = (
        ("usajobs_key", "USAJOBS_API_KEY"),
        ("usajobs_email", "USAJOBS_EMAIL"),
        ("adzuna_app_id", "ADZUNA_APP_ID"),
        ("adzuna_app_key", "ADZUNA_APP_KEY"),
    )
    for attr, env_name in pairs:
        env_value = os.environ.get(env_name, "")
        yaml_value = getattr(cfg.sources, attr)
        if env_value:
            setattr(cfg.sources, attr, env_value)
        elif yaml_value and attr.endswith(("_key", "_id")):
            cfg.warnings.append(
                f"sources.{attr} is set in {cfg.path or 'config.yaml'}. "
                f"Move it to .env as {env_name} — YAML files get committed."
            )


# ── Validation ─────────────────────────────────────────────────────────────────

def _validate(cfg: Config) -> None:
    if not cfg.titles_include:
        raise ConfigError(
            "titles.include is empty. Without it there is nothing to search for, "
            "and every keyword source needs a term to expand."
        )

    loc = cfg.locations
    if isinstance(loc.radius, str) and loc.radius.strip().lower() != RADIUS_EXACT:
        try:
            loc.radius = float(loc.radius)
        except ValueError:
            raise ConfigError(
                f"locations.radius is {loc.radius!r}. Accepted: "
                f"'{RADIUS_EXACT}', or a distance such as 25."
            ) from None
    if loc.radius != RADIUS_EXACT and float(loc.radius) <= 0:
        raise ConfigError("locations.radius must be positive")
    if loc.radius != RADIUS_EXACT and not loc.anchor:
        raise ConfigError(
            f"locations.radius is {loc.radius} but locations.anchor is empty. "
            "A radius needs somewhere to measure from, e.g. "
            "anchor: \"Chicago, IL\" or anchor: \"Makati, Philippines\"."
        )

    known = _known_countries()
    for country in loc.countries:
        if country not in known:
            raise ConfigError(
                f"locations.countries has {country!r}, which is not an ISO "
                "3166-1 alpha-2 code the geocoder knows. Add it to "
                "geo.COUNTRY_CODES if the country is missing."
            )

    if loc.units and loc.units not in UNITS:
        raise ConfigError(
            f"locations.units is {loc.units!r}. Accepted: {', '.join(UNITS)}."
        )
    if not loc.units:
        from .geo import default_units
        loc.units = default_units(loc.countries)
    for mode in loc.work_modes:
        if mode not in WORK_MODES:
            raise ConfigError(
                f"locations.work_modes has {mode!r}. Accepted: "
                f"{', '.join(WORK_MODES)}. Empty keeps all three. "
                "'unstated' is refused: a posting that names no arrangement is "
                "always kept and flagged, because about half of them name none."
            )

    if cfg.salary.currency not in CURRENCIES:
        raise ConfigError(
            f"salary.currency is {cfg.salary.currency!r}. Accepted: "
            f"{', '.join(CURRENCIES)}. Other currencies are never converted."
        )
    if cfg.salary.floor is not None and cfg.salary.floor < 0:
        raise ConfigError("salary.floor cannot be negative")

    for db in cfg.dealbreakers:
        if not db.pattern:
            raise ConfigError(f"dealbreaker {db.name!r} has no pattern")
        try:
            db.regex = re.compile(db.pattern, re.IGNORECASE)
        except re.error as exc:
            raise ConfigError(
                f"dealbreaker {db.name!r} has a broken pattern: {exc}. "
                "Left alone it would match nothing and look like a clean run."
            ) from exc

    # Checked on every load on purpose: a resume you moved should fail loudly
    # rather than quietly producing a document about a career you did not have.
    if cfg.resume_path:
        p = Path(cfg.resume_path).expanduser()
        if not p.is_file():
            raise ConfigError(
                f"resume.path points at {p}, which is not a file. "
                "Fix the path or clear the setting."
            )
        cfg.resume_path = str(p)

    for name in cfg.sources.keyless:
        if name not in ALL_SOURCES:
            raise ConfigError(
                f"sources.keyless has {name!r}. Known sources: "
                f"{', '.join(ALL_SOURCES)}."
            )

    for i, company in enumerate(cfg.sources.companies):
        if not company.name or not company.platform or not company.token:
            raise ConfigError(
                f"sources.companies[{i}] needs name, platform and token. "
                "Use `jobdork discover <employer>` to find the token — board "
                "tokens rarely match company names."
            )
        if company.platform not in KEYLESS_SOURCES:
            raise ConfigError(
                f"sources.companies[{i}] platform is {company.platform!r}. "
                f"Employer boards: {', '.join(KEYLESS_SOURCES)}."
            )

    # Normalised, not merely validated: 'markdown' and 'md' must not reach the
    # writer as two different strings, or one of them silently writes nothing.
    normalised: list[str] = []
    for fmt in cfg.output.formats:
        canonical = OUTPUT_FORMATS.get(fmt)
        if canonical is None:
            raise ConfigError(
                f"output.formats has {fmt!r}. Accepted: "
                f"{', '.join(sorted(set(OUTPUT_FORMATS.values())))}."
            )
        if canonical not in normalised:
            normalised.append(canonical)
    cfg.output.formats = normalised

    if cfg.fetch.concurrency < 1:
        raise ConfigError("fetch.concurrency must be at least 1")
    if cfg.fetch.concurrency > 64:
        cfg.warnings.append(
            f"fetch.concurrency {cfg.fetch.concurrency} capped to 64. "
            "That limit is about your own sockets, not their servers."
        )
        cfg.fetch.concurrency = 64
    if cfg.fetch.timeout < 1:
        raise ConfigError("fetch.timeout must be at least 1 second")
    if cfg.fetch.retries < 0:
        raise ConfigError("fetch.retries cannot be negative")


def _str_list(value: Any, field_name: str) -> list[str]:
    """Accept a list, or a single string, and reject anything else loudly."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if item is None:
                continue
            if not isinstance(item, (str, int, float)):
                raise ConfigError(f"{field_name} contains a {type(item).__name__}")
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    raise ConfigError(f"{field_name} must be a list of strings")
