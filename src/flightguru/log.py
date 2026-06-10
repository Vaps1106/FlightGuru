"""Logging setup — console (clean) + rotating file (timestamped).

Console shows just the message (so output reads like before); the rotating file
at logs/flightguru.log keeps a timestamped history for troubleshooting.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "flightguru.log")

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

        logger.addHandler(file_handler)
        logger.addHandler(console)
        logger.propagate = False
        _configured = True
    return logger
