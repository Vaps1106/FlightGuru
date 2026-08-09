"""Understand what someone typed in a chat.

People do not type ISO dates. They type "12 sep", "next friday", "sep 12th", or
just "tomorrow", and any of those has to work or the bot is more annoying than
opening a browser.

The one thing this module refuses to do is guess when guessing could be wrong in
an expensive way. "03/09" means the 3rd of September to half the world and the
9th of March to the other half, and there is no way to tell from the text which
one someone meant. Rather than pick, it asks. Booking the wrong month is a much
worse outcome than one extra question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

AFFIRMATIVE = {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "please", "1"}
NEGATIVE = {"no", "n", "nope", "nah", "not", "skip", "none", "0"}


@dataclass(frozen=True)
class ParsedDate:
    """A date, or a reason it could not be read.

    ``needs_clarification`` marks the ambiguous case — the text was a valid date
    format but means two different days depending on convention.
    """

    value: str | None = None            # YYYY-MM-DD
    error: str = ""
    needs_clarification: bool = False

    @property
    def ok(self) -> bool:
        return self.value is not None


def parse_date(text: str, today: date | None = None) -> ParsedDate:
    """Read a departure or return date out of free text."""
    today = today or date.today()
    raw = (text or "").strip().lower()
    if not raw:
        return ParsedDate(error="I need a date.")

    raw = re.sub(r"\s+", " ", raw)

    for reader in (
        _iso,
        _relative_day,
        _weekday,
        _in_n_days,
        _day_month_name,
        _numeric_slashes,
    ):
        result = reader(raw, today)
        if result is not None:
            return result

    return ParsedDate(
        error=(
            f'I could not read "{text}" as a date. '
            f"Try something like 2026-09-12, or \"12 sep\", or \"next friday\"."
        )
    )


def _iso(raw: str, today: date) -> ParsedDate | None:
    """2026-09-12 — unambiguous, so always preferred."""
    if not re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", raw):
        return None
    try:
        parsed = date.fromisoformat(
            "-".join(part.zfill(2) if i else part for i, part in enumerate(raw.split("-")))
        )
    except ValueError:
        return ParsedDate(error=f'"{raw}" is not a real date.')
    return _check_future(parsed, today)


def _relative_day(raw: str, today: date) -> ParsedDate | None:
    if raw == "today":
        return _check_future(today, today)
    if raw == "tomorrow":
        return _check_future(today + timedelta(days=1), today)
    if raw in ("day after tomorrow", "overmorrow"):
        return _check_future(today + timedelta(days=2), today)
    return None


def _weekday(raw: str, today: date) -> ParsedDate | None:
    """"friday", "next friday" — the coming one, never one in the past."""
    match = re.fullmatch(r"(?:(this|next|coming) )?([a-z]+)", raw)
    if not match:
        return None
    qualifier, name = match.group(1), match.group(2)
    if name not in WEEKDAYS:
        return None

    target = WEEKDAYS[name]
    ahead = (target - today.weekday()) % 7
    # Plain "friday" on a Friday means the next one, not today.
    if ahead == 0:
        ahead = 7
    if qualifier == "next":
        ahead += 7
    return _check_future(today + timedelta(days=ahead), today)


def _in_n_days(raw: str, today: date) -> ParsedDate | None:
    """"in 3 days", "in 2 weeks", "in a month"."""
    match = re.fullmatch(r"in (\d+|a|an) (day|days|week|weeks|month|months)", raw)
    if not match:
        return None
    count = 1 if match.group(1) in ("a", "an") else int(match.group(1))
    unit = match.group(2)
    if unit.startswith("day"):
        delta = timedelta(days=count)
    elif unit.startswith("week"):
        delta = timedelta(weeks=count)
    else:
        delta = timedelta(days=30 * count)
    return _check_future(today + delta, today)


def _day_month_name(raw: str, today: date) -> ParsedDate | None:
    """"12 sep", "sep 12", "12 september 2026", "sept 12th"."""
    cleaned = raw.replace(",", " ")
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    patterns = (
        r"(?P<day>\d{1,2}) (?P<month>[a-z]+)(?: (?P<year>\d{4}))?",
        r"(?P<month>[a-z]+) (?P<day>\d{1,2})(?: (?P<year>\d{4}))?",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, cleaned)
        if not match:
            continue
        month = MONTHS.get(match.group("month"))
        if month is None:
            continue

        day = int(match.group("day"))
        year_text = match.group("year")
        if year_text:
            year = int(year_text)
        else:
            # No year given: assume the next time this date comes around, so
            # "12 sep" in December means next year, not nine months ago.
            year = today.year
            try:
                if date(year, month, day) < today:
                    year += 1
            except ValueError:
                return ParsedDate(error=f'"{raw}" is not a real date.')

        try:
            return _check_future(date(year, month, day), today)
        except ValueError:
            return ParsedDate(error=f'"{raw}" is not a real date.')
    return None


def _numeric_slashes(raw: str, today: date) -> ParsedDate | None:
    """"12/09", "12/09/2026", "12-09-2026".

    Only resolved when one number is above 12 and therefore must be the day.
    Otherwise it is genuinely ambiguous and gets a question, not a guess.
    """
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", raw)
    if not match:
        return None

    first, second = int(match.group(1)), int(match.group(2))
    year_text = match.group(3)
    if year_text:
        year = int(year_text)
        if year < 100:
            year += 2000
    else:
        year = today.year

    if first > 12 and second <= 12:
        day, month = first, second
    elif second > 12 and first <= 12:
        month, day = first, second
    elif first <= 12 and second <= 12:
        return ParsedDate(
            needs_clarification=True,
            error=(
                f'"{raw}" could be {first}/{second} or {second}/{first} — '
                f"I can't tell which is the day. "
                f"Write it as 2026-09-12, or \"12 sep\"."
            ),
        )
    else:
        return ParsedDate(error=f'"{raw}" is not a real date.')

    try:
        parsed = date(year, month, day)
    except ValueError:
        return ParsedDate(error=f'"{raw}" is not a real date.')

    if not year_text and parsed < today:
        parsed = date(year + 1, month, day)
    return _check_future(parsed, today)


def _check_future(value: date, today: date) -> ParsedDate:
    """Reject dates in the past — you cannot buy a ticket for last Tuesday."""
    if value < today:
        return ParsedDate(
            error=f"{value.isoformat()} is in the past. Give me a future date."
        )
    # Airlines do not sell much beyond a year out, so a date further away is
    # almost certainly a typo in the year.
    if value > today + timedelta(days=400):
        return ParsedDate(
            error=(
                f"{value.isoformat()} is more than a year away — "
                f"airlines don't sell that far ahead. Did you mean a nearer date?"
            )
        )
    return ParsedDate(value=value.isoformat())


# --- other answers ----------------------------------------------------------


def parse_yes_no(text: str) -> bool | None:
    """True, False, or None when the answer is neither."""
    word = (text or "").strip().lower().strip(".!")
    if word in AFFIRMATIVE:
        return True
    if word in NEGATIVE:
        return False
    return None


def parse_trip_type(text: str) -> str | None:
    """Read "round trip", "one way" or "multi-city" from free text."""
    raw = (text or "").strip().lower().replace("-", " ")
    raw = re.sub(r"\s+", " ", raw)

    if raw in ("1", "r", "rt") or "round" in raw or "return" in raw:
        return "round_trip"
    if raw in ("2", "o", "ow") or "one way" in raw or raw == "oneway" or "single" in raw:
        return "one_way"
    if raw in ("3", "m", "mc") or "multi" in raw:
        return "multi_city"
    return None


@dataclass(frozen=True)
class Passengers:
    adults: int = 1
    children: int = 0
    infants_in_seat: int = 0
    infants_on_lap: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def parse_passengers(text: str) -> Passengers:
    """Read "2", "2 adults 1 child", "just me", "me and my wife"."""
    raw = (text or "").strip().lower()
    if not raw:
        return Passengers()

    if raw in ("just me", "me", "myself", "alone", "solo", "1 adult"):
        return Passengers(adults=1)

    # A bare number is the most common answer: how many people, all adults.
    if re.fullmatch(r"\d+", raw):
        count = int(raw)
        if count < 1:
            return Passengers(error="There has to be at least one traveller.")
        if count > 9:
            return Passengers(error="Google Flights allows at most 9 travellers.")
        return Passengers(adults=count)

    adults = _count_for(raw, r"adults?|grown ?ups?|people|passengers?")
    children = _count_for(raw, r"child(?:ren)?|kids?")
    infants = _count_for(raw, r"infants?|babies|baby|lap infants?")

    if adults is None and children is None and infants is None:
        return Passengers(
            error=(
                'I could not read that as a number of travellers. '
                'Try "2", or "2 adults 1 child".'
            )
        )

    result = Passengers(
        adults=adults if adults is not None else 1,
        children=children or 0,
        infants_on_lap=infants or 0,
    )
    if result.adults + result.children > 9:
        return Passengers(error="Google Flights allows at most 9 seated travellers.")
    if result.infants_on_lap > result.adults:
        return Passengers(
            error="Every lap infant needs an adult to hold them — add more adults."
        )
    return result


def _count_for(text: str, noun_pattern: str) -> int | None:
    """Find "2 adults" / "two kids" and return the number."""
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    }
    match = re.search(rf"(\d+|{'|'.join(words)})\s*(?:{noun_pattern})", text)
    if not match:
        # "an adult and a child" -- a bare noun means one.
        if re.search(rf"\b(?:a|an|one)\s+(?:{noun_pattern})", text):
            return 1
        return None
    token = match.group(1)
    return int(token) if token.isdigit() else words[token]
