"""
jobdork.geo
===========
Turns a posting's location string into somewhere on a map, then measures how
far that is from your anchor.

Almost no job source supports a radius. Adzuna does, in kilometres, and
USAJOBS does, in miles. Everything else — Workable's search, every employer
board, and every Google result you click — hands back a string like
"San Francisco, CA" or "Remote - US". So the radius is computed here, against
a gazetteer that ships with the tool: no geocoding API, no key, no rate limit,
and no per-role network call.

Two rules worth stating up front, because they are the difference between a
filter and a shredder:

  A location that cannot be resolved is KEPT and flagged. "We could not read
  it" is not evidence the job is somewhere else.

  A remote role bypasses the radius entirely. Distance from your house to a
  job that has no office is not a number that means anything.
"""

from __future__ import annotations

import csv
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
GAZETTEER = DATA_DIR / "cities.csv"

EARTH_RADIUS_MI = 3958.7613
KM_PER_MILE = 1.609344

# Countries that think in miles. Everywhere else a radius is kilometres, and
# telling a Berlin reader their search is "25 mi" is telling them nothing.
MILE_COUNTRIES = ("US", "GB", "LR", "MM")

# ── State and province codes ───────────────────────────────────────────────────

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN",
    "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "puerto rico": "PR", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI",
    "wyoming": "WY",
}

CA_PROVINCES = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB",
    "new brunswick": "NB", "newfoundland and labrador": "NL",
    "newfoundland": "NL", "northwest territories": "NT", "nova scotia": "NS",
    "nunavut": "NU", "ontario": "ON", "prince edward island": "PE",
    "quebec": "QC", "québec": "QC", "saskatchewan": "SK", "yukon": "YT",
}

# Australian postings abbreviate their states the way American ones do.
AU_STATES = {
    "new south wales": "NSW", "victoria": "VIC", "queensland": "QLD",
    "western australia": "WA", "south australia": "SA", "tasmania": "TAS",
    "northern territory": "NT", "australian capital territory": "ACT",
}

# Countries whose postings routinely name a region by code. Everywhere else,
# a posting says "Berlin, Germany" or "Makati, Philippines" and the country
# name is what identifies it.
REGIONS: dict[str, dict[str, str]] = {
    "US": US_STATES,
    "CA": CA_PROVINCES,
    "AU": AU_STATES,
}

# Abbreviations people actually write, including the ones that collide.
# Keys are dotless: normalise_state strips periods before looking them up,
# so "D.C." and "DC" are the same key.
STATE_ALIASES = {
    "calif": "CA", "cali": "CA", "wash": "WA", "mass": "MA", "penn": "PA",
    "conn": "CT", "fla": "FL", "ill": "IL", "tenn": "TN",
    "dc": "DC", "washington dc": "DC",
}

US_CODES = set(US_STATES.values())
CA_CODES = set(CA_PROVINCES.values())
AU_CODES = set(AU_STATES.values())

# Region codes that mean different things in different countries. "WA" is
# Washington in a US posting and Western Australia in an Australian one, and
# nothing in the string itself can tell you which. The reader's configured
# countries break the tie; without that hint the first match wins.
AMBIGUOUS_REGIONS = {"WA": ("US", "AU"), "NT": ("CA", "AU"), "SA": ("AU",)}

# Code back to the spelled-out name. Some search APIs — Workable's is one —
# take "Texas" and ignore "TX".
STATE_NAMES: dict[str, str] = {
    code: name.title()
    for name, code in (list(US_STATES.items()) + list(CA_PROVINCES.items())
                       + list(AU_STATES.items()))
}
STATE_NAMES["DC"] = "District of Columbia"
STATE_NAMES["QC"] = "Quebec"
STATE_NAMES["NL"] = "Newfoundland and Labrador"

def state_name(code: str) -> str:
    """'TX' -> 'Texas'. Returns the input when it is not a code we know."""
    return STATE_NAMES.get((code or "").upper(), code or "")


def country_name(code: str) -> str:
    """'DE' -> 'Germany'. Spelled out, because search APIs want it that way.

    Workable's `location` silently ignores two-letter codes, so sending "DE"
    returns the whole world and looks like it worked.
    """
    code = (code or "").upper()
    for name, iso in COUNTRY_CODES.items():
        if iso == code:
            return name.title()
    return code

# ── Metro names that are not cities ────────────────────────────────────────────
# Postings say "Bay Area" far more often than they say "San Francisco, CA".
# Each maps to an anchor point, which is an approximation and marked as one.

