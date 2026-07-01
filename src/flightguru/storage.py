"""Persistence — store every price check in SQLite.

The database lives at data/flightguru.db and is committed back to the repo by the
monitor workflow, which is how history survives between runs on GitHub Actions.
We store the single cheapest verified offer per run (one row), giving a clean
price-over-time history without bloating the committed file.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from .models import Offer

DB_PATH = "data/flightguru.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at_utc TEXT NOT NULL,
    source         TEXT,
    origin         TEXT,
    destination    TEXT,
    depart_date    TEXT,
    airline        TEXT,
    flight_numbers TEXT,
    base_price     REAL,
    taxes_fees     REAL,
    total_price    REAL,
    currency       TEXT,
    stops          INTEGER,
    duration       TEXT,
    layovers       TEXT,
    deep_link      TEXT,
    below_target   INTEGER
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at_utc TEXT NOT NULL,
    depart_date TEXT,
    source      TEXT,
    total_price REAL,
    currency    TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _connect(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return sqlite3.connect(path)


def init_db(path: str = DB_PATH) -> None:
    """Create tables if they do not exist."""
    conn = _connect(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save_snapshot(
    offer: Offer,
    origin: str,
    destination: str,
    deep_link: str | None,
    below_target: bool,
    path: str = DB_PATH,
    checked_at: str | None = None,
) -> None:
    """Append one price snapshot (the cheapest offer for this run)."""
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO price_snapshots (checked_at_utc, source, origin, destination, "
            "depart_date, airline, flight_numbers, base_price, taxes_fees, total_price, "
            "currency, stops, duration, layovers, deep_link, below_target) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                checked_at or _now(),
                offer.source,
                origin,
                destination,
                offer.search_date,
                offer.airline,
                offer.flight_numbers,
                offer.base_price,
                offer.taxes_fees,
                offer.total_price,
                offer.currency,
                offer.stops,
                offer.duration,
                offer.layovers,
                deep_link,
                int(below_target),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_total_price(path: str = DB_PATH) -> float | None:
    """The total price from the most recent snapshot, or None if no history."""
    if not os.path.exists(path):
        return None
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT total_price FROM price_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def count_snapshots(path: str = DB_PATH) -> int:
    """How many snapshots are stored."""
    if not os.path.exists(path):
        return 0
    conn = _connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    finally:
        conn.close()


def last_alert_price(depart_date: str, path: str = DB_PATH) -> float | None:
    """Total price of the most recent alert sent for this depart_date.

    Returns None if no alert has been sent for that date yet. Used to suppress
    repeat alerts for the same fare when the price has not dropped further.
    """
    if not os.path.exists(path):
        return None
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT total_price FROM alerts_sent WHERE depart_date = ? "
            "ORDER BY id DESC LIMIT 1",
            (depart_date,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def record_alert(
    offer: Offer, currency: str, path: str = DB_PATH, sent_at: str | None = None
) -> None:
    """Log that an alert was sent (used in Phase 4 to avoid duplicate alerts)."""
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO alerts_sent (sent_at_utc, depart_date, source, total_price, currency) "
            "VALUES (?,?,?,?,?)",
            (sent_at or _now(), offer.search_date, offer.source, offer.total_price, currency),
        )
        conn.commit()
    finally:
        conn.close()
