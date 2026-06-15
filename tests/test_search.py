"""Tests for the date-range and sampling logic (no network)."""

from __future__ import annotations

from flightguru import search as search_mod
from flightguru.models import Offer
from flightguru.search import evenly_sample, search_all, search_dates


def _offer(date_: str, total: float, source: str = "Duffel") -> Offer:
    return Offer(
        source=source,
        search_date=date_,
        airline="Etihad",
        flight_numbers="EY 1",
        depart_time="2026-07-20T19:40:00",
        arrive_time="2026-07-21T08:10:00",
        duration="20h",
        stops=0,
        layovers="",
        base_price=0.0,
        taxes_fees=0.0,
        total_price=total,
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


def test_evenly_sample_has_no_duplicates():
    # n close to len once produced repeated indices; samples must stay unique.
    for n in range(1, 12):
        sample = evenly_sample(list(range(10)), n)
        assert len(sample) == len(set(sample))


def _stub_providers(monkeypatch):
    """Make both providers return one deterministic offer per (provider, date)."""
    monkeypatch.setattr(
        search_mod.duffel, "search_duffel",
        lambda s, d: [_offer(d, 600 + int(d[-2:]))],
    )
    monkeypatch.setattr(
        search_mod.serpapi, "search_serpapi",
        lambda s, d: [_offer(d, 500 + int(d[-2:]))],
    )


def test_search_all_sequential_and_parallel_match(make_settings, monkeypatch):
    _stub_providers(monkeypatch)
    seq = search_all(make_settings(search_workers=1))
    par = search_all(make_settings(search_workers=5))
    # Same set of offers regardless of concurrency — order may differ, content can't.
    key = lambda o: (o.source, o.search_date, o.total_price)
    assert sorted(map(key, seq)) == sorted(map(key, par))
    assert len(seq) > 0


def test_search_all_isolates_errors(make_settings, monkeypatch):
    def boom(s, d):
        raise RuntimeError("provider down")

    monkeypatch.setattr(search_mod.duffel, "search_duffel", boom)
    monkeypatch.setattr(
        search_mod.serpapi, "search_serpapi",
        lambda s, d: [_offer(d, 650, source="SerpApi")],
    )
    errors: list[str] = []
    offers = search_all(
        make_settings(search_workers=4),
        on_error=lambda p, d, e: errors.append(f"{p} {d}"),
    )
    # SerpApi offers still come back; every Duffel date reported its error.
    assert offers and all(o.source == "SerpApi" for o in offers)
    assert all(e.startswith("duffel") for e in errors)
