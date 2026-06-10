"""FlightGuru v2 entry point + CLI.

Pipeline: control gate -> search (providers) -> normalize/validate -> record
history + delta -> Telegram report. Production hardening (Phase 5): retries with
429-aware backoff (net.py), rotating logs (log.py), and health checks.

Run a check:   python -m flightguru.main
Health check:  python -m flightguru.main --health
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from . import delta, notify, search as search_mod, storage
from .config import enabled_providers, load_settings
from .control import check_active, load_control
from .deeplink import build_deep_link
from .health import run_health
from .log import get_logger
from .normalize import normalize

log = get_logger()


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1) Usage control gate — bail before any API work if paused / out of window.
    active, reason = check_active(load_control())
    if not active:
        log.info(f"[FlightGuru v2] Skipped - {reason}. No API calls made. ({now})")
        return 0

    # 2) Config — missing secrets means we stop cleanly, not crash.
    try:
        settings = load_settings()
    except RuntimeError as exc:
        log.info(f"[FlightGuru v2] Config incomplete: {exc}")
        return 0

    providers = enabled_providers(settings)
    if not providers:
        log.info(
            "[FlightGuru v2] No flight providers configured. Add DUFFEL_ACCESS_TOKEN "
            "and/or SERPAPI_API_KEY (see README). No search performed."
        )
        return 0

    log.info(
        f"[FlightGuru v2] Searching {settings.origin}->{settings.destination} "
        f"{settings.search_start_date}..{settings.search_end_date} "
        f"via {', '.join(providers)} ({now})"
    )

    # 3) Search every provider across the date range.
    errors: list[str] = []
    raw = search_mod.search_all(
        settings, on_error=lambda p, d, e: errors.append(f"{p} {d}: {e}")
    )
    offers = normalize(raw)
    for warn in errors[:5]:
        log.warning(f"  warn: {warn}")

    if not offers:
        log.info("No verified offers found in range.")
        return 0

    # 4) Pick the cheapest, compare to history, record it.
    cheapest = offers[0]
    link = build_deep_link(cheapest, settings)
    last_price = storage.get_last_total_price()
    decision = delta.decide(cheapest.total_price, last_price, settings.target_price)
    storage.save_snapshot(
        cheapest, settings.origin, settings.destination, link, decision.below_target
    )

    # 5) Report the cheapest verified fare (once).
    log.info("Cheapest in range:")
    log.info(
        f"  {cheapest.currency} {cheapest.total_price:.0f}  ({cheapest.source})  "
        f"{cheapest.airline}  {cheapest.flight_numbers}"
    )
    if cheapest.base_price > 0:
        log.info(f"  fare {cheapest.base_price:.0f} + tax/fees {cheapest.taxes_fees:.0f}")
    log.info(
        f"  {cheapest.search_date}  depart {cheapest.depart_time}  "
        f"arrive {cheapest.arrive_time}  {cheapest.duration}  {cheapest.stops} stop(s)"
    )
    if cheapest.layovers:
        log.info(f"  via {cheapest.layovers}")
    log.info(f"  book: {link}")
    log.info(
        f"  target < {settings.currency} {settings.target_price}: "
        f"{'YES, below target' if decision.below_target else 'no'}"
    )
    if last_price is not None:
        line = f"  last recorded: {settings.currency} {last_price:.0f}"
        if decision.dropped:
            line += f"  (dropped {settings.currency} {decision.drop_amount:.0f} since last check)"
        log.info(line)
    log.info(f"  history: {storage.count_snapshots()} snapshot(s) in {storage.DB_PATH}")

    # 6) Notify. Rule: no booking link -> no alert (per spec).
    if link is None:
        log.info("  Telegram: suppressed - no booking link could be built.")
        return 0
    if settings.notify_every_run or decision.alert or decision.dropped:
        message = notify.build_message(settings, cheapest, decision, link, now)
        try:
            ok = notify.send_telegram(settings, message)
            log.info(f"  Telegram: {'sent' if ok else 'not sent (API said not ok)'}")
            if ok and decision.alert:
                storage.record_alert(cheapest, settings.currency)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the run
            log.error(f"  Telegram: failed - {exc}")
    else:
        log.info("  Telegram: skipped (no alert; NOTIFY_EVERY_RUN is off).")
    return 0


def cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="flightguru")
    parser.add_argument(
        "--health", action="store_true", help="run health checks and exit"
    )
    args = parser.parse_args(argv)

    if args.health:
        try:
            settings = load_settings()
        except RuntimeError as exc:
            log.info(f"Config incomplete: {exc}")
            return 1
        all_ok = True
        for name, ok, info in run_health(settings):
            log.info(f"  health {name}: {'OK' if ok else 'FAIL'}  {info}")
            all_ok = all_ok and ok
        log.info(f"Health: {'ALL OK' if all_ok else 'PROBLEMS FOUND'}")
        return 0 if all_ok else 1

    return main()


if __name__ == "__main__":
    sys.exit(cli())
