"""SerpApi provider — live Google Flights display prices (cross-check source).

API: GET https://serpapi.com/search?engine=google_flights
Free tier is ~100 searches/month, so search.py caps how many dates it checks.
SerpApi gives an all-in display price but no base/tax breakdown.
"""

from __future__ import annotations

from .. import net
from ..config import Settings
from ..models import Offer
from ..normalize import fmt_minutes, to_float

BASE_URL = "https://serpapi.com/search"


def search_serpapi(settings: Settings, dep_date: str) -> list[Offer]:
    """Live SerpApi (Google Flights) search for one departure date."""
    params = {
        "engine": "google_flights",
        "departure_id": settings.origin,
        "arrival_id": settings.destination,
        "outbound_date": dep_date,
        "type": "2",  # one-way
        "currency": settings.currency,
        "hl": "en",
        "api_key": settings.serpapi_key,
    }
    data = net.request_json("GET", BASE_URL, params=params)
    return parse_serpapi(data, dep_date, settings.currency)


def parse_serpapi(response_json: dict, dep_date: str, currency: str = "USD") -> list[Offer]:
    """Convert a SerpApi google_flights response into Offers (no validation here).

    SerpApi prices are plain numbers with no per-offer currency, so we stamp the
    currency SerpApi reports having used (``search_parameters.currency``) rather
    than blindly assuming the one we requested. If SerpApi ever prices in a
    different currency than asked, the offer is then labeled with the real
    currency, and the currency guard in ``normalize()`` filters it out instead of
    silently comparing, say, EUR against a USD target. ``currency`` is the
    fallback only for the (rare) case where SerpApi doesn't echo one back.

    Residual limit: SerpApi does not independently confirm the currency of each
    price, so this reflects SerpApi's own reported currency, not a per-price
    guarantee. Duffel remains the source with a verified currency + tax breakdown.
    """
    reported = ((response_json.get("search_parameters") or {}).get("currency") or "").strip()
    offer_currency = reported or currency

    offers: list[Offer] = []
    raw = (response_json.get("best_flights") or []) + (response_json.get("other_flights") or [])
    for f in raw:
        legs = f.get("flights") or []
        if not legs:
            continue
        first, last = legs[0], legs[-1]

        flight_numbers = " + ".join(leg.get("flight_number", "") for leg in legs)
        layovers = ", ".join(
            f"{lo.get('id') or lo.get('name', '')} ({fmt_minutes(lo.get('duration') or 0)})"
            for lo in (f.get("layovers") or [])
        )

        offers.append(
            Offer(
                source="SerpApi",
                search_date=dep_date,
                airline=first.get("airline", ""),
                flight_numbers=flight_numbers,
                depart_time=(first.get("departure_airport") or {}).get("time", ""),
                arrive_time=(last.get("arrival_airport") or {}).get("time", ""),
                duration=fmt_minutes(f.get("total_duration") or 0),
                stops=len(legs) - 1,
                layovers=layovers,
                base_price=0.0,
                taxes_fees=0.0,
                total_price=to_float(f.get("price")) or 0.0,
                currency=offer_currency,
            )
        )
    return offers
