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
