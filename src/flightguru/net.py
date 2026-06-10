"""HTTP with retry + backoff — shared by all providers and Telegram.

Retries transient failures (network errors and HTTP 429/5xx) with exponential
backoff. 429-aware backoff is our rate-limit handling; combined with the SerpApi
date cap and the date step, it keeps us within provider quotas.
"""

from __future__ import annotations

import time

import requests

from .log import get_logger

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def request_json(
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.5,
    timeout: int = 30,
    **kwargs,
) -> dict:
    """Make a request and return parsed JSON, retrying transient failures.

    Raises the last requests exception if all attempts fail.
    """
    log = get_logger()
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in RETRYABLE_STATUS:
                raise requests.HTTPError(f"{resp.status_code} {resp.reason}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                wait = backoff ** attempt
                log.warning(
                    f"request failed ({exc}); retry {attempt}/{retries - 1} in {wait:.1f}s"
                )
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc
