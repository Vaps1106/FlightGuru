"""Search orchestrator — query every enabled provider across the date range.

Duffel is searched for every date in the (stepped) range. SerpApi is capped to
``serpapi_max_dates`` dates, evenly sampled across the range, to protect its
small free quota.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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
    """Pick ~n items spread evenly across the list (keeps first and last).

    Indices are de-duplicated, so a scarce SerpApi call is never wasted checking
    a date we already sampled — the spare slot effectively widens coverage.
    """
    if n <= 0 or n >= len(items):
        return list(items)
    if n == 1:
        return [items[0]]
    step = (len(items) - 1) / (n - 1)
    idxs = sorted({round(i * step) for i in range(n)})
    return [items[i] for i in idxs]


def _build_tasks(settings: Settings) -> list[tuple[str, str]]:
    """The (provider, departure_date) pairs to search this run, in order."""
    dates = search_dates(settings)
    tasks: list[tuple[str, str]] = []
    for provider in enabled_providers(settings):
        if provider == "duffel":
            tasks.extend(("duffel", d) for d in dates)
        elif provider == "serpapi":
            tasks.extend(
                ("serpapi", d) for d in evenly_sample(dates, settings.serpapi_max_dates)
            )
    return tasks


def search_all(
    settings: Settings,
    on_error: Callable[[str, str, Exception], None] | None = None,
) -> list[Offer]:
    """Return raw offers from all enabled providers across the date range.

    Tasks run with up to ``settings.search_workers`` threads (1 = sequential,
    identical to a plain loop). Result order is preserved regardless, and
    normalize() sorts by price, so concurrency never changes which fare wins.

    Errors per (provider, date) are reported via ``on_error`` and skipped, so one
    failing call never aborts the whole run.
    """
    tasks = _build_tasks(settings)

    def run(task: tuple[str, str]) -> list[Offer]:
        provider, dep_date = task
        try:
            if provider == "duffel":
                return duffel.search_duffel(settings, dep_date)
            if provider == "serpapi":
                return serpapi.search_serpapi(settings, dep_date)
            return []
        except Exception as exc:  # noqa: BLE001 - report and continue
            if on_error:
                on_error(provider, dep_date, exc)
            return []

    workers = max(1, settings.search_workers)
    offers: list[Offer] = []
    if workers == 1:
        for task in tasks:
            offers.extend(run(task))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for batch in ex.map(run, tasks):  # map preserves input order
                offers.extend(batch)
    return offers
