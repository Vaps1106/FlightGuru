"""Tests for the question flow.

Runs the whole conversation without a network, a token, or Telegram — which is
the point of keeping the state machine separate from the bot.
"""

from __future__ import annotations

from datetime import date

from flightguru import conversation as convo
from flightguru.conversation import (
    ASK_DEPART_DATE,
    ASK_DESTINATION,
    ASK_ORIGIN,
    ASK_PASSENGERS,
    ASK_RETURN_DATE,
    ASK_TRIP_TYPE,
    READY,
)

TODAY = date(2026, 8, 12)


def say(conversation, *answers):
    """Feed several answers in and return the final reply."""
    reply = None
    for answer in answers:
        reply = convo.handle(conversation, answer, TODAY)
        conversation = reply.conversation
    return reply


def full_conversation():
    return say(
        convo.start().conversation,
        "JFK", "LAX", "round trip", "2026-09-12", "2026-09-19", "1",
    )


# --- the happy path ---------------------------------------------------------


def test_conversation_opens_by_asking_where_from():
    reply = convo.start()
    assert reply.conversation.state == ASK_ORIGIN
    assert "flying from" in reply.text


def test_questions_come_one_at_a_time_in_order():
    conversation = convo.start().conversation
    for answer, next_state in (
        ("JFK", ASK_DESTINATION),
        ("LAX", ASK_TRIP_TYPE),
        ("round trip", ASK_DEPART_DATE),
        ("2026-09-12", ASK_RETURN_DATE),
        ("2026-09-19", ASK_PASSENGERS),
        ("1", READY),
    ):
        reply = convo.handle(conversation, answer, TODAY)
        assert reply.conversation.state == next_state
        conversation = reply.conversation


def test_a_complete_conversation_is_ready_to_search():
    reply = full_conversation()
    assert reply.ready_to_search
    conversation = reply.conversation
    assert conversation.origin_codes == ("JFK",)
    assert conversation.destination_codes == ("LAX",)
    assert conversation.depart_date == "2026-09-12"
    assert conversation.return_date == "2026-09-19"
    assert conversation.adults == 1


def test_summary_reads_the_request_back():
    text = full_conversation().text
    assert "JFK to LAX" in text
    assert "2026-09-12" in text
    assert "2026-09-19" in text


def test_one_way_skips_the_return_date_question():
    reply = say(
        convo.start().conversation, "JFK", "LAX", "one way", "2026-09-12", "1"
    )
    assert reply.ready_to_search
    assert reply.conversation.return_date is None


# --- city names -------------------------------------------------------------


def test_city_names_are_accepted():
    reply = say(convo.start().conversation, "new york")
    assert set(reply.conversation.origin_codes) >= {"JFK", "LGA", "EWR"}


def test_ambiguous_city_offers_a_numbered_list():
    reply = say(convo.start().conversation, "springfield")
    assert "1." in reply.text and "2." in reply.text
    # Still on the same question until it is resolved.
    assert reply.conversation.state == ASK_ORIGIN


def test_replying_with_a_number_picks_from_the_list():
    conversation = convo.start().conversation
    reply = convo.handle(conversation, "springfield", TODAY)
    reply = convo.handle(reply.conversation, "1", TODAY)
    assert reply.conversation.state == ASK_DESTINATION
    assert reply.conversation.origin_codes == ("SGF",)


def test_unknown_place_re_asks_without_advancing():
    reply = say(convo.start().conversation, "xyzzy")
    assert reply.conversation.state == ASK_ORIGIN
    assert "don't know" in reply.text


def test_flying_to_where_you_started_is_caught_before_searching():
    reply = say(convo.start().conversation, "JFK", "JFK")
    assert reply.conversation.state == ASK_DESTINATION
    assert "where you're flying from" in reply.text


# --- bad answers do not advance ---------------------------------------------


def test_unreadable_date_re_asks():
    reply = say(convo.start().conversation, "JFK", "LAX", "round trip", "whenever")
    assert reply.conversation.state == ASK_DEPART_DATE
    assert reply.conversation.depart_date == ""


def test_ambiguous_date_re_asks_rather_than_guessing():
    reply = say(convo.start().conversation, "JFK", "LAX", "round trip", "03/09")
    assert reply.conversation.state == ASK_DEPART_DATE
    assert "can't tell which is the day" in reply.text


def test_return_before_departure_re_asks():
    reply = say(
        convo.start().conversation,
        "JFK", "LAX", "round trip", "2026-09-12", "2026-09-01",
    )
    assert reply.conversation.state == ASK_RETURN_DATE
    assert "before you fly out" in reply.text


def test_unclear_trip_type_re_asks():
    reply = say(convo.start().conversation, "JFK", "LAX", "dunno")
    assert reply.conversation.state == ASK_TRIP_TYPE


def test_bad_passenger_count_re_asks():
    reply = say(
        convo.start().conversation,
        "JFK", "LAX", "round trip", "2026-09-12", "2026-09-19", "0",
    )
    assert reply.conversation.state == ASK_PASSENGERS


def test_multi_city_is_declined_honestly_rather_than_half_working():
    reply = say(convo.start().conversation, "JFK", "LAX", "multi city")
    assert reply.conversation.state == ASK_TRIP_TYPE
    assert "isn't wired into the chat yet" in reply.text


# --- corrections ------------------------------------------------------------


def test_back_returns_to_the_previous_question():
    conversation = say(convo.start().conversation, "JFK", "LAX").conversation
    assert conversation.state == ASK_TRIP_TYPE
    reply = convo.handle(conversation, "back", TODAY)
    assert reply.conversation.state == ASK_DESTINATION


def test_back_at_the_start_stays_at_the_start():
    reply = convo.handle(convo.start().conversation, "back", TODAY)
    assert reply.conversation.state == ASK_ORIGIN


def test_back_from_passengers_on_a_one_way_skips_the_return_question():
    conversation = say(
        convo.start().conversation, "JFK", "LAX", "one way", "2026-09-12"
    ).conversation
    assert conversation.state == ASK_PASSENGERS
    reply = convo.handle(conversation, "back", TODAY)
    assert reply.conversation.state == ASK_DEPART_DATE


def test_cancel_ends_the_conversation():
    conversation = say(convo.start().conversation, "JFK").conversation
    reply = convo.handle(conversation, "cancel", TODAY)
    assert reply.conversation.cancelled


def test_cancel_works_at_any_point():
    for answers in ((), ("JFK",), ("JFK", "LAX"), ("JFK", "LAX", "round trip")):
        conversation = say(convo.start().conversation, *answers).conversation if answers else convo.start().conversation
        assert convo.handle(conversation, "cancel", TODAY).conversation.cancelled


# --- passenger answers ------------------------------------------------------


def test_passenger_details_are_carried_through():
    reply = say(
        convo.start().conversation,
        "JFK", "LAX", "round trip", "2026-09-12", "2026-09-19", "2 adults 1 child",
    )
    assert reply.conversation.adults == 2
    assert reply.conversation.children == 1
    assert "2 adults, 1 child" in reply.text


def test_natural_dates_work_through_the_flow():
    reply = say(
        convo.start().conversation, "JFK", "LAX", "round trip", "12 sep", "19 sep", "1"
    )
    assert reply.conversation.depart_date == "2026-09-12"
    assert reply.conversation.return_date == "2026-09-19"
