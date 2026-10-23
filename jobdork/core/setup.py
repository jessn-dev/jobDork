"""
jobdork.core.setup
==================
First run: the steps a new user is walked through, and the one place a config
file is written from answers, whether they come from the dashboard or from
`jobdork setup` in a terminal.

Progress is kept in the config file itself, as `setup: {step: <next step>}`,
so a wizard closed halfway resumes where it stopped, in the browser or the
terminal alike. Finishing removes the section. A config without it counts as
set up, which is every config written before the wizard existed.

There is no config until the first answer is saved: nothing is copied from
the example, so nobody starts out searching for somebody else's job titles.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..search import geo
from . import config as config_mod

# (name, what the user sees). The order is the order they are asked.
STEPS = (
    ("welcome", "Welcome"),
    ("resume", "Your resume"),
    ("ai", "AI"),
    ("search", "What you are looking for"),
    ("where", "Where"),
    ("pay", "Pay and job sources"),
    ("scan", "First scan"),
)
STEP_NAMES = tuple(name for name, _ in STEPS)
DONE = "done"

# Steps that cannot be passed without an answer. The resume is the one: every
# later step, and every score, reads it.
REQUIRED = {"resume": "upload your resume first",
            "search": "give at least one job title to search for",
            "where": "choose the country and city you are in"}

# When the AI test passes in setup, every scan has the model read this many
# of the best new job posts (llm.judge_on_scan, llm.judge_top). The page's
# SETUP_JUDGE_TOP says the same number.
JUDGE_TOP = 15

# Below this many characters a resume has probably lost most of itself on the
# way in (a two-column PDF, a table layout): shown, so the user can look.
THIN_RESUME = 800


def resume_note(chars: int) -> str:
    """A word about a resume that read thin, or nothing."""
    if chars >= THIN_RESUME:
        return ""
    return (f"Only {chars:,} characters were read. If parts of your resume are "
            "missing below, export it again as Word or as a plain PDF and "
            "upload that.")


def title(step: str) -> str:
    return dict(STEPS).get(step, step)


def next_step(step: str) -> str:
    """The step after this one, or DONE after the last."""
    at = STEP_NAMES.index(step)
    return STEP_NAMES[at + 1] if at + 1 < len(STEP_NAMES) else DONE


def _check_required(data: dict, step: str) -> None:
    """Refuse moving past a required step that has no answer yet."""
    reached = len(STEP_NAMES) if step == DONE else STEP_NAMES.index(step)
    resume = (data.get("resume") or {}).get("path") or ""
    if reached > STEP_NAMES.index("resume") and not Path(resume).expanduser().is_file():
        raise ValueError(REQUIRED["resume"])
    if reached > STEP_NAMES.index("search") and not (data.get("titles") or {}).get("include"):
        raise ValueError(REQUIRED["search"])
    if reached > STEP_NAMES.index("where") and not (data.get("locations") or {}).get("anchor"):
        raise ValueError(REQUIRED["where"])


def write(path: str, payload: dict) -> config_mod.Config:
    """Apply `payload` to the config at `path`, then re-read it to prove it.

    The file is created on the first save. An edit that would not survive
    `jobdork scan` is refused, and a refused edit leaves the file exactly as
    it was, or absent if it was absent.
    """
    target = Path(path)
    existed = target.is_file()
    original = target.read_text(encoding="utf-8") if existed else ""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rewrite(original, payload), encoding="utf-8")
    except OSError as exc:
        hint = (" The folder mapped to /app/data must be writable by user 1000 "
                "(chown -R 1000:1000 on the host)."
                if config_mod.in_container() else "")
        raise ValueError(f"cannot write {target}: {exc}.{hint}") from exc
    try:
        return config_mod.load(str(target))
    except Exception:
        if existed:
            target.write_text(original, encoding="utf-8")      # put it back
        else:
            target.unlink(missing_ok=True)
        raise


def _deal_row(d: dict) -> dict:
    """One dealbreaker as config.yaml holds it: words, or an advanced pattern."""
    words = d.get("words") or []
    if isinstance(words, str):
        words = words.split(",")
    row = {"name": str(d.get("name") or "").strip()}
    words = [str(w).strip() for w in words if str(w).strip()]
    if words:
        row["words"] = words
    else:
        row["pattern"] = str(d.get("pattern") or "")
    row["hard"] = str(d.get("hard")).lower() in ("1", "true", "yes", "on")
    return row



def rewrite(original: str, payload: dict) -> str:
    """Replace the editable settings in a config file, keeping its comments.

    Rewritten as text rather than dumped through YAML, because a dump strips
    every comment out of a file that is mostly comments explaining what the
    settings mean.
    """
    data = yaml.safe_load(original) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml is not a mapping")
    if not original.strip():
        # A new config: no place and every country until the Where step, so
        # nobody starts out measured from the built-in default's Naperville
        # or limited to the United States.
        data["locations"] = {"anchor": "", "countries": []}

    titles = data.setdefault("titles", {})
    if "titles_include" in payload:
        titles["include"] = [str(t).strip() for t in payload["titles_include"]
                             if str(t).strip()]
    if "titles_exclude" in payload:
        titles["exclude"] = [str(t).strip() for t in payload["titles_exclude"]
                             if str(t).strip()]

    locations = data.setdefault("locations", {})
    if "anchor_pick" in payload:
        # The picker's three choices, written as text resolve() reads back.
        # A city not in the gazetteer is refused rather than saved unplaced,
        # which would quietly turn the radius off.
        pick = payload["anchor_pick"] or {}
        city = str(pick.get("city") or "").strip()
        country = str(pick.get("country") or "").strip().upper()
        region = str(pick.get("region") or "").strip().upper()
        if not city or not country:
            raise ValueError("choose a country and a city")
        anchor = geo.picker_anchor(city, region, country)
        where = geo.resolve_anchor(anchor, (country,))
        if (not where.located or where.country != country
                or (region and geo.region_at(where) != region)):
            raise ValueError(f"{city!r} is not in the place list for that "
                             "country and region; choose one from the suggestions")
        payload = {**payload, "anchor": anchor}
    for key, field in (("anchor", "anchor"), ("radius", "radius"),
                       ("units", "units"), ("countries", "countries"),
                       ("work_modes", "work_modes")):
        if key in payload:
            locations[field] = payload[key]

    salary = data.setdefault("salary", {})
    if "salary_floor" in payload:
        floor = payload["salary_floor"]
        salary["floor"] = None if floor in (None, "", "null") else float(floor)
    if "currency" in payload:
        salary["currency"] = str(payload["currency"]).upper()

    if "show_days" in payload:
        # How old a post Job posts shows; 0 or empty shows every age.
        days = payload["show_days"]
        data.setdefault("freshness", {})["show_days"] = \
            0 if days in (None, "", "null") else int(days)

    # Whole lists, as the page's tables hold them after an add or a delete.
    # Named fields only; the loader then refuses a broken pattern, a missing
    # token or an unknown board type, and the file is put back.
    if "dealbreakers" in payload:
        data["dealbreakers"] = [_deal_row(d) for d in payload["dealbreakers"] or []
                                if isinstance(d, dict)]
    if "companies" in payload:
        data.setdefault("sources", {})["companies"] = [
            {"name": str(c.get("name") or "").strip(),
             "platform": str(c.get("platform") or "").strip().lower(),
             "token": str(c.get("token") or "").strip()}
            for c in payload["companies"] or [] if isinstance(c, dict)]

    if "industries" in payload:
        # Which built-in employer boards to read; none ticked is every industry.
        data.setdefault("sources", {}).setdefault("directory", {})["industries"] = [
            str(i).strip().lower() for i in payload["industries"] or [] if str(i).strip()]
    if "directory_enabled" in payload or "directory_skip" in payload:
        directory = data.setdefault("sources", {}).get("directory")
        # `directory: false` is the short way of writing it off.
        if not isinstance(directory, dict):
            directory = {"enabled": directory is not False}
            data["sources"]["directory"] = directory
        if "directory_enabled" in payload:
            directory["enabled"] = str(payload["directory_enabled"]).lower() in (
                "1", "true", "yes", "on")
        if "directory_skip" in payload:
            directory["skip"] = sorted({str(n).strip() for n in payload["directory_skip"] or []
                                        if str(n).strip()}, key=str.casefold)

    if "update_check" in payload:
        data["update_check"] = str(payload["update_check"]).lower() in (
            "1", "true", "yes", "on")

    if "credentials" in payload:
        data["credentials"] = [str(c).strip() for c in payload["credentials"] or []
                               if str(c).strip()]

    if "resume_path" in payload:
        data.setdefault("resume", {})["path"] = payload["resume_path"]

    if "llm" in payload:
        given = payload["llm"] or {}
        section = data.setdefault("llm", {})
        # Named fields only: whatever else the page sends, a key included,
        # never reaches the file.
        for key, cast in (("provider", str), ("model", str),
                          ("ollama_url", str), ("judge_top", int),
                          ("checker_provider", str), ("checker_model", str)):
            if key in given:
                section[key] = cast(given[key]).strip() if cast is str \
                    else cast(given[key])
        for key in ("judge_on_scan", "read_pages", "guard"):
            if key in given:
                section[key] = str(given[key]).lower() in ("1", "true", "yes", "on")

    if "setup_step" in payload:
        step = str(payload["setup_step"] or "").strip()
        if step == DONE:
            _check_required(data, step)
            data.pop("setup", None)
        elif step in STEP_NAMES:
            _check_required(data, step)
            data["setup"] = {"step": step}
        else:
            raise ValueError(f"no setup step {step!r}")

    # Sections opened above and left empty say nothing; a first save would
    # otherwise write `titles: {}` and the like.
    data = {k: v for k, v in data.items() if v != {}}
    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                            default_flow_style=False)
    header = (
        "# Written by jobdork, from the dashboard or `jobdork setup`.\n"
        "# Comments from a hand-edited config are not preserved through a\n"
        "# save; keep annotations in config.local.yaml if you want them.\n"
        "# API keys are never written to this file; they live in .env.\n\n"
    )
    return header + dumped
