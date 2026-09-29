#!/usr/bin/env python3
"""
build_gazetteer.py
==================
Builds `jobdork/data/cities.csv` — the offline place list the radius filter
measures against.

Run once, and again whenever you want it refreshed:

    python scripts/build_gazetteer.py

Source is GeoNames `cities5000` (CC BY 4.0). Every place with 5,000 people or
more, which is every place a job is advertised in and few that are not. It
ships in the repository, so the radius needs no geocoding API, no key and no
per-role network call.

It also writes `jobdork/data/regions.csv`, every country's first-level regions
by name (GeoNames `admin1CodesASCII`), which the dashboard's Country, Region,
City picker lists. Each city row carries its region code in a sixth column.

Rows are written most-populous first. `geo.py` keeps the first entry for a
(city, state) pair, so a collision resolves to the city people actually mean.
"""

from __future__ import annotations

import csv
import io
import re
import sys
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

URL = "https://download.geonames.org/export/dump/cities5000.zip"
ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
COUNTRY_URL = "https://download.geonames.org/export/dump/countryInfo.txt"
OUT = Path(__file__).resolve().parent.parent / "jobdork" / "data" / "cities.csv"
REGIONS_OUT = OUT.parent / "regions.csv"

# GeoNames numbers Canadian provinces rather than lettering them, so admin1
# comes back as "08" where the rest of the world would say "ON". Australia is
# numbered too. Everywhere else, admin1 is either a usable code or a number
# that means nothing to a job posting, and the country alone identifies it.
ADMIN1_FIXUPS = {
    "CA": {"01": "AB", "02": "BC", "03": "MB", "04": "NB", "05": "NL",
           "07": "NS", "08": "ON", "09": "PE", "10": "QC", "11": "SK",
           "12": "YT", "13": "NT", "14": "NU"},
    "AU": {"01": "ACT", "02": "NSW", "03": "NT", "04": "QLD", "05": "SA",
           "06": "TAS", "07": "VIC", "08": "WA"},
}

# Countries whose region code is worth keeping. Elsewhere a posting says
# "Makati, Philippines" rather than naming a province, so the region is left
# blank and the country does the work.
CODED_REGIONS = {"US", "CA", "AU"}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Build the offline place list the radius filter uses.")
    parser.add_argument(
        "countries", nargs="*", default=[],
        help="ISO alpha-2 codes to include, e.g. PH SG. "
             "Default: read locations.countries from your config; "
             "'all' for every country.")
    parser.add_argument(
        "--source", default="",
        help="a folder already holding cities5000.zip and admin1CodesASCII.txt, "
             "instead of downloading them")
    args = parser.parse_args(argv)

    wanted = _wanted_countries(args.countries)
    if wanted:
        print(f"including: {', '.join(sorted(wanted))}")
    else:
        print("including: every country")

    return _build(wanted, Path(args.source) if args.source else None)


def _wanted_countries(requested: list[str]) -> set[str]:
    if requested and requested[0].lower() == "all":
        return set()
    if requested:
        return {c.upper() for c in requested}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from jobdork import config
        cfg = config.load(require=False)
        if cfg.locations.countries:
            return set(cfg.locations.countries)
    except Exception as exc:
        print(f"could not read config ({exc}); building for every country",
              file=sys.stderr)
    return set()


_LATIN = re.compile(r"^[A-Za-zÀ-ÿĀ-ž .'’-]+$")


