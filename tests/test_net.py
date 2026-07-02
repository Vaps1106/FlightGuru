"""Tests for the HTTP retry/backoff helper (no real network or sleeping)."""

from __future__ import annotations

import pytest
import requests

from flightguru import net


class FakeResp:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self.reason = "reason"
        self.headers = headers or {}
        self._payload = payload if payload is not None else {"ok": True}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _no_sleep(monkeypatch):
    monkeypatch.setattr(net.time, "sleep", lambda s: None)


def test_succeeds_after_transient_errors(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("boom")
        return FakeResp(200, {"ok": True, "data": 1})

    monkeypatch.setattr(net.requests, "request", fake_request)
    data = net.request_json("GET", "http://x", retries=3, backoff=1.0)
    assert data["ok"] and calls["n"] == 3


def test_retries_on_429(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        return FakeResp(429) if calls["n"] == 1 else FakeResp(200, {"ok": True})

    monkeypatch.setattr(net.requests, "request", fake_request)
    data = net.request_json("GET", "http://x", retries=3)
    assert data["ok"] and calls["n"] == 2


def test_honors_retry_after_header(monkeypatch):
    slept = []
    monkeypatch.setattr(net.time, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp(429, headers={"Retry-After": "7"})
        return FakeResp(200, {"ok": True})

    monkeypatch.setattr(net.requests, "request", fake_request)
    data = net.request_json("GET", "http://x", retries=3, backoff=1.5)
    assert data["ok"] and slept == [7.0]  # waited exactly what the header said


def test_retry_after_is_capped(monkeypatch):
    slept = []
    monkeypatch.setattr(net.time, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp(503, headers={"Retry-After": "9999"})
        return FakeResp(200, {"ok": True})

    monkeypatch.setattr(net.requests, "request", fake_request)
    net.request_json("GET", "http://x", retries=3)
    assert slept == [net.RETRY_AFTER_CAP]  # capped, won't hang the run


def test_non_json_body_is_not_retried(monkeypatch):
    _no_sleep(monkeypatch)
    calls = {"n": 0}

    class BadJson(FakeResp):
        def json(self):
            raise ValueError("Expecting value")

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        return BadJson(200)

    monkeypatch.setattr(net.requests, "request", fake_request)
    with pytest.raises(requests.RequestException):
        net.request_json("GET", "http://x", retries=3)
    assert calls["n"] == 1  # a malformed 200 body fails fast, no wasted retries


def test_raises_after_exhausting_retries(monkeypatch):
    _no_sleep(monkeypatch)

    def fake_request(method, url, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(net.requests, "request", fake_request)
    with pytest.raises(requests.RequestException):
        net.request_json("GET", "http://x", retries=2, backoff=1.0)
