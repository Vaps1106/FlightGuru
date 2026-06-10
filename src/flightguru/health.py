"""Health checks — verify the system is ready to run unattended.

Used by ``python -m flightguru.main --health``. Returns a list of
(name, ok, detail) tuples.
"""

from __future__ import annotations

from . import net
from .config import Settings, enabled_providers

TELEGRAM_API = "https://api.telegram.org"


def providers_check(settings: Settings) -> tuple[str, bool, str]:
    provs = enabled_providers(settings)
    return ("providers_configured", bool(provs), ", ".join(provs) or "none")


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


def run_health(settings: Settings) -> list[tuple[str, bool, str]]:
    return [providers_check(settings), telegram_check(settings)]
