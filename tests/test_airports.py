"""Tests for airport lookup, city resolution and nearby-airport suggestions.

These run against the real bundled airports table rather than a fixture. The
table is the feature -- most of the bugs worth catching here are data problems
(a heliport pretending to have airline service, a city whose airports file under
a different name), and a hand-written fixture would hide exactly those.
"""

from __future__ import annotations

from flightguru import airports as A


# --- table sanity -----------------------------------------------------------


def test_table_loads_and_is_plausible_size():
    table = A.all_airports()
    # ~4,000 airports worldwide have an IATA code and scheduled service. Loose
    # bounds: this only needs to catch a truncated or empty data file.
    assert 3000 < len(table) < 6000


def test_every_airport_has_a_usable_code_and_position():
    for airport in A.all_airports():
        assert len(airport.iata) == 3 and airport.iata.isalpha()
        assert -90 <= airport.lat <= 90
        assert -180 <= airport.lon <= 180


def test_low_cost_carrier_bases_are_present():
    """The small fields are the whole point -- losing them defeats the feature.

    HVN is Avelo's base, PSM is Breeze's, SWF/ISP/ACY carry the low-cost
    operators around New York. An airport-size filter would silently drop these.
    """
    for code in ("HVN", "PSM", "SWF", "ISP", "ACY", "PVD"):
        assert A.get(code) is not None, f"{code} missing from table"


def test_lookup_is_case_insensitive_and_forgiving():
    assert A.get("jfk") is A.get("JFK") is A.get(" jfk ")
    assert A.get("ZZZ") is None
    assert A.get("") is None


# --- distance ---------------------------------------------------------------


def test_distance_matches_known_separation():
    # JFK to LAX is about 2,470 miles. Allow slack for great-circle vs published.
    d = A.distance_miles(A.get("JFK"), A.get("LAX"))
    assert 2400 < d < 2550


def test_distance_is_zero_to_itself_and_symmetric():
    jfk, ewr = A.get("JFK"), A.get("EWR")
    assert A.distance_miles(jfk, jfk) == 0
    assert A.distance_miles(jfk, ewr) == A.distance_miles(ewr, jfk)


# --- resolve ----------------------------------------------------------------


def test_airport_code_resolves_to_exactly_that_airport():
    """Naming a code is unambiguous, so don't quietly widen it."""
    r = A.resolve("JFK")
    assert r.ok and r.matched_as == "code"
    assert A.codes(r.airports) == "JFK"


def test_city_name_resolves_to_its_airports():
    r = A.resolve("mumbai")
    assert r.ok
    assert "BOM" in A.codes(r.airports)


def test_new_york_includes_newark():
    """Newark files its city as "Newark", so a name match alone would miss it.

    Anyone asking about New York flights wants Newark considered.
    """
    codes = A.codes(A.resolve("new york").airports).split(",")
    assert {"JFK", "LGA", "EWR"} <= set(codes)


def test_metro_shorthand_works():
    assert A.codes(A.resolve("nyc").airports) == A.codes(A.resolve("new york").airports)


def test_metro_does_not_reach_another_city():
    """New York must not resolve to Philadelphia, 80+ miles away."""
    assert "PHL" not in A.codes(A.resolve("new york").airports)


def test_old_city_names_still_work():
    assert A.codes(A.resolve("bombay").airports) == A.codes(A.resolve("mumbai").airports)
    assert A.resolve("calcutta").ok


def test_ambiguous_city_asks_instead_of_guessing():
    """Three Springfields exist; merging them would price the wrong state."""
    r = A.resolve("springfield")
    assert r.ambiguous and not r.ok
    regions = {a.region for a in r.candidates}
    assert len(regions) > 1


def test_unknown_input_is_reported_not_guessed():
    r = A.resolve("xyzzy")
    assert not r.ok and not r.ambiguous
    assert r.query == "xyzzy"


def test_blank_input_is_handled():
    for blank in ("", "   ", None):
        r = A.resolve(blank)
        assert not r.ok and not r.ambiguous


def test_resolution_states_are_mutually_exclusive():
    for query in ("JFK", "new york", "springfield", "xyzzy"):
        r = A.resolve(query)
        assert not (r.ok and r.ambiguous)


# --- nearby / alternatives --------------------------------------------------


def test_nearby_excludes_the_airport_itself():
    assert all(a.iata != "JFK" for a, _ in A.nearby("JFK"))


def test_nearby_is_sorted_by_distance():
    dists = [d for _, d in A.nearby("JFK")]
    assert dists == sorted(dists)


def test_nearby_respects_the_radius():
    for _, d in A.nearby("JFK", radius_miles=25):
        assert d <= 25


def test_nearby_unknown_airport_is_empty_not_an_error():
    assert A.nearby("ZZZ") == []


def test_non_commercial_airports_are_never_suggested():
    """Teterboro sits 21 miles from JFK but sells no airline tickets.

    The source data flags it as having scheduled service, so without the
    explicit exclusion it displaces Newark from the suggestions.
    """
    suggested = {a.iata for a, _ in A.nearby("JFK", radius_miles=60)}
    assert "TEB" not in suggested
    assert "EWR" in suggested


def test_alternatives_surface_low_cost_regional_fields():
    """The New Haven case: a cheap Avelo base near a big airport.

    Ranking alternatives by airport size instead of distance would replace HVN
    with Boston and lose the cheap fare.
    """
    hartford = A.resolve("hartford").airports
    assert "HVN" in {a.iata for a, _ in A.alternatives(hartford)}

    boston = A.resolve("boston").airports
    assert "PSM" in {a.iata for a, _ in A.alternatives(boston)}


def test_alternatives_never_repeat_the_primary_airports():
    primary = A.resolve("new york").airports
    primary_codes = {a.iata for a in primary}
    assert not primary_codes & {a.iata for a, _ in A.alternatives(primary)}


def test_alternatives_report_the_shortest_hop():
    """With several primaries, distance should be to the nearest of them."""
    primary = A.resolve("new york").airports
    for airport, dist in A.alternatives(primary):
        closest = min(A.distance_miles(airport, p) for p in primary)
        assert abs(dist - closest) < 0.01


def test_alternatives_of_nothing_is_empty():
    assert A.alternatives(()) == []


def test_alternatives_are_capped():
    primary = A.resolve("new york").airports
    assert len(A.alternatives(primary)) <= A.MAX_NEARBY


# --- formatting -------------------------------------------------------------


def test_codes_formats_for_google_flights():
    """Google Flights takes several origins as one comma-separated value."""
    assert A.codes(A.resolve("new york").airports).count(",") == 2
    assert " " not in A.codes(A.resolve("new york").airports)


def test_codes_of_empty_is_empty_string():
    assert A.codes(()) == ""
