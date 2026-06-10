"""Build a booking deep link for an offer.

Uses a Kayak deterministic URL (kayak.com/flights/ORIGIN-DEST/DATE) which lands
the user directly on real results for the route and date, pre-filled, sorted
cheapest-first. This replaced the old Google Flights "#flt=" hash format, which
Google deprecated — it dumped the user on a blank search page (the exact problem
the rebuild spec calls unacceptable). See docs/DECISIONS.md D6.

Returns None if the route/date are missing — and per the project rules, the
caller must then NOT send an alert.
"""

from __future__ import annotations

from .config import Settings
from .models import Offer


def build_deep_link(offer: Offer, settings: Settings) -> str | None:
    origin = (settings.origin or "").strip()
    destination = (settings.destination or "").strip()
    date_ = (offer.search_date or "").strip()
    if not (origin and destination and date_):
        return None
    # sort=price_a -> cheapest first on arrival.
    return f"https://www.kayak.com/flights/{origin}-{destination}/{date_}?sort=price_a"
