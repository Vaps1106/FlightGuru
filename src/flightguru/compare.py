"""Work out whether a different airport would be cheaper.

This is the feature FlightGuru v3 exists for. You ask about JFK to LAX; the
search quietly also priced LGA, EWR and Tweed New Haven in the same call, and
this module decides whether any of them is worth telling you about.

Two rules shape everything here:

**Your airport leads.** The cheapest fare from the airport you actually named is
always the headline. An alternative is an extra, never a substitute -- quoting
a Newark departure to someone who asked about JFK would be answering a question
they did not ask.

**A saving has to be worth the drive.** Four dollars is not worth an hour in the
car, so small differences are dropped rather than reported as findings.
"""

from __future__ import annotations

from dataclasses import dataclass

from .airports import Airport, get as get_airport
from .models import Offer
from .request import SearchRequest

# Below this, the saving is not worth changing your plans for. Absolute floor,
# so a cheap domestic hop is not "improved" by a $6 difference.
MIN_SAVING = 25.0

# And it has to be a real proportion of the fare -- $30 off a $2,000 long-haul
# is noise, not a finding.
MIN_SAVING_FRACTION = 0.04

# Most alternatives to report. Beyond a few, a chat message becomes a wall of
# numbers nobody reads.
MAX_SUGGESTIONS = 3

# --- when a slightly dearer flight is obviously the better buy --------------
#
# Ranking on price alone can hand you an eleven-hour itinerary with a seven-hour
# layover while a nonstop sits fourteen dollars away. That is technically the
# cheapest flight and plainly the wrong answer, so a notably faster option gets
# mentioned alongside it. The cheapest still leads -- this only stops the bot
# staying quiet about the trade.

# How much more we will mention paying, in absolute terms...
MAX_PREMIUM = 75.0
# ...or as a share of the cheapest fare, whichever is more generous. Keeps the
# rule sane for both a $70 hop and a $900 long-haul.
MAX_PREMIUM_FRACTION = 0.25

# How much time has to be saved before it is worth raising at all.
MIN_TIME_SAVED_MINUTES = 120


@dataclass(frozen=True)
class AirportOption:
    """The cheapest fare found from one departure airport."""

    airport: str            # IATA code
    offer: Offer
    distance_miles: float | None = None   # from the requested airport, if known

    @property
    def price(self) -> float:
        return self.offer.total_price

    @property
    def city(self) -> str:
        airport = get_airport(self.airport)
        return airport.city or airport.name if airport else self.airport


@dataclass(frozen=True)
class Comparison:
    """What to tell the traveller.

    ``best`` is the cheapest option from an airport they asked for.
    ``suggestions`` are cheaper alternatives, biggest saving first, already
    filtered to ones worth mentioning.
    ``faster`` is an option that costs a little more but saves real time --
    None unless one clearly qualifies.
    """

    best: AirportOption | None
    suggestions: tuple[AirportOption, ...] = ()
    all_options: tuple[AirportOption, ...] = ()
    faster: AirportOption | None = None

    @property
    def has_suggestions(self) -> bool:
        return bool(self.suggestions)

    def saving_over_best(self, option: AirportOption) -> float:
        """How much this option saves against the requested airport's fare."""
        if self.best is None:
            return 0.0
        return self.best.price - option.price


def cheapest_by_airport(offers: list[Offer]) -> dict[str, Offer]:
    """The single cheapest offer from each departure airport.

    Offers with no departure airport recorded are skipped rather than lumped
    together -- attributing them to the wrong airport is worse than dropping
    them, because the whole output is a claim about which airport is cheaper.
    """
    best: dict[str, Offer] = {}
    for offer in offers:
        code = (offer.origin_airport or "").strip().upper()
        if not code or offer.total_price <= 0:
            continue
        current = best.get(code)
        if current is None or offer.total_price < current.total_price:
            best[code] = offer
    return best


def compare(
    offers: list[Offer],
    request: SearchRequest,
    distances: dict[str, float] | None = None,
) -> Comparison:
    """Split results into "the airport you asked for" and "cheaper nearby".

    ``distances`` maps an alternative airport code to how far it is from the
    requested one, so the message can say how far out of the way it is.
    """
    per_airport = cheapest_by_airport(offers)
    if not per_airport:
        return Comparison(best=None)

    distances = distances or {}
    requested = {a.iata for a in request.origins}

    options = [
        AirportOption(
            airport=code,
            offer=offer,
            distance_miles=distances.get(code),
        )
        for code, offer in per_airport.items()
    ]
    options.sort(key=lambda o: o.price)

    # The headline is the cheapest fare from an airport actually asked for. If
    # the search somehow returned nothing from those, fall back to the overall
    # cheapest rather than reporting nothing at all.
    from_requested = [o for o in options if o.airport in requested]
    best = from_requested[0] if from_requested else options[0]

    suggestions = [
        option
        for option in options
        if option.airport != best.airport and _worth_mentioning(best.price, option.price)
    ][:MAX_SUGGESTIONS]

    return Comparison(
        best=best,
        suggestions=tuple(suggestions),
        all_options=tuple(options),
        faster=_find_faster(offers, best, suggestions, distances),
    )


def _find_faster(
    offers: list[Offer],
    best: AirportOption,
    suggestions: list[AirportOption],
    distances: dict[str, float],
) -> AirportOption | None:
    """A notably quicker itinerary that costs only a little more, if one exists.

    Searches every offer, not just the cheapest per airport, because the better
    trade is often a different flight from the *same* airport -- a nonstop an
    hour later for twenty dollars more.

    Anything already reported as a cheaper alternative is skipped: it is being
    recommended on price already, and saying it twice reads like two findings.
    """
    if best.offer.duration_minutes <= 0:
        return None

    ceiling = max(MAX_PREMIUM, best.price * MAX_PREMIUM_FRACTION)
    already = {option.airport for option in suggestions}

    candidates: list[tuple[int, float, Offer]] = []
    for offer in offers:
        if offer.duration_minutes <= 0 or offer.total_price <= 0:
            continue
        if offer.origin_airport in already:
            continue

        premium = offer.total_price - best.price
        # A cheaper *and* faster flight from the best airport is simply a better
        # version of the same answer, so allow a negative premium here.
        if premium > ceiling:
            continue

        saved = best.offer.duration_minutes - offer.duration_minutes
        if saved < MIN_TIME_SAVED_MINUTES:
            continue

        candidates.append((saved, offer.total_price, offer))

    if not candidates:
        return None

    # Most time saved wins; cheaper breaks a tie.
    saved, _, winner = max(candidates, key=lambda c: (c[0], -c[1]))
    return AirportOption(
        airport=winner.origin_airport,
        offer=winner,
        distance_miles=distances.get(winner.origin_airport),
    )


def _worth_mentioning(best_price: float, other_price: float) -> bool:
    """True if the difference justifies travelling to a different airport."""
    saving = best_price - other_price
    if saving < MIN_SAVING:
        return False
    return saving >= best_price * MIN_SAVING_FRACTION


def describe_saving(comparison: Comparison, option: AirportOption) -> str:
    """One line explaining an alternative, e.g. 'EWR - save $47, 21 mi away'."""
    saving = comparison.saving_over_best(option)
    parts = [f"{option.airport} - save {saving:.0f}"]
    if option.distance_miles is not None:
        parts.append(f"{option.distance_miles:.0f} mi away")
    return ", ".join(parts)


def distances_from(
    request: SearchRequest, alternatives: list[tuple[Airport, float]]
) -> dict[str, float]:
    """Build the code -> miles map that ``compare`` uses for its wording."""
    return {airport.iata: miles for airport, miles in alternatives}
