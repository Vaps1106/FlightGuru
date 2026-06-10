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
