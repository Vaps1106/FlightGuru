"""Tests for SQLite snapshot storage (each uses an isolated temp DB)."""

from __future__ import annotations

from flightguru import storage
from flightguru.models import Offer


def _offer(total=630.0, date_="2026-07-20") -> Offer:
    return Offer(
        source="SerpApi",
        search_date=date_,
        airline="Etihad",
        flight_numbers="EY 207 + EY 3",
        depart_time="2026-07-20T19:40:00",
        arrive_time="2026-07-21T08:10:00",
        duration="20h 30m",
        stops=1,
        layovers="AUH (3h 10m)",
        base_price=0.0,
        taxes_fees=0.0,
        total_price=total,
        currency="USD",
    )


def test_save_and_count(tmp_path):
    db = str(tmp_path / "t.db")
    storage.init_db(db)
    assert storage.count_snapshots(db) == 0
    storage.save_snapshot(_offer(630), "BOM", "JFK", "http://link", False, path=db)
    assert storage.count_snapshots(db) == 1
    assert storage.get_last_total_price(db) == 630.0


def test_last_price_none_when_empty(tmp_path):
    assert storage.get_last_total_price(str(tmp_path / "none.db")) is None


def test_last_price_is_most_recent(tmp_path):
    db = str(tmp_path / "m.db")
    storage.save_snapshot(_offer(700), "BOM", "JFK", "l", False, path=db)
    storage.save_snapshot(_offer(650), "BOM", "JFK", "l", True, path=db)
    assert storage.get_last_total_price(db) == 650.0


def test_last_alert_price_none_when_no_alert(tmp_path):
    db = str(tmp_path / "a.db")
    storage.init_db(db)
    assert storage.last_alert_price("2026-07-20", db) is None


def test_last_alert_price_per_date_and_most_recent(tmp_path):
    db = str(tmp_path / "a.db")
    storage.record_alert(_offer(650, "2026-07-20"), "USD", path=db)
    storage.record_alert(_offer(620, "2026-07-20"), "USD", path=db)
    storage.record_alert(_offer(700, "2026-07-21"), "USD", path=db)
    assert storage.last_alert_price("2026-07-20", db) == 620.0   # most recent for date
    assert storage.last_alert_price("2026-07-21", db) == 700.0   # scoped by date
    assert storage.last_alert_price("2026-07-22", db) is None
