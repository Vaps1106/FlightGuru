"""The question flow: from "I need a flight" to a search.

A conversation is a small state machine. Each state asks one question, reads one
answer, and moves on. Keeping it explicit rather than clever means the bot can be
tested end to end without a network, a token, or a running Telegram.

Design choices worth stating:

**One question at a time.** A wall of six questions in one message gets a wall of
six answers back in an order nobody can parse reliably.

**A bad answer re-asks the same question.** It never advances on something it
could not read, because carrying a wrong date forward produces a confident answer
to the wrong question.

**Anything can be corrected.** "back" returns to the previous question, and
"cancel" abandons the whole thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from . import airports, parse
from .request import MULTI_CITY, ONE_WAY, ROUND_TRIP

# States, in the order they are asked.
ASK_ORIGIN = "ask_origin"
ASK_DESTINATION = "ask_destination"
ASK_TRIP_TYPE = "ask_trip_type"
ASK_DEPART_DATE = "ask_depart_date"
ASK_RETURN_DATE = "ask_return_date"
ASK_PASSENGERS = "ask_passengers"
READY = "ready"
CANCELLED = "cancelled"

# Which question follows which, for a round trip. one-way skips the return date.
ORDER = [
    ASK_ORIGIN,
    ASK_DESTINATION,
    ASK_TRIP_TYPE,
    ASK_DEPART_DATE,
    ASK_RETURN_DATE,
    ASK_PASSENGERS,
]


@dataclass(frozen=True)
class Conversation:
    """One person's half-finished flight request.

    Immutable: every answer produces a new Conversation. That makes "go back"
    trivial and means a half-answered state can never be corrupted by a partial
    update.
    """

    state: str = ASK_ORIGIN

    origin_text: str = ""
    destination_text: str = ""
    origin_codes: tuple[str, ...] = ()
    destination_codes: tuple[str, ...] = ()

    trip_type: str = ROUND_TRIP
    depart_date: str = ""
    return_date: str | None = None

    adults: int = 1
    children: int = 0
    infants_on_lap: int = 0

    # Candidate airports offered when a place name was ambiguous, so a reply of
    # "2" can be matched back to what was actually listed.
    pending_choices: tuple[str, ...] = field(default=())

    @property
    def done(self) -> bool:
        return self.state == READY

    @property
    def cancelled(self) -> bool:
        return self.state == CANCELLED


@dataclass(frozen=True)
class Reply:
    """What to say back, and the conversation to carry forward."""

    text: str
    conversation: Conversation

    @property
    def ready_to_search(self) -> bool:
        return self.conversation.done


def start() -> Reply:
    """Open a new conversation."""
    return Reply(text=question_for(ASK_ORIGIN, Conversation()), conversation=Conversation())


def question_for(state: str, conversation: Conversation) -> str:
    """The question to ask in a given state."""
    if state == ASK_ORIGIN:
        return (
            "Where are you flying from?\n"
            "An airport code or a city both work - JFK, or new york."
        )
    if state == ASK_DESTINATION:
        return "Where are you flying to?"
    if state == ASK_TRIP_TYPE:
        return "Round trip, one way, or multi-city?"
    if state == ASK_DEPART_DATE:
        return (
            "What date are you flying out?\n"
            "2026-09-12, \"12 sep\" and \"next friday\" all work."
        )
    if state == ASK_RETURN_DATE:
        return "And what date are you coming back?"
    if state == ASK_PASSENGERS:
        return "How many travelling? (just press 1 if it's only you)"
    return ""


def handle(conversation: Conversation, text: str, today: date | None = None) -> Reply:
    """Take one answer and move the conversation on.

    Returns the next question, or a confirmation when everything is gathered.
    """
    raw = (text or "").strip()
    lowered = raw.lower()

    if lowered in ("cancel", "stop", "quit", "/cancel", "nevermind", "never mind"):
        return Reply(
            text="Cancelled. Say \"flight\" whenever you want to start again.",
            conversation=replace(conversation, state=CANCELLED),
        )

    if lowered in ("back", "/back"):
        return _go_back(conversation)

    if conversation.state == ASK_ORIGIN:
        return _answer_place(conversation, raw, is_origin=True)
    if conversation.state == ASK_DESTINATION:
        return _answer_place(conversation, raw, is_origin=False)
    if conversation.state == ASK_TRIP_TYPE:
        return _answer_trip_type(conversation, raw)
    if conversation.state == ASK_DEPART_DATE:
        return _answer_depart_date(conversation, raw, today)
    if conversation.state == ASK_RETURN_DATE:
        return _answer_return_date(conversation, raw, today)
    if conversation.state == ASK_PASSENGERS:
        return _answer_passengers(conversation, raw)

    return Reply(text=question_for(conversation.state, conversation), conversation=conversation)


# --- individual answers -----------------------------------------------------


def _answer_place(conversation: Conversation, raw: str, is_origin: bool) -> Reply:
    """Resolve a city or airport, asking again if it is unclear."""
    # If we just offered a numbered list, a bare number picks from it.
    if conversation.pending_choices and raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(conversation.pending_choices):
            raw = conversation.pending_choices[index]

    resolution = airports.resolve(raw)

    if resolution.ambiguous:
        listing = "\n".join(
            f"{i}. {a.iata} - {a.city}, {a.region}"
            for i, a in enumerate(resolution.candidates, start=1)
        )
        return Reply(
            text=f'Which "{raw}" do you mean?\n{listing}\n\nReply with the number.',
            conversation=replace(
                conversation,
                pending_choices=tuple(a.iata for a in resolution.candidates),
            ),
        )

    if not resolution.ok:
        return Reply(
            text=(
                f'I don\'t know anywhere called "{raw}".\n'
                f"Try an airport code (JFK) or a city (new york)."
            ),
            conversation=replace(conversation, pending_choices=()),
        )

    codes = tuple(a.iata for a in resolution.airports)
    found = ", ".join(codes)

    if is_origin:
        updated = replace(
            conversation,
            origin_text=raw,
            origin_codes=codes,
            pending_choices=(),
            state=ASK_DESTINATION,
        )
    else:
        # Flying to where you are leaving from finds nothing, so catch it here
        # rather than after spending a search.
        if set(codes) == set(conversation.origin_codes):
            return Reply(
                text=(
                    f"That's where you're flying from. "
                    f"Where do you want to go?"
                ),
                conversation=replace(conversation, pending_choices=()),
            )
        updated = replace(
            conversation,
            destination_text=raw,
            destination_codes=codes,
            pending_choices=(),
            state=ASK_TRIP_TYPE,
        )

    confirm = f"Got it: {found}." if len(codes) == 1 else f"Got it: {found}."
    return Reply(
        text=f"{confirm}\n\n{question_for(updated.state, updated)}",
        conversation=updated,
    )


def _answer_trip_type(conversation: Conversation, raw: str) -> Reply:
    trip_type = parse.parse_trip_type(raw)
    if trip_type is None:
        return Reply(
            text='Sorry - "round trip", "one way", or "multi-city"?',
            conversation=conversation,
        )

    if trip_type == MULTI_CITY:
        # Multi-city needs a different, longer flow. Rather than pretend, say so.
        return Reply(
            text=(
                "Multi-city isn't wired into the chat yet - I can search it, but "
                "the questions for it aren't built.\n"
                "Round trip or one way for now?"
            ),
            conversation=conversation,
        )

    updated = replace(conversation, trip_type=trip_type, state=ASK_DEPART_DATE)
    return Reply(text=question_for(ASK_DEPART_DATE, updated), conversation=updated)


def _answer_depart_date(conversation: Conversation, raw: str, today) -> Reply:
    parsed = parse.parse_date(raw, today)
    if not parsed.ok:
        return Reply(text=parsed.error, conversation=conversation)

    if conversation.trip_type == ONE_WAY:
        updated = replace(
            conversation, depart_date=parsed.value, state=ASK_PASSENGERS
        )
    else:
        updated = replace(
            conversation, depart_date=parsed.value, state=ASK_RETURN_DATE
        )

    return Reply(
        text=f"Out on {parsed.value}.\n\n{question_for(updated.state, updated)}",
        conversation=updated,
    )


def _answer_return_date(conversation: Conversation, raw: str, today) -> Reply:
    parsed = parse.parse_date(raw, today)
    if not parsed.ok:
        return Reply(text=parsed.error, conversation=conversation)

    if parsed.value < conversation.depart_date:
        return Reply(
            text=(
                f"That's before you fly out ({conversation.depart_date}). "
                f"When are you coming back?"
            ),
            conversation=conversation,
        )

    updated = replace(conversation, return_date=parsed.value, state=ASK_PASSENGERS)
    return Reply(
        text=f"Back on {parsed.value}.\n\n{question_for(ASK_PASSENGERS, updated)}",
        conversation=updated,
    )


def _answer_passengers(conversation: Conversation, raw: str) -> Reply:
    passengers = parse.parse_passengers(raw)
    if not passengers.ok:
        return Reply(text=passengers.error, conversation=conversation)

    updated = replace(
        conversation,
        adults=passengers.adults,
        children=passengers.children,
        infants_on_lap=passengers.infants_on_lap,
        state=READY,
    )
    return Reply(text=summary(updated), conversation=updated)


def _go_back(conversation: Conversation) -> Reply:
    """Return to the previous question."""
    order = [s for s in ORDER if not (s == ASK_RETURN_DATE and conversation.trip_type == ONE_WAY)]
    try:
        index = order.index(conversation.state)
    except ValueError:
        index = len(order)  # from READY, step back into the last question

    if index <= 0:
        return Reply(
            text=question_for(ASK_ORIGIN, conversation),
            conversation=replace(conversation, state=ASK_ORIGIN, pending_choices=()),
        )

    previous = order[index - 1]
    updated = replace(conversation, state=previous, pending_choices=())
    return Reply(text=question_for(previous, updated), conversation=updated)


def summary(conversation: Conversation) -> str:
    """Read the gathered request back before spending a search on it."""
    route = (
        f"{', '.join(conversation.origin_codes)} to "
        f"{', '.join(conversation.destination_codes)}"
    )
    lines = [f"Searching {route}"]

    if conversation.trip_type == ROUND_TRIP:
        lines.append(f"Out {conversation.depart_date}, back {conversation.return_date}")
    else:
        lines.append(f"Out {conversation.depart_date}, one way")

    people = f"{conversation.adults} adult" + ("s" if conversation.adults != 1 else "")
    if conversation.children:
        people += f", {conversation.children} child" + (
            "ren" if conversation.children != 1 else ""
        )
    if conversation.infants_on_lap:
        people += f", {conversation.infants_on_lap} infant" + (
            "s" if conversation.infants_on_lap != 1 else ""
        )
    lines.append(people)
    lines.append("")
    lines.append("Checking nearby airports too. One moment...")
    return "\n".join(lines)
