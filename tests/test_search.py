"""Tests for the date-range and sampling logic (no network)."""

from __future__ import annotations

from flightguru.search import evenly_sample, search_dates


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