def _fold(text: str) -> str:
    """The same folding geo.py does, so redundant aliases are never written."""
    text = unicodedata.normalize("NFKD", (text or "").strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _aliases(name: str, asciiname: str, alternates: str) -> list[str]:
    """Other names for a place that a job posting might use.

    Only names that actually fold differently are written. 'Zürich' needs no
    'Zurich' row because the lookup strips accents on both sides; writing one
    anyway inflated the file to 5.7MB *and* made São Paulo look like two
    different places, so the ambiguity check refused to resolve it.

    What is worth a row:

      the "City" suffix     'Makati City' -> 'Makati'
      endonyms              'Munich' -> 'München'

    Endonyms matter more than they look. GeoNames files Munich under its
    English name, so a German posting saying "München, Germany" places nowhere
    without one.
    """
    out: list[str] = []
    seen = {_fold(name)}

    def add(candidate: str) -> None:
        candidate = candidate.strip()
        folded = _fold(candidate)
        if (folded and folded not in seen
                and len(candidate) <= 30 and _LATIN.match(candidate)):
            seen.add(folded)
            out.append(candidate)

    for base in (name, asciiname):
        if base and base.lower().endswith(" city"):
            add(base[: -len(" city")])

    # GeoNames `alternatenames` is deliberately NOT used. It is unordered and
    # runs to hundreds of scripts per city, so taking the first few Latin
    # entries added four megabytes and still missed München — the entry exists,
    # just not near the front. Local spellings are handled by the curated
    # exonym table in geo.py instead, which costs nothing and covers the
    # cities that actually advertise jobs.
    return out


def _fetch(url: str, source: Path | None) -> bytes:
    local = source / url.rsplit("/", 1)[1] if source else None
    if local and local.is_file():
        print(f"reading {local}")
        return local.read_bytes()
    print(f"downloading {url} ...")
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def _region_code(country: str, admin1: str) -> str:
    """The code a city row carries: lettered where a posting uses one."""
    return ADMIN1_FIXUPS.get(country, {}).get(admin1, admin1)


def _build(wanted: set[str], source: Path | None = None) -> int:
    try:
        payload = _fetch(URL, source)
        admin1_text = _fetch(ADMIN1_URL, source).decode("utf-8")
        country_text = _fetch(COUNTRY_URL, source).decode("utf-8")
    except OSError as exc:
        print(f"download failed: {exc}", file=sys.stderr)
        print("The bundled fallback list still works; the radius is just "
              "limited to the metros in geo.py.", file=sys.stderr)
        return 1

    # "PH.15<tab>Cordillera<tab>..." -> ("PH", "15"): "Cordillera"
    region_names: dict[tuple[str, str], str] = {}
    for line in admin1_text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 3 and "." in cols[0]:
            country, admin1 = cols[0].split(".", 1)
            region_names[(country, _region_code(country, admin1))] = cols[2] or cols[1]

    # "PH<tab>PHL<tab>608<tab>RP<tab>Philippines<tab>...<tab>PHP<tab>..."
    # Column 5 is the English name and column 11 the currency code.
    country_names: dict[str, str] = {}
    currencies: dict[str, str] = {}
    for line in country_text.splitlines():
        cols = line.split("\t")
        if len(cols) > 10 and not line.startswith("#"):
            country_names[cols[0]] = cols[4]
            currencies[cols[0]] = cols[10]

    rows: list[tuple[int, str, str, str, str, str, str]] = []
    with (zipfile.ZipFile(io.BytesIO(payload)) as archive,
          archive.open("cities5000.txt") as handle):
        for raw in io.TextIOWrapper(handle, encoding="utf-8"):
            cols = raw.rstrip("\n").split("\t")
            if len(cols) < 15:
                continue
            country = cols[8]
            if wanted and country not in wanted:
                continue

            admin1 = cols[10]
            region = _region_code(country, admin1)
            if (country, region) not in region_names:
                region = ""        # "00" and the like: no named region
            state = region
            if country in CODED_REGIONS:
                # A numeric admin1 that has no fixup is not a region code
                # anybody writes in a posting, so it is dropped.
                if not state or state.isdigit() or len(state) > 3:
                    continue
            else:
                # Elsewhere a posting names the country, not a region code,
                # so `state` stays blank; the region is kept in its own
                # column for the dashboard's picker.
                state = ""

            try:
                population = int(cols[14] or 0)
            except ValueError:
                population = 0

            lat, lon = cols[4], cols[5]
            name = cols[1]
            rows.append((population, name, state, country, lat, lon, region))

            # Postings do not always use the gazetteer's spelling. Extra
            # rows are written for the names people actually type; geo.py
            # keeps the first entry per (name, region), and rows are
            # sorted most-populous first, so an alias never outranks a
            # bigger city of the same name.
            for alias in _aliases(name, cols[2], cols[3]):
                rows.append((population - 1, alias, state, country, lat, lon, region))

    if not rows:
        print("no rows parsed — the file format may have changed", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: -r[0])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["# city", "state", "country", "lat", "lon", "region"])
        for _pop, city, state, country, lat, lon, region in rows:
            writer.writerow([city, state, country, lat, lon, region])

    # Only regions that hold at least one listed city: a region with nothing
    # in it would be a choice that leads to an empty city list.
    used = {(r[3], r[6]) for r in rows if r[6]}
    with REGIONS_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["# country", "code", "name", "currency"])
        # A blank code is the country itself: its English name and currency.
        for country in sorted({r[3] for r in rows}):
            if country in country_names:
                writer.writerow([country, "", country_names[country],
                                 currencies.get(country, "")])
        for (country, code), name in sorted(region_names.items(),
                                            key=lambda kv: (kv[0][0], kv[1])):
            if (country, code) in used:
                writer.writerow([country, code, name])

    by_country: dict[str, int] = {}
    for row in rows:
        by_country[row[3]] = by_country.get(row[3], 0) + 1
    top = sorted(by_country.items(), key=lambda kv: -kv[1])[:8]
    print(f"wrote {OUT} — {len(rows)} places across {len(by_country)} countries, "
          f"{OUT.stat().st_size // 1024}KB")
    print("  " + ", ".join(f"{c} {n}" for c, n in top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
