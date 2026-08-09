"""Tests for Telegram message construction (pure; no network)."""

from __future__ import annotations

from flightguru.delta import Decision
from flightguru.models import Offer
from flightguru.notify import build_message


def _offer(total=630.0) -> Offer:
    return Offer(
        source="SerpApi",
        search_date="2026-07-20",
        airline="Etihad",
        flight_numbers="EY 207 + EY 3",
        depart_time="2026-07-20 05:00",
        arrive_time="2026-07-20 16:00",
        duration="20h 30m",
        stops=1,
        layovers="AUH (3h 10m)",
        base_price=0.0,
        taxes_fees=0.0,
        total_price=total,
        currency="USD",
    )


def test_message_below_target(make_settings):
    decision = Decision(below_target=True, dropped=False, drop_amount=0.0, alert=True)
    msg = build_message(make_settings(), _offer(), decision, "http://kayak/x", "2026-06-10 18:50 UTC")
    assert "BELOW TARGET" in msg
    assert "Verified at: 2026-06-10 18:50 UTC" in msg
    assert "http://kayak/x" in msg
    assert "<" not in msg and ">" not in msg.replace("->", "")  # plain text, no HTML tags


def test_message_reports_drop(make_settings):
    decision = Decision(below_target=True, dropped=True, drop_amount=40.0, alert=True)
    msg = build_message(make_settings(), _offer(), decision, "http://x", "t")
    assert "Price dropped USD 40" in msg


def test_message_above_target(make_settings):
    decision = Decision(below_target=False, dropped=False, drop_amount=0.0, alert=False)
    msg = build_message(make_settings(), _offer(750), decision, "http://x", "t")
    assert "above target" in msg
