"""Telegram notifications.

Messages are plain text (no HTML parse mode), so a stray "&" can never silently
drop an alert — a v1 bug we are not repeating. ``build_message`` is pure and
unit-tested; ``send_telegram`` does the actual HTTP POST.
"""

from __future__ import annotations

from . import net
from .config import Settings
from .delta import Decision
from .models import Offer

TELEGRAM_API = "https://api.telegram.org"


def build_message(
    settings: Settings,
    offer: Offer,
    decision: Decision,
    link: str,
    verified_at: str,
) -> str:
    """Compose the plain-text report for one cheapest offer."""
    lines = [
        f"FlightGuru - {settings.origin} to {settings.destination}",
        f"Verified at: {verified_at}",
        "",
        f"Cheapest: {offer.currency} {offer.total_price:.0f} ({offer.source})",
        f"{offer.airline}  {offer.flight_numbers}",
    ]
    if offer.base_price > 0:
        lines.append(f"Fare {offer.base_price:.0f} + tax/fees {offer.taxes_fees:.0f}")
    lines.append(f"Depart {offer.depart_time} -> arrive {offer.arrive_time}")

    stopinfo = "nonstop" if offer.stops == 0 else f"{offer.stops} stop(s)"
    if offer.layovers:
        stopinfo += f" via {offer.layovers}"
    lines.append(f"{offer.duration}, {stopinfo}")
    lines.append("")

    if decision.below_target:
        lines.append(f"Status: BELOW TARGET (under {offer.currency} {settings.target_price})")
    else:
        lines.append(f"Status: above target ({offer.currency} {settings.target_price})")
    if decision.dropped:
        lines.append(
            f"Price dropped {offer.currency} {decision.drop_amount:.0f} since last check"
        )

    lines.append(f"Book: {link}")
    return "\n".join(lines)


def send_telegram(settings: Settings, message: str, timeout: int = 30) -> bool:
    """Send a plain-text Telegram message. Returns True on success."""
    url = f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    body = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }
    data = net.request_json("POST", url, json=body, timeout=timeout)
    return bool(data.get("ok"))
