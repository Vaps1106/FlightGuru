"""One flight search, described.

v2 kept the route in environment variables because there was only ever one of
them: BOM to JFK, for good. v3 answers a different question every time someone
opens a chat, so a search has to be a value you can build, pass around and test
-- not global state.

``SearchRequest`` is that value. It is immutable, carries everything a provider
needs, and knows nothing about Telegram or SerpApi.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from .airports import Airport, codes

# Google Flights trip types, named so call sites don't read as magic numbers.
ROUND_TRIP = "round_trip"
ONE_WAY = "one_way"
MULTI_CITY = "multi_city"

TRIP_TYPE_CODES = {ROUND_TRIP: "1", ONE_WAY: "2", MULTI_CITY: "3"}

CABINS = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}


@dataclass(frozen=True)
class Leg:
    """One hop of a multi-city itinerary.

    ``origins`` and ``destinations`` are lists because a single hop can search
    several airports at once -- that is the whole nearby-airport trick.
    """

    origins: tuple[Airport, ...]
    destinations: tuple[Airport, ...]
    depart_date: str  # YYYY-MM-DD

    @property
    def origin_codes(self) -> str:
        return codes(self.origins)

    @property
    def destination_codes(self) -> str:
        return codes(self.destinations)


@dataclass(frozen=True)
class SearchRequest:
    """Everything needed to price one trip.

    Airports are held as lists throughout. A search for "New York" is a search
    for JFK, LGA and EWR together, and Google Flights takes them as one
    comma-separated value, so there is no reason to model a single airport as a
    special case.

    ``alternative_origins`` are the extra airports we added ourselves -- the
    nearby ones the traveller did not ask for. They are kept separate from
    ``origins`` so results can be labelled honestly: "you asked about JFK, but
    Newark is $47 cheaper" reads very differently from silently quoting Newark.
    """

    origins: tuple[Airport, ...]
    destinations: tuple[Airport, ...]
    depart_date: str                      # YYYY-MM-DD
    return_date: str | None = None        # required for ROUND_TRIP
    trip_type: str = ROUND_TRIP
    legs: tuple[Leg, ...] = ()            # MULTI_CITY only

    alternative_origins: tuple[Airport, ...] = ()
    alternative_destinations: tuple[Airport, ...] = ()

    adults: int = 1
    children: int = 0
    infants_in_seat: int = 0
    infants_on_lap: int = 0

    cabin: str = "economy"
    max_stops: int = 0                    # 0 = any; 1 = nonstop; 2 = <=1 stop
    bags: int = 0
    currency: str = "USD"

    # Set when the traveller names an airport code directly. Their airport still
    # leads the results even if a neighbour is cheaper.
    requested_origin_codes: tuple[str, ...] = field(default=())

    # --- derived views ---------------------------------------------------

    @property
    def all_origins(self) -> tuple[Airport, ...]:
        """Requested origins plus the nearby ones, de-duplicated, order kept."""
        return _dedupe(self.origins + self.alternative_origins)

    @property
    def all_destinations(self) -> tuple[Airport, ...]:
        return _dedupe(self.destinations + self.alternative_destinations)

    @property
    def is_round_trip(self) -> bool:
        return self.trip_type == ROUND_TRIP

    @property
    def google_type(self) -> str:
        return TRIP_TYPE_CODES[self.trip_type]

    @property
    def passengers(self) -> int:
        return (
            self.adults + self.children + self.infants_in_seat + self.infants_on_lap
        )

    def is_alternative_origin(self, iata: str) -> bool:
        """True if this airport is one we suggested, not one that was asked for."""
        return any(a.iata == iata for a in self.alternative_origins)

    def with_alternatives(
        self,
        origins: tuple[Airport, ...] = (),
        destinations: tuple[Airport, ...] = (),
    ) -> SearchRequest:
        """Copy of this request with nearby airports attached."""
        return replace(
            self,
            alternative_origins=_dedupe(origins),
            alternative_destinations=_dedupe(destinations),
        )

    def describe(self) -> str:
        """Short human summary, for logs and chat confirmations."""
        where = f"{codes(self.origins)} to {codes(self.destinations)}"
        if self.trip_type == MULTI_CITY:
            hops = " then ".join(
                f"{leg.origin_codes}-{leg.destination_codes} {leg.depart_date}"
                for leg in self.legs
            )
            return f"multi-city: {hops}"
        when = self.depart_date
        if self.is_round_trip and self.return_date:
            when = f"{self.depart_date} returning {self.return_date}"
        return f"{where}, {when}"

    def validate(self) -> list[str]:
        """Problems that would make this search meaningless. Empty means fine.

        Returned as a list rather than raised, so a chat flow can tell someone
        everything wrong at once instead of one error per round trip.
        """
        problems: list[str] = []

        if self.trip_type not in TRIP_TYPE_CODES:
            problems.append(f"Unknown trip type: {self.trip_type}")

        if self.trip_type == MULTI_CITY:
            if len(self.legs) < 2:
                problems.append("A multi-city trip needs at least two flights.")
            for i, leg in enumerate(self.legs, start=1):
                if not leg.origins:
                    problems.append(f"Flight {i} has no departure airport.")
                if not leg.destinations:
                    problems.append(f"Flight {i} has no arrival airport.")
                problems += _date_problems(leg.depart_date, f"Flight {i} date")
            # Each hop must start on or after the one before it.
            dates = [leg.depart_date for leg in self.legs]
            for earlier, later in zip(dates, dates[1:]):
                if _is_date(earlier) and _is_date(later) and later < earlier:
                    problems.append("Multi-city dates must move forward in time.")
                    break
        else:
            if not self.origins:
                problems.append("No departure airport.")
            if not self.destinations:
                problems.append("No arrival airport.")
            problems += _date_problems(self.depart_date, "Departure date")

            if self.is_round_trip:
                if not self.return_date:
                    problems.append("A round trip needs a return date.")
                else:
                    problems += _date_problems(self.return_date, "Return date")
                    if (
                        _is_date(self.depart_date)
                        and _is_date(self.return_date)
                        and self.return_date < self.depart_date
                    ):
                        problems.append("Return date is before the departure date.")

            # Flying somewhere you are already leaving from finds nothing.
            if self.origins and self.destinations:
                overlap = {a.iata for a in self.origins} & {
                    a.iata for a in self.destinations
                }
                if overlap and len(self.destinations) == len(overlap):
                    problems.append(
                        "Departure and arrival are the same airport."
                    )

        if self.adults < 1:
            problems.append("A trip needs at least one adult.")
        if min(self.children, self.infants_in_seat, self.infants_on_lap) < 0:
            problems.append("Passenger counts cannot be negative.")
        # Google Flights refuses more than nine seats on one booking.
        if self.adults + self.children + self.infants_in_seat > 9:
            problems.append("Google Flights allows at most 9 seated passengers.")
        # Every lap infant needs an adult to sit on.
        if self.infants_on_lap > self.adults:
            problems.append("There are more lap infants than adults to hold them.")

        if self.cabin not in CABINS:
            problems.append(f"Unknown cabin: {self.cabin}")
        if self.max_stops not in (0, 1, 2, 3):
            problems.append(f"Unknown stops filter: {self.max_stops}")

        return problems


def _dedupe(airports: tuple[Airport, ...]) -> tuple[Airport, ...]:
    """Drop repeats, keep first-seen order."""
    seen: set[str] = set()
    out: list[Airport] = []
    for airport in airports:
        if airport.iata not in seen:
            seen.add(airport.iata)
            out.append(airport)
    return tuple(out)


def _is_date(value: str | None) -> bool:
    try:
        date.fromisoformat(value or "")
        return True
    except (TypeError, ValueError):
        return False


def _date_problems(value: str | None, label: str) -> list[str]:
    if not value:
        return [f"{label} is missing."]
    if not _is_date(value):
        return [f"{label} is not a real date (use YYYY-MM-DD): {value}"]
    return []
