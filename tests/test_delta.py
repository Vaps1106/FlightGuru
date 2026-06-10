"""Tests for the price decision logic."""

from __future__ import annotations

from flightguru.delta import decide


def test_below_target_triggers_alert():
    d = decide(650, None, 700)
    assert d.below_target
    assert d.alert
    assert not d.dropped


def test_above_target_no_alert():
    d = decide(750, None, 700)
    assert not d.below_target
    assert not d.alert


def test_detects_price_drop():
    d = decide(650, 700, 800)
    assert d.dropped
    assert d.drop_amount == 50


def test_no_drop_when_price_higher():
    d = decide(720, 700, 800)
    assert not d.dropped
    assert d.drop_amount == 0.0
