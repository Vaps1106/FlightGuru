"""Tests for the Telegram layer: update parsing, message splitting, offsets."""

from __future__ import annotations

from flightguru.telegram import (
    MAX_MESSAGE_CHARS,
    TelegramClient,
    Update,
    parse_update,
    split_message,
)


def raw_update(update_id=1, chat_id=42, text="hello", username="me"):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": chat_id},
            "text": text,
            "from": {"username": username},
        },
    }


# --- parsing incoming messages ----------------------------------------------


def test_parses_a_normal_message():
    update = parse_update(raw_update())
    assert update.chat_id == "42"
    assert update.text == "hello"
    assert update.from_username == "me"


def test_ignores_updates_with_no_text():
    """A photo or a sticker has nothing to act on."""
    assert parse_update({"update_id": 1, "message": {"chat": {"id": 42}}}) is None


def test_ignores_empty_updates():
    assert parse_update({}) is None


def test_ignores_whitespace_only_messages():
    assert parse_update(raw_update(text="   ")) is None


def test_command_detection():
    assert parse_update(raw_update(text="/help")).command == "help"
    assert parse_update(raw_update(text="/help extra")).command == "help"
    assert parse_update(raw_update(text="hello")).command == ""


def test_command_strips_the_bot_mention():
    """Telegram sends "/start@FlightGuruBot" in groups."""
    assert parse_update(raw_update(text="/start@FlightGuruBot")).command == "start"


def test_command_argument():
    assert parse_update(raw_update(text="/search JFK LAX")).argument == "JFK LAX"
    assert parse_update(raw_update(text="/search")).argument == ""


# --- splitting long messages ------------------------------------------------


def test_short_message_is_not_split():
    assert split_message("hello") == ["hello"]


def test_long_message_is_split_at_line_boundaries():
    text = "\n".join(["a line of text"] * 500)
    chunks = split_message(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= MAX_MESSAGE_CHARS for chunk in chunks)
    # Nothing may be silently dropped: losing the cheaper-airport suggestion off
    # the end would defeat the feature.
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_a_single_overlong_line_is_still_handled():
    chunks = split_message("x" * (MAX_MESSAGE_CHARS * 2 + 50))
    assert all(len(chunk) <= MAX_MESSAGE_CHARS for chunk in chunks)
    assert sum(len(c) for c in chunks) == MAX_MESSAGE_CHARS * 2 + 50


def test_message_exactly_at_the_limit_is_not_split():
    assert len(split_message("x" * MAX_MESSAGE_CHARS)) == 1


# --- update offsets ---------------------------------------------------------


class FakeNet:
    """Stands in for the network so polling can be tested without Telegram."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0) if self.responses else {"result": []}


def test_poll_advances_the_offset_so_messages_are_not_repeated(monkeypatch):
    fake = FakeNet({"result": [raw_update(update_id=7)]})
    monkeypatch.setattr("flightguru.telegram.net", fake)

    client = TelegramClient("token")
    client.poll(1)
    assert client._offset == 8

    client.poll(1)
    # The second call must ask for everything after what it already saw.
    assert fake.calls[-1][2]["params"]["offset"] == 8


def test_unparseable_updates_are_still_acknowledged(monkeypatch):
    """Otherwise one malformed message wedges the bot redelivering it forever."""
    fake = FakeNet({"result": [{"update_id": 9, "message": {}}]})
    monkeypatch.setattr("flightguru.telegram.net", fake)

    client = TelegramClient("token")
    assert client.poll(1) == []
    assert client._offset == 10


def test_drain_pending_skips_messages_received_while_offline(monkeypatch):
    fake = FakeNet(
        {"result": [raw_update(update_id=3), raw_update(update_id=4)]},
        {"result": []},
    )
    monkeypatch.setattr("flightguru.telegram.net", fake)

    client = TelegramClient("token")
    assert client.drain_pending() == 2
    assert client._offset == 5


def test_drain_pending_with_nothing_waiting(monkeypatch):
    monkeypatch.setattr("flightguru.telegram.net", FakeNet({"result": []}))
    client = TelegramClient("token")
    assert client.drain_pending() == 0


def test_send_splits_long_messages(monkeypatch):
    fake = FakeNet(*[{"ok": True}] * 10)
    monkeypatch.setattr("flightguru.telegram.net", fake)

    text = "\n".join(["line"] * 2000)
    client = TelegramClient("token")
    client.send(42, text)

    sends = [c for c in fake.calls if c[1].endswith("sendMessage")]
    assert len(sends) == len(split_message(text)) > 1
    # Every part must be within Telegram's limit, or the send is rejected.
    for _, _, kwargs in sends:
        assert len(kwargs["json"]["text"]) <= MAX_MESSAGE_CHARS


def test_typing_failure_does_not_raise(monkeypatch):
    class Boom:
        def request_json(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr("flightguru.telegram.net", Boom())
    # Cosmetic only -- must never stop a real reply going out.
    TelegramClient("token").send_typing(42)
