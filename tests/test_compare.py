"""Tests for the nearby-airport comparison — the heart of the v3 feature.

The rule being protected: the airport you asked for always leads, and an
alternative is only mentioned when the saving justifies the journey.
"""

from __future__ import annotations

from flightguru import airports as A, compare
from flightguru.models import Offer
from flightguru.request import SearchRequest


def ap(*codes):
    return tuple(A.get(c) for c in codes)


def req(origins=("JFK",), **overrides) -> SearchRequest:
    base = dict(
        origins=ap(*origins),
        destinations=ap("LAX"),
        depart_date="2026-09-12",
        return_date="2026-09-19",
    )
    base.update(overrides)
    return SearchRequest(**base)


def offer(price, origin, airline="Delta", minutes=385, stops=0) -> Offer:
    return Offer(
        source="GoogleFlights",
        search_date="2026-09-12",
        airline=airline,
        flight_numbers="DL 1",
        depart_time="2026-09-12 08:15",
        arrive_time="2026-09-12 11:40",
        duration="6h 25m",
        stops=stops,
        layovers="",
        base_price=0.0,
        taxes_fees=0.0,
        total_price=price,
        currency="USD",
        duration_minutes=minutes,
        origin_airport=origin,
        destination_airport="LAX",
    )


# --- grouping ---------------------------------------------------------------


def test_cheapest_per_airport_is_picked():
    offers = [offer(300, "JFK"), offer(250, "JFK"), offer(180, "EWR")]
    best = compare.cheapest_by_airport(offers)
    assert best["JFK"].total_price == 250
    assert best["EWR"].total_price == 180


def test_offers_without_an_airport_are_dropped_not_guessed():
    """Attributing a fare to the wrong airport would corrupt the whole answer."""
    best = compare.cheapest_by_airport([offer(100, "")])
    assert best == {}


def test_zero_and_negative_prices_are_ignored():
    best = compare.cheapest_by_airport([offer(0, "JFK"), offer(-5, "JFK")])
    assert best == {}


def test_airport_codes_are_normalised():
    best = compare.cheapest_by_airport([offer(200, "ewr")])
    assert "EWR" in best


# --- the headline -----------------------------------------------------------


def test_requested_airport_leads_even_when_another_is_cheaper():
    """You asked about JFK, so the JFK fare is the answer. Newark is an extra."""
    offers = [offer(240, "JFK"), offer(137, "EWR")]
    result = compare.compare(offers, req())
    assert result.best.airport == "JFK"
    assert result.best.price == 240
    assert [s.airport for s in result.suggestions] == ["EWR"]


def test_cheapest_requested_airport_wins_when_several_were_asked_for():
    offers = [offer(240, "JFK"), offer(200, "LGA"), offer(137, "EWR")]
    result = compare.compare(offers, req(origins=("JFK", "LGA")))
    assert result.best.airport == "LGA"


def test_falls_back_to_the_cheapest_overall_if_the_requested_airport_had_nothing():
    """Better to answer with Newark, labelled, than to answer with nothing."""
    result = compare.compare([offer(137, "EWR")], req())
    assert result.best.airport == "EWR"
    assert result.suggestions == ()


def test_no_offers_gives_no_answer():
    result = compare.compare([], req())
    assert result.best is None
    assert not result.has_suggestions


# --- what counts as worth mentioning ----------------------------------------


def test_a_trivial_saving_is_not_worth_a_drive():
    offers = [offer(240, "JFK"), offer(236, "EWR")]
    assert not compare.compare(offers, req()).has_suggestions


def test_a_real_saving_is_reported():
    offers = [offer(240, "JFK"), offer(180, "EWR")]
    assert compare.compare(offers, req()).has_suggestions


def test_a_small_saving_on_an_expensive_fare_is_noise():
    """$30 off a $2,000 long-haul is not a reason to change airports."""
    offers = [offer(2000, "JFK"), offer(1970, "EWR")]
    assert not compare.compare(offers, req()).has_suggestions


def test_a_proportionate_saving_on_an_expensive_fare_is_reported():
    offers = [offer(2000, "JFK"), offer(1600, "EWR")]
    assert compare.compare(offers, req()).has_suggestions


def test_more_expensive_alternatives_are_never_suggested():
    offers = [offer(240, "JFK"), offer(400, "EWR")]
    assert not compare.compare(offers, req()).has_suggestions


def test_suggestions_are_ordered_by_saving():
    offers = [offer(400, "JFK"), offer(300, "EWR"), offer(200, "HVN")]
    result = compare.compare(offers, req())
    assert [s.airport for s in result.suggestions] == ["HVN", "EWR"]


def test_suggestions_are_capped():
    offers = [offer(500, "JFK")] + [
        offer(100 + i, code) for i, code in enumerate(["EWR", "LGA", "HVN", "ISP"])
    ]
    result = compare.compare(offers, req())
    assert len(result.suggestions) <= compare.MAX_SUGGESTIONS


