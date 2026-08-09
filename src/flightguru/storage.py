"""Persistence — a log of searches, in SQLite at data/flightguru.db.

v2 stored one row per scheduled run and used it to answer "has the price
dropped since last time". v3 has no last time, so the table changes purpose: it
is now a record of what was searched and what came back, useful for seeing
whether a fare you were quoted last week is still around.

It is a log, not state the bot depends on. A failure to write must never lose
someone their search result, so callers treat saving as best-effort.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from .models import Offer

DB_PATH = "data/flightguru.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    searched_at_utc TEXT NOT NULL,
    chat_id        TEXT,
    trip_type      TEXT,
    requested_from TEXT,   -- what the traveller asked for, comma separated
    requested_to   TEXT,
    searched_from  TEXT,   -- including the nearby airports we added
    depart_date    TEXT,
    return_date    TEXT,
    passengers     INTEGER
);

CREATE TABLE IF NOT EXISTS results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id      INTEGER NOT NULL,
    origin         TEXT,   -- the airport this fare actually departs from
    destination    TEXT,
    airline        TEXT,
    flight_numbers TEXT,
    total_price    REAL,
    currency       TEXT,
    stops          INTEGER,
    duration       TEXT,
    layovers       TEXT,
    deep_link      TEXT,
    is_suggestion  INTEGER,  -- 1 if a nearby airport we offered, 0 if requested
    FOREIGN KEY (search_id) REFERENCES searches(id)
);

CREATE INDEX IF NOT EXISTS idx_results_search ON results(search_id);
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


def save_search(
    request,
    comparison,
    chat_id: str = "",
    links: dict[str, str] | None = None,
    path: str = DB_PATH,
    searched_at: str | None = None,
) -> int:
    """Record one search and every airport's cheapest fare. Returns its id.

    ``links`` maps an airport code to its booking link, so the log holds the same
    URL the traveller was actually given.
    """
    init_db(path)
    links = links or {}
    requested = {a.iata for a in request.origins}

    conn = _connect(path)
    try:
        cursor = conn.execute(
            "INSERT INTO searches (searched_at_utc, chat_id, trip_type, requested_from, "
            "requested_to, searched_from, depart_date, return_date, passengers) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                searched_at or _now(),
                str(chat_id),
                request.trip_type,
                ",".join(a.iata for a in request.origins),
                ",".join(a.iata for a in request.destinations),
                ",".join(a.iata for a in request.all_origins),
                request.depart_date,
                request.return_date,
                request.passengers,
            ),
        )
        search_id = cursor.lastrowid

        if comparison is not None:
            for option in comparison.all_options:
                offer: Offer = option.offer
                conn.execute(
                    "INSERT INTO results (search_id, origin, destination, airline, "
                    "flight_numbers, total_price, currency, stops, duration, layovers, "
                    "deep_link, is_suggestion) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        search_id,
                        option.airport,
                        offer.destination_airport,
                        offer.airline,
                        offer.flight_numbers,
                        offer.total_price,
                        offer.currency,
                        offer.stops,
                        offer.duration,
                        offer.layovers,
                        links.get(option.airport),
                        int(option.airport not in requested),
                    ),
                )
        conn.commit()
        return search_id
    finally:
        conn.close()


def count_searches(path: str = DB_PATH) -> int:
    """How many searches have been logged."""
    if not os.path.exists(path):
        return 0
    conn = _connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    finally:
        conn.close()


def recent_searches(limit: int = 5, chat_id: str = "", path: str = DB_PATH) -> list[dict]:
    """The most recent searches, newest first — used by the /history command."""
    if not os.path.exists(path):
        return []
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        if chat_id:
            rows = conn.execute(
                "SELECT * FROM searches WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (str(chat_id), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM searches ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def cheapest_for_search(search_id: int, path: str = DB_PATH) -> dict | None:
    """The cheapest recorded fare for one search."""
    if not os.path.exists(path):
        return None
    conn = _connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM results WHERE search_id = ? ORDER BY total_price ASC LIMIT 1",
            (search_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
