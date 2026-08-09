"""Airport lookup: turn what a person types into airport codes we can search.

Two jobs, both driven by the bundled ``data/airports.csv``:

1. **Resolve** free text into airports. Someone will type "JFK", but they will
   equally type "new york", "nyc", or "bombay", and all of those have to work.
2. **Find nearby airports**, so a search from JFK also prices LGA, EWR and
   Tweed New Haven -- which is where the genuinely cheap fares often hide.

Why distance and not just city names: in the source data JFK and LGA say their
city is "New York", but Newark says "Newark" and Stewart says "Newburgh". Anyone
asking for New York flights obviously wants Newark included, so city lookups
resolve to a *location* and then sweep a radius around it. String matching alone
would quietly drop the second-busiest airport in the region.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

# Two different radii, because "which airports serve this city" and "what else
# could I fly from" are different questions and one number cannot answer both.
#
# METRO: airports belonging to the place someone named. Tight, because sweeping
# wider makes "New Haven" resolve to all of New York and buries the airport they
# actually asked about. 35 miles still reaches Newark from JFK (21 mi).
METRO_RADIUS_MILES = 35.0

# ALTERNATIVE: how far someone might reasonably drive for a cheaper fare --
# roughly two hours. This is the wider sweep that suggests Providence to a
# Boston traveller, or Tweed New Haven to someone flying out of Hartford. Only
# ever offered as an extra, never folded into the primary search silently.
DEFAULT_RADIUS_MILES = 100.0

# Most alternates you would ever seriously consider. Also keeps the
# comma-separated Google query from growing unbounded.
MAX_NEARBY = 4

# Sizes worth offering as an *alternative* airport. Small fields stay in the
# table so someone can still name one directly, but they are not volunteered:
# the low-cost bases that make this feature worthwhile -- Tweed New Haven,
# Portsmouth, Stewart, Islip, Atlantic City -- are all classed medium or larger.
SUGGESTABLE_SIZES = ("large", "medium")

# A whole state can hold dozens of airfields. Cap it at the busiest few, or a
# search for "texas" becomes an unreadable comma-separated wall.
MAX_STATE_AIRPORTS = 5

# Airports the source data marks as having scheduled service but which are in
# practice private / business-aviation fields you cannot buy an airline ticket
# from. Left in unchecked they crowd out real options -- Teterboro sits 21 miles
# from JFK and would displace Newark. Add to this list if a suggestion ever
# comes back that you obviously cannot fly from.
NON_COMMERCIAL = frozenset(
    {
        "TEB",  # Teterboro, NJ - business jets
        "BED",  # Hanscom Field, MA - business jets
        "MMU",  # Morristown, NJ - business jets
        "VNY",  # Van Nuys, CA - business jets
        "HHR",  # Hawthorne, CA - business jets
        "MTP",  # Montauk, NY - seasonal air taxi
        "JRB",  # Downtown Manhattan Heliport
    }
)

EARTH_RADIUS_MILES = 3958.8


@dataclass(frozen=True)
class Airport:
    """One airport from the bundled table."""

    iata: str
    name: str
    city: str
    country: str
    region: str
    lat: float
    lon: float
    size: str  # "large" | "medium" | "small" | "other"

    @property
    def label(self) -> str:
        """Short human description, e.g. 'EWR - Newark (Newark Liberty ...)'."""
        where = self.city or self.name
        return f"{self.iata} - {where} ({self.name})"


# Metro areas whose airports do not share a single city name, plus the
# shorthand people actually type. Without these, "nyc" resolves to nothing and
# "new york" misses Newark.
#
# These are *seed* codes: the resolver expands them by radius too, so listing
# the obvious ones is enough.
METRO_ALIASES: dict[str, tuple[str, ...]] = {
    "nyc": ("JFK", "LGA", "EWR"),
    "ny": ("JFK", "LGA", "EWR"),
    "new york": ("JFK", "LGA", "EWR"),
    "new york city": ("JFK", "LGA", "EWR"),
    "la": ("LAX", "BUR", "SNA", "LGB", "ONT"),
    "los angeles": ("LAX", "BUR", "SNA", "LGB", "ONT"),
    "sf": ("SFO", "OAK", "SJC"),
    "san francisco": ("SFO", "OAK", "SJC"),
    "bay area": ("SFO", "OAK", "SJC"),
    "dc": ("DCA", "IAD", "BWI"),
    "washington": ("DCA", "IAD", "BWI"),
    "washington dc": ("DCA", "IAD", "BWI"),
    "chicago": ("ORD", "MDW"),
    "houston": ("IAH", "HOU"),
    "dallas": ("DFW", "DAL"),
    "miami": ("MIA", "FLL"),
    "boston": ("BOS", "PVD", "MHT"),
    "london": ("LHR", "LGW", "STN", "LTN", "LCY"),
    "paris": ("CDG", "ORY", "BVA"),
    "milan": ("MXP", "LIN", "BGY"),
    "rome": ("FCO", "CIA"),
    "tokyo": ("HND", "NRT"),
    "seoul": ("ICN", "GMP"),
    "moscow": ("SVO", "DME", "VKO"),
    "istanbul": ("IST", "SAW"),
    "delhi": ("DEL",),
    "mumbai": ("BOM",),
}

# US states, by abbreviation and full name. People say "flying from CT" as
# readily as they name a city, and the airport table already carries an ISO
# region code (US-CT) to match against.
#
# This also fixes a nastier problem: without it, "CT" fell through to matching
# airport *names* containing that pair of letters, and confidently offered
# Mactan, Victoria Falls and Victoria BC as places to fly from Connecticut.
US_STATES: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington state": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

# The two-letter forms, plus the ones that collide with something else. "LA"
# means Los Angeles far more often than Louisiana, and "DC" is a city, so both
# are left to the metro aliases above.
STATE_CODES = {code for code in US_STATES.values()} - {"LA"}

# Below this many characters, matching against airport *names* produces
# nonsense: two letters appear inside hundreds of unrelated names. Short input
# is only ever matched against codes, metros, states and exact city names.
MIN_NAME_MATCH_CHARS = 4

# Names that changed, or that people still use the old form of.
CITY_SYNONYMS: dict[str, str] = {
    "bombay": "mumbai",
    "bangalore": "bengaluru",
    "calcutta": "kolkata",
    "madras": "chennai",
    "trivandrum": "thiruvananthapuram",
    "pekin": "beijing",
    "peking": "beijing",
    "saigon": "ho chi minh city",
}


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, drop punctuation people type casually."""
    cleaned = re.sub(r"[.,]", " ", (text or "").strip().lower())
    return re.sub(r"\s+", " ", cleaned).strip()


