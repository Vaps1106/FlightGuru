"""Tests for SerpApi (Google Flights) response parsing (fixture-based)."""

from __future__ import annotations

from flightguru.providers.serpapi import parse_serpapi

SAMPLE = {
    "best_flights": [
        {
            "flights": [
                {
                    "airline": "Air India",
                    "flight_number": "AI 119",
                    "departure_airport": {"id": "BOM", "time": "2026-07-20 02:00"},
                    "arrival_airport": {"id": "JFK", "time": "2026-07-20 08:30"},
                }
            ],
            "total_duration": 930,
            "price": 690,
            "layovers": [],
        }
    ],
    "other_flights": [
        {
            "flights": [
                {
                    "airline": "Emirates",
                    "flight_number": "EK 509",
                    "departure_airport": {"id": "BOM", "time": "2026-07-20 22:25"},
                    "arrival_airport": {"id": "DXB", "time": "2026-07-20 23:50"},
                },
                {
                    "airline": "Emirates",
                    "flight_number": "EK 203",
                    "departure_airport": {"id": "DXB", "time": "2026-07-21 03:40"},
                    "arrival_airport": {"id": "JFK", "time": "2026-07-21 08:50"},
                },
            ],
            "total_duration": 1255,
            "price": 812,
            "layovers": [{"id": "DXB", "duration": 231}],
        }
    ],
}


def test_parses_best_and_other_flights():
    offers = parse_serpapi(SAMPLE, "2026-07-20", "USD")
    assert len(offers) == 2
    assert offers[0].currency == "USD"  # no search_parameters -> falls back to requested

    ai = offers[0]
    assert ai.source == "SerpApi"
    assert ai.airline == "Air India"
    assert ai.total_price == 690.0
    assert ai.stops == 0
    assert ai.duration == "15h 30m"

    ek = offers[1]
    assert ek.flight_numbers == "EK 509 + EK 203"
    assert ek.stops == 1
    assert ek.duration == "20h 55m"
    assert "DXB" in ek.layovers


def test_uses_currency_serpapi_reports_not_requested():
    # We asked for USD, but SerpApi says it priced in EUR. The offer must carry
    # EUR so the downstream currency guard can catch the mismatch (M2).
    resp = dict(SAMPLE, search_parameters={"currency": "EUR"})
    offers = parse_serpapi(resp, "2026-07-20", "USD")
    assert offers and all(o.currency == "EUR" for o in offers)


def test_currency_guard_drops_serpapi_mismatch_end_to_end():
    # A price that is really EUR must not survive a USD-preferred normalize().
    from flightguru.normalize import normalize

    resp = dict(SAMPLE, search_parameters={"currency": "EUR"})
    offers = parse_serpapi(resp, "2026-07-20", "USD")
    kept = normalize(offers, prefer_currency="USD")
    assert kept == []  # mislabeling avoided: nothing wrongly compared to a USD target
