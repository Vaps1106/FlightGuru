"""Normalize, validate, and de-duplicate offers from all providers.

This is home to the "never invent data" guardrail: any offer missing a price,
currency, times, or airline is rejected — never guessed. Shared parsing helpers
live here too and are reused by the provider modules.
"""

from __future__ import annotations

import re
from datetime import datetime

from .models import Offer


# --- shared parsing helpers (used by providers) ------------------------------

def to_float(value) -> float | None:
    """Best-effort float; returns None if the value isn't a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_minutes(total) -> str:
    """123 -> '2h 3m'."""
    total = int(total or 0)
    return f"{total // 60}h {total % 60}m"


def fmt_time(value: str) -> str:
    """ISO datetime -> 'YYYY-MM-DD HH:MM' for clean display.

    Duffel returns full ISO timestamps (``2026-07-20T02:15:00-04:00``); SerpApi
    already returns ``2026-07-20 08:00``. Normalizing here keeps both providers'
    depart/arrive times consistent in the log and Telegram message. Anything that
    isn't ISO is passed through unchanged.
    """
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value


def iso_duration_to_minutes(iso: str) -> int:
    """ISO-8601 duration 'PT20H55M' -> 1255 minutes."""
    if not iso:
        return 0
    h = re.search(r"(\d+)H", iso)
    m = re.search(r"(\d+)M", iso)
    return (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)


def fmt_iso_duration(iso: str) -> str:
    """'PT20H55M' -> '20h 55m'."""
    return fmt_minutes(iso_duration_to_minutes(iso))


def minutes_between(iso_a: str, iso_b: str) -> int:
    """Minutes between two ISO datetimes; 0 if either can't be parsed."""
    try:
        a = datetime.fromisoformat(iso_a)
        b = datetime.fromisoformat(iso_b)
        return int((b - a).total_seconds() // 60)
    except (TypeError, ValueError):
        return 0


# --- validation + normalization ----------------------------------------------

def is_valid(offer: Offer) -> bool:
    """An offer is trustworthy only if these core fields are real."""
    return (
        bool(offer.currency)
        and offer.total_price > 0
        and bool(offer.depart_time)
        and bool(offer.arrive_time)
        and bool(offer.airline)
    )


def normalize(offers: list[Offer]) -> list[Offer]:
    """Drop invalid offers, de-duplicate, and sort cheapest-first."""
    seen: set[tuple] = set()
    result: list[Offer] = []
    for offer in offers:
        if not is_valid(offer):
            continue
        key = (offer.airline, offer.flight_numbers, offer.search_date, round(offer.total_price, 2))
        if key in seen:
            continue
        seen.add(key)
        result.append(offer)
    # Cheapest first; the extra keys break price ties deterministically so the
    # same offers always pick the same "cheapest" winner, run to run.
    result.sort(
        key=lambda o: (o.total_price, o.search_date, o.source, o.flight_numbers)
    )
    return result