@lru_cache(maxsize=1)
def _load() -> tuple[Airport, ...]:
    """Read the bundled airports table once and keep it in memory."""
    raw = resources.files("flightguru").joinpath("data/airports.csv").read_text(
        encoding="utf-8"
    )
    airports: list[Airport] = []
    for row in csv.DictReader(raw.splitlines()):
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except (TypeError, ValueError):
            continue
        airports.append(
            Airport(
                iata=row["iata"].strip().upper(),
                name=row["name"].strip(),
                city=row["city"].strip(),
                country=row["country"].strip(),
                region=row["region"].strip(),
                lat=lat,
                lon=lon,
                size=row["size"].strip(),
            )
        )
    return tuple(airports)


@lru_cache(maxsize=1)
def _by_code() -> dict[str, Airport]:
    return {a.iata: a for a in _load()}


def all_airports() -> tuple[Airport, ...]:
    """Every airport in the table (IATA code + scheduled service, any size)."""
    return _load()


def get(code: str) -> Airport | None:
    """Look up one airport by IATA code, or None if we don't have it."""
    return _by_code().get((code or "").strip().upper())


def distance_miles(a: Airport, b: Airport) -> float:
    """Great-circle distance between two airports, in miles.

    Straight-line distance, not driving distance, so it slightly understates how
    far a drive really is. Good enough for deciding whether an airport is a
    plausible alternative.
    """
    return _haversine(a.lat, a.lon, b.lat, b.lon)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def nearby(
    code: str,
    radius_miles: float = DEFAULT_RADIUS_MILES,
    limit: int = MAX_NEARBY,
    sizes: tuple[str, ...] = SUGGESTABLE_SIZES,
) -> list[tuple[Airport, float]]:
    """Airports within ``radius_miles`` of ``code``, nearest first.

    Excludes the airport itself. Returns (airport, distance) pairs so the bot can
    say "EWR, 21 miles away" rather than just naming a code.

    Ordering is purely by distance, which is only safe because ``sizes`` and
    ``NON_COMMERCIAL`` have already removed the heliports and business-jet
    fields that would otherwise sit closer than any real airport. Ranking by
    airport size instead would be actively wrong here: the cheap fares this
    feature exists to find come from the *small* fields, so preferring big
    airports drops Tweed New Haven in favour of Boston.
    """
    origin = get(code)
    if origin is None:
        return []

    found: list[tuple[Airport, float]] = []
    for other in _load():
        if other.iata == origin.iata or other.size not in sizes:
            continue
        if other.iata in NON_COMMERCIAL:
            continue
        d = distance_miles(origin, other)
        if d <= radius_miles:
            found.append((other, d))

    found.sort(key=lambda pair: pair[1])
    return found[:limit]


