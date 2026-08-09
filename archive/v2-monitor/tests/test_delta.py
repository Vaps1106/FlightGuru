"""Tests for the price decision logic."""

from __future__ import annotations

from flightguru.delta import decide, should_send_alert


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


def test_alert_sends_when_no_prior_alert():
    d = decide(650, None, 700)
    assert should_send_alert(d, 650, None)


def test_alert_suppressed_when_not_lower():
    d = decide(650, None, 700)
    assert not should_send_alert(d, 650, 650)   # same as last alert
    assert not should_send_alert(d, 650, 640)   # higher than last alert


def test_alert_resends_when_price_drops_further():
    d = decide(600, None, 700)
    assert should_send_alert(d, 600, 650)       # dropped below last alert


def test_no_alert_when_above_target():
    d = decide(750, None, 700)
    assert not should_send_alert(d, 750, None)
