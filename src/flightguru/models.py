"""Shared data types for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Offer:
    """One normalized flight option, from any provider.

    Prices are in ``currency``. ``base_price`` + ``taxes_fees`` == ``total_price``
    when a provider gives the breakdown; SerpApi only gives a display total, so
    its base/taxes are 0 and ``total_price`` is the all-in figure shown.

    The fields after ``currency`` all carry defaults, because v2 offers had no
    concept of which airport a fare left from -- there was only ever one. v3
    searches several airports at once, so ``origin_airport`` is read back off
    the itinerary rather than assumed.
    """

    source: str            # "Duffel" | "SerpApi" | "GoogleFlights"
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

    # ``duration`` is for display; this is the same span in minutes, kept so two
    # itineraries can actually be compared against each other. A formatted
    # string like "11h 32m" cannot be.
    duration_minutes: int = 0

    # Which airports this itinerary actually uses. Taken from the flight legs,
    # not from the search, so a Newark fare found while searching "JFK,LGA,EWR"
    # is correctly attributed to Newark.
    origin_airport: str = ""
    destination_airport: str = ""

    return_date: str | None = None
    trip_type: str = "one_way"

    # Google Flights tokens. ``departure_token`` fetches the return leg of a
    # round trip; ``booking_token`` fetches where to actually buy it. Both cost
    # an extra search, so they are only spent on the option we recommend.
    departure_token: str = ""
    booking_token: str = ""
