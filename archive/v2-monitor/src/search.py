"""Search orchestrator — query every enabled provider across the date range.

Duffel is searched for every date in the (stepped) range. SerpApi is capped to
``serpapi_max_dates`` dates, evenly sampled across the range, to protect its
small free quota.

Requests run concurrently with a bounded thread pool (``search_max_workers``):
the per-date calls don't depend on each other, so we don't wait for one to
finish before starting the next. The cap keeps us from bursting past provider
rate limits. Results are reassembled in their original (deterministic) order so
the cheapest pick is reproducible regardless of which request finishes first.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Callable

from .config import Settings, enabled_providers
from .models import Offer
from .providers import duffel, serpapi

# Maps a provider name to the function that searches it for one date.
_SEARCHERS = {
    "duffel": duffel.search_duffel,
    "serpapi": serpapi.search_serpapi,
}


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


def plan_searches(settings: Settings) -> list[tuple[str, str]]:
    """The (provider, date) calls to make this run, in deterministic order.

    Duffel covers every date in the range; SerpApi is down-sampled to protect
    its free quota.
    """
    dates = search_dates(settings)
    tasks: list[tuple[str, str]] = []
    for provider in enabled_providers(settings):
        if provider == "duffel":
            tasks += [("duffel", d) for d in dates]
        elif provider == "serpapi":
            tasks += [("serpapi", d) for d in evenly_sample(dates, settings.serpapi_max_dates)]
    return tasks


def search_all(
    settings: Settings,
    on_error: Callable[[str, str, Exception], None] | None = None,
) -> list[Offer]:
    """Return raw offers from all enabled providers across the date range.

    Calls run concurrently (bounded by ``search_max_workers``). Errors per
    (provider, date) are reported via ``on_error`` and skipped, so one failing
    call never aborts the whole run. The returned order matches ``plan_searches``
    regardless of which request finishes first.
    """
    tasks = plan_searches(settings)
    if not tasks:
        return []

    # One result slot per task, filled in place so order stays deterministic.
    results: list[list[Offer]] = [[] for _ in tasks]
    error_lock = threading.Lock()

    def run(index: int, provider: str, dep_date: str) -> None:
        try:
            results[index] = _SEARCHERS[provider](settings, dep_date)
        except Exception as exc:  # noqa: BLE001 - report and continue
            if on_error:
                with error_lock:  # on_error may touch shared state; serialize it
                    on_error(provider, dep_date, exc)

    workers = max(1, min(settings.search_max_workers, len(tasks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (provider, dep_date) in enumerate(tasks):
            pool.submit(run, index, provider, dep_date)

    offers: list[Offer] = []
    for chunk in results:
        offers.extend(chunk)
    return offers