# --- wording ----------------------------------------------------------------


def test_saving_is_measured_against_the_requested_airport():
    offers = [offer(240, "JFK"), offer(137, "EWR")]
    result = compare.compare(offers, req())
    assert result.saving_over_best(result.suggestions[0]) == 103


def test_distance_is_reported_when_known():
    offers = [offer(240, "JFK"), offer(137, "EWR")]
    result = compare.compare(offers, req(), distances={"EWR": 21.4})
    line = compare.describe_saving(result, result.suggestions[0])
    assert "EWR" in line and "103" in line and "21 mi" in line


def test_distance_is_omitted_when_unknown():
    offers = [offer(240, "JFK"), offer(137, "EWR")]
    result = compare.compare(offers, req())
    assert "mi away" not in compare.describe_saving(result, result.suggestions[0])


def test_option_reports_its_city():
    offers = [offer(240, "JFK"), offer(137, "HVN")]
    result = compare.compare(offers, req())
    assert result.suggestions[0].city == "New Haven"


# --- a slightly dearer flight that is obviously the better buy --------------


def test_a_much_faster_flight_for_a_small_premium_is_flagged():
    """The real case: $70 with a 7-hour layover vs $84 nonstop.

    Ranking on price alone would send the eleven-hour itinerary and say nothing
    about the nonstop $14 away.
    """
    offers = [
        offer(70, "BDL", airline="Breeze", minutes=692, stops=1),
        offer(84, "HVN", airline="Avelo", minutes=170, stops=0),
    ]
    result = compare.compare(offers, req(origins=("BDL",)))
    assert result.best.airport == "BDL"          # cheapest still leads
    assert result.faster is not None
    assert result.faster.airport == "HVN"


def test_a_faster_flight_that_costs_far_more_is_not_flagged():
    offers = [
        offer(70, "BDL", minutes=692),
        offer(600, "HVN", minutes=170),
    ]
    assert compare.compare(offers, req(origins=("BDL",))).faster is None


def test_a_marginally_faster_flight_is_not_flagged():
    """Twenty minutes saved is not a reason to spend more."""
    offers = [
        offer(70, "BDL", minutes=200),
        offer(84, "HVN", minutes=180),
    ]
    assert compare.compare(offers, req(origins=("BDL",))).faster is None


def test_a_faster_option_from_the_same_airport_is_found():
    """The better trade is often a different flight from the same airport."""
    offers = [
        offer(70, "BDL", minutes=692, stops=2),
        offer(95, "BDL", airline="JetBlue", minutes=200, stops=0),
    ]
    faster = compare.compare(offers, req(origins=("BDL",))).faster
    assert faster is not None and faster.airport == "BDL"


def test_an_already_suggested_airport_is_not_reported_twice():
    """If it is already the cheaper option, it does not need a second heading."""
    offers = [
        offer(240, "JFK", minutes=692),
        offer(137, "EWR", minutes=170),
    ]
    result = compare.compare(offers, req())
    assert [s.airport for s in result.suggestions] == ["EWR"]
    assert result.faster is None


def test_the_largest_time_saving_wins():
    offers = [
        offer(70, "BDL", minutes=692),
        offer(80, "HVN", minutes=400),
        offer(85, "PVD", minutes=170),
    ]
    assert compare.compare(offers, req(origins=("BDL",))).faster.airport == "PVD"


def test_a_bigger_premium_is_allowed_on_an_expensive_fare():
    """25% of a long-haul is a fairer ceiling than a flat $75."""
    offers = [
        offer(900, "JFK", minutes=1400),
        offer(1050, "EWR", minutes=800),
    ]
    assert compare.compare(offers, req()).faster is not None


def test_offers_without_a_duration_are_not_compared_on_speed():
    offers = [offer(70, "BDL", minutes=0), offer(84, "HVN", minutes=170)]
    assert compare.compare(offers, req(origins=("BDL",))).faster is None


# --- the New Haven scenario end to end --------------------------------------


def test_the_avelo_case():
    """The example that started this: a cheap regional beside a big airport.

    Asked about New York; Avelo out of Tweed New Haven is far cheaper. The JFK
    fare still leads, with New Haven offered as the saving.
    """
    offers = [
        offer(240, "JFK", airline="Delta"),
        offer(228, "LGA", airline="American"),
        offer(84, "HVN", airline="Avelo"),
    ]
    request = req(origins=("JFK", "LGA")).with_alternatives(origins=ap("HVN"))
    result = compare.compare(offers, request, distances={"HVN": 63.0})

    assert result.best.airport == "LGA"
    assert result.suggestions[0].airport == "HVN"
    assert result.suggestions[0].offer.airline == "Avelo"
    assert result.saving_over_best(result.suggestions[0]) == 144
