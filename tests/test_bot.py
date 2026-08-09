"""Tests for the bot's message handling.

The search itself is stubbed — this covers routing, access control, and the
conversation being carried correctly between messages.
"""

from __future__ import annotations

import pytest

from flightguru.bot import Bot
from flightguru.telegram import Update

CHAT = "6889043609"
STRANGER = "999999"


class FakeClient:
    """Records what would have been sent, sends nothing."""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, chat_id, text):
        self.sent.append((str(chat_id), text))
        return True

    def send_typing(self, chat_id):
        pass

    def get_me(self):
        return {"username": "FlightGuruBot"}

    def drain_pending(self):
        return 0


@pytest.fixture
def bot(settings):
    return Bot(settings, client=FakeClient())


def msg(text, chat_id=CHAT, update_id=1) -> Update:
    return Update(update_id=update_id, chat_id=chat_id, text=text)


# --- access control ---------------------------------------------------------


def test_strangers_are_ignored(bot):
    """The token is effectively public and every search costs quota."""
    assert bot.handle_update(msg("flight", chat_id=STRANGER)) is None


def test_the_configured_chat_is_answered(bot):
    assert bot.handle_update(msg("flight")) is not None


def test_a_wildcard_chat_id_allows_anyone(make_settings):
    bot = Bot(make_settings(telegram_chat_id="*"), client=FakeClient())
    assert bot.handle_update(msg("flight", chat_id=STRANGER)) is not None


def test_an_unset_chat_id_ignores_everyone(make_settings):
    """Safer to be silent than to let a stranger spend the quota."""
    bot = Bot(make_settings(telegram_chat_id=""), client=FakeClient())
    assert bot.handle_update(msg("flight")) is None


def test_several_chat_ids_can_be_allowed(make_settings):
    bot = Bot(make_settings(telegram_chat_id=f"{CHAT},{STRANGER}"), client=FakeClient())
    assert bot.handle_update(msg("hi", chat_id=STRANGER)) is not None


# --- commands ---------------------------------------------------------------


def test_help_explains_itself(bot):
    reply = bot.handle_update(msg("/help"))
    assert "cheapest" in reply and "/flight" in reply


def test_start_shows_help(bot):
    assert "cheapest" in bot.handle_update(msg("/start"))


def test_flight_command_opens_the_questions(bot):
    assert "flying from" in bot.handle_update(msg("/flight"))


def test_cancel_clears_an_in_progress_conversation(bot):
    bot.handle_update(msg("/flight"))
    bot.handle_update(msg("JFK"))
    bot.handle_update(msg("/cancel"))
    assert CHAT not in bot.conversations


def test_help_abandons_an_in_progress_conversation(bot):
    bot.handle_update(msg("/flight"))
    bot.handle_update(msg("/help"))
    assert CHAT not in bot.conversations


# --- starting a conversation ------------------------------------------------


@pytest.mark.parametrize("opener", ["flight", "hi", "I need a flight", "Fly", "hello"])
def test_natural_openers_start_the_questions(bot, opener):
    assert "flying from" in bot.handle_update(msg(opener))


def test_unrecognised_chatter_points_at_the_command(bot):
    reply = bot.handle_update(msg("what's the weather"))
    assert "flight" in reply.lower()
    assert CHAT not in bot.conversations


# --- carrying the conversation ----------------------------------------------


def test_answers_advance_the_conversation(bot):
    bot.handle_update(msg("flight"))
    bot.handle_update(msg("JFK"))
    assert bot.conversations[CHAT].origin_codes == ("JFK",)

    bot.handle_update(msg("LAX"))
    assert bot.conversations[CHAT].destination_codes == ("LAX",)


def test_two_chats_do_not_share_a_conversation(make_settings):
    bot = Bot(make_settings(telegram_chat_id=f"{CHAT},{STRANGER}"), client=FakeClient())
    bot.handle_update(msg("flight", chat_id=CHAT))
    bot.handle_update(msg("JFK", chat_id=CHAT))
    bot.handle_update(msg("flight", chat_id=STRANGER))
    bot.handle_update(msg("BOS", chat_id=STRANGER))

    assert bot.conversations[CHAT].origin_codes == ("JFK",)
    assert bot.conversations[STRANGER].origin_codes == ("BOS",)


def test_a_finished_conversation_is_marked_ready(bot):
    for answer in ("flight", "JFK", "LAX", "round trip", "2027-03-12", "2027-03-19", "1"):
        bot.handle_update(msg(answer))
    assert bot.conversations[CHAT].done


# --- searching --------------------------------------------------------------


def test_missing_api_key_is_reported_not_crashed(make_settings):
    bot = Bot(make_settings(serpapi_key=""), client=FakeClient())
    for answer in ("flight", "JFK", "LAX", "round trip", "2027-03-12", "2027-03-19", "1"):
        bot.handle_update(msg(answer))
    reply = bot.run_search(CHAT, bot.conversations[CHAT])
    assert "no SerpApi key" in reply


