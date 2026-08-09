"""Tests for reading dates and passenger counts out of free text."""

from __future__ import annotations

from datetime import date

from flightguru.parse import (
    parse_date,
    parse_passengers,
    parse_trip_type,
    parse_yes_no,
)

# A fixed "today" so tests do not drift. A Wednesday.
TODAY = date(2026, 8, 12)


def d(text):
    return parse_date(text, TODAY)


# --- dates ------------------------------------------------------------------


def test_iso_date():
    assert d("2026-09-12").value == "2026-09-12"


def test_iso_date_with_single_digits():
    assert d("2026-9-5").value == "2026-09-05"


def test_today_and_tomorrow():
    assert d("today").value == "2026-08-12"
    assert d("tomorrow").value == "2026-08-13"


def test_day_then_month_name():
    assert d("12 sep").value == "2026-09-12"
    assert d("12 september").value == "2026-09-12"
    assert d("12 september 2027").value == "2027-09-12"


def test_month_name_then_day():
    assert d("sep 12").value == "2026-09-12"
    assert d("september 12").value == "2026-09-12"


def test_ordinal_suffixes_are_ignored():
    assert d("12th sep").value == "2026-09-12"
    assert d("sep 1st").value == "2026-09-01"


def test_month_without_year_rolls_forward_rather_than_backward():
    """"5 jan" in August means next January, not eight months ago."""
    assert d("5 jan").value == "2027-01-05"


def test_weekday_means_the_coming_one():
    # TODAY is a Wednesday; Friday is two days later.
    assert d("friday").value == "2026-08-14"


def test_same_weekday_means_next_week_not_today():
    assert d("wednesday").value == "2026-08-19"


def test_next_weekday_skips_a_week():
    assert d("next friday").value == "2026-08-21"


def test_relative_offsets():
    assert d("in 3 days").value == "2026-08-15"
    assert d("in 2 weeks").value == "2026-08-26"
    assert d("in a week").value == "2026-08-19"


def test_unambiguous_slash_date_is_read():
    """25/09 can only be the 25th of September."""
    assert d("25/09").value == "2026-09-25"


def test_ambiguous_slash_date_asks_rather_than_guessing():
    """The expensive mistake this avoids: booking March instead of September."""
    result = d("03/09")
    assert not result.ok
    assert result.needs_clarification
    assert "can't tell which is the day" in result.error


def test_past_dates_are_rejected():
    result = d("2026-08-01")
    assert not result.ok
    assert "in the past" in result.error


def test_absurdly_distant_dates_are_rejected():
    result = d("2029-09-12")
    assert not result.ok
    assert "more than a year" in result.error


def test_impossible_dates_are_rejected():
    assert not d("2026-02-30").ok
    assert not d("31 feb").ok


def test_gibberish_gets_a_helpful_error():
    result = d("sometime nextish")
    assert not result.ok
    assert "2026-09-12" in result.error  # shows an example that works


def test_empty_input():
    assert not d("").ok


def test_whitespace_and_case_are_tolerated():
    assert d("  12 SEP  ").value == "2026-09-12"


# --- yes / no ---------------------------------------------------------------


def test_yes_variants():
    for word in ("yes", "y", "yeah", "sure", "ok", "YES"):
        assert parse_yes_no(word) is True


def test_no_variants():
    for word in ("no", "n", "nope", "skip", "NO"):
        assert parse_yes_no(word) is False


def test_unclear_answer_is_neither():
    assert parse_yes_no("maybe") is None


# --- trip type --------------------------------------------------------------


def test_trip_type_round():
    for text in ("round trip", "return", "roundtrip", "1", "round"):
        assert parse_trip_type(text) == "round_trip"


def test_trip_type_one_way():
    for text in ("one way", "oneway", "one-way", "2", "single"):
        assert parse_trip_type(text) == "one_way"


def test_trip_type_multi_city():
    for text in ("multi city", "multi-city", "3", "multicity"):
        assert parse_trip_type(text) == "multi_city"


def test_trip_type_unclear():
    assert parse_trip_type("dunno") is None


# --- passengers -------------------------------------------------------------


def test_bare_number_is_adults():
    assert parse_passengers("2").adults == 2


def test_default_is_one_adult():
    assert parse_passengers("").adults == 1


def test_just_me():
    assert parse_passengers("just me").adults == 1


def test_adults_and_children():
    people = parse_passengers("2 adults 1 child")
    assert (people.adults, people.children) == (2, 1)


def test_written_numbers():
    assert parse_passengers("two adults").adults == 2


def test_article_means_one():
    people = parse_passengers("an adult and a child")
    assert (people.adults, people.children) == (1, 1)


def test_infants_are_counted():
    assert parse_passengers("2 adults 1 infant").infants_on_lap == 1


def test_too_many_travellers_is_rejected():
    result = parse_passengers("12")
    assert not result.ok
    assert "at most 9" in result.error


def test_zero_travellers_is_rejected():
    assert not parse_passengers("0").ok


def test_more_lap_infants_than_adults_is_rejected():
    result = parse_passengers("1 adult 2 infants")
    assert not result.ok
    assert "hold them" in result.error


def test_unreadable_passenger_answer():
    result = parse_passengers("a whole bunch")
    assert not result.ok
