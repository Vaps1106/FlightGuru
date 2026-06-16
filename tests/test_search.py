"""Tests for the date-range and sampling logic (no network)."""

from __future__ import annotations

import threading
import time

from flightguru import search as search_mod
from flightguru.models import Offer
from flightguru.search import evenly_sample, plan_searches, search_all, search_dates


def _offer(price: float, dep_date: str, source: str = "Test") -> Offer:
    return Offer(
        source=source,
        search_date=dep_date,
        airline="Air India",
        flight_numbers="AI 119",
        depart_time="x",
        arrive_time="y",
        duration="9h 0m",
        stops=0,
        layovers="",
        base_price=0.0,
        taxes_fees=0.0,
        total_price=price,
        currency="USD",
    )


def test_search_dates_every_day(make_settings):
    dates = search_dates(make_settings(search_date_step=1))
    assert dates[0] == "2026-07-20"
    assert dates[-1] == "2026-08-14"
    assert len(dates) == 26  # 12 days in July + 14 in August


def test_search_dates_with_step(make_settings):
    dates = search_dates(make_settings(search_date_step=7))
    assert dates == ["2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10"]


def test_evenly_sample_keeps_ends():
    sample = evenly_sample(list(range(26)), 8)
    assert len(sample) == 8
    assert sample[0] == 0
    assert sample[-1] == 25


def test_evenly_sample_no_cap_returns_all():
    assert evenly_sample([1, 2, 3], 0) == [1, 2, 3]
    assert evenly_sample([1, 2, 3], 10) == [1, 2, 3]


def test_plan_searches_duffel_every_date_serpapi_sampled(make_settings):
    settings = make_settings(search_date_step=7, serpapi_max_dates=2)
    tasks = plan_searches(settings)
    duffel_dates = [d for p, d in tasks if p == "duffel"]
    serpapi_dates = [d for p, d in tasks if p == "serpapi"]
    assert duffel_dates == ["2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10"]
    assert serpapi_dates == ["2026-07-20", "2026-08-10"]  # sampled to 2, keeps ends


def test_search_all_preserves_deterministic_order(make_settings, monkeypatch):
    """Even when later requests finish first, offers come back in plan order."""
    settings = make_settings(
        providers=("duffel",), search_date_step=7, search_max_workers=4
    )

    def slow_duffel(_settings, dep_date):
        # Earlier dates sleep longer, so they finish last — order must still hold.
        delay = {"2026-07-20": 0.06, "2026-07-27": 0.04, "2026-08-03": 0.02}
        time.sleep(delay.get(dep_date, 0.0))
        return [_offer(100.0, dep_date)]

    monkeypatch.setitem(search_mod._SEARCHERS, "duffel", slow_duffel)
    offers = search_all(settings)
    assert [o.search_date for o in offers] == [
        "2026-07-20",
        "2026-07-27",
        "2026-08-03",
        "2026-08-10",
    ]


def test_search_all_runs_concurrently(make_settings, monkeypatch):
    """A bounded pool should overlap requests, not run them one-by-one."""
    settings = make_settings(
        providers=("duffel",), search_date_step=1, search_max_workers=6
    )
    active = 0
    peak = 0
    lock = threading.Lock()

    def counting_duffel(_settings, dep_date):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return [_offer(100.0, dep_date)]

    monkeypatch.setitem(search_mod._SEARCHERS, "duffel", counting_duffel)
    search_all(settings)
    assert peak > 1  # at least some requests overlapped


def test_search_all_reports_errors_and_continues(make_settings, monkeypatch):
    settings = make_settings(
        providers=("duffel",), search_date_step=7, search_max_workers=4
    )

    def flaky_duffel(_settings, dep_date):
        if dep_date == "2026-07-27":
            raise RuntimeError("boom")
        return [_offer(100.0, dep_date)]

    monkeypatch.setitem(search_mod._SEARCHERS, "duffel", flaky_duffel)
    errors: list[str] = []
    offers = search_all(settings, on_error=lambda p, d, e: errors.append(f"{p} {d}"))
    assert len(offers) == 3  # 4 dates, one failed
    assert errors == ["duffel 2026-07-27"]


def test_search_all_no_providers_returns_empty(make_settings):
    settings = make_settings(providers=())
    assert search_all(settings) == []
