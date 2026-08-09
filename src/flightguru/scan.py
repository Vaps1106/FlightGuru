"""One complete flight scan: text in, answer out.

Ties the pieces together in the order they run:

    "new york" / "los angeles"  ->  airports.resolve
                                ->  airports.alternatives   (nearby, cheaper?)
                                ->  SearchRequest
                                ->  one Google Flights search
                                ->  compare                 (which airport wins)
                                ->  a message

Deliberately knows nothing about Telegram. The chat layer calls this and formats
the result; the CLI calls the same thing. That keeps the interesting logic
testable without a bot token.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import airports, compare
from .compare import Comparison
from .providers import flights
from .request import ROUND_TRIP, SearchRequest


@dataclass(frozen=True)
class ScanResult:
    """The outcome of a scan, including the ways it can fail.

    ``problems`` covers anything that stopped us searching -- an unrecognised
    place, an impossible date. ``comparison`` is None when the search ran but
    Google had nothing to sell.
    """

    request: SearchRequest | None
    comparison: Comparison | None
    problems: tuple[str, ...] = ()
    searched_airports: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems and self.comparison is not None


def plan(
    origins: tuple[airports.Airport, ...],
    destinations: tuple[airports.Airport, ...],
    depart_date: str,
    return_date: str | None = None,
    trip_type: str = ROUND_TRIP,
    include_nearby: bool = True,
    nearby_destination: bool = False,
    radius_miles: float = airports.DEFAULT_RADIUS_MILES,
    **passenger_options,
) -> tuple[SearchRequest | None, list[str], dict[str, float]]:
    """Build a search from airports that are *already resolved*.

    This is the core. Callers that start from free text go through
    ``build_request``, which resolves first and then lands here.

    The split exists because of a real bug: the chat resolves "NYC" into three
    airports, and the bot then joined them back into the string "EWR, JFK, LGA"
    and handed that to the resolver as if it were a place name. It is not one,
    so every search from a multi-airport city failed. Resolved airports should
    never be flattened to text and re-parsed.
    """
    request = SearchRequest(
        origins=origins,
        destinations=destinations,
        depart_date=depart_date,
        return_date=return_date,
        trip_type=trip_type,
        **passenger_options,
    )

    distances: dict[str, float] = {}
    if include_nearby:
        nearby_origins = airports.alternatives(request.origins, radius_miles)
        nearby_dests = (
            airports.alternatives(request.destinations, radius_miles)
            if nearby_destination
            else []
        )
        distances = compare.distances_from(request, nearby_origins)
        request = request.with_alternatives(
            origins=tuple(a for a, _ in nearby_origins),
            destinations=tuple(a for a, _ in nearby_dests),
        )

    problems = request.validate()
    if problems:
        return None, problems, distances

    return request, [], distances


def build_request(
    origin_text: str,
    destination_text: str,
    depart_date: str,
    **options,
) -> tuple[SearchRequest | None, list[str], dict[str, float]]:
    """Resolve two place names, then plan the search.

    Returns ``(request, problems, distances)``. When a place cannot be resolved
    the problem text names the alternatives rather than just failing, so the
    chat can ask a useful follow-up question.
    """
    problems: list[str] = []

    origin = airports.resolve(origin_text)
    destination = airports.resolve(destination_text)

    for label, resolution in (("from", origin), ("to", destination)):
        if resolution.ambiguous:
            options_text = "; ".join(
                f"{a.iata} ({a.city}, {a.region})" for a in resolution.candidates
            )
            problems.append(
                f"Which {resolution.query} did you mean, flying {label}? {options_text}"
            )
        elif not resolution.ok:
            problems.append(
                f"I don't know an airport or city called "
                f"\"{resolution.query}\" (flying {label})."
            )

    if problems:
        return None, problems, {}

    return plan(origin.airports, destination.airports, depart_date, **options)


def scan(
    origin_text: str,
    destination_text: str,
    depart_date: str,
    api_key: str,
    **options,
) -> ScanResult:
    """Run one scan from two place names. One search against the API quota."""
    request, problems, distances = build_request(
        origin_text, destination_text, depart_date, **options
    )
    return _execute(request, problems, distances, api_key)


def scan_airports(
    origins: tuple[airports.Airport, ...],
    destinations: tuple[airports.Airport, ...],
    depart_date: str,
    api_key: str,
    **options,
) -> ScanResult:
    """Run one scan from airports the caller has already resolved.

    What the chat uses: the conversation resolved the place names when it asked
    the questions, so re-parsing them here would be both wasteful and wrong.
    """
    request, problems, distances = plan(
        origins, destinations, depart_date, **options
    )
    return _execute(request, problems, distances, api_key)


def _execute(
    request: SearchRequest | None,
    problems: list[str],
    distances: dict[str, float],
    api_key: str,
) -> ScanResult:
    """Run a planned search and compare the results."""
    if request is None:
        return ScanResult(request=None, comparison=None, problems=tuple(problems))

    searched = airports.codes(request.all_origins)
    offers = flights.search(request, api_key)
    if not offers:
        return ScanResult(
            request=request, comparison=None, searched_airports=searched
        )

    return ScanResult(
        request=request,
        comparison=compare.compare(offers, request, distances),
        searched_airports=searched,
    )


def format_result(result: ScanResult) -> str:
    """Plain-text summary, ready to send as a chat message.

    Plain text on purpose: v1 lost alerts to HTML parse errors when a fare
    contained an "&", and no formatting is worth dropping a message over.
    """
    if result.problems:
        return "\n".join(result.problems)

    request = result.request
    if request is None:
        return "I couldn't work out what to search for."

    header = f"{request.describe()}"

    if result.comparison is None or result.comparison.best is None:
        return (
            f"{header}\n\nNo flights came back for that. "
            f"Searched {result.searched_airports}. "
            f"Try different dates, or a wider date range."
        )

    comparison = result.comparison
    best = comparison.best
    lines = [
        header,
        f"Searched: {result.searched_airports}",
        "",
        "CHEAPEST",
        f"{best.offer.currency} {best.price:.0f} from {best.airport} ({best.city})",
        f"{best.offer.airline}  {best.offer.flight_numbers}",
        f"Depart {best.offer.depart_time} -> arrive {best.offer.arrive_time}",
        _stops_line(best.offer),
    ]

    for option in comparison.suggestions:
        saving = comparison.saving_over_best(option)
        lines += [
            "",
            f"CHEAPER FROM {option.airport} ({option.city}) - save "
            f"{option.offer.currency} {saving:.0f}",
            f"{option.offer.currency} {option.price:.0f}  "
            f"{option.offer.airline}  {option.offer.flight_numbers}",
            _stops_line(option.offer),
        ]
        if option.distance_miles is not None:
            lines.append(f"{option.airport} is {option.distance_miles:.0f} mi away")

    if not comparison.has_suggestions:
        lines += ["", "No nearby airport was meaningfully cheaper."]

    faster = comparison.faster
    if faster is not None:
        premium = faster.price - best.price
        saved = best.offer.duration_minutes - faster.offer.duration_minutes
        cost = (
            f"{premium:.0f} more"
            if premium > 0
            else f"{abs(premium):.0f} less"
        )
        lines += [
            "",
            f"WORTH A LOOK - {_hours(saved)} faster for {best.offer.currency} {cost}",
            f"{faster.offer.currency} {faster.price:.0f} from {faster.airport} "
            f"({faster.city})",
            f"{faster.offer.airline}  {faster.offer.flight_numbers}",
            f"Depart {faster.offer.depart_time} -> arrive {faster.offer.arrive_time}",
            _stops_line(faster.offer),
        ]

    return "\n".join(lines)


def _hours(minutes: int) -> str:
    """"5h 10m" from a count of minutes, for talking about time saved."""
    hours, mins = divmod(max(0, minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def _stops_line(offer) -> str:
    stops = "nonstop" if offer.stops == 0 else f"{offer.stops} stop(s)"
    if offer.layovers:
        stops += f" via {offer.layovers}"
    return f"{offer.duration}, {stops}"
