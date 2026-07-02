"""Start/stop control — pause monitoring or set an active date window, so the
owner can control API usage without touching code or deleting the schedule.

Reads ``control.json`` at the repo root:

    {
      "enabled": true,             # master switch; false = paused immediately
      "active_from": "2026-06-10", # optional; do not run before this date (UTC)
      "active_until": "2026-08-14" # optional; stop running after this date (UTC)
    }

When monitoring is not active, main.py exits early and makes NO API calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

CONTROL_PATH = "control.json"


@dataclass(frozen=True)
class Control:
    enabled: bool = True
    active_from: str = ""
    active_until: str = ""
    error: str = ""  # non-empty when control.json could not be read/parsed


def load_control(path: str = CONTROL_PATH) -> Control:
    """Load control.json; if it is missing, default to 'always enabled'.

    ``control.json`` is meant to be hand-edited by the owner, so a typo is
    likely. Rather than crash the run on malformed JSON, we fail closed: return a
    Control whose ``error`` is set, which ``check_active`` reports as "not
    active" so no API calls are made until the file is fixed.
    """
    p = Path(path)
    if not p.exists():
        return Control()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return Control(enabled=False, error=f"control.json could not be read ({exc})")
    if not isinstance(data, dict):
        return Control(enabled=False, error="control.json must be a JSON object")
    return Control(
        enabled=bool(data.get("enabled", True)),
        active_from=str(data.get("active_from", "")).strip(),
        active_until=str(data.get("active_until", "")).strip(),
    )


def check_active(control: Control, today: date | None = None) -> tuple[bool, str]:
    """Return (is_active, human-readable reason)."""
    if control.error:
        return False, control.error

    if today is None:
        today = datetime.now(timezone.utc).date()

    if not control.enabled:
        return False, "monitoring is paused (enabled=false in control.json)"

    # A hand-typed date can be malformed (e.g. "2026-8-1"); fail closed with a
    # clear reason instead of raising an uncaught ValueError.
    try:
        if control.active_from:
            start = date.fromisoformat(control.active_from)
            if today < start:
                return False, f"before active window (starts {control.active_from})"

        if control.active_until:
            end = date.fromisoformat(control.active_until)
            if today > end:
                return False, f"after active window (ended {control.active_until})"
    except ValueError:
        return False, (
            "control.json has an invalid date "
            f"(active_from={control.active_from!r}, active_until={control.active_until!r}); "
            "use YYYY-MM-DD"
        )

    return True, "active"
