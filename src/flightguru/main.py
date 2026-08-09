"""FlightGuru v3 entry point.

    python -m flightguru.main                     start the Telegram bot
    python -m flightguru.main --health            check keys and connectivity
    python -m flightguru.main --search FROM TO DATE [RETURN]
                                                  one search from the terminal

The ``--search`` form is the dry-run path: it exercises the whole pipeline --
airport resolution, nearby airports, the Google Flights query, the comparison and
the message -- without needing Telegram. Same code the bot calls.
"""

from __future__ import annotations

import argparse
import sys

from .config import load_settings
from .health import run_health
from .log import get_logger
from .request import ONE_WAY, ROUND_TRIP
from .scan import build_request, format_result, scan

log = get_logger()


def run_search(args, settings) -> int:
    """One search from the command line."""
    trip_type = ROUND_TRIP if args.ret else ONE_WAY

    if args.dry_run:
        # Resolve and plan the search, but spend nothing. Useful for checking
        # which airports would be included before committing a search.
        request, problems, distances = build_request(
            args.origin,
            args.destination,
            args.date,
            return_date=args.ret,
            trip_type=trip_type,
            include_nearby=settings.nearby_enabled,
            nearby_destination=settings.nearby_destination,
            radius_miles=settings.nearby_radius_miles,
            adults=args.adults,
            currency=settings.currency,
        )
        if request is None:
            for problem in problems:
                log.info(problem)
            return 1

        log.info(f"Would search: {request.describe()}")
        log.info(f"  you asked for : {', '.join(a.iata for a in request.origins)}")
        log.info(
            f"  also checking : "
            f"{', '.join(f'{a.iata} ({distances.get(a.iata, 0):.0f} mi)' for a in request.alternative_origins) or 'nothing nearby'}"
        )
        log.info(f"  arriving at   : {', '.join(a.iata for a in request.all_destinations)}")
        log.info("  API calls that would be spent: 1")
        return 0

    if not settings.serpapi_configured:
        log.error("No SerpApi key configured. Set SERPAPI_API_KEY in .env.")
        return 1

    result = scan(
        origin_text=args.origin,
        destination_text=args.destination,
        depart_date=args.date,
        api_key=settings.serpapi_key,
        return_date=args.ret,
        trip_type=trip_type,
        include_nearby=settings.nearby_enabled,
        nearby_destination=settings.nearby_destination,
        radius_miles=settings.nearby_radius_miles,
        adults=args.adults,
        currency=settings.currency,
    )
    print(format_result(result))
    return 0 if result.ok else 1


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flightguru")
    parser.add_argument("--health", action="store_true", help="check keys and connectivity")
    parser.add_argument("--search", nargs="+", metavar=("FROM TO DATE", ""),
                        help="one search: FROM TO DATE [RETURN_DATE]")
    parser.add_argument("--adults", type=int, default=1, help="number of adults (default 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --search: plan it but spend no API call")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except RuntimeError as exc:
        log.error(str(exc))
        return 1

    if args.health:
        all_ok = True
        for name, ok, info in run_health(settings):
            log.info(f"  health {name}: {'OK' if ok else 'FAIL'}  {info}")
            all_ok = all_ok and ok
        log.info(f"Health: {'ALL OK' if all_ok else 'PROBLEMS FOUND'}")
        return 0 if all_ok else 1

    if args.search:
        if len(args.search) < 3:
            log.error("--search needs at least FROM TO DATE")
            return 1
        args.origin, args.destination, args.date = args.search[:3]
        args.ret = args.search[3] if len(args.search) > 3 else None
        return run_search(args, settings)

    # No flags: run the bot.
    from .bot import Bot

    Bot(settings).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
