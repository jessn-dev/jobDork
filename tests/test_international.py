"""
Tests for readers outside the United States.

The first version of this tool hardcoded two countries and carried a list of
"foreign" ones to drop. That design would have silently deleted a Manila
reader's entire market, so these tests exist to keep the country model
symmetric: out of scope means "not in YOUR countries", and nothing else.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork import geo, screen
from jobdork.config import Config, Locations, Salary
from jobdork.fetch import adzuna, usajobs, workable
from jobdork.store import Role


def _cfg(anchor: str, countries: list[str], radius=25, units="") -> Config:
    cfg = Config(
        titles_include=["software engineer"],
        locations=Locations(anchor=anchor, radius=radius, units=units,
                            countries=countries),
        salary=Salary(),
    )
    if not cfg.locations.units:
        cfg.locations.units = geo.default_units(countries)
    return cfg


# ── the country model is symmetric ─────────────────────────────────────────────

def test_a_us_posting_is_out_of_scope_for_a_manila_reader():
    """The mirror of dropping Berlin for a Chicago reader."""
    cfg = _cfg("Makati, Philippines", ["PH"])
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", location_raw="Chicago, Illinois, United States",
                work_mode="office")
    verdict = screen.screen(role, cfg)
    assert not verdict.keep
    assert "US" in verdict.reasons[0]


def test_a_manila_posting_is_kept_for_a_manila_reader():
    cfg = _cfg("Makati, Philippines", ["PH"])
    role = Role(platform="workable", title="Software Engineer",
                url="https://x.test/1", location_raw="Makati, Philippines",
                work_mode="office")
    assert screen.screen(role, cfg).keep


def test_empty_countries_accepts_everywhere():
    """Somebody with no geographic constraint means it."""
    cfg = _cfg("", [], radius="exact")
    for place in ("Berlin, Germany", "Singapore", "Chicago, IL", "Sydney, NSW"):
        role = Role(platform="workable", title="Software Engineer",
                    url=f"https://x.test/{place}", location_raw=place,
                    work_mode="remote")
        assert screen.screen(role, cfg).keep, place


# ── resolution ─────────────────────────────────────────────────────────────────

def test_cities_resolve_across_regions():
    for text, prefer, country in (
        ("Makati, Philippines", ("PH",), "PH"),
        ("Singapore", ("SG",), "SG"),
        ("Berlin, Germany", ("DE",), "DE"),
        ("Sydney, NSW", ("AU",), "AU"),
        ("Auckland, New Zealand", ("NZ",), "NZ"),
        ("Mumbai", ("IN",), "IN"),
        ("London, United Kingdom", ("GB",), "GB"),
        ("Chicago, IL", ("US",), "US"),
    ):
        resolved = geo.resolve(text, prefer)
        assert resolved.country == country, f"{text!r} -> {resolved.country}"
        assert resolved.located, f"{text!r} did not place"


def test_english_exonyms_and_local_spellings_are_the_same_city():
    """'Munich' and 'München' share almost no letters."""
    for local, english, prefer in (
        ("München", "Munich", ("DE",)),
        ("Den Haag", "The Hague", ("NL",)),
        ("Bombay", "Mumbai", ("IN",)),
        ("Genève", "Geneva", ("CH",)),
    ):
        a, b = geo.resolve(local, prefer), geo.resolve(english, prefer)
        assert a.located and b.located, (local, english)
        assert abs(a.lat - b.lat) < 0.2 and abs(a.lon - b.lon) < 0.2, (local, english)


def test_accents_fold_both_ways():
    for a, b, prefer in (("Zurich", "Zürich", ("CH",)),
                         ("Sao Paulo", "São Paulo", ("BR",))):
        one, two = geo.resolve(a, prefer), geo.resolve(b, prefer)
        assert one.located and two.located, (a, b)
        assert abs(one.lat - two.lat) < 0.2, (a, b)


def test_a_country_name_alone_is_not_a_city():
    """There is a town called Australia, in Cuba, with 3,000 people."""
    resolved = geo.resolve("Remote - Australia", ("AU",))
    assert resolved.country == "AU"
    assert not resolved.located


def test_city_states_resolve_as_cities():
    """In Singapore the country name is also the city name."""
    resolved = geo.resolve("Singapore", ("SG",))
    assert resolved.country == "SG" and resolved.located


def test_city_suffix_is_optional():
    a = geo.resolve("Makati", ("PH",))
    b = geo.resolve("Makati City", ("PH",))
    assert a.located and b.located
    assert abs(a.lat - b.lat) < 0.2


# ── ambiguity ──────────────────────────────────────────────────────────────────

def test_wa_means_different_things_to_different_readers():
    """Washington to a Seattle reader, Western Australia to one in Perth."""
    assert geo.resolve("Seattle, WA", ("US",)).country == "US"
    assert geo.resolve("Perth, WA", ("AU",)).country == "AU"
    # And each still resolves correctly for the other reader, because the
    # city settles it before the region code has to.
    assert geo.resolve("Perth, WA", ("US", "AU")).country == "AU"


# ── units ──────────────────────────────────────────────────────────────────────

def test_units_default_by_country():
    assert geo.default_units(["US"]) == "mi"
    assert geo.default_units(["GB"]) == "mi"
    assert geo.default_units(["PH"]) == "km"
    assert geo.default_units(["DE"]) == "km"
    assert geo.default_units(["SG"]) == "km"


def test_a_km_radius_is_converted_not_taken_literally():
    """25 km is 15.5 miles. Treating it as 25 miles searches 2.6x the area."""
    cfg = _cfg("Berlin, Germany", ["DE"], radius=25)
    assert cfg.locations.units == "km"
    assert abs(cfg.radius_miles() - 15.53) < 0.05


def test_miles_config_is_unchanged():
    cfg = _cfg("Chicago, IL", ["US"], radius=25)
    assert cfg.locations.units == "mi"
    assert abs(cfg.radius_miles() - 25.0) < 0.001


def test_km_radius_actually_filters_in_km():
    cfg = _cfg("Berlin, Germany", ["DE"], radius=30)   # 30 km ≈ 18.6 mi
    anchor = geo.resolve_anchor(cfg.locations.anchor, cfg.country_prefs())
    near = Role(platform="w", title="Software Engineer", url="https://x.test/1",
                location_raw="Potsdam, Germany", work_mode="office")
    far = Role(platform="w", title="Software Engineer", url="https://x.test/2",
               location_raw="Hamburg, Germany", work_mode="office")
    assert screen.screen(near, cfg, anchor).keep, "Potsdam is ~25 km from Berlin"
    assert not screen.screen(far, cfg, anchor).keep, "Hamburg is ~250 km away"


# ── source routing ─────────────────────────────────────────────────────────────

def test_adzuna_follows_your_countries():
    assert adzuna._indexes(_cfg("Berlin, Germany", ["DE"])) == ["de"]
    assert adzuna._indexes(_cfg("Sydney, NSW", ["AU"])) == ["au"]
    assert adzuna._indexes(_cfg("Chicago, IL", ["US"])) == ["us"]


def test_adzuna_says_so_when_a_country_has_no_index():
    """There is no Philippine index. Silence would look like no jobs."""
    cfg = _cfg("Makati, Philippines", ["PH"])
    cfg.sources.adzuna_app_id = "x"
    cfg.sources.adzuna_app_key = "y"
    result = adzuna.fetch(None, cfg)
    assert result.skipped and "PH" in result.skipped


def test_usajobs_skips_outside_the_us():
    cfg = _cfg("Singapore", ["SG"])
    cfg.sources.usajobs_key = "x"
    cfg.sources.usajobs_email = "a@b.c"
    result = usajobs.fetch(None, cfg)
    assert result.skipped and "US federal" in result.skipped


def test_workable_queries_are_spelled_out_not_coded():
    """Workable ignores two-letter codes silently, returning the whole world."""
    assert workable.location_queries(_cfg("Sydney, NSW", ["AU"])) == ["New South Wales"]
    assert workable.location_queries(_cfg("Berlin, Germany", ["DE"])) == ["Berlin, Germany"]
    assert workable.location_queries(_cfg("Makati, Philippines", ["PH"])) == \
        ["Makati, Philippines"]


# ── metros outside North America ───────────────────────────────────────────────

def test_metros_resolve_worldwide():
    for text, prefer, _city in (
        ("Kanto", ("JP",), "Tokyo"),
        ("Klang Valley", ("MY",), "Kuala Lumpur"),
        ("Metro Manila", ("PH",), "Manila"),
        ("BGC", ("PH",), "Taguig"),
        ("Randstad", ("NL",), "Amsterdam"),
        ("Greater London", ("GB",), "London"),
        ("Gauteng", ("ZA",), "Johannesburg"),
        ("CDMX", ("MX",), "Mexico City"),
        ("Greater Sydney", ("AU",), "Sydney"),
        ("Ruhrgebiet", ("DE",), "Essen"),
        ("Jabodetabek", ("ID",), "Jakarta"),
        ("Öresund", ("DK",), "Copenhagen"),
    ):
        resolved = geo.resolve(text, prefer)
        assert resolved.located, text
        assert resolved.country == prefer[0], f"{text} -> {resolved.country}"
        assert resolved.approximate, f"{text} should be marked approximate"


def test_a_hyphenated_metro_survives_the_cleanup():
    """The cleanup turns hyphens into commas, and France is a country.

    Without an early check, 'Île-de-France' splits into three fragments and
    the last one is read as the country, leaving a city called 'Île'.
    """
    for text in ("Île-de-France", "Ile-de-France"):
        resolved = geo.resolve(text, ("FR",))
        assert resolved.city == "Paris", f"{text} -> {resolved.city}"


def test_one_metro_name_three_countries():
    """NCR is the National Capital Region in Canada, India and the Philippines."""
    assert geo.resolve("NCR", ("CA",)).city == "Ottawa"
    assert geo.resolve("NCR", ("PH",)).city == "Manila"
    assert geo.resolve("NCR", ("IN",)).city == "New Delhi"
    # With no countries configured it still resolves rather than giving up.
    assert geo.resolve("NCR", ()).located


def test_north_american_metros_are_unchanged():
    for text, city in (("GTA", "Toronto"), ("DMV", "Washington"),
                       ("Silicon Valley", "San Jose"), ("DFW", "Dallas"),
                       ("Bay Area", "San Francisco")):
        assert geo.resolve(text, ("US", "CA")).city == city, text


# ── locations.exclude ──────────────────────────────────────────────────────────

def _dropped(exclude, location, countries=("US",)) -> bool:
    cfg = Config(
        titles_include=["engineer"],
        locations=Locations(anchor="", radius="exact", units="mi",
                            countries=list(countries), exclude=list(exclude)),
        salary=Salary(),
    )
    role = Role(platform="w", title="Engineer", url=f"https://x.test/{location}",
                location_raw=location, work_mode="office")
    return not screen.screen(role, cfg).keep


def test_exclude_matches_a_region_however_it_is_written():
    """A substring match was too literal: postings say 'Texas', configs say TX."""
    assert _dropped(["TX"], "Austin, Texas")
    assert _dropped(["Texas"], "Austin, TX")
    assert not _dropped(["TX"], "Chicago, Illinois")


def test_exclude_matches_a_city_and_the_metro_that_stands_for_it():
    assert _dropped(["Chicago"], "Chicago, IL")
    assert not _dropped(["Chicago"], "Austin, TX")
    assert _dropped(["Bay Area"], "San Francisco, CA")


def test_exclude_matches_a_country():
    assert _dropped(["Canada"], "Toronto, Ontario, Canada", ("US", "CA"))


def test_exclude_still_takes_an_arbitrary_phrase():
    assert _dropped(["Bee Cave"], "Bee Cave, Texas")


# ── keep this block LAST ───────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
