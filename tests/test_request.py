"""Tests for SearchRequest — the description of one trip and its validation."""

from __future__ import annotations

from flightguru import airports as A
from flightguru.request import (
    MULTI_CITY,
    ONE_WAY,
    ROUND_TRIP,
    Leg,
    SearchRequest,
)


def ap(*codes):
    return tuple(A.get(c) for c in codes)


def req(**overrides) -> SearchRequest:
    base = dict(
        origins=ap("JFK"),
        destinations=ap("LAX"),
        depart_date="2026-09-12",
        return_date="2026-09-19",
        trip_type=ROUND_TRIP,
    )
    base.update(overrides)
    return SearchRequest(**base)


# --- shape ------------------------------------------------------------------


def test_valid_round_trip_has_no_problems():
    assert req().validate() == []


def test_one_way_does_not_need_a_return_date():
    assert req(trip_type=ONE_WAY, return_date=None).validate() == []


def test_google_trip_type_codes():
    assert req().google_type == "1"
    assert req(trip_type=ONE_WAY).google_type == "2"
    assert req(trip_type=MULTI_CITY, legs=_two_legs()).google_type == "3"


def test_describe_reads_naturally():
    assert req().describe() == "JFK to LAX, 2026-09-12 returning 2026-09-19"
    assert req(trip_type=ONE_WAY, return_date=None).describe() == (
        "JFK to LAX, 2026-09-12"
    )


# --- alternatives are kept distinct from what was asked for -----------------


def test_alternatives_join_the_search_but_stay_labelled():
    """Both sets get searched, but we must still know which was requested.

    Quoting a Newark fare to someone who asked about JFK, without saying so,
    would be answering a different question than the one they asked.
    """
    r = req().with_alternatives(origins=ap("EWR", "LGA"))
    assert A.codes(r.all_origins) == "JFK,EWR,LGA"
    assert A.codes(r.origins) == "JFK"
    assert r.is_alternative_origin("EWR")
    assert not r.is_alternative_origin("JFK")


def test_alternatives_do_not_duplicate_a_requested_airport():
    r = req(origins=ap("JFK", "EWR")).with_alternatives(origins=ap("EWR", "LGA"))
    codes = A.codes(r.all_origins).split(",")
    assert codes.count("EWR") == 1


def test_with_alternatives_leaves_the_original_untouched():
    original = req()
    original.with_alternatives(origins=ap("EWR"))
    assert original.alternative_origins == ()


# --- dates ------------------------------------------------------------------


def test_return_before_departure_is_rejected():
    problems = req(depart_date="2026-09-19", return_date="2026-09-12").validate()
    assert any("before the departure" in p for p in problems)


def test_round_trip_without_return_date_is_rejected():
    assert any("needs a return date" in p for p in req(return_date=None).validate())


def test_malformed_date_is_rejected_clearly():
    problems = req(depart_date="12/09/2026").validate()
    assert any("not a real date" in p for p in problems)


def test_impossible_date_is_rejected():
    assert req(depart_date="2026-02-30").validate() != []


def test_same_day_return_is_allowed():
    assert req(depart_date="2026-09-12", return_date="2026-09-12").validate() == []


# --- airports ---------------------------------------------------------------


def test_missing_airports_are_reported():
    assert any("No departure airport" in p for p in req(origins=()).validate())
    assert any("No arrival airport" in p for p in req(destinations=()).validate())


def test_flying_from_and_to_the_same_airport_is_rejected():
    problems = req(origins=ap("JFK"), destinations=ap("JFK")).validate()
    assert any("same airport" in p for p in problems)


def test_overlapping_metros_are_allowed_when_a_real_route_remains():
    """New York to Boston should not be rejected just because sets overlap.

    Only a total overlap means there is no route left to price.
    """
    r = req(origins=ap("JFK", "EWR"), destinations=ap("EWR", "BOS"))
    assert r.validate() == []


# --- passengers -------------------------------------------------------------


def test_defaults_to_one_adult():
    assert req().adults == 1
    assert req().passengers == 1


def test_passenger_total_counts_everyone():
    r = req(adults=2, children=1, infants_in_seat=1, infants_on_lap=1)
    assert r.passengers == 5


def test_zero_adults_is_rejected():
    assert any("at least one adult" in p for p in req(adults=0).validate())


def test_negative_counts_are_rejected():
    assert req(children=-1).validate() != []


def test_more_lap_infants_than_adults_is_rejected():
    problems = req(adults=1, infants_on_lap=2).validate()
    assert any("lap infants" in p for p in problems)


def test_google_nine_passenger_ceiling_is_enforced():
    problems = req(adults=9, children=1).validate()
    assert any("9 seated" in p for p in problems)


# --- cabin and filters ------------------------------------------------------


def test_unknown_cabin_is_rejected():
    assert any("Unknown cabin" in p for p in req(cabin="luxury").validate())


def test_known_cabins_are_accepted():
    for cabin in ("economy", "premium_economy", "business", "first"):
        assert req(cabin=cabin).validate() == []


def test_unknown_stops_filter_is_rejected():
    assert req(max_stops=7).validate() != []


# --- multi-city -------------------------------------------------------------


def _two_legs():
    return (
        Leg(origins=ap("JFK"), destinations=ap("LAX"), depart_date="2026-09-12"),
        Leg(origins=ap("LAX"), destinations=ap("SFO"), depart_date="2026-09-16"),
    )


def test_valid_multi_city_passes():
    r = req(trip_type=MULTI_CITY, legs=_two_legs())
    assert r.validate() == []


def test_multi_city_needs_at_least_two_flights():
    r = req(trip_type=MULTI_CITY, legs=_two_legs()[:1])
    assert any("at least two" in p for p in r.validate())


def test_multi_city_dates_must_move_forward():
    legs = (
        Leg(origins=ap("JFK"), destinations=ap("LAX"), depart_date="2026-09-16"),
        Leg(origins=ap("LAX"), destinations=ap("SFO"), depart_date="2026-09-12"),
    )
    r = req(trip_type=MULTI_CITY, legs=legs)
    assert any("forward in time" in p for p in r.validate())


def test_multi_city_describe_lists_the_hops():
    r = req(trip_type=MULTI_CITY, legs=_two_legs())
    assert r.describe() == (
        "multi-city: JFK-LAX 2026-09-12 then LAX-SFO 2026-09-16"
    )


def test_multi_city_leg_can_search_several_airports():
    leg = Leg(
        origins=ap("JFK", "EWR"), destinations=ap("LAX"), depart_date="2026-09-12"
    )
    assert leg.origin_codes == "JFK,EWR"


# --- validation reports everything at once ----------------------------------


def test_all_problems_are_reported_together():
    """A chat flow should be able to say what is wrong in one message."""
    problems = req(origins=(), adults=0, cabin="luxury").validate()
    assert len(problems) >= 3
