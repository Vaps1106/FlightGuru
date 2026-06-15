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

# One shared Session so repeated calls to the same host (e.g. the many Duffel
# date searches in one run) reuse the underlying TCP/TLS connection instead of
# doing a fresh handshake every time. Safe to share across the search threads
# because we never mutate session state (no session.headers/cookies) — every
# call passes its own headers/params, and urllib3's connection pool underneath
# is itself thread-safe.
_session = requests.Session()


def _retry_after_seconds(exc: Exception) -> float | None:
    """If a 429 response carries a numeric Retry-After header, return it."""
    resp = getattr(exc, "response", None)
    if resp is None or getattr(resp, "status_code", None) != 429:
        return None
    value = getattr(resp, "headers", {}).get("Retry-After")
    if value and str(value).strip().isdigit():
        return float(value)
    return None


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
            resp = _session.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in RETRYABLE_STATUS:
                raise requests.HTTPError(f"{resp.status_code} {resp.reason}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                # Default to exponential backoff, but honor a server-provided
                # Retry-After on 429 — wait exactly as long as we're asked.
                wait = max(backoff ** attempt, _retry_after_seconds(exc) or 0.0)
                log.warning(
                    f"request failed ({exc}); "
                    f"retry {attempt} of {retries - 1} in {wait:.1f}s"
                )
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc
