"""Tests for booking deep-link construction."""

from __future__ import annotations

from flightguru.deeplink import build_deep_link
from flightguru.models import Offer


def _offer(search_date="2026-07-20") -> Offer:
    return Offer(
        source="Test",
        search_date=search_date,
        airline="Air India",
        flight_numbers="AI 119",
        depart_time="x",
        arrive_time="y",
        duration="9h 0m",
        stops=0,
        layovers="",
        base_price=0.0,
        taxes_fees=0.0,
        total_price=600.0,
        currency="USD",
    )


def test_builds_kayak_link(make_settings):
    link = build_deep_link(_offer(), make_settings())
    assert link is not None
    assert "kayak.com/flights/BOM-JFK/2026-07-20" in link


def test_returns_none_without_date(make_settings):
    assert build_deep_link(_offer(search_date=""), make_settings()) is None
