"""Small progress and inactivity reporting helpers."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Mapping

from .storage import read_json

def _parse_utc(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(dt.timezone.utc)


def active_progress(run_root: Path, state: Mapping[str, Any], *,
                    now: dt.datetime | None = None) -> dict[str, Any] | None:
    current_time = now or dt.datetime.now(dt.timezone.utc)
    for cell_id, cell in state.get("cells", {}).items():
        if cell.get("status") not in {"checked", "running"}:
            continue
        attempts = cell.get("attempts", [])
        attempt = attempts[-1] if attempts else {}
        active_value = attempt.get("active_command")
        if not active_value:
            return {"cell": cell_id, "phase": cell.get("status")}
        command_root = run_root / str(active_value)
        started_path = command_root / "started.json"
        started = read_json(started_path) if started_path.is_file() else {}
        started_time = _parse_utc(started.get("started_utc"))
        activity_times = [started_time] if started_time else []
        for name in ("stdout.log", "stderr.log"):
            path = command_root / name
            if path.is_file():
                activity_times.append(dt.datetime.fromtimestamp(
                    path.stat().st_mtime, tz=dt.timezone.utc))
        latest = max(activity_times) if activity_times else None
        return {
            "cell": cell_id,
            "phase": attempt.get("status", cell.get("status")),
            "command": started.get("label"),
            "elapsed_seconds": None if started_time is None else max(
                0.0, (current_time - started_time).total_seconds()),
            "inactivity_seconds": None if latest is None else max(
                0.0, (current_time - latest).total_seconds()),
        }
    return None


__all__ = ["active_progress"]
