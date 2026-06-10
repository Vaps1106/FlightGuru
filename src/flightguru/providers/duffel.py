"""Duffel provider — real, bookable fares with a tax/fee breakdown.

API: POST https://api.duffel.com/air/offer_requests?return_offers=true
Searching is free; you only pay if you actually issue a ticket.
"""

from __future__ import annotations

from .. import net
from ..config import Settings
from ..models import Offer
from ..normalize import fmt_iso_duration, fmt_minutes, minutes_between, to_float

BASE_URL = "https://api.duffel.com"


def search_duffel(settings: Settings, dep_date: str) -> list[Offer]:
    """Live Duffel search for one departure date."""
    headers = {
        "Authorization": f"Bearer {settings.duffel_token}",
        "Duffel-Version": settings.duffel_version,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "data": {
            "slices": [
                {
                    "origin": settings.origin,
                    "destination": settings.destination,
                    "departure_date": dep_date,
                }
            ],
            "passengers": [{"type": "adult"}],
            "cabin_class": "economy",
        }
    }
    data = net.request_json(
        "POST",
        f"{BASE_URL}/air/offer_requests?return_offers=true",
        json=body,
        headers=headers,
    )
    return parse_duffel(data, dep_date)


def parse_duffel(response_json: dict, dep_date: str) -> list[Offer]:
    """Convert a Duffel offer_requests response into Offers (no validation here)."""
    offers: list[Offer] = []
    for o in (response_json.get("data") or {}).get("offers") or []:
        slices = o.get("slices") or []
        if not slices:
            continue
        segs = slices[0].get("segments") or []
        if not segs:
            continue

        total = to_float(o.get("total_amount"))
        base = to_float(o.get("base_amount"))
        tax = to_float(o.get("tax_amount"))
        currency = (o.get("total_currency") or "").strip()

        airline = (
            (o.get("owner") or {}).get("name")
            or (segs[0].get("marketing_carrier") or {}).get("name")
            or ""
        )
        first, last = segs[0], segs[-1]
        flight_numbers = " + ".join(
            f"{(s.get('marketing_carrier') or {}).get('iata_code', '')} "
            f"{s.get('marketing_carrier_flight_number', '')}".strip()
            for s in segs
        )

        if tax is not None:
            taxes_fees = tax
        elif total is not None and base is not None:
            taxes_fees = round(total - base, 2)
        else:
            taxes_fees = 0.0

        layovers = ", ".join(
            f"{(segs[i].get('destination') or {}).get('iata_code', '')} "
            f"({fmt_minutes(minutes_between(segs[i].get('arriving_at'), segs[i + 1].get('departing_at')))})"
            for i in range(len(segs) - 1)
        )

        offers.append(
            Offer(
                source="Duffel",
                search_date=dep_date,
                airline=airline,
                flight_numbers=flight_numbers,
                depart_time=first.get("departing_at") or "",
                arrive_time=last.get("arriving_at") or "",
                duration=fmt_iso_duration(slices[0].get("duration", "")),
                stops=len(segs) - 1,
                layovers=layovers,
                base_price=base or 0.0,
                taxes_fees=taxes_fees or 0.0,
                total_price=total or 0.0,
                currency=currency,
            )
        )
    return offers
