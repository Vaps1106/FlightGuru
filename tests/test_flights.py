"""Tests for the Google Flights provider: query building and response parsing.

No network. ``build_params`` is pure by design so the translation can be checked
without spending searches from a ~100/month free quota.
"""

from __future__ import annotations

import json

from flightguru import airports as A
from flightguru.providers import flights
from flightguru.request import MULTI_CITY, ONE_WAY, ROUND_TRIP, Leg, SearchRequest

KEY = "test-key"


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


# --- query building ---------------------------------------------------------


def test_round_trip_sends_both_dates():
    params = flights.build_params(req(), KEY)
    assert params["type"] == "1"
    assert params["outbound_date"] == "2026-09-12"
    assert params["return_date"] == "2026-09-19"


def test_one_way_sends_no_return_date():
    params = flights.build_params(req(trip_type=ONE_WAY, return_date=None), KEY)
    assert params["type"] == "2"
    assert "return_date" not in params


def test_results_are_sorted_by_price_not_google_default():
    """We want the cheapest fare, not Google's blend of price and convenience."""
    assert flights.build_params(req(), KEY)["sort_by"] == "2"


def test_several_airports_become_one_comma_separated_query():
    """The reason the nearby feature is affordable: this is ONE search.

    Google Flights takes a list of departure airports, so pricing four airports
    costs one call against the quota rather than four.
    """
    r = req().with_alternatives(origins=ap("EWR", "LGA", "HVN"))
    params = flights.build_params(r, KEY)
    assert params["departure_id"] == "JFK,EWR,LGA,HVN"


def test_requested_airport_leads_the_query():
    r = req().with_alternatives(origins=ap("EWR"))
    assert flights.build_params(r, KEY)["departure_id"].startswith("JFK")


def test_destination_alternatives_are_included_too():
    r = req().with_alternatives(destinations=ap("BUR", "SNA"))
    assert flights.build_params(r, KEY)["arrival_id"] == "LAX,BUR,SNA"


def test_optional_filters_are_omitted_at_their_defaults():
    """Keeps the query stable so SerpApi's free cache can hit it."""
    params = flights.build_params(req(), KEY)
    for absent in ("children", "infants_in_seat", "infants_on_lap", "stops", "bags"):
        assert absent not in params


def test_passengers_and_filters_are_sent_when_set():
    r = req(children=2, infants_on_lap=1, max_stops=1, bags=1)
    params = flights.build_params(r, KEY)
    assert params["adults"] == "1"
    assert params["children"] == "2"
    assert params["infants_on_lap"] == "1"
    assert params["stops"] == "1"
    assert params["bags"] == "1"


def test_cabin_maps_to_google_travel_class():
    assert flights.build_params(req(cabin="economy"), KEY)["travel_class"] == "1"
    assert flights.build_params(req(cabin="business"), KEY)["travel_class"] == "3"


def test_currency_is_passed_through():
    assert flights.build_params(req(currency="INR"), KEY)["currency"] == "INR"


def test_multi_city_builds_the_leg_json():
    legs = (
        Leg(origins=ap("JFK"), destinations=ap("LAX"), depart_date="2026-09-12"),
        Leg(origins=ap("LAX"), destinations=ap("SFO"), depart_date="2026-09-16"),
    )
    params = flights.build_params(req(trip_type=MULTI_CITY, legs=legs), KEY)

    assert params["type"] == "3"
    assert json.loads(params["multi_city_json"]) == [
        {"departure_id": "JFK", "arrival_id": "LAX", "date": "2026-09-12"},
        {"departure_id": "LAX", "arrival_id": "SFO", "date": "2026-09-16"},
    ]
    # Multi-city carries its route inside the JSON, not at the top level.
    assert "outbound_date" not in params


# --- response parsing -------------------------------------------------------


def _itinerary(price, origin, dest, airline="Delta", number="DL 1", token=""):
    return {
        "price": price,
        "total_duration": 385,
        "departure_token": token,
        "flights": [
            {
                "airline": airline,
                "flight_number": number,
                "departure_airport": {"id": origin, "time": "2026-09-12 08:15"},
                "arrival_airport": {"id": dest, "time": "2026-09-12 11:40"},
            }
        ],
    }


def _response(*itineraries, currency="USD"):
    return {
        "search_parameters": {"currency": currency},
        "best_flights": list(itineraries[:1]),
        "other_flights": list(itineraries[1:]),
    }


def test_parse_reads_the_real_departure_airport():
    """Critical: with several origins searched, the airport must come from the
    itinerary. Assuming the requested one would credit a Newark fare to JFK."""
    data = _response(_itinerary(137, "EWR", "LAX"))
    offer = flights.parse(data, req().with_alternatives(origins=ap("EWR")))[0]
    assert offer.origin_airport == "EWR"
    assert offer.destination_airport == "LAX"


def test_parse_reads_both_best_and_other_flights():
    data = _response(_itinerary(200, "JFK", "LAX"), _itinerary(150, "EWR", "LAX"))
    assert len(flights.parse(data, req())) == 2


def test_parse_records_trip_shape():
    offer = flights.parse(_response(_itinerary(300, "JFK", "LAX")), req())[0]
    assert offer.trip_type == "round_trip"
    assert offer.return_date == "2026-09-19"


def test_one_way_offers_carry_no_return_date():
    r = req(trip_type=ONE_WAY, return_date=None)
    offer = flights.parse(_response(_itinerary(120, "JFK", "LAX")), r)[0]
    assert offer.return_date is None


def test_parse_counts_stops_from_the_legs():
    itinerary = _itinerary(300, "JFK", "LAX")
    itinerary["flights"].append(
        {
            "airline": "Delta",
            "flight_number": "DL 2",
            "departure_airport": {"id": "SLC", "time": "2026-09-12 12:00"},
            "arrival_airport": {"id": "LAX", "time": "2026-09-12 14:00"},
        }
    )
    offer = flights.parse(_response(itinerary), req())[0]
    assert offer.stops == 1
    assert offer.flight_numbers == "DL 1 + DL 2"
    # Origin comes from the first leg, destination from the last.
    assert offer.origin_airport == "JFK"
    assert offer.destination_airport == "LAX"


def test_parse_uses_the_currency_google_reports():
    """Guards against comparing a EUR price against a USD budget."""
    data = _response(_itinerary(300, "JFK", "LAX"), currency="EUR")
    assert flights.parse(data, req(currency="USD"))[0].currency == "EUR"


def test_parse_falls_back_to_requested_currency_when_none_reported():
    data = {"best_flights": [_itinerary(300, "JFK", "LAX")]}
    assert flights.parse(data, req(currency="USD"))[0].currency == "USD"


def test_parse_keeps_the_departure_token_for_the_return_leg():
    data = _response(_itinerary(300, "JFK", "LAX", token="tok123"))
    assert flights.parse(data, req())[0].departure_token == "tok123"


def test_parse_skips_itineraries_with_no_legs():
    data = {"best_flights": [{"price": 100, "flights": []}]}
    assert flights.parse(data, req()) == []


def test_parse_handles_an_empty_response():
    assert flights.parse({}, req()) == []


def test_parse_survives_a_missing_airport_block():
    """A malformed itinerary should not crash the whole search."""
    data = {"best_flights": [{"price": 100, "flights": [{"airline": "X"}]}]}
    offer = flights.parse(data, req())[0]
    assert offer.origin_airport == ""
