"""Tests for the pure part of health checks (no network)."""

from __future__ import annotations

from flightguru.health import providers_check


def test_providers_check_ok(make_settings):
    name, ok, info = providers_check(make_settings())
    assert name == "providers_configured"
    assert ok
    assert "serpapi" in info


def test_providers_check_fails_when_none(make_settings):
    _, ok, info = providers_check(make_settings(duffel_token="", serpapi_key=""))
    assert not ok
    assert info == "none"
