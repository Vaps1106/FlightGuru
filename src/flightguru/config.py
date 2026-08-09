"""Secrets and defaults.

v2 kept the whole route here — origin, destination, date range, price target —
because there was only ever one route and it never changed. v3 gets the route
from the conversation, so this file is down to what genuinely belongs in the
environment: API keys, and a few defaults worth being able to tune without a
code change.

Locally these come from a ``.env`` file (git-ignored). On Railway they come from
the service's environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv not installed
    pass


def _require(name: str) -> str:
    """Return a required env var, or raise a clear error if it is missing."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in "
            f"(or set it in the Railway service variables)."
        )
    return value


def _int_env(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` if unset or non-numeric.

    A typo in a setting should not take the bot down.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _looks_placeholder(value: str) -> bool:
    """True if a key is empty or still the .env.example placeholder text."""
    v = (value or "").upper()
    if not v:
        return True
    return any(token in v for token in ("PASTE", "YOUR", "HERE", "XXXX", "EXAMPLE"))


@dataclass(frozen=True)
class Settings:
    """Everything the bot needs that is not part of a specific search."""

    serpapi_key: str
    telegram_bot_token: str

    # Who the bot will talk to. Empty means anyone who finds it, which is not
    # what you want for a bot spending your API quota -- see allowed_chat().
    telegram_chat_id: str

    currency: str = "USD"

    # Nearby-airport search. Radius is in miles; roughly a two-hour drive.
    nearby_radius_miles: float = 100.0
    nearby_enabled: bool = True
    nearby_destination: bool = False

    # How long to hold a Telegram long-poll open. Higher means fewer requests
    # and faster replies; Telegram allows up to 50.
    poll_timeout: int = 30

    @property
    def serpapi_configured(self) -> bool:
        return not _looks_placeholder(self.serpapi_key)

    def allowed_chat(self, chat_id: str | int) -> bool:
        """True if this chat is permitted to use the bot.

        The bot's token is effectively public the moment anyone messages it, and
        every search costs quota, so by default only the configured chat gets
        answers. Setting TELEGRAM_CHAT_ID to "*" opens it to anyone, which is
        only sensible for a throwaway bot.
        """
        allowed = (self.telegram_chat_id or "").strip()
        if allowed == "*":
            return True
        if not allowed:
            return False
        return str(chat_id).strip() in {
            part.strip() for part in allowed.split(",") if part.strip()
        }


def load_settings() -> Settings:
    """Build a Settings object from the current environment."""
    return Settings(
        serpapi_key=os.environ.get("SERPAPI_API_KEY", "").strip(),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
        currency=os.environ.get("CURRENCY", "USD").strip() or "USD",
        nearby_radius_miles=_float_env("NEARBY_RADIUS_MILES", 100.0),
        nearby_enabled=_bool_env("NEARBY_ENABLED", True),
        nearby_destination=_bool_env("NEARBY_DESTINATION", False),
        poll_timeout=_int_env("POLL_TIMEOUT", 30),
    )
