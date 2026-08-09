"""Health checks — confirm the bot can actually do its job before it starts.

Run with ``python -m flightguru.main --health``. Returns a list of
(name, ok, detail) tuples.
"""

from __future__ import annotations

from . import net
from .airports import all_airports, get
from .config import Settings

TELEGRAM_API = "https://api.telegram.org"


def serpapi_check(settings: Settings) -> tuple[str, bool, str]:
    """Is a search key present? Deliberately does not spend a search to find out."""
    if not settings.serpapi_configured:
        return ("serpapi_key", False, "missing or still a placeholder")
    return ("serpapi_key", True, "configured")


def telegram_check(settings: Settings) -> tuple[str, bool, str]:
    try:
        data = net.request_json(
            "GET",
            f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/getMe",
            retries=2,
        )
        if data.get("ok"):
            return ("telegram", True, "@" + data.get("result", {}).get("username", "?"))
        return ("telegram", False, "API said not ok")
    except Exception as exc:  # noqa: BLE001
        return ("telegram", False, str(exc))


def chat_check(settings: Settings) -> tuple[str, bool, str]:
    """An unset chat id means the bot ignores every message that arrives."""
    if settings.telegram_chat_id == "*":
        return ("chat_allowlist", True, "open to anyone (*)")
    if not settings.telegram_chat_id:
        return (
            "chat_allowlist",
            False,
            "TELEGRAM_CHAT_ID unset - every message would be ignored",
        )
    return ("chat_allowlist", True, settings.telegram_chat_id)


def airports_check(_: Settings) -> tuple[str, bool, str]:
    """The airport table is bundled data, so a bad build shows up here."""
    try:
        count = len(all_airports())
    except Exception as exc:  # noqa: BLE001
        return ("airport_data", False, str(exc))

    if count < 3000:
        return ("airport_data", False, f"only {count} airports loaded - data looks truncated")
    if get("JFK") is None or get("HVN") is None:
        return ("airport_data", False, "expected airports missing from the table")
    return ("airport_data", True, f"{count} airports")


def run_health(settings: Settings) -> list[tuple[str, bool, str]]:
    return [
        serpapi_check(settings),
        telegram_check(settings),
        chat_check(settings),
        airports_check(settings),
    ]
