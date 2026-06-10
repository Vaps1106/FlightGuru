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


def load_control(path: str = CONTROL_PATH) -> Control:
    """Load control.json; if it is missing, default to 'always enabled'."""
    p = Path(path)
    if not p.exists():
        return Control()
    data = json.loads(p.read_text(encoding="utf-8"))
    return Control(
        enabled=bool(data.get("enabled", True)),
        active_from=str(data.get("active_from", "")).strip(),
        active_until=str(data.get("active_until", "")).strip(),
    )


def check_active(control: Control, today: date | None = None) -> tuple[bool, str]:
    """Return (is_active, human-readable reason)."""
    if today is None:
        today = datetime.now(timezone.utc).date()

    if not control.enabled:
        return False, "monitoring is paused (enabled=false in control.json)"

    if control.active_from:
        start = date.fromisoformat(control.active_from)
        if today < start:
            return False, f"before active window (starts {control.active_from})"

    if control.active_until:
        end = date.fromisoformat(control.active_until)
        if today > end:
            return False, f"after active window (ended {control.active_until})"

    return True, "active"
