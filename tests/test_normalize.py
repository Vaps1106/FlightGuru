"""Tests for validation, de-duplication, and sorting."""

from __future__ import annotations

from flightguru.models import Offer
from flightguru.normalize import is_valid, normalize


def mk(total, **overrides) -> Offer:
    base = dict(
        source="Test",
        search_date="2026-07-20",
        airline="Air India",
        flight_numbers="AI 119",
        depart_time="2026-07-20T02:00:00",
        arrive_time="2026-07-20T08:30:00",
        duration="9h 0m",
        stops=0,
        layovers="",
        base_price=0.0,
        taxes_fees=0.0,
        total_price=total,
        currency="USD",
    )
    base.update(overrides)
    return Offer(**base)


def test_rejects_zero_price():
    assert not is_valid(mk(0))


def test_rejects_missing_currency():
    assert not is_valid(mk(500, currency=""))


def test_rejects_missing_airline():
    assert not is_valid(mk(500, airline=""))


def test_sorts_cheapest_first():
    out = normalize([mk(800, flight_numbers="B"), mk(600, flight_numbers="C")])
    assert [o.total_price for o in out] == [600, 800]


def test_dedupes_identical_offers():
    out = normalize([mk(600), mk(600)])
    assert len(out) == 1


def test_price_ties_break_deterministically():
    # Same price, different dates/sources: order must not depend on input order.
    a = mk(600, search_date="2026-07-21", source="SerpApi", flight_numbers="AI 1")
    b = mk(600, search_date="2026-07-20", source="Duffel", flight_numbers="AI 2")
    forward = [o.search_date for o in normalize([a, b])]
    backward = [o.search_date for o in normalize([b, a])]
    assert forward == backward == ["2026-07-20", "2026-07-21"]


def test_drops_invalid_keeps_valid():
    out = normalize([mk(0, flight_numbers="Z"), mk(690, flight_numbers="Y")])
    assert len(out) == 1
    assert out[0].total_price == 690