METRO_ALIASES: dict[str, tuple[str, str]] = {
    "bay area": ("San Francisco", "CA"),
    "sf bay area": ("San Francisco", "CA"),
    "san francisco bay area": ("San Francisco", "CA"),
    "silicon valley": ("San Jose", "CA"),
    "socal": ("Los Angeles", "CA"),
    "southern california": ("Los Angeles", "CA"),
    "norcal": ("San Francisco", "CA"),
    "greater los angeles": ("Los Angeles", "CA"),
    "la metro": ("Los Angeles", "CA"),
    "nyc": ("New York", "NY"),
    "new york city": ("New York", "NY"),
    "manhattan": ("New York", "NY"),
    "brooklyn": ("New York", "NY"),
    "queens": ("New York", "NY"),
    "tri-state area": ("New York", "NY"),
    "tri state area": ("New York", "NY"),
    "greater new york": ("New York", "NY"),
    "dmv": ("Washington", "DC"),
    "dmv area": ("Washington", "DC"),
    "dc metro": ("Washington", "DC"),
    "washington metro": ("Washington", "DC"),
    "northern virginia": ("Arlington", "VA"),
    "nova": ("Arlington", "VA"),
    "greater boston": ("Boston", "MA"),
    "greater chicago": ("Chicago", "IL"),
    "chicagoland": ("Chicago", "IL"),
    "dfw": ("Dallas", "TX"),
    "dallas-fort worth": ("Dallas", "TX"),
    "dallas fort worth": ("Dallas", "TX"),
    "metroplex": ("Dallas", "TX"),
    "greater houston": ("Houston", "TX"),
    "greater atlanta": ("Atlanta", "GA"),
    "metro atlanta": ("Atlanta", "GA"),
    "research triangle": ("Raleigh", "NC"),
    "rtp": ("Raleigh", "NC"),
    "triangle area": ("Raleigh", "NC"),
    "twin cities": ("Minneapolis", "MN"),
    "pnw": ("Seattle", "WA"),
    "pacific northwest": ("Seattle", "WA"),
    "puget sound": ("Seattle", "WA"),
    "greater seattle": ("Seattle", "WA"),
    "front range": ("Denver", "CO"),
    "greater denver": ("Denver", "CO"),
    "greater phoenix": ("Phoenix", "AZ"),
    "valley of the sun": ("Phoenix", "AZ"),
    "greater philadelphia": ("Philadelphia", "PA"),
    "delaware valley": ("Philadelphia", "PA"),
    "south florida": ("Miami", "FL"),
    "tampa bay": ("Tampa", "FL"),
    "greater miami": ("Miami", "FL"),
    "greater austin": ("Austin", "TX"),
    "greater nashville": ("Nashville", "TN"),
    "greater detroit": ("Detroit", "MI"),
    "metro detroit": ("Detroit", "MI"),
    "greater portland": ("Portland", "OR"),
    "wasatch front": ("Salt Lake City", "UT"),
    "silicon slopes": ("Salt Lake City", "UT"),
    # Canada
    "gta": ("Toronto", "ON"),
    "greater toronto area": ("Toronto", "ON"),
    "greater toronto": ("Toronto", "ON"),
    "gva": ("Vancouver", "BC"),
    "metro vancouver": ("Vancouver", "BC"),
    "lower mainland": ("Vancouver", "BC"),
    "greater montreal": ("Montreal", "QC"),
    "national capital region": ("Ottawa", "ON"),
    "ncr": ("Ottawa", "ON"),
    "greater calgary": ("Calgary", "AB"),
}

# ── Fallback gazetteer ─────────────────────────────────────────────────────────
# Used when data/cities.csv has not been built. Enough to make the radius work
# out of the box in the metros most postings name; run `scripts/build_gazetteer.py`
# for the full ~4,500-place file.

