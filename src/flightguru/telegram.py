"""Telegram: send messages, and read the ones sent back.

v2's ``notify.py`` only ever pushed. A chat bot has to listen too, which is done
here with long polling — ``getUpdates`` held open for up to 50 seconds. Polling
rather than webhooks on purpose: no public URL, no TLS certificate, and nothing
to re-register when the service restarts.

Messages are plain text with no parse mode. v1 lost alerts when an "&" in an
airline name broke Telegram's HTML parsing, and no amount of bold text is worth
dropping a message over.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import net

TELEGRAM_API = "https://api.telegram.org"

# Telegram rejects anything longer than this. Long replies are split rather
# than truncated -- losing the cheaper-airport suggestion off the end of a
# message would defeat the point of the whole feature.
MAX_MESSAGE_CHARS = 4096

# Attempts per poll. More than the usual three because a dropped poll means the
# bot is deaf until the next one, which is far more visible to the person typing
# than a slow reply would be.
POLL_RETRIES = 4

# Attempts per outgoing message. A reply that fails to send looks exactly like a
# bot that found nothing -- the person is left staring at a chat that never
# answers, with no way to tell the difference. On a link that resets a quarter of
# connections, three attempts was not enough and searches appeared to fail when
# they had actually succeeded.
SEND_RETRIES = 6


@dataclass(frozen=True)
class Update:
    """One incoming message, reduced to what the bot cares about."""

    update_id: int
    chat_id: str
    text: str
    from_username: str = ""

    @property
    def is_command(self) -> bool:
        return self.text.startswith("/")

    @property
    def command(self) -> str:
        """The command word without its slash, lowercased. Empty if not one.

        Handles the "/start@MyBot" form Telegram uses in group chats.
        """
        if not self.is_command:
            return ""
        word = self.text.split()[0][1:]
        return word.split("@")[0].lower()

    @property
    def argument(self) -> str:
        """Anything after the command word."""
        parts = self.text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""


class TelegramClient:
    """Thin wrapper over the Telegram bot API."""

    def __init__(self, token: str, timeout: int = 30):
        self.token = token
        self.timeout = timeout
        # Telegram redelivers an update until it is acknowledged by asking for a
        # higher offset. Tracking it here is what stops the bot answering the
        # same message forever after a restart.
        self._offset: int | None = None

    def _url(self, method: str) -> str:
        return f"{TELEGRAM_API}/bot{self.token}/{method}"

    def get_me(self) -> dict:
        """Identify the bot. Used as a startup check that the token works."""
        data = net.request_json("GET", self._url("getMe"), retries=POLL_RETRIES)
        return data.get("result") or {}

    def send(self, chat_id: str | int, text: str) -> bool:
        """Send a message, splitting it if Telegram would reject the length."""
        ok = True
        for chunk in split_message(text):
            data = net.request_json(
                "POST",
                self._url("sendMessage"),
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
                timeout=self.timeout,
                retries=SEND_RETRIES,
            )
            ok = ok and bool(data.get("ok"))
        return ok

    def send_typing(self, chat_id: str | int) -> None:
        """Show "typing..." while a search runs, so the bot doesn't look dead.

        Best-effort: a failure here must never stop the actual reply.
        """
        try:
            net.request_json(
                "POST",
                self._url("sendChatAction"),
                json={"chat_id": chat_id, "action": "typing"},
                timeout=10,
                retries=1,
            )
        except Exception:  # noqa: BLE001 - cosmetic only
            pass

    def poll(self, wait_seconds: int = 30) -> list[Update]:
        """Wait for incoming messages and return them.

        Blocks up to ``wait_seconds`` on Telegram's side, so an idle bot makes
        roughly two requests a minute rather than hammering the API.
        """
        params: dict[str, str | int] = {
            "timeout": wait_seconds,
            # Only message updates; we do not use inline queries or edits.
            "allowed_updates": '["message"]',
        }
        if self._offset is not None:
            params["offset"] = self._offset

        data = net.request_json(
            "GET",
            self._url("getUpdates"),
            params=params,
            # Must outlast Telegram's own hold or the connection dies first.
            timeout=wait_seconds + 15,
            # Some networks reset connections to api.telegram.org intermittently
            # -- measured around a quarter of attempts on one home ISP, while
            # other hosts were unaffected. Those resets come back in well under a
            # second, so retrying costs almost nothing and turns a flaky link
            # into a working one. A single attempt here made the bot look broken.
            retries=POLL_RETRIES,
        )

        updates: list[Update] = []
        for raw in data.get("result") or []:
            update_id = raw.get("update_id")
            if update_id is not None:
                # Acknowledge every update we have seen, including ones we
                # cannot parse, or a single malformed message would wedge the
                # bot in a loop redelivering it forever.
                self._offset = max(self._offset or 0, update_id + 1)
            parsed = parse_update(raw)
            if parsed is not None:
                updates.append(parsed)
        return updates

    def drain_pending(self) -> int:
        """Discard messages that arrived while the bot was down.

        Answering a day-old "find me a flight" on restart would be confusing,
        and each stale request costs a real search. Returns how many were
        dropped.
        """
        data = net.request_json(
            "GET",
            self._url("getUpdates"),
            params={"timeout": 0},
            retries=POLL_RETRIES,
        )
        results = data.get("result") or []
        if results:
            self._offset = max(r.get("update_id", 0) for r in results) + 1
            # Confirm the offset so Telegram stops redelivering them.
            net.request_json(
                "GET",
                self._url("getUpdates"),
                params={"timeout": 0, "offset": self._offset},
                retries=POLL_RETRIES,
            )
        return len(results)


def parse_update(raw: dict) -> Update | None:
    """Pull the fields we need out of a raw update, or None if unusable."""
    message = raw.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    # No text means a photo, sticker or join event -- nothing to act on.
    if chat_id is None or not text:
        return None

    return Update(
        update_id=raw.get("update_id", 0),
        chat_id=str(chat_id),
        text=text,
        from_username=((message.get("from") or {}).get("username") or ""),
    )


def split_message(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Break a long message at line boundaries so nothing is lost.

    Splits between lines where possible, since cutting mid-sentence in the
    middle of a fare quote is worse than sending two messages.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        # A single line longer than the limit has to be cut somewhere.
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]

        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks
