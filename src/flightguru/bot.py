"""The Telegram bot: read a message, run the conversation, send the answer.

Long-polls Telegram, keeps one in-progress conversation per chat, and calls
``scan`` when a conversation has gathered everything it needs.

Conversations live in memory. A restart loses a half-finished one, which is
acceptable: the questions take fifteen seconds to answer again, and persisting
them would mean a database write on every keystroke for very little gain. What is
*not* acceptable is answering a stale request on restart, so pending messages are
dropped at startup rather than replayed.
"""

from __future__ import annotations

import time
from dataclasses import replace

from . import conversation as convo, storage
from .airports import get as get_airport
from .config import Settings, load_settings
from .conversation import Conversation
from .deeplink import build_deep_link
from .log import get_logger
from .request import ONE_WAY, ROUND_TRIP
from .scan import format_result, scan_airports
from .telegram import TelegramClient, Update

log = get_logger()

HELP = """FlightGuru finds the cheapest flight, including from airports near you.

Say "flight" and I'll ask where you're going.

Commands:
/flight   start a search
/cancel   abandon the one in progress
/history  your last few searches
/help     this message

While answering:
  back    go to the previous question
  cancel  stop

You can answer with a city or an airport code - "new york" or JFK. If a nearby
airport is cheaper, I'll tell you."""

START_WORDS = {
    "flight", "flights", "fly", "search", "find", "start", "hi", "hello", "hey",
    "i need a flight", "need a flight", "book a flight", "find me a flight",
}


