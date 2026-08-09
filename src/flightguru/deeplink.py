"""Build a booking link for an offer.

Kayak takes a deterministic URL — ``kayak.com/flights/ORIGIN-DEST/DATE`` — which
lands on real results for that exact route and date, sorted cheapest first. The
old Google Flights ``#flt=`` hash format was dropped by Google and dumped people
on a blank search page, which is worse than no link at all. See
docs/DECISIONS.md D6.

v2 read the route from global settings, because there was only one. v3 reads it
off the offer itself: a search covering JFK, LGA and EWR at once must link to the
airport the fare actually departs from, or the link contradicts the message.

Returns None when the route or date is missing. A missing link is reported as
such rather than papered over with a guess.
"""

from __future__ import annotations

from .models import Offer

KAYAK = "https://www.kayak.com/flights"


def build_deep_link(offer: Offer) -> str | None:
    """A Kayak link for this offer's real route and date."""
    origin = (offer.origin_airport or "").strip().upper()
    destination = (offer.destination_airport or "").strip().upper()
    depart = (offer.search_date or "").strip()

    if not (origin and destination and depart):
        return None

    route = f"{KAYAK}/{origin}-{destination}/{depart}"
    # Round trips take a second date segment, which is what makes Kayak show
    # return fares rather than a one-way price that contradicts our total.
    if offer.return_date:
        route = f"{route}/{offer.return_date.strip()}"

    return f"{route}?sort=price_a"
