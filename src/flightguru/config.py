"""Configuration and secrets loading.

All settings come from environment variables so that secrets never live in the
code. Locally they are read from a ``.env`` file (git-ignored); in GitHub
Actions they come from encrypted repository secrets.

Flight data comes from multiple providers (Duffel + SerpApi); each has its own
key and is only used if that key is actually configured.
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
            f"(or add it as a GitHub Actions secret)."
        )
    return value


def _looks_placeholder(value: str) -> bool:
    """True if a key is empty or still the .env.example placeholder text."""
    v = (value or "").upper()
    if not v:
        return True
    return any(token in v for token in ("PASTE", "YOUR", "HERE", "XXXX", "EXAMPLE"))


@dataclass(frozen=True)
class Settings:
    """All values the app needs for one run. Immutable once loaded."""

    duffel_token: str
    duffel_version: str
    serpapi_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    providers: tuple[str, ...]  # which providers to use, e.g. ("duffel", "serpapi")
    origin: str
    destination: str
    search_start_date: str      # earliest departure date to check (YYYY-MM-DD)
    search_end_date: str        # latest departure date to check (YYYY-MM-DD)
    search_date_step: int       # days between dates checked (1 = every day)
    search_max_workers: int     # how many provider requests to run at once (bounded)
    serpapi_max_dates: int      # cap SerpApi to N dates/run (protects its free quota)
    target_price: int
    currency: str
    notify_every_run: bool      # True = report every run; False = only on alert/drop


def load_settings() -> Settings:
    """Build a Settings object from the current environment."""
    providers = tuple(
        p.strip().lower()
        for p in os.environ.get("PROVIDERS", "duffel,serpapi").split(",")
        if p.strip()
    )
    return Settings(
        duffel_token=os.environ.get("DUFFEL_ACCESS_TOKEN", "").strip(),
        duffel_version=os.environ.get("DUFFEL_VERSION", "v2").strip(),
        serpapi_key=os.environ.get("SERPAPI_API_KEY", "").strip(),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_require("TELEGRAM_CHAT_ID"),
        providers=providers,
        origin=os.environ.get("ORIGIN", "BOM").strip(),
        destination=os.environ.get("DESTINATION", "JFK").strip(),
        search_start_date=os.environ.get("SEARCH_START_DATE", "2026-07-20").strip(),
        search_end_date=os.environ.get("SEARCH_END_DATE", "2026-08-14").strip(),
        search_date_step=int(os.environ.get("SEARCH_DATE_STEP", "1")),
        search_max_workers=int(os.environ.get("SEARCH_MAX_WORKERS", "6")),
        serpapi_max_dates=int(os.environ.get("SERPAPI_MAX_DATES", "8")),
        target_price=int(os.environ.get("TARGET_PRICE", "700")),
        currency=os.environ.get("CURRENCY", "USD").strip(),
        notify_every_run=os.environ.get("NOTIFY_EVERY_RUN", "true").strip().lower()
        in ("1", "true", "yes", "on"),
    )


def provider_configured(settings: Settings, name: str) -> bool:
    """True if the given provider has a real (non-placeholder) key."""
    if name == "duffel":
        return not _looks_placeholder(settings.duffel_token)
    if name == "serpapi":
        return not _looks_placeholder(settings.serpapi_key)
    return False


def enabled_providers(settings: Settings) -> list[str]:
    """The requested providers that are actually configured with a real key."""
    return [p for p in settings.providers if provider_configured(settings, p)]
