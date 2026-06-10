"""Shared data types for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Offer:
    """One normalized flight option, from any provider.

    Prices are in ``currency``. ``base_price`` + ``taxes_fees`` == ``total_price``
    when a provider gives the breakdown; SerpApi only gives a display total, so
    its base/taxes are 0 and ``total_price`` is the all-in figure shown.
    """

    source: str            # "Duffel" | "SerpApi"
    search_date: str       # departure date searched (YYYY-MM-DD)
    airline: str
    flight_numbers: str    # e.g. "EK 509 + EK 203"
    depart_time: str
    arrive_time: str
    duration: str          # e.g. "20h 55m"
    stops: int
    layovers: str          # e.g. "DXB (3h 51m)"
    base_price: float
    taxes_fees: float
    total_price: float
    currency: str
