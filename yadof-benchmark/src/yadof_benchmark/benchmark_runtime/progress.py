"""Read-only progress and bounded timing estimates for one workspace."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Mapping

from .storage import read_json


def _parse_utc(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: dt.datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    output.append(item)
    except OSError:
        return []
    return output


def _latest_progress(command_root: Path) -> dict[str, Any] | None:
    events = [
        item
        for item in _jsonl(command_root / "progress.jsonl")
        if item.get("event") == "cell-progress"
    ]
    return events[-1] if events else None


def _cell_progress(
    root: Path,
    cell_id: str,
    cell: Mapping[str, Any],
    *,
    now: dt.datetime,
) -> dict[str, Any]:
    created = _parse_utc(cell.get("created_utc"))
    active_value = cell.get("active_command")
    if not active_value:
        return {
            "cell": cell_id,
            "display_label": cell.get("display_label", cell_id),
            "phase": cell.get("status"),
            "cell_elapsed_seconds": (
                None if created is None else max(0.0, (now - created).total_seconds())
            ),
        }
    command_root = root / str(active_value)
    started_path = command_root / "started.json"
    started = read_json(started_path) if started_path.is_file() else {}
    started_time = _parse_utc(started.get("started_utc"))
    latest_progress = _latest_progress(command_root)
    activity_times = [started_time] if started_time else []
    progress_time = _parse_utc(
        None if latest_progress is None else latest_progress.get("utc")
    )
    if progress_time is not None:
        activity_times.append(progress_time)
    for name in ("stdout.log", "stderr.log"):
        path = command_root / name
        if path.is_file():
            activity_times.append(
                dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
            )
    latest = max(activity_times) if activity_times else None
    output = {
        "cell": cell_id,
        "display_label": cell.get("display_label", cell_id),
        "phase": (
            latest_progress.get("phase")
            if latest_progress is not None
            else cell.get("status")
        ),
        "command": started.get("label"),
        "command_elapsed_seconds": (
            None
            if started_time is None
            else max(0.0, (now - started_time).total_seconds())
        ),
        "cell_elapsed_seconds": (
            None if created is None else max(0.0, (now - created).total_seconds())
        ),
        "last_activity_utc": _iso(latest),
        "inactivity_seconds": (
            None if latest is None else max(0.0, (now - latest).total_seconds())
        ),
        "logs": {
            name.removesuffix(".log"): str(command_root / name)
            for name in ("stdout.log", "stderr.log")
            if (command_root / name).is_file()
        },
    }
    if latest_progress is not None:
        for source, target in (
            ("generation_number", "generation"),
            ("generations", "generations"),
            ("evaluations", "evaluations"),
            ("planned_evaluations", "planned_evaluations"),
            ("successful", "successful"),
            ("errors", "errors"),
        ):
            output[target] = latest_progress.get(source)
    return output


def active_progresses(
    root: Path,
    state: Mapping[str, Any],
    *,
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    current = now or dt.datetime.now(dt.timezone.utc)
    return [
        _cell_progress(root, str(cell_id), cell, now=current)
        for cell_id, cell in state.get("cells", {}).items()
        # A successfully executed cell remains active while collection commands
        # (for example ``view-cost`` and baseline postprocessing) are running.
        if cell.get("status") in {"checked", "running", "succeeded"}
    ]


def active_progress(
    root: Path,
    state: Mapping[str, Any],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any] | None:
    current = now or dt.datetime.now(dt.timezone.utc)
    active = active_progresses(root, state, now=current)
    if active:
        return active[0]
    for item_id, item in state.get("postprocessors", {}).items():
        if item.get("status") == "running":
            started = _parse_utc(item.get("created_utc"))
            return {
                "postprocessor": item_id,
                "phase": "running",
                "elapsed_seconds": (
                    None
                    if started is None
                    else max(0.0, (current - started).total_seconds())
                ),
                "last_activity_utc": state.get("updated_utc"),
            }
    return None


def _generation_trend(
    command_root: Path,
    *,
    generations: int,
    now: dt.datetime,
) -> dict[str, Any] | None:
    started_path = command_root / "started.json"
    if not started_path.is_file():
        return None
    started = _parse_utc(read_json(started_path).get("started_utc"))
    if started is None:
        return None
    events = [
        item
        for item in _jsonl(command_root / "progress.jsonl")
        if item.get("event") == "cell-progress"
        and isinstance(item.get("generation"), int)
        and _parse_utc(item.get("utc")) is not None
    ]
    completed: dict[int, dt.datetime] = {}
    for item in events:
        if int(item.get("remaining", 1)) <= 0:
            ended = _parse_utc(item["utc"])
            if ended is not None:
                completed[int(item["generation"])] = ended
    ordered = sorted(completed)
    if len(ordered) < 3 or not events:
        return None
    durations: list[tuple[int, float]] = []
    previous = started
    for generation in ordered:
        ended = completed[generation]
        durations.append(
            (generation, max(0.001, (ended - previous).total_seconds()))
        )
        previous = ended
    xs = [float(item[0]) for item in durations]
    ys = [float(item[1]) for item in durations]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    slope = (
        0.0
        if denominator <= 0
        else max(
            0.0,
            sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
            / denominator,
        )
    )
    intercept = max(0.001, mean_y - slope * mean_x)
    latest = events[-1]
    current_generation = int(latest["generation"])

    def predicted(index: int) -> float:
        return max(0.001, intercept + slope * index)

    if current_generation in completed and int(latest.get("remaining", 1)) <= 0:
        next_generation = current_generation + 1
        current_remaining = 0.0
    else:
        previous_end = completed.get(current_generation - 1, started)
        current_elapsed = max(0.0, (now - previous_end).total_seconds())
        total = max(1, int(latest.get("total", 1)))
        fraction = min(1.0, max(0.0, int(latest.get("finished", 0)) / total))
        expected = predicted(current_generation)
        current_remaining = max(
            0.0,
            expected - current_elapsed,
            expected * (1.0 - fraction),
        )
        next_generation = current_generation + 1
    tail = sum(predicted(index) for index in range(next_generation, generations))
    return {
        "remaining_seconds": current_remaining + tail,
        "completed_generations": len(ordered),
        "seconds_per_generation_slope": slope,
    }


def _lower_bound_seconds(
    spec: Mapping[str, Any],
    cell: Mapping[str, Any],
    *,
    remaining_evaluations: int | None = None,
) -> float:
    baseline = spec.get("baselines", {}).get(str(cell.get("baseline")), {})
    estimates = baseline.get("estimates", {}) if isinstance(baseline, Mapping) else {}
    try:
        per_evaluation = max(0.0, float(estimates.get("evaluation_seconds", 0.0)))
    except (TypeError, ValueError):
        per_evaluation = 0.0
    count = (
        int(cell.get("planned_evaluations", 0))
        if remaining_evaluations is None
        else max(0, int(remaining_evaluations))
    )
    return per_evaluation * count


def estimate_workspace_timing(
    root: Path,
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Estimate remaining time from this workspace only."""

    current = now or dt.datetime.now(dt.timezone.utc)
    started = _parse_utc(state.get("started_utc"))
    finished = _parse_utc(state.get("finished_utc"))
    elapsed_end = finished or current
    elapsed = (
        0.0
        if started is None and state.get("status") == "planned"
        else None
        if started is None
        else max(0.0, (elapsed_end - started).total_seconds())
    )
    actives = active_progresses(root, state, now=current)
    recent_candidates = [
        parsed
        for item in actives
        if (parsed := _parse_utc(item.get("last_activity_utc"))) is not None
    ]
    updated = _parse_utc(state.get("updated_utc"))
    if updated is not None:
        recent_candidates.append(updated)
    recent = max(recent_candidates) if recent_candidates else None
    base = {
        "elapsed_seconds": elapsed,
        "active_cell_count": len(actives),
        "active_cells": [str(item["cell"]) for item in actives[:8]],
        "active_cell_labels": [
            str(item.get("display_label", item["cell"])) for item in actives[:8]
        ],
        "active_cells_truncated": max(0, len(actives) - 8),
        "recent_activity_utc": _iso(recent),
        "inactivity_seconds": (
            None if recent is None else max(0.0, (current - recent).total_seconds())
        ),
    }
    status = str(state.get("status", "unknown"))
    if status == "completed":
        return {
            **base,
            "estimated_remaining_seconds": 0.0,
            "estimated_completion_utc": _iso(finished or current),
            "confidence": "high",
            "evidence": [{"kind": "terminal-state", "status": "completed"}],
        }
    if status == "failed":
        return {
            **base,
            "estimated_remaining_seconds": None,
            "estimated_completion_utc": None,
            "confidence": "unavailable",
            "evidence": [{"kind": "terminal-state", "status": "failed"}],
        }

    cell_specs = {str(item["id"]): item for item in spec.get("cells", [])}
    active_by_cell = {str(item["cell"]): item for item in actives}
    remaining_by_cell: dict[str, float] = {}
    evidence: list[dict[str, Any]] = []
    for cell_id, cell in cell_specs.items():
        cell_state = state.get("cells", {}).get(cell_id, {})
        cell_status = str(cell_state.get("status", "planned"))
        if cell_status in {"collected", "failed"}:
            continue
        active_cell = active_by_cell.get(cell_id)
        trend = None
        if active_cell is not None and cell_state.get("active_command"):
            trend = _generation_trend(
                root / str(cell_state["active_command"]),
                generations=max(1, int(cell.get("generations", 1))),
                now=current,
            )
        if trend is not None:
            remaining_by_cell[cell_id] = float(trend["remaining_seconds"])
            evidence.append({"kind": "generation-trend", "cell": cell_id, **trend})
            continue
        observed = 0 if active_cell is None else int(active_cell.get("evaluations") or 0)
        lower = _lower_bound_seconds(
            spec,
            cell,
            remaining_evaluations=max(
                0, int(cell.get("planned_evaluations", 0)) - observed
            ),
        )
        remaining_by_cell[cell_id] = lower
        evidence.append(
            {
                "kind": "evaluation-lower-bound",
                "cell": cell_id,
                "seconds": lower,
                "note": "does not include optimizer or surrogate-training overhead",
            }
        )

    configured = max(1, int(spec.get("workflow", {}).get("cell_concurrency", 1)))
    lane_count = max(configured, len(actives), 1)
    lane_loads = [0.0 for _ in range(lane_count)]
    active_ids = [str(item["cell"]) for item in actives]
    for index, cell_id in enumerate(active_ids):
        lane_loads[index] = max(0.0, remaining_by_cell.get(cell_id, 0.0))
    queued = 0
    for cell_id in cell_specs:
        if cell_id in active_by_cell:
            continue
        cell_status = str(
            state.get("cells", {}).get(cell_id, {}).get("status", "planned")
        )
        if cell_status in {"collected", "failed"}:
            continue
        lane = min(range(lane_count), key=lambda index: (lane_loads[index], index))
        lane_loads[lane] += max(0.0, remaining_by_cell.get(cell_id, 0.0))
        queued += 1
    remaining = max(lane_loads, default=0.0)
    evidence.insert(
        0,
        {
            "kind": "cell-concurrency-schedule",
            "configured": configured,
            "active": len(actives),
            "queued": queued,
            "lane_remaining_seconds": lane_loads[:8],
            "lanes_truncated": max(0, len(lane_loads) - 8),
        },
    )
    return {
        **base,
        "estimated_remaining_seconds": remaining,
        "estimated_completion_utc": _iso(
            current + dt.timedelta(seconds=remaining)
        ),
        "confidence": "medium" if any(
            item.get("kind") == "generation-trend" for item in evidence
        ) else "low",
        "evidence": evidence[:12],
        "evidence_truncated": max(0, len(evidence) - 12),
    }


__all__ = [
    "active_progress",
    "active_progresses",
    "estimate_workspace_timing",
]
