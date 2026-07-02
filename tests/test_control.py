"""Tests for the start/stop usage control gate."""

from __future__ import annotations

from datetime import date

from flightguru.control import Control, check_active, load_control


def test_enabled_no_window_is_active():
    active, _ = check_active(Control(enabled=True), today=date(2026, 7, 1))
    assert active


def test_paused_is_inactive():
    active, reason = check_active(Control(enabled=False), today=date(2026, 7, 1))
    assert not active
    assert "paused" in reason


def test_before_window_is_inactive():
    c = Control(enabled=True, active_from="2026-07-20")
    active, reason = check_active(c, today=date(2026, 7, 1))
    assert not active
    assert "before" in reason


def test_after_window_is_inactive():
    c = Control(enabled=True, active_until="2026-08-14")
    active, reason = check_active(c, today=date(2026, 8, 20))
    assert not active
    assert "after" in reason


def test_inside_window_is_active():
    c = Control(enabled=True, active_from="2026-06-10", active_until="2026-08-14")
    active, _ = check_active(c, today=date(2026, 7, 15))
    assert active


def test_boundaries_are_inclusive():
    c = Control(enabled=True, active_from="2026-06-10", active_until="2026-08-14")
    assert check_active(c, today=date(2026, 6, 10))[0]
    assert check_active(c, today=date(2026, 8, 14))[0]


# --- malformed control.json must fail closed, never crash (M1) ---------------

def test_malformed_json_fails_closed(tmp_path):
    f = tmp_path / "control.json"
    f.write_text('{ "enabled": true, }', encoding="utf-8")  # trailing comma = invalid
    c = load_control(str(f))
    active, reason = check_active(c, today=date(2026, 7, 1))
    assert not active
    assert "control.json" in reason


def test_non_object_json_fails_closed(tmp_path):
    f = tmp_path / "control.json"
    f.write_text("[1, 2, 3]", encoding="utf-8")  # valid JSON, wrong shape
    c = load_control(str(f))
    active, reason = check_active(c, today=date(2026, 7, 1))
    assert not active
    assert "JSON object" in reason


def test_bad_date_fails_closed():
    c = Control(enabled=True, active_from="2026-8-1")  # not zero-padded ISO
    active, reason = check_active(c, today=date(2026, 7, 1))
    assert not active
    assert "invalid date" in reason


def test_missing_file_defaults_to_active(tmp_path):
    c = load_control(str(tmp_path / "does_not_exist.json"))
    active, _ = check_active(c, today=date(2026, 7, 1))
    assert active