@dataclass(frozen=True)
class Resolution:
    """What we made of the text someone typed.

    Exactly one of these situations applies:

    - ``airports`` non-empty          -> understood it
    - ``candidates`` non-empty        -> ambiguous, ask which one they meant
    - both empty                      -> no idea, ``query`` echoes what they typed
    """

    query: str
    airports: tuple[Airport, ...] = ()
    candidates: tuple[Airport, ...] = ()
    matched_as: str = ""  # "code" | "metro" | "city" | "name"

    @property
    def ok(self) -> bool:
        return bool(self.airports)

    @property
    def ambiguous(self) -> bool:
        return not self.airports and bool(self.candidates)


def resolve(
    text: str,
    radius_miles: float = METRO_RADIUS_MILES,
    expand_metro: bool = True,
) -> Resolution:
    """Turn "JFK", "new york", "nyc" or "bombay" into concrete airports.

    Answers only "which airports serve this place". Cheaper airports an hour's
    drive away are a separate question -- see ``alternatives``.

    Tried in order, most specific first:

    1. An exact 3-letter IATA code -- unambiguous, return just that airport
    2. A known metro alias ("nyc", "bay area") -- curated, used as written
    3. An exact city name, widened slightly to catch same-metro airports filed
       under a different city name (Newark for New York)
    4. A partial city or airport-name match -- offered back as candidates

    Naming a code gives you that one airport and nothing else. If you say "JFK"
    you meant JFK; alternatives are offered separately rather than assumed.
    """
    query = _normalize(text)
    if not query:
        return Resolution(query=text or "")

    # 1. Straight airport code.
    if len(query) == 3 and query.isalpha():
        hit = get(query)
        if hit is not None:
            return Resolution(query=text, airports=(hit,), matched_as="code")

    # Fold old city names onto current ones before any name matching.
    query = CITY_SYNONYMS.get(query, query)

    # 2. Known multi-airport metro. These lists are curated and already correct,
    #    so they are used exactly as written -- no radius expansion, which is
    #    what used to drag Philadelphia into a New York search.
    if query in METRO_ALIASES:
        seeds = tuple(a for a in (get(c) for c in METRO_ALIASES[query]) if a)
        if seeds:
            return Resolution(
                query=text,
                airports=tuple(sorted(seeds, key=_prominence)),
                matched_as="metro",
            )

    table = _load()

    # 3. A US state, by name or two-letter code.
    state = US_STATES.get(query)
    if state is None and query.upper() in STATE_CODES:
        state = query.upper()
    if state is not None:
        in_state = _offerable(a for a in table if a.region == f"US-{state}")
        if in_state:
            return Resolution(
                query=text,
                airports=tuple(sorted(in_state, key=_prominence)[:MAX_STATE_AIRPORTS]),
                matched_as="state",
            )

    # 4. Exact city name. Careful: plenty of city names are not unique --
    #    Springfield exists in Missouri, Illinois and Massachusetts, and merging
    #    them into one search would quote a fare from the wrong side of the
    #    country. Distinct places means ask, not guess.
    exact = tuple(_offerable(a for a in table if _normalize(a.city) == query))
    if exact:
        if len(_places(exact)) > 1:
            ranked = sorted(exact, key=_prominence)
            return Resolution(query=text, candidates=tuple(ranked[:6]))
        group = _expand_around(exact, radius_miles) if expand_metro else exact
        return Resolution(query=text, airports=group, matched_as="city")

    # 5. Partial match on city, then on airport name. Ambiguity is handed back
    #    as candidates rather than guessed at -- booking the wrong Springfield
    #    is an expensive mistake to make on someone's behalf.
    #
    #    Short input never reaches the name match: two or three letters occur
    #    inside hundreds of unrelated airport names, and the results are noise
    #    dressed up as answers.
    if len(query) < MIN_NAME_MATCH_CHARS:
        # "ny" is inside Albany and Nizhny Novgorod; "ct" is inside Mactan and
        # Victoria. Anything this short that has not matched a code, metro,
        # state or exact city is not going to be rescued by substring search.
        return Resolution(query=text)

    partial = _offerable(a for a in table if query in _normalize(a.city))
    if not partial:
        partial = _offerable(a for a in table if query in _normalize(a.name))

    if not partial:
        return Resolution(query=text)

    if len(_places(partial)) == 1:
        group = tuple(partial)
        if expand_metro:
            group = _expand_around(group, radius_miles)
        return Resolution(query=text, airports=group, matched_as="city")

    # Several distinct places match. Offer the busiest first so the likely one
    # is at the top of the list.
    ranked = sorted(partial, key=_prominence)
    return Resolution(query=text, candidates=tuple(ranked[:6]))