_FALLBACK = """\
New York,NY,US,40.7143,-74.0060
Los Angeles,CA,US,34.0522,-118.2437
Chicago,IL,US,41.8500,-87.6501
Houston,TX,US,29.7633,-95.3633
Phoenix,AZ,US,33.4484,-112.0740
Philadelphia,PA,US,39.9526,-75.1652
San Antonio,TX,US,29.4241,-98.4936
San Diego,CA,US,32.7153,-117.1573
Dallas,TX,US,32.7831,-96.8067
San Jose,CA,US,37.3394,-121.8950
Austin,TX,US,30.2672,-97.7431
Jacksonville,FL,US,30.3322,-81.6557
Fort Worth,TX,US,32.7254,-97.3208
Columbus,OH,US,39.9612,-82.9988
Charlotte,NC,US,35.2271,-80.8431
San Francisco,CA,US,37.7749,-122.4194
Indianapolis,IN,US,39.7684,-86.1581
Seattle,WA,US,47.6062,-122.3321
Denver,CO,US,39.7392,-104.9903
Washington,DC,US,38.8951,-77.0364
Boston,MA,US,42.3584,-71.0598
El Paso,TX,US,31.7587,-106.4869
Nashville,TN,US,36.1659,-86.7844
Detroit,MI,US,42.3314,-83.0458
Oklahoma City,OK,US,35.4676,-97.5164
Portland,OR,US,45.5234,-122.6762
Las Vegas,NV,US,36.1750,-115.1372
Memphis,TN,US,35.1495,-90.0490
Louisville,KY,US,38.2542,-85.7594
Baltimore,MD,US,39.2904,-76.6122
Milwaukee,WI,US,43.0389,-87.9065
Albuquerque,NM,US,35.0844,-106.6504
Tucson,AZ,US,32.2226,-110.9747
Fresno,CA,US,36.7378,-119.7871
Sacramento,CA,US,38.5816,-121.4944
Mesa,AZ,US,33.4152,-111.8315
Kansas City,MO,US,39.0997,-94.5786
Atlanta,GA,US,33.7490,-84.3880
Omaha,NE,US,41.2565,-95.9345
Colorado Springs,CO,US,38.8339,-104.8214
Raleigh,NC,US,35.7796,-78.6382
Virginia Beach,VA,US,36.8529,-75.9780
Long Beach,CA,US,33.7701,-118.1937
Miami,FL,US,25.7617,-80.1918
Oakland,CA,US,37.8044,-122.2712
Minneapolis,MN,US,44.9778,-93.2650
Tulsa,OK,US,36.1540,-95.9928
Bakersfield,CA,US,35.3733,-119.0187
Wichita,KS,US,37.6872,-97.3301
Arlington,TX,US,32.7357,-97.1081
Tampa,FL,US,27.9506,-82.4572
New Orleans,LA,US,29.9511,-90.0715
Cleveland,OH,US,41.4993,-81.6944
Honolulu,HI,US,21.3069,-157.8583
Anaheim,CA,US,33.8366,-117.9143
Santa Ana,CA,US,33.7455,-117.8677
St. Louis,MO,US,38.6270,-90.1994
Pittsburgh,PA,US,40.4406,-79.9959
Cincinnati,OH,US,39.1031,-84.5120
Orlando,FL,US,28.5383,-81.3792
Salt Lake City,UT,US,40.7608,-111.8910
Irvine,CA,US,33.6846,-117.8265
Newark,NJ,US,40.7357,-74.1724
Jersey City,NJ,US,40.7178,-74.0431
Buffalo,NY,US,42.8864,-78.8784
Richmond,VA,US,37.5407,-77.4360
Boise,ID,US,43.6150,-116.2023
Des Moines,IA,US,41.5868,-93.6250
Madison,WI,US,43.0731,-89.4012
Reno,NV,US,39.5296,-119.8138
Arlington,VA,US,38.8816,-77.0910
Alexandria,VA,US,38.8048,-77.0469
Bellevue,WA,US,47.6101,-122.2015
Palo Alto,CA,US,37.4419,-122.1430
Mountain View,CA,US,37.3861,-122.0839
Sunnyvale,CA,US,37.3688,-122.0363
Santa Clara,CA,US,37.3541,-121.9552
Redwood City,CA,US,37.4852,-122.2364
San Mateo,CA,US,37.5630,-122.3255
Berkeley,CA,US,37.8715,-122.2730
Fremont,CA,US,37.5485,-121.9886
Pasadena,CA,US,34.1478,-118.1445
Santa Monica,CA,US,34.0195,-118.4912
Cambridge,MA,US,42.3736,-71.1097
Somerville,MA,US,42.3876,-71.0995
Stamford,CT,US,41.0534,-73.5387
Hartford,CT,US,41.7658,-72.6734
Providence,RI,US,41.8240,-71.4128
Durham,NC,US,35.9940,-78.8986
Charleston,SC,US,32.7765,-79.9311
Savannah,GA,US,32.0809,-81.0912
Birmingham,AL,US,33.5186,-86.8104
Little Rock,AR,US,34.7465,-92.2896
Boulder,CO,US,40.0150,-105.2705
Ann Arbor,MI,US,42.2808,-83.7430
Columbus,GA,US,32.4610,-84.9877
Plano,TX,US,33.0198,-96.6989
Irving,TX,US,32.8140,-96.9489
Scottsdale,AZ,US,33.4942,-111.9261
Tempe,AZ,US,33.4255,-111.9400
Toronto,ON,CA,43.7001,-79.4163
Montreal,QC,CA,45.5088,-73.5878
Vancouver,BC,CA,49.2827,-123.1207
Calgary,AB,CA,51.0447,-114.0719
Edmonton,AB,CA,53.5461,-113.4938
Ottawa,ON,CA,45.4215,-75.6972
Winnipeg,MB,CA,49.8951,-97.1384
Quebec City,QC,CA,46.8139,-71.2080
Hamilton,ON,CA,43.2557,-79.8711
Kitchener,ON,CA,43.4516,-80.4925
Waterloo,ON,CA,43.4643,-80.5204
London,ON,CA,42.9849,-81.2453
Halifax,NS,CA,44.6488,-63.5752
Victoria,BC,CA,48.4284,-123.3656
Saskatoon,SK,CA,52.1332,-106.6700
Regina,SK,CA,50.4452,-104.6189
Mississauga,ON,CA,43.5890,-79.6441
Brampton,ON,CA,43.7315,-79.7624
Markham,ON,CA,43.8561,-79.3370
Burnaby,BC,CA,49.2488,-122.9805
Richmond,BC,CA,49.1666,-123.1336
Surrey,BC,CA,49.1913,-122.8490
Laval,QC,CA,45.6066,-73.7124
Gatineau,QC,CA,45.4765,-75.7013
St. John's,NL,CA,47.5615,-52.7126
"""


