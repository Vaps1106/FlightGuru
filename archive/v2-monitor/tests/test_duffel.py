"""Tests for Duffel response parsing (fixture-based, no network)."""

from __future__ import annotations

from flightguru.providers.duffel import parse_duffel

SAMPLE = {
    "data": {
        "offers": [
            {
                "total_amount": "812.30",
                "base_amount": "520.00",
                "tax_amount": "292.30",
                "total_currency": "USD",
                "owner": {"name": "Emirates", "iata_code": "EK"},
                "slices": [
                    {
                        "duration": "PT20H55M",
                        "segments": [
                            {
                                "marketing_carrier": {"iata_code": "EK", "name": "Emirates"},
                                "marketing_carrier_flight_number": "509",
                                "departing_at": "2026-07-20T22:25:00",
                                "arriving_at": "2026-07-20T23:50:00",
                                "origin": {"iata_code": "BOM"},
                                "destination": {"iata_code": "DXB"},
                            },
                            {
                                "marketing_carrier": {"iata_code": "EK", "name": "Emirates"},
                                "marketing_carrier_flight_number": "203",
                                "departing_at": "2026-07-21T03:40:00",
                                "arriving_at": "2026-07-21T08:50:00",
                                "origin": {"iata_code": "DXB"},
                                "destination": {"iata_code": "JFK"},
                            },
                        ],
                    }
                ],
            },
            {
                # Junk: zero price — parsed here, dropped later by normalize().
                "total_amount": "0",
                "base_amount": "0",
                "tax_amount": "0",
                "total_currency": "USD",
                "owner": {"name": "Junk Air"},
                "slices": [
                    {
                        "duration": "PT10H",
                        "segments": [
                            {
                                "marketing_carrier": {"iata_code": "XX", "name": "Junk Air"},
                                "marketing_carrier_flight_number": "1",
                                "departing_at": "2026-07-20T01:00:00",
                                "arriving_at": "2026-07-20T11:00:00",
                                "origin": {"iata_code": "BOM"},
                                "destination": {"iata_code": "JFK"},
                            }
                        ],
                    }
                ],
            },
        ]
    }
}


def test_parses_offer_fields():
    offers = parse_duffel(SAMPLE, "2026-07-20")
    assert len(offers) == 2  # parsing keeps both; validation happens in normalize
    ek = offers[0]
    assert ek.source == "Duffel"
    assert ek.airline == "Emirates"
    assert ek.flight_numbers == "EK 509 + EK 203"
    assert ek.total_price == 812.30
    assert ek.base_price == 520.00
    assert ek.taxes_fees == 292.30
    assert ek.currency == "USD"
    assert ek.stops == 1
    assert ek.duration == "20h 55m"
    assert "DXB" in ek.layovers
