"""Tests for the scan orchestration and its message formatting.

No network: ``build_request`` and ``format_result`` are the parts worth testing
here, and both are pure.
"""

from __future__ import annotations

from flightguru import airports as A, compare
from flightguru.models import Offer
from flightguru.request import ONE_WAY, SearchRequest
from flightguru.scan import ScanResult, build_request, format_result


# --- building a request from typed text -------------------------------------


def test_city_names_become_a_multi_airport_search():
    request, problems, _ = build_request(
        "new york", "los angeles", "2026-09-12", return_date="2026-09-19"
    )
    assert problems == []
    assert {"JFK", "LGA", "EWR"} <= {a.iata for a in request.all_origins}


def test_nearby_airports_are_added_and_measured():
    request, _, distances = build_request(
        "JFK", "LAX", "2026-09-12", return_date="2026-09-19"
    )
    assert request.alternative_origins
    # Every alternative should come with a distance for the message to quote.
    for airport in request.alternative_origins:
        assert airport.iata in distances


def test_nearby_can_be_turned_off():
    request, _, distances = build_request(
        "JFK", "LAX", "2026-09-12", return_date="2026-09-19", include_nearby=False
    )
    assert request.alternative_origins == ()
    assert distances == {}


def test_destination_alternatives_are_off_by_default():
    request, _, _ = build_request(
        "JFK", "LAX", "2026-09-12", return_date="2026-09-19"
    )
    assert request.alternative_destinations == ()


def test_destination_alternatives_can_be_enabled():
    request, _, _ = build_request(
        "JFK",
        "LAX",
        "2026-09-12",
        return_date="2026-09-19",
        nearby_destination=True,
    )
    assert request.alternative_destinations


def test_ambiguous_place_asks_which_one():
    request, problems, _ = build_request("springfield", "LAX", "2026-09-12")
    assert request is None
    assert "Which springfield" in problems[0]
    # The question has to list the options to be answerable.
    assert "SGF" in problems[0] and "SPI" in problems[0]


def test_unknown_place_says_so_plainly():
    request, problems, _ = build_request("xyzzy", "LAX", "2026-09-12")
    assert request is None
    assert "xyzzy" in problems[0]


def test_both_places_are_checked_before_giving_up():
    """Report everything wrong at once instead of one question per round trip."""
    _, problems, _ = build_request("xyzzy", "quux", "2026-09-12")
    assert len(problems) == 2


def test_invalid_dates_are_caught_before_spending_a_search():
    request, problems, _ = build_request(
        "JFK", "LAX", "2026-09-19", return_date="2026-09-12"
    )
    assert request is None
    assert any("before the departure" in p for p in problems)


def test_passenger_options_pass_through():
    request, _, _ = build_request(
        "JFK", "LAX", "2026-09-12", return_date="2026-09-19", adults=2, children=1
    )
    assert request.adults == 2 and request.children == 1


# --- formatting -------------------------------------------------------------


def ap(*codes):
    return tuple(A.get(c) for c in codes)


def offer(price, origin, airline="Delta") -> Offer:
    return Offer(
        source="GoogleFlights",
        search_date="2026-09-12",
        airline=airline,
        flight_numbers="DL 1",
        depart_time="2026-09-12 08:15",
        arrive_time="2026-09-12 11:40",
        duration="6h 25m",
        stops=0,
        layovers="",
        base_price=0.0,
        taxes_fees=0.0,
        total_price=price,
        currency="USD",
        origin_airport=origin,
        destination_airport="LAX",
    )


def result_for(offers, origins=("JFK",), distances=None) -> ScanResult:
    request = SearchRequest(
        origins=ap(*origins),
        destinations=ap("LAX"),
        depart_date="2026-09-12",
        return_date="2026-09-19",
    )
    return ScanResult(
        request=request,
        comparison=compare.compare(offers, request, distances or {}),
        searched_airports="JFK,LGA,EWR",
    )


def test_message_leads_with_the_requested_airport():
    text = format_result(result_for([offer(240, "JFK"), offer(137, "EWR")]))
    cheapest = text.index("CHEAPEST")
    cheaper_from = text.index("CHEAPER FROM")
    assert cheapest < cheaper_from
    assert "240 from JFK" in text


def test_message_quotes_the_saving_and_the_distance():
    text = format_result(
        result_for([offer(240, "JFK"), offer(137, "EWR")], distances={"EWR": 21.0})
    )
    assert "save USD 103" in text
    assert "21 mi away" in text


def test_message_says_so_when_nothing_nearby_is_cheaper():
    text = format_result(result_for([offer(240, "JFK"), offer(238, "EWR")]))
    assert "No nearby airport was meaningfully cheaper" in text


def test_message_handles_no_flights_found():
    request = SearchRequest(
        origins=ap("JFK"),
        destinations=ap("LAX"),
        depart_date="2026-09-12",
        return_date="2026-09-19",
    )
    text = format_result(
        ScanResult(request=request, comparison=None, searched_airports="JFK,LGA")
    )
    assert "No flights came back" in text
    assert "JFK,LGA" in text


def test_message_reports_problems_instead_of_a_result():
    text = format_result(
        ScanResult(request=None, comparison=None, problems=("Bad date.",))
    )
    assert text == "Bad date."


def test_awkward_characters_survive_intact():
    """v1 lost alerts because an "&" in a name broke Telegram's HTML parsing.

    Messages are sent with no parse mode, so nothing needs escaping and nothing
    should be escaped. The check is that the text arrives as written -- an
    ampersand stays an ampersand, not "&amp;".
    """
    text = format_result(
        result_for([offer(240, "JFK"), offer(137, "EWR", airline="B & C Air")])
    )
    assert "B & C Air" in text
    assert "&amp;" not in text


def test_message_emits_no_html_tags():
    """No markup means no tag can be left unclosed and eat the message."""
    text = format_result(result_for([offer(240, "JFK"), offer(137, "EWR")]))
    import re

    assert re.search(r"</?[a-zA-Z]+>", text) is None