@dataclass(frozen=True)
class Place:
    city: str
    state: str
    country: str
    lat: float
    lon: float


_INDEX: dict[tuple[str, str], Place] | None = None
_BY_CITY: dict[str, list[Place]] | None = None


def _load_gazetteer() -> tuple[dict[tuple[str, str], Place], dict[str, list[Place]]]:
    """Read the gazetteer once. Falls back to the bundled metros if unbuilt."""
    global _INDEX, _BY_CITY
    if _INDEX is not None and _BY_CITY is not None:
        return _INDEX, _BY_CITY

    index: dict[tuple[str, str], Place] = {}
    by_city: dict[str, list[Place]] = {}

    def add(city: str, state: str, country: str, lat: str, lon: str) -> None:
        try:
            place = Place(city, state.upper(), country.upper(), float(lat), float(lon))
        except ValueError:
            return
        key = (_key(city), place.state)
        # First entry wins. The builder writes most-populous first, so a
        # collision resolves to the city people actually mean.
        index.setdefault(key, place)

        # Two rows at the same coordinates are one place under two spellings,
        # not two candidates. Counting them separately made "São Paulo" look
        # ambiguous against its own alias and refused to resolve it.
        bucket = by_city.setdefault(_key(city), [])
        spot = (round(place.lat, 3), round(place.lon, 3))
        if not any((round(p.lat, 3), round(p.lon, 3)) == spot for p in bucket):
            bucket.append(place)

    if GAZETTEER.is_file():
        with GAZETTEER.open(encoding="utf-8", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) >= 5 and not row[0].startswith("#"):
                    add(*row[:5])
    else:
        for line in _FALLBACK.strip().splitlines():
            add(*line.split(","))

    _INDEX, _BY_CITY = index, by_city
    return index, by_city


