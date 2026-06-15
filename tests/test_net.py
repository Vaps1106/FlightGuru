"""Tests for the HTTP retry/backoff helper (no real network or sleeping)."""

from __future__ import annotations

import pytest
import requests

from flightguru import net


class FakeResp:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self.reason = "reason"
        self._payload = payload if payload is not None else {"ok": True}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _no_sleep(monkeypatch):
    monkeypatch.setattr(net.time, "sleep", lambda s: None)


def _patch_request(monkeypatch, fn):
    """Intercept the shared Session's request method."""
    monkeypatch.setattr(net._session, "request", fn)


def test_succeeds_after_transient_errors(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("boom")
        return FakeResp(200, {"ok": True, "data": 1})

    _patch_request(monkeypatch, fake_request)
    data = net.request_json("GET", "http://x", retries=3, backoff=1.0)
    assert data["ok"] and calls["n"] == 3


def test_retries_on_429(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        return FakeResp(429) if calls["n"] == 1 else FakeResp(200, {"ok": True})

    _patch_request(monkeypatch, fake_request)
    data = net.request_json("GET", "http://x", retries=3)
    assert data["ok"] and calls["n"] == 2


def test_honors_retry_after_on_429(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(net.time, "sleep", lambda s: waits.append(s))
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp(429, headers={"Retry-After": "12"})
        return FakeResp(200, {"ok": True})

    _patch_request(monkeypatch, fake_request)
    data = net.request_json("GET", "http://x", retries=3, backoff=1.0)
    # We waited at least the server-requested 12s, not the 1.0s default backoff.
    assert data["ok"] and waits and waits[0] >= 12.0


def test_raises_after_exhausting_retries(monkeypatch):
    _no_sleep(monkeypatch)

    def fake_request(method, url, **kwargs):
        raise requests.ConnectionError("down")

    _patch_request(monkeypatch, fake_request)
    with pytest.raises(requests.RequestException):
        net.request_json("GET", "http://x", retries=2, backoff=1.0)
