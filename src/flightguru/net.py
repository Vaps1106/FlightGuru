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
RETRY_AFTER_CAP = 60.0  # never wait longer than this on a Retry-After header


def _retry_after_seconds(exc: Exception) -> float | None:
    """Seconds to wait per a response's ``Retry-After`` header, if present.

    Providers (SerpApi, Telegram, Duffel) return this on a 429/503 to say exactly
    how long to back off. Honor the numeric-seconds form, capped so one run can't
    hang; ignore the HTTP-date form and fall back to exponential backoff.
    """
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) or {}
    raw = headers.get("Retry-After")
    if not raw:
        return None
    try:
        return min(float(raw), RETRY_AFTER_CAP)
    except (TypeError, ValueError):
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
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in RETRYABLE_STATUS:
                raise requests.HTTPError(f"{resp.status_code} {resp.reason}", response=resp)
            resp.raise_for_status()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                wait = _retry_after_seconds(exc) or backoff ** attempt
                log.warning(
                    f"request failed ({exc}); retry {attempt}/{retries - 1} in {wait:.1f}s"
                )
                time.sleep(wait)
            continue
        # HTTP succeeded. A malformed body is a hard failure — retrying an
        # identical request won't turn it into valid JSON, so fail immediately.
        # (No URL in the message, so no secret can leak here.)
        try:
            return resp.json()
        except ValueError as exc:
            raise requests.RequestException("response body was not valid JSON") from exc
    assert last_exc is not None
    raise last_exc