def test_a_failing_search_does_not_take_the_bot_down(bot, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("SerpApi exploded")

    monkeypatch.setattr("flightguru.bot.scan_airports", boom)
    for answer in ("flight", "JFK", "LAX", "round trip", "2027-03-12", "2027-03-19", "1"):
        bot.handle_update(msg(answer))

    reply = bot.run_search(CHAT, bot.conversations[CHAT])
    assert "failed" in reply.lower()
    # And the conversation is cleared, so the next message starts cleanly.
    assert CHAT not in bot.conversations


def test_startup_survives_telegram_being_unreachable(make_settings):
    """A reset during startup used to kill the process outright.

    get_me() ran before any retry logic and its failure propagated straight out
    of run_forever, so a single dropped connection in the first second meant the
    bot exited and never answered anyone. It must log and carry on instead.
    """
    reached_the_loop = []

    class UnreachableAtStartup:
        def get_me(self):
            raise ConnectionError("connection reset")

        def drain_pending(self):
            raise ConnectionError("connection reset")

        def poll(self, wait):
            reached_the_loop.append(True)
            raise KeyboardInterrupt  # stop the loop so the test can end

        def send(self, chat_id, text):
            return True

        def send_typing(self, chat_id):
            pass

    bot = Bot(make_settings(), client=UnreachableAtStartup())
    with pytest.raises(KeyboardInterrupt):
        bot.run_forever()

    assert reached_the_loop, "startup failure stopped the bot reaching its poll loop"


def test_search_clears_the_conversation(bot, monkeypatch):
    monkeypatch.setattr(
        "flightguru.bot.scan_airports",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("x")),
    )
    for answer in ("flight", "JFK", "LAX", "one way", "2027-03-12", "1"):
        bot.handle_update(msg(answer))
    bot.run_search(CHAT, bot.conversations[CHAT])
    assert CHAT not in bot.conversations


# --- the whole path, with only the network faked -----------------------------
#
# These stub the HTTP call and nothing else. The earlier tests stubbed `scan`
# itself, which is precisely the call that was broken: the bot flattened its
# resolved airports back into the string "EWR, JFK, LGA" and asked the resolver
# to look that up as a place name. Every search from a multi-airport city failed
# and no test noticed, because the tests replaced the broken step.


def fake_google_response(*origins):
    """A Google Flights response with one itinerary per origin airport."""
    return {
        "search_parameters": {"currency": "USD"},
        "best_flights": [
            {
                "price": 200 + i * 10,
                "total_duration": 300,
                "flights": [
                    {
                        "airline": "Delta",
                        "flight_number": f"DL {i}",
                        "departure_airport": {"id": code, "time": "2027-03-12 08:00"},
                        "arrival_airport": {"id": "PBI", "time": "2027-03-12 11:00"},
                    }
                ],
            }
            for i, code in enumerate(origins)
        ],
        "other_flights": [],
    }


def answer_all(bot, *answers):
    for answer in answers:
        bot.handle_update(msg(answer))
    return bot.run_search(CHAT, bot.conversations[CHAT])


def test_a_multi_airport_city_search_actually_runs(bot, monkeypatch):
    """The NYC bug: "NYC" resolves to three airports and the search must work."""
    monkeypatch.setattr(
        "flightguru.providers.flights.net.request_json",
        lambda *a, **k: fake_google_response("JFK", "LGA", "EWR"),
    )
    reply = answer_all(
        bot, "flight", "NYC", "west palm beach", "one way", "2027-03-12", "1"
    )
    assert "I don't know an airport or city" not in reply
    assert "CHEAPEST" in reply


def test_a_single_airport_search_still_runs(bot, monkeypatch):
    monkeypatch.setattr(
        "flightguru.providers.flights.net.request_json",
        lambda *a, **k: fake_google_response("JFK"),
    )
    reply = answer_all(bot, "flight", "JFK", "PBI", "one way", "2027-03-12", "1")
    assert "CHEAPEST" in reply


def test_a_state_search_runs(bot, monkeypatch):
    """"CT" resolves to two airports and must survive the same round trip."""
    monkeypatch.setattr(
        "flightguru.providers.flights.net.request_json",
        lambda *a, **k: fake_google_response("BDL", "HVN"),
    )
    reply = answer_all(bot, "flight", "CT", "orlando", "one way", "2027-03-12", "1")
    assert "CHEAPEST" in reply


def test_a_round_trip_runs(bot, monkeypatch):
    monkeypatch.setattr(
        "flightguru.providers.flights.net.request_json",
        lambda *a, **k: fake_google_response("JFK", "EWR"),
    )
    reply = answer_all(
        bot, "flight", "NYC", "miami", "round trip", "2027-03-12", "2027-03-19", "2"
    )
    assert "CHEAPEST" in reply


def test_a_search_that_finds_nothing_says_so(bot, monkeypatch):
    monkeypatch.setattr(
        "flightguru.providers.flights.net.request_json",
        lambda *a, **k: {"search_parameters": {"currency": "USD"}},
    )
    reply = answer_all(bot, "flight", "NYC", "PBI", "one way", "2027-03-12", "1")
    assert "No flights came back" in reply