class Bot:
    """Holds the client, the settings, and everyone's in-progress conversation."""

    def __init__(self, settings: Settings, client: TelegramClient | None = None):
        self.settings = settings
        self.client = client or TelegramClient(
            settings.telegram_bot_token, timeout=settings.poll_timeout
        )
        self.conversations: dict[str, Conversation] = {}

    # --- message handling ------------------------------------------------

    def handle_update(self, update: Update) -> str | None:
        """Work out the reply to one message. Returns None to stay silent."""
        if not self.settings.allowed_chat(update.chat_id):
            log.warning(
                f"Ignoring message from chat {update.chat_id} "
                f"(@{update.from_username}) - not in TELEGRAM_CHAT_ID."
            )
            return None

        text = update.text.strip()
        command = update.command

        if command in ("start", "help"):
            self.conversations.pop(update.chat_id, None)
            return HELP
        if command == "cancel":
            self.conversations.pop(update.chat_id, None)
            return "Cancelled."
        if command == "history":
            return self._history(update.chat_id)
        if command == "flight":
            reply = convo.start()
            self.conversations[update.chat_id] = reply.conversation
            return reply.text

        active = self.conversations.get(update.chat_id)

        if active is None:
            if text.lower().strip("!.?") in START_WORDS:
                reply = convo.start()
                self.conversations[update.chat_id] = reply.conversation
                return reply.text
            return (
                'Say "flight" and I\'ll find you the cheapest one.\n'
                "/help for more."
            )

        reply = convo.handle(active, text)

        if reply.conversation.cancelled:
            self.conversations.pop(update.chat_id, None)
            return reply.text

        self.conversations[update.chat_id] = reply.conversation
        return reply.text

    def run_search(self, chat_id: str, conversation: Conversation) -> str:
        """Run the scan for a completed conversation and format the answer."""
        self.conversations.pop(chat_id, None)

        if not self.settings.serpapi_configured:
            return (
                "I can't search - no SerpApi key is configured. "
                "Set SERPAPI_API_KEY and restart me."
            )

        # The conversation already resolved these when it asked the questions.
        # Pass the airports through as they are -- flattening them back to text
        # and re-parsing broke every search from a multi-airport city.
        origins = tuple(a for a in map(get_airport, conversation.origin_codes) if a)
        destinations = tuple(
            a for a in map(get_airport, conversation.destination_codes) if a
        )

        try:
            result = scan_airports(
                origins=origins,
                destinations=destinations,
                depart_date=conversation.depart_date,
                api_key=self.settings.serpapi_key,
                return_date=conversation.return_date,
                trip_type=conversation.trip_type,
                include_nearby=self.settings.nearby_enabled,
                nearby_destination=self.settings.nearby_destination,
                radius_miles=self.settings.nearby_radius_miles,
                adults=conversation.adults,
                children=conversation.children,
                infants_on_lap=conversation.infants_on_lap,
                currency=self.settings.currency,
            )
        except Exception as exc:  # noqa: BLE001 - a failed search must not kill the bot
            log.error(f"Search failed for chat {chat_id}: {exc}")
            return (
                "The flight search failed on me. Try again in a minute - "
                "if it keeps happening the API may be down or out of quota."
            )

        message = format_result(result)
        message = self._append_links(message, result)

        # Logging the search is a convenience, never a reason to lose an answer.
        try:
            if result.request is not None:
                storage.save_search(
                    result.request,
                    result.comparison,
                    chat_id=chat_id,
                    links=self._links(result),
                )
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Could not log search: {exc}")

        return message

    def _links(self, result) -> dict[str, str]:
        """Booking link per airport, for the options we are showing."""
        links: dict[str, str] = {}
        if result.comparison is None:
            return links
        options = [result.comparison.best] + list(result.comparison.suggestions)
        for option in options:
            if option is None:
                continue
            link = build_deep_link(option.offer)
            if link:
                links[option.airport] = link
        return links

    def _append_links(self, message: str, result) -> str:
        links = self._links(result)
        if not links:
            return message
        lines = [message, "", "Book:"]
        for airport, link in links.items():
            lines.append(f"{airport}: {link}")
        return "\n".join(lines)

    def _history(self, chat_id: str) -> str:
        try:
            searches = storage.recent_searches(limit=5, chat_id=chat_id)
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Could not read history: {exc}")
            return "I couldn't read the search history."

        if not searches:
            return "No searches yet."

        lines = ["Your last searches:"]
        for row in searches:
            when = (row.get("searched_at_utc") or "")[:10]
            route = f"{row.get('requested_from')} to {row.get('requested_to')}"
            dates = row.get("depart_date") or ""
            if row.get("return_date"):
                dates += f" / {row['return_date']}"
            cheapest = storage.cheapest_for_search(row["id"])
            price = (
                f"  {cheapest['currency']} {cheapest['total_price']:.0f} "
                f"from {cheapest['origin']}"
                if cheapest
                else "  (no result)"
            )
            lines.append(f"{when}  {route}  {dates}\n{price}")
        return "\n".join(lines)

    # --- the loop --------------------------------------------------------

    def run_forever(self) -> None:
        """Poll Telegram and answer, until stopped."""
        # Startup must not be able to kill the bot. Identifying itself and
        # clearing the backlog are both conveniences, and both talk to a network
        # that is sometimes hostile -- one reset here used to end the process
        # before it ever reached the retry logic in the loop below.
        try:
            me = self.client.get_me()
            log.info(f"FlightGuru bot running as @{me.get('username', '?')}")
        except Exception as exc:  # noqa: BLE001
            log.warning(
                f"Could not reach Telegram at startup ({exc}). "
                f"Starting anyway and will keep trying."
            )

        try:
            dropped = self.client.drain_pending()
            if dropped:
                log.info(f"Ignored {dropped} message(s) received while offline.")
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Could not clear the backlog at startup ({exc}). Continuing.")

        if not self.settings.telegram_chat_id:
            log.warning(
                "TELEGRAM_CHAT_ID is not set, so every message will be ignored. "
                "Set it to your chat id, or to * to allow anyone."
            )

        consecutive_failures = 0
        while True:
            try:
                updates = self.client.poll(self.settings.poll_timeout)
            except Exception as exc:  # noqa: BLE001 - network blips are expected
                consecutive_failures += 1
                # Back off gradually rather than hammering a network that is
                # already refusing us, but stay responsive enough that the bot
                # recovers quickly once it clears. Capped at a minute.
                wait = min(2 ** min(consecutive_failures, 5), 60)
                # Log the first failure and then only occasionally: a flaky link
                # otherwise fills the log with identical lines and hides
                # anything that actually matters.
                if consecutive_failures == 1 or consecutive_failures % 10 == 0:
                    log.warning(
                        f"Poll failed ({consecutive_failures} in a row), "
                        f"retrying in {wait}s: {exc}"
                    )
                time.sleep(wait)
                continue

            if consecutive_failures:
                log.info(f"Polling recovered after {consecutive_failures} failure(s).")
                consecutive_failures = 0

            for update in updates:
                self._respond(update)

    def _respond(self, update: Update) -> None:
        """Answer one message, including running a search if it completed one."""
        try:
            reply = self.handle_update(update)
            if reply is None:
                return
            self.client.send(update.chat_id, reply)

            # A finished conversation triggers the search as a second message,
            # so the confirmation lands immediately rather than after the wait.
            pending = self.conversations.get(update.chat_id)
            if pending is not None and pending.done:
                self.client.send_typing(update.chat_id)
                self.client.send(
                    update.chat_id, self.run_search(update.chat_id, pending)
                )
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the bot
            log.error(f"Failed handling update {update.update_id}: {exc}")
            try:
                self.client.send(
                    update.chat_id, "Something went wrong there. Try again?"
                )
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    try:
        settings = load_settings()
    except RuntimeError as exc:
        log.error(str(exc))
        return 1

    Bot(settings).run_forever()
    return 0