def _key(text: str) -> str:
    """Fold a place name to something comparable.

    'St. Louis', 'St Louis' and 'Saint Louis' are one city; the gazetteer only
    spells it one way and postings spell it all three.

    Accents are folded too, because the gazetteer stores 'Zürich' and 'São
    Paulo' and a posting is as likely to write 'Zurich' and 'Sao Paulo'.
    """
    text = unicodedata.normalize("NFKD", (text or "").strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\bsaint\b", "st", text)
    text = re.sub(r"\bst\.\s*", "st ", text)
    text = re.sub(r"\bft\.?\s*", "fort ", text)
    text = re.sub(r"\bmt\.?\s*", "mount ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # 'München' and 'Munich' share almost no letters; folding cannot connect
    # them, so a small exonym table does it before the lookup.
    return _key_exonym(text)


def _key_exonym(folded: str) -> str:
    mapped = CITY_EXONYMS.get(folded)
    if not mapped:
        return folded
    m = unicodedata.normalize("NFKD", mapped.lower())
    m = "".join(c for c in m if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", m)).strip()


def normalise_state(text: str, prefer: tuple[str, ...] = ()) -> str:
    """'California', 'Calif', 'ca', 'D.C.' -> 'CA' / 'DC'.

    Periods go first, so "D.C." and "DC" resolve the same way. Without that
    "Washington, D.C." falls through to its second word and becomes
    Washington *state*, which is 2,300 miles wrong.

    `prefer` is your configured countries, and it settles ambiguous codes: WA
    is Washington to a US reader and Western Australia to an Australian one.
    """
    raw = re.sub(r"\.", "", (text or "").strip()).lower()
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return ""

    upper = raw.upper()
    # A bare code. Where it belongs to more than one country, the reader's
    # own countries decide.
    owners = [c for c, regions in REGIONS.items() if upper in set(regions.values())]
    if owners:
        if len(owners) > 1 and prefer:
            for country in prefer:
                if country in owners:
                    return upper
        return upper

    for country, regions in REGIONS.items():
        if raw in regions:
            if len(_owners_of_name(raw)) > 1 and prefer and country not in prefer:
                continue
            return regions[raw]

    if raw in STATE_ALIASES:
        return STATE_ALIASES[raw]
    return ""


def _owners_of_name(name: str) -> list[str]:
    return [c for c, regions in REGIONS.items() if name in regions]


def country_of(state: str, prefer: tuple[str, ...] = ()) -> str:
    """Which country a region code belongs to, preferring your own."""
    owners = [c for c, regions in REGIONS.items()
              if (state or "").upper() in set(regions.values())]
    if not owners:
        return ""
    if len(owners) > 1 and prefer:
        for country in prefer:
            if country in owners:
                return country
    return owners[0]


# ── Parsing a posting's location string ────────────────────────────────────────

# Boards write these where a place should go. They are not places.
_NON_PLACES = re.compile(
    r"^(remote|anywhere|distributed|virtual|work from home|wfh|n/?a|tbd|"
    r"multiple locations|various|flexible|global|worldwide|international|"
    r"north america|europe|asia|africa|south america|oceania)$",
    re.IGNORECASE,
)


def _country_suffix_pattern() -> re.Pattern:
    """Any known country name in the trailing segment.

    Built from COUNTRY_CODES rather than hardcoded, so adding a country to
    that map teaches the parser to strip it here too. Longest first, or
    "United States" is matched as "US" and the rest is left behind.
    """
    names = sorted(COUNTRY_CODES, key=len, reverse=True)
    alts = "|".join(re.escape(n) for n in names)
    return re.compile(rf",\s*({alts}|u\.s\.a?\.?)\s*$", re.IGNORECASE)

# "Remote - US" and "Remote, Canada" name no place but do name a country, and
# that country is the whole point: a remote role still has a legal boundary.
_COUNTRY_TOKENS = {
    "us": "US", "usa": "US", "united states": "US",
    "united states of america": "US", "u s": "US", "u s a": "US",
    "canada": "CA", "can": "CA",
}


# Country names as postings write them, mapped to ISO 3166-1 alpha-2.
#
# There is no notion of "foreign" here on purpose. A country is out of scope
# when it is not in YOUR `locations.countries`, which makes the rule the same
# whether you are in Chicago, Manila, Munich or Melbourne. An earlier version
# carried a hardcoded list of "not North America" and would have silently
# dropped a Singapore reader's entire market.
COUNTRY_CODES = {
    # Anglophone
    "united states": "US", "united states of america": "US", "usa": "US",
    "u s a": "US", "u s": "US", "america": "US",
    "canada": "CA", "united kingdom": "GB", "uk": "GB", "great britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "ireland": "IE", "republic of ireland": "IE",
    "australia": "AU", "new zealand": "NZ", "aotearoa": "NZ",
    # Europe
    "germany": "DE", "deutschland": "DE", "france": "FR", "spain": "ES",
    "españa": "ES", "portugal": "PT", "italy": "IT", "italia": "IT",
    "netherlands": "NL", "the netherlands": "NL", "holland": "NL",
    "belgium": "BE", "switzerland": "CH", "austria": "AT", "poland": "PL",
    "czech republic": "CZ", "czechia": "CZ", "slovakia": "SK",
    "slovenia": "SI", "croatia": "HR", "serbia": "RS", "hungary": "HU",
    "romania": "RO", "bulgaria": "BG", "greece": "GR", "cyprus": "CY",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI",
    "iceland": "IS", "estonia": "EE", "latvia": "LV", "lithuania": "LT",
    "luxembourg": "LU", "malta": "MT", "ukraine": "UA", "moldova": "MD",
    "albania": "AL", "north macedonia": "MK", "bosnia and herzegovina": "BA",
    "montenegro": "ME", "russia": "RU", "belarus": "BY", "turkey": "TR",
    "türkiye": "TR", "armenia": "AM", "azerbaijan": "AZ",
    # Asia Pacific
    "singapore": "SG", "philippines": "PH", "the philippines": "PH",
    "malaysia": "MY", "indonesia": "ID", "thailand": "TH", "vietnam": "VN",
    "viet nam": "VN", "cambodia": "KH", "laos": "LA", "myanmar": "MM",
    "brunei": "BN", "india": "IN", "pakistan": "PK", "bangladesh": "BD",
    "sri lanka": "LK", "nepal": "NP", "china": "CN", "hong kong": "HK",
    "taiwan": "TW", "japan": "JP", "south korea": "KR",
    "republic of korea": "KR", "korea": "KR", "mongolia": "MN",
    # Middle East
    "israel": "IL", "united arab emirates": "AE", "uae": "AE",
    "saudi arabia": "SA", "qatar": "QA", "kuwait": "KW", "bahrain": "BH",
    "oman": "OM", "jordan": "JO", "lebanon": "LB",
    # Africa
    "south africa": "ZA", "nigeria": "NG", "kenya": "KE", "ghana": "GH",
    "egypt": "EG", "morocco": "MA", "tunisia": "TN", "ethiopia": "ET",
    "tanzania": "TZ", "uganda": "UG", "rwanda": "RW", "senegal": "SN",
    # Americas
    "mexico": "MX", "méxico": "MX", "brazil": "BR", "brasil": "BR",
    "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE",
    "uruguay": "UY", "paraguay": "PY", "bolivia": "BO", "ecuador": "EC",
    "venezuela": "VE", "costa rica": "CR", "panama": "PA", "guatemala": "GT",
    "honduras": "HN", "el salvador": "SV", "nicaragua": "NI",
    "dominican republic": "DO", "puerto rico": "PR", "jamaica": "JM",
    "trinidad and tobago": "TT",
}

# Regional shorthands that appear where a country should. Each resolves to a
# representative country so the role is placed rather than lost; the note on
# the result says it was read as an approximation.
REGION_SHORTHANDS = {
    "emea": "GB", "apac": "SG", "apj": "SG", "anz": "AU", "latam": "BR",
    "sea": "SG", "southeast asia": "SG", "south east asia": "SG",
    "dach": "DE", "benelux": "NL", "nordics": "SE", "scandinavia": "SE",
    "mena": "AE", "gcc": "AE", "eu": "DE", "europe": "DE",
}

ALL_COUNTRY_CODES = set(COUNTRY_CODES.values())

# English exonyms, and the local spelling the gazetteer may file a city under.
# Postings use both, sometimes in the same sentence. Accent folding handles
# Zürich/Zurich on its own; these are the cases where the two names share no
# letters — Munich is not a respelling of München, it is a different word.
CITY_EXONYMS = {
    "munchen": "Munich", "muenchen": "Munich",
    "koln": "Cologne", "koeln": "Cologne",
    "wien": "Vienna", "praha": "Prague", "warszawa": "Warsaw",
    "kobenhavn": "Copenhagen", "koebenhavn": "Copenhagen",
    "lisboa": "Lisbon", "firenze": "Florence", "napoli": "Naples",
    "roma": "Rome", "milano": "Milan", "torino": "Turin",
    "venezia": "Venice", "genova": "Genoa", "geneve": "Geneva",
    "bruxelles": "Brussels", "brussel": "Brussels",
    "den haag": "The Hague", "s gravenhage": "The Hague",
    "antwerpen": "Antwerp", "goteborg": "Gothenburg",
    "moskva": "Moscow", "athina": "Athens", "bucuresti": "Bucharest",
    "beograd": "Belgrade", "zagreb": "Zagreb", "sevilla": "Seville",
    "malaga": "Malaga", "a coruna": "A Coruna", "donostia": "San Sebastian",
    "nurnberg": "Nuremberg", "nuernberg": "Nuremberg",
    "basel": "Basel", "luzern": "Lucerne", "bern": "Bern",
    "gdansk": "Gdansk", "krakow": "Krakow", "wroclaw": "Wroclaw",
    "bengaluru": "Bangalore", "mumbai": "Mumbai", "chennai": "Chennai",
    "kolkata": "Kolkata", "bombay": "Mumbai", "madras": "Chennai",
    "calcutta": "Kolkata", "saigon": "Ho Chi Minh City",
    "ho chi minh": "Ho Chi Minh City", "hanoi": "Hanoi",
    "seoul": "Seoul", "kyiv": "Kiev", "kyev": "Kiev",
}


def _country_token(text: str) -> str:
    return _COUNTRY_TOKENS.get(_key(text), "")


def country_code(text: str) -> str:
    """'Germany', 'Deutschland', 'DE', 'EMEA' -> an ISO alpha-2 code."""
    key = _key(text)
    if not key:
        return ""
    upper = key.upper()
    if len(upper) == 2 and upper in ALL_COUNTRY_CODES:
        return upper
    return COUNTRY_CODES.get(key) or REGION_SHORTHANDS.get(key, "")


_COUNTRY_SUFFIX = _country_suffix_pattern()


@dataclass
class Resolved:
    city: str = ""
    state: str = ""
    country: str = ""
    lat: float | None = None
    lon: float | None = None
    approximate: bool = False   # came from a metro alias, not an exact city
    note: str = ""

    @property
    def located(self) -> bool:
        return self.lat is not None and self.lon is not None


def resolve(location: str, prefer: tuple[str, ...] = ()) -> Resolved:
    """Best effort at turning a posting's location string into coordinates.

    Never raises and never guesses wildly: an unrecognised string comes back
    unlocated with a note, and the caller keeps the role and flags it.

    `prefer` is your configured countries. It only breaks ties — between
    region codes that exist in more than one country, and between cities of
    the same name — and never invents a country the string did not name.
    """
    raw = (location or "").strip()
    if not raw:
        return Resolved(note="no location given")

    # "Remote - US", "Hybrid | Austin, TX", "Chicago, IL (Hybrid)" all put the
    # arrangement next to the place. Strip the decoration, keep the place.
    cleaned = re.sub(
        r"\b(remote|hybrid|on-?site|in-?office|flexible|work from home|wfh)\b",
        " ", raw, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[()\[\]|/]+", ",", cleaned)
    cleaned = re.sub(r"\s*[-–—]\s*", ",", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")

    country_hint = ""
    m = _COUNTRY_SUFFIX.search(cleaned)
    if m:
        country_hint = country_code(m.group(1)) or "US"
        cleaned = cleaned[: m.start()].strip(" ,")

    if not country_hint:
        country_hint = _country_token(cleaned) or _country_token(
            cleaned.rsplit(",", 1)[-1]
        )

    # A named country settles the question before any city lookup. "Georgia"
    # is a US state far more often than it is the country, so only trailing
    # segments are tested and the region map is consulted first.
    if not country_hint:
        for candidate in reversed([p.strip() for p in cleaned.split(",") if p.strip()]):
            if normalise_state(candidate, prefer):
                break
            named = country_code(candidate)
            if named:
                if named in prefer or not prefer:
                    country_hint = named
                    remainder = cleaned[: cleaned.rfind(candidate)].strip(" ,")
                    if not remainder:
                        # The whole string was the country. Usually that names
                        # no city — and looking one up for "Remote - Australia"
                        # finds Australia, a town of 3,000 people in Cuba.
                        #
                        # City-states are the exception: in Singapore, Monaco
                        # and Hong Kong the country name IS the city, so a
                        # same-country lookup is tried before giving up.
                        index, by_city = _load_gazetteer()
                        same = [p for p in by_city.get(_key(candidate), [])
                                if p.country == named]
                        if len(same) == 1:
                            p = same[0]
                            return Resolved(p.city, p.state, p.country,
                                            p.lat, p.lon)
                        return Resolved(country=named,
                                        note=f"{raw!r} names a country, not a place")
                    cleaned = remainder
                    break
                # A country you did not ask for. That is the employer saying
                # where the job is, so it is placed and the caller drops it.
                return Resolved(country=named,
                                note=f"{raw!r} is in {candidate.strip()}")

    if not cleaned or _NON_PLACES.match(cleaned):
        return Resolved(country=country_hint, note=f"not a place: {raw!r}")

    index, by_city = _load_gazetteer()

    # Metro names first: they are not cities and would otherwise miss.
    alias_key = _key(cleaned)
    if alias_key in METRO_ALIASES:
        city, state = METRO_ALIASES[alias_key]
        place = index.get((_key(city), state))
        if place:
            return Resolved(
                city=place.city, state=place.state, country=place.country,
                lat=place.lat, lon=place.lon, approximate=True,
                note=f"{raw!r} read as {city}, {state}",
            )

    parts = [p.strip() for p in cleaned.split(",") if p.strip()]

    # "Austin, TX" and "Austin, Texas"
    for i in range(len(parts) - 1):
        state = normalise_state(parts[i + 1], prefer)
        if not state:
            continue
        place = index.get((_key(parts[i]), state))
        if place:
            return Resolved(place.city, place.state, place.country,
                            place.lat, place.lon)
        # A real region with an unknown city still tells us the region.
        return Resolved(city=parts[i], state=state,
                        country=country_hint or country_of(state, prefer),
                        note=f"city {parts[i]!r} not in gazetteer")

    # A city with a country but no region: "Makati, Philippines", already
    # stripped to "Makati" with the country in hand.
    if country_hint:
        for part in parts:
            matches = [p for p in by_city.get(_key(part), [])
                       if p.country == country_hint]
            if len(matches) == 1:
                p = matches[0]
                return Resolved(p.city, p.state, p.country, p.lat, p.lon)
            if len(matches) > 1:
                p = matches[0]          # gazetteer is most-populous first
                return Resolved(p.city, p.state, p.country, p.lat, p.lon,
                                approximate=True,
                                note=f"{part!r} matches {len(matches)} places "
                                     f"in {country_hint}; largest used")

    # A bare region: "Texas", "ON", "NSW"
    for part in parts:
        state = normalise_state(part, prefer)
        if state:
            return Resolved(state=state,
                            country=country_hint or country_of(state, prefer),
                            note="region only, no city")

    # A bare city, if it is unambiguous.
    for part in parts:
        matches = by_city.get(_key(part), [])
        narrowed = [p for p in matches if p.country in prefer] if prefer else []
        if len(narrowed) == 1:
            p = narrowed[0]
            return Resolved(p.city, p.state, p.country, p.lat, p.lon)
        if len(narrowed) > 1:
            # Several places of that name inside your own countries. The
            # gazetteer is most-populous first, so the biggest is the one a
            # posting almost certainly means; it is marked approximate.
            p = narrowed[0]
            return Resolved(p.city, p.state, p.country, p.lat, p.lon,
                            approximate=True,
                            note=f"{part!r} matches {len(narrowed)} places in "
                                 f"{'/'.join(prefer)}; largest used")
        if len(matches) == 1:
            p = matches[0]
            return Resolved(p.city, p.state, p.country, p.lat, p.lon)
        if len(matches) > 1:
            return Resolved(city=part, country=country_hint,
                            note=f"{part!r} is ambiguous ({len(matches)} places)")

    return Resolved(country=country_hint, note=f"could not read {raw!r}")


def resolve_anchor(anchor: str, prefer: tuple[str, ...] = ()) -> Resolved:
    """Your own location. Unlike a posting, this one has to work.

    Returns an unlocated Resolved rather than raising; the caller reports it,
    because a bad anchor should name itself rather than silently drop every
    role for being too far from nowhere.
    """
    return resolve(anchor, prefer)


# ── Distance ───────────────────────────────────────────────────────────────────

def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def distance_between(a: Resolved, b: Resolved) -> float | None:
    if not (a.located and b.located):
        return None
    return haversine_mi(a.lat, a.lon, b.lat, b.lon)


def miles_to_km(miles: float) -> float:
    """Adzuna takes `distance` in kilometres, not miles."""
    return miles * KM_PER_MILE


def km_to_miles(km: float) -> float:
    return km / KM_PER_MILE


def to_miles(value: float, units: str) -> float:
    """Normalise a configured radius to miles, which is what the maths uses."""
    return float(value) if (units or "mi").startswith("mi") else km_to_miles(float(value))


def from_miles(miles: float, units: str) -> float:
    """Back to the reader's own units, for anything they will actually read."""
    return miles if (units or "mi").startswith("mi") else miles * KM_PER_MILE


def default_units(countries: tuple[str, ...] | list[str]) -> str:
    """Miles for the handful of countries that use them, kilometres otherwise."""
    for country in countries or ():
        if country.upper() in MILE_COUNTRIES:
            return "mi"
    return "km" if countries else "mi"


def same_place(a: Resolved, b: Resolved) -> bool:
    """For radius: exact. City and state must match after normalisation.

    A posting with only a state matches an anchor in that state, because
    "Texas" is the most precise thing the employer said.
    """
    if a.state and b.state and a.state != b.state:
        return False
    if a.city and b.city:
        return _key(a.city) == _key(b.city)
    return bool(a.state and b.state)


def gazetteer_size() -> int:
    index, _ = _load_gazetteer()
    return len(index)


def gazetteer_is_bundled() -> bool:
    """True when running on the small fallback rather than the built file."""
    return not GAZETTEER.is_file()
