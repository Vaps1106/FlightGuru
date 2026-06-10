"""Shared test fixtures."""

from __future__ import annotations

import pytest

from flightguru.config import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        duffel_token="dummy-duffel-token-1234567890",
        duffel_version="v2",
        serpapi_key="serpapi_realkey1234567890abcdef",
        telegram_bot_token="t",
        telegram_chat_id="c",
        providers=("duffel", "serpapi"),
        origin="BOM",
        destination="JFK",
        search_start_date="2026-07-20",
        search_end_date="2026-08-14",
        search_date_step=1,
        serpapi_max_dates=8,
        target_price=700,
        currency="USD",
        notify_every_run=True,
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
