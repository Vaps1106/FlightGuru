"""Secrets must never reach the logs (console = GitHub Actions logs, or the file).

Guards the C1 fix: the redaction helper + the logging filter strip Telegram bot
tokens and SerpApi keys out of any message, including a raw ``requests``
exception whose text contains the request URL.
"""

from __future__ import annotations

import logging

from flightguru.log import _RedactingFilter, redact


def test_redacts_telegram_bot_token():
    msg = (
        "request failed (HTTPSConnectionPool(host='api.telegram.org', port=443): "
        "Max retries exceeded with url: /bot123456:AAExampleBotTokenSECRET/sendMessage)"
    )
    out = redact(msg)
    assert "AAExampleBotTokenSECRET" not in out
    assert "/bot<redacted>" in out


def test_redacts_serpapi_key_in_url():
    msg = "401 Client Error for url: https://serpapi.com/search?engine=google_flights&api_key=SERPKEY_SECRET_abc123"
    out = redact(msg)
    assert "SERPKEY_SECRET_abc123" not in out
    assert "api_key=<redacted>" in out


def test_redacts_bearer_token():
    out = redact("Authorization: Bearer duffel_live_SECRETtoken123")
    assert "duffel_live_SECRETtoken123" not in out
    assert "Bearer <redacted>" in out


def test_leaves_ordinary_messages_untouched():
    msg = "Searching BOM->JFK 2026-07-20..2026-08-14 via duffel, serpapi"
    assert redact(msg) == msg


def test_filter_scrubs_secret_passed_as_arg():
    # A secret sneaked in via %-arg must still be caught (filter flattens args).
    record = logging.LogRecord(
        name="flightguru", level=logging.WARNING, pathname=__file__, lineno=1,
        msg="Telegram: failed - %s",
        args=("/bot999:HIDDENtoken/sendMessage timed out",),
        exc_info=None,
    )
    assert _RedactingFilter().filter(record) is True
    assert "HIDDENtoken" not in record.getMessage()
    assert "/bot<redacted>" in record.getMessage()
