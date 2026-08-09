"""Shared test fixtures."""

from __future__ import annotations

import pytest

from flightguru.config import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        serpapi_key="serpapi_realkey1234567890abcdef",
        telegram_bot_token="123456:test-token",
        telegram_chat_id="6889043609",
        currency="USD",
        nearby_radius_miles=100.0,
        nearby_enabled=True,
        nearby_destination=False,
        poll_timeout=30,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings() -> Settings:
    return _settings()


@pytest.fixture
def make_settings():
    """Factory so tests can build Settings with overrides."""
    return _settings