_SIZE_RANK = {"large": 0, "medium": 1, "small": 2}


def _offerable(airports) -> list[Airport]:
    """Drop airports we should never put forward as somewhere to fly from.

    Applied wherever a *group* is built -- a state, a city, a metro sweep --
    but not to a direct code lookup: if someone types TEB they know what they
    are asking for, and should get it.
    """
    return [a for a in airports if a.iata not in NON_COMMERCIAL]


def _places(airports) -> set[tuple[str, str, str]]:
    """The distinct real-world locations a set of airports covers.

    Keyed on city + region + country, so the three Springfields count as three
    places while JFK and LGA count as one.
    """
    return {(_normalize(a.city), a.region, a.country) for a in airports}


def _prominence(airport: Airport) -> tuple[int, str]:
    """Sort key putting bigger airports first, then alphabetical for stability."""
    return (_SIZE_RANK.get(airport.size, 3), airport.iata)


def _expand_around(
    seeds: tuple[Airport, ...], radius_miles: float
) -> tuple[Airport, ...]:
    """Add airports within ``radius_miles`` of any seed, biggest first.

    This is what makes "new york" include Newark, which files its city as
    "Newark" and so never matches the name "New York".
    """
    group: dict[str, Airport] = {a.iata: a for a in _offerable(seeds)}
    for seed in seeds:
        for other, _ in nearby(seed.iata, radius_miles, limit=MAX_NEARBY):
            group.setdefault(other.iata, other)
    return tuple(sorted(group.values(), key=_prominence))


def alternatives(
    primary: tuple[Airport, ...] | list[Airport],
    radius_miles: float = DEFAULT_RADIUS_MILES,
    limit: int = MAX_NEARBY,
) -> list[tuple[Airport, float]]:
    """Cheaper-airport candidates near the ones already being searched.

    This is the feature that catches an Avelo fare out of Tweed New Haven when
    you asked about New York. Returned as (airport, miles from the nearest
    primary airport) so the bot can tell you how far out of your way it is,
    sorted nearest first.

    Airports already in ``primary`` are excluded, so nothing is offered twice.
    """
    if not primary:
        return []

    already = {a.iata for a in primary}
    best: dict[str, tuple[Airport, float]] = {}

    for seed in primary:
        for other, dist in nearby(seed.iata, radius_miles, limit=limit * 3):
            if other.iata in already:
                continue
            # Several primaries may reach the same alternative; keep the
            # shortest hop, since that is the honest "how far is it" answer.
            prior = best.get(other.iata)
            if prior is None or dist < prior[1]:
                best[other.iata] = (other, dist)

    ranked = sorted(best.values(), key=lambda pair: pair[1])
    return ranked[:limit]


def codes(airports: tuple[Airport, ...] | list[Airport]) -> str:
    """Format airports as the comma-separated list Google Flights expects."""
    return ",".join(a.iata for a in airports)
