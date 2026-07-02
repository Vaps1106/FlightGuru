"""Logging setup — console (clean) + rotating file (timestamped).

Console shows just the message (so output reads like before); the rotating file
at logs/flightguru.log keeps a timestamped history for troubleshooting.

Every record is passed through a redaction filter first, so secrets can never
leak into the console (GitHub Actions logs) or the file — even from code that
logs a raw ``requests`` exception whose message contains the request URL.
"""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "flightguru.log")

# Patterns for secrets that can appear in a requests exception / URL string.
_REDACTIONS = (
    # Telegram bot token in the URL path: /bot<id>:<secret>/sendMessage
    (re.compile(r"/bot\d+:[A-Za-z0-9_-]+"), "/bot<redacted>"),
    # SerpApi key (or any) as a query param: ...?api_key=<secret>&...
    (re.compile(r"(api_key=)[^&\s]+", re.IGNORECASE), r"\1<redacted>"),
    # Bearer tokens (e.g. Duffel) if a header ever ends up in a message.
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._-]+", re.IGNORECASE), r"\1<redacted>"),
)


def redact(message: str) -> str:
    """Strip known secret shapes (tokens, api keys) out of a log message."""
    for pattern, replacement in _REDACTIONS:
        message = pattern.sub(replacement, message)
    return message


class _RedactingFilter(logging.Filter):
    """Scrub secrets from every record before any handler formats it.

    We flatten ``msg`` + ``args`` into the final text, then redact, so a secret
    passed as a ``%s`` argument is caught too.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


_configured = False


def get_logger(name: str = "flightguru") -> logging.Logger:
    global _configured
    logger = logging.getLogger(name)
    if not _configured:
        logger.setLevel(logging.INFO)
        os.makedirs(LOG_DIR, exist_ok=True)

        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(message)s"))

        logger.addFilter(_RedactingFilter())
        logger.addHandler(file_handler)
        logger.addHandler(console)
        logger.propagate = False
        _configured = True
    return logger
