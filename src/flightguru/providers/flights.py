"""Google Flights search, via SerpApi, driven by a SearchRequest.

Replaces the v2 ``serpapi.py`` provider, which could only ask one question:
one-way, one origin, one destination, one date. This one handles round trips,
multi-city, and several airports per side.

The multi-airport part is the reason the nearby-airport feature is affordable.
``departure_id`` accepts a comma-separated list, so pricing JFK, LGA, EWR and
HVN together is a **single** search against the quota, not four. Each returned
flight says which airport it actually leaves from, which is what lets us tell
you that Newark is cheaper than the JFK you asked about.
"""

from __future__ import annotations

from .. import net
from ..airports import get as get_airport
from ..models import Offer
from ..normalize import fmt_minutes, to_float
from ..request import CABINS, MULTI_CITY, SearchRequest

BASE_URL = "https://serpapi.com/search"


def build_params(request: SearchRequest, api_key: str) -> dict:
    """Translate a SearchRequest into SerpApi query parameters.

    Pure -- no network. Kept separate so the translation can be tested without
    spending quota, which matters on a ~100 searches/month free tier.
    """
    params: dict[str, str] = {
        "engine": "google_flights",
        "type": request.google_type,
        "currency": request.currency,
        "hl": "en",
        "gl": "us",
        "api_key": api_key,
        # Cheapest first. We are looking for the lowest price, not Google's
        # "best" blend of price and convenience.
        "sort_by": "2",
        "travel_class": str(CABINS[request.cabin]),
        "adults": str(request.adults),
    }

    if request.trip_type == MULTI_CITY:
        params["multi_city_json"] = _multi_city_json(request)
    else:
        params["departure_id"] = _codes(request.all_origins)
        params["arrival_id"] = _codes(request.all_destinations)
        params["outbound_date"] = request.depart_date
        if request.is_round_trip and request.return_date:
            params["return_date"] = request.return_date

    # Only send optional filters when they differ from Google's default, so the
    # query string stays stable and cache-friendly.
    if request.children:
        params["children"] = str(request.children)
    if request.infants_in_seat:
        params["infants_in_seat"] = str(request.infants_in_seat)
    if request.infants_on_lap:
        params["infants_on_lap"] = str(request.infants_on_lap)
    if request.max_stops:
        params["stops"] = str(request.max_stops)
    if request.bags:
        params["bags"] = str(request.bags)

    return params


def _codes(airports) -> str:
    return ",".join(a.iata for a in airports)


def _multi_city_json(request: SearchRequest) -> str:
    """Build the JSON leg list Google Flights wants for a multi-city trip."""
    import json

    return json.dumps(
        [
            {
                "departure_id": leg.origin_codes,
                "arrival_id": leg.destination_codes,
                "date": leg.depart_date,
            }
            for leg in request.legs
        ],
        separators=(",", ":"),
    )


def search(request: SearchRequest, api_key: str, timeout: int = 60) -> list[Offer]:
    """Run one search and return normalized offers."""
    data = net.request_json(
        "GET", BASE_URL, params=build_params(request, api_key), timeout=timeout
    )
    return parse(data, request)


def parse(response_json: dict, request: SearchRequest) -> list[Offer]:
    """Convert a Google Flights response into Offers.

    Every offer records the airport it departs from and arrives at, taken from
    the itinerary itself rather than from what we asked for. With several
    origins in one query that distinction is the whole point -- assuming the
    requested airport would attribute a Newark fare to JFK.

    Note on prices for round trips: Google returns the **total** round-trip
    price on the outbound result, which is what we rank on. The specific return
    flights need a second call with ``departure_token``, so that is spent only
    on the single cheapest option, not on every candidate.
    """
    reported = (
        (response_json.get("search_parameters") or {}).get("currency") or ""
    ).strip()
    offer_currency = reported or request.currency

    offers: list[Offer] = []
    raw = (response_json.get("best_flights") or []) + (
        response_json.get("other_flights") or []
    )

    for itinerary in raw:
        legs = itinerary.get("flights") or []
        if not legs:
            continue
        first, last = legs[0], legs[-1]

        origin_code = ((first.get("departure_airport") or {}).get("id") or "").strip()
        dest_code = ((last.get("arrival_airport") or {}).get("id") or "").strip()

        layovers = ", ".join(
            f"{lo.get('id') or lo.get('name', '')} ({fmt_minutes(lo.get('duration') or 0)})"
            for lo in (itinerary.get("layovers") or [])
        )

        offers.append(
            Offer(
                source="GoogleFlights",
                search_date=request.depart_date,
                origin_airport=origin_code,
                destination_airport=dest_code,
                return_date=request.return_date if request.is_round_trip else None,
                trip_type=request.trip_type,
                airline=first.get("airline", ""),
                flight_numbers=" + ".join(
                    leg.get("flight_number", "") for leg in legs
                ),
                depart_time=(first.get("departure_airport") or {}).get("time", ""),
                arrive_time=(last.get("arrival_airport") or {}).get("time", ""),
                duration=fmt_minutes(itinerary.get("total_duration") or 0),
                stops=len(legs) - 1,
                layovers=layovers,
                base_price=0.0,
                taxes_fees=0.0,
                total_price=to_float(itinerary.get("price")) or 0.0,
                currency=offer_currency,
                departure_token=(itinerary.get("departure_token") or "").strip(),
                booking_token=(itinerary.get("booking_token") or "").strip(),
            )
        )

    return offers


def airport_name(iata: str) -> str:
    """Readable name for an airport code, falling back to the code itself."""
    airport = get_airport(iata)
    return airport.city or airport.name if airport else iata
