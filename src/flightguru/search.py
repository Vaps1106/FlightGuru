"""Search orchestrator — query every enabled provider across the date range.

Duffel is searched for every date in the (stepped) range. SerpApi is capped to
``serpapi_max_dates`` dates, evenly sampled across the range, to protect its
small free quota.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from .config import Settings, enabled_providers
from .models import Offer
from .providers import duffel, serpapi


def search_dates(settings: Settings) -> list[str]:
    """All departure dates to check, from start to end at the configured step."""
    start = date.fromisoformat(settings.search_start_date)
    end = date.fromisoformat(settings.search_end_date)
    step = max(1, settings.search_date_step)
    out: list[str] = []
    d = start
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=step)
    return out


def evenly_sample(items: list, n: int) -> list:
    """Pick ~n items spread evenly across the list (keeps first and last)."""
    if n <= 0 or n >= len(items):
        return list(items)
    if n == 1:
        return [items[0]]
    step = (len(items) - 1) / (n - 1)
    return [items[round(i * step)] for i in range(n)]


def search_all(
    settings: Settings,
    on_error: Callable[[str, str, Exception], None] | None = None,
) -> list[Offer]:
    """Return raw offers from all enabled providers across the date range.

    Errors per (provider, date) are reported via ``on_error`` and skipped, so one
    failing call never aborts the whole run.
    """
    dates = search_dates(settings)
    offers: list[Offer] = []

    for provider in enabled_providers(settings):
        if provider == "duffel":
            for d in dates:
                try:
                    offers.extend(duffel.search_duffel(settings, d))
                except Exception as exc:  # noqa: BLE001 - report and continue
                    if on_error:
                        on_error("duffel", d, exc)
        elif provider == "serpapi":
            for d in evenly_sample(dates, settings.serpapi_max_dates):
                try:
                    offers.extend(serpapi.search_serpapi(settings, d))
                except Exception as exc:  # noqa: BLE001 - report and continue
                    if on_error:
                        on_error("serpapi", d, exc)

    return offers
