"""Read-only progress, inactivity, and matched-history ETA reporting."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .storage import read_json
from .timing import TIMING_HISTORY_FORMAT, matched_prior, timing_record


def _parse_utc(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    output: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
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


def active_progress(
    run_root: Path,
    state: Mapping[str, Any],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any] | None:
    current_time = now or dt.datetime.now(dt.timezone.utc)
    for cell_id, cell in state.get("cells", {}).items():
        if cell.get("status") not in {"checked", "running"}:
            continue
        attempts = cell.get("attempts", [])
        attempt = attempts[-1] if attempts else {}
        attempt_started = _parse_utc(attempt.get("created_utc"))
        active_value = attempt.get("active_command")
        if not active_value:
            return {
                "cell": cell_id,
                "phase": cell.get("status"),
                "cell_elapsed_seconds": (
                    None
                    if attempt_started is None
                    else max(0.0, (current_time - attempt_started).total_seconds())
                ),
            }
        command_root = run_root / str(active_value)
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
            "phase": (
                latest_progress.get("phase")
                if latest_progress is not None
                else attempt.get("status", cell.get("status"))
            ),
            "command": started.get("label"),
            "command_elapsed_seconds": (
                None
                if started_time is None
                else max(0.0, (current_time - started_time).total_seconds())
            ),
            "cell_elapsed_seconds": (
                None
                if attempt_started is None
                else max(0.0, (current_time - attempt_started).total_seconds())
            ),
            "last_activity_utc": _iso(latest),
            "inactivity_seconds": (
                None
                if latest is None
                else max(0.0, (current_time - latest).total_seconds())
            ),
            "logs": {
                name.removesuffix(".log"): str(command_root / name)
                for name in ("stdout.log", "stderr.log")
                if (command_root / name).is_file()
            },
        }
        if latest_progress is not None:
            output["generation"] = latest_progress.get("generation_number")
            output["generations"] = latest_progress.get("generations")
            output["evaluations"] = latest_progress.get("evaluations")
            output["planned_evaluations"] = latest_progress.get(
                "planned_evaluations"
            )
            output["successful"] = latest_progress.get("successful")
            output["errors"] = latest_progress.get("errors")
        return output
    for item_id, item in state.get("postprocessors", {}).items():
        if item.get("status") == "running":
            attempts = item.get("attempts", [])
            attempt = attempts[-1] if attempts else {}
            started = _parse_utc(attempt.get("created_utc"))
            return {
                "postprocessor": item_id,
                "phase": "running",
                "elapsed_seconds": (
                    None
                    if started is None
                    else max(0.0, (current_time - started).total_seconds())
                ),
                "last_activity_utc": state.get("updated_utc"),
            }
    return None


def _history_records(
    run_root: Path,
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    history_path = run_root / "timing_history.json"
    history = read_json(history_path) if history_path.is_file() else {}
    records = (
        [
            dict(item)
            for item in history.get("records", [])
            if isinstance(item, Mapping)
        ]
        if history.get("format") == TIMING_HISTORY_FORMAT
        else []
    )
    cells = {str(item.get("id")): item for item in spec.get("cells", [])}
    for cell_id, cell_state in state.get("cells", {}).items():
        if cell_state.get("status") != "collected" or cell_id not in cells:
            continue
        attempts = cell_state.get("attempts", [])
        if not attempts:
            continue
        record = timing_record(
            run_id=str(state.get("run_id", run_root.name)),
            spec=spec,
            state=state,
            cell=cells[cell_id],
            attempt=attempts[-1],
        )
        if record is not None:
            records.append(record)
    return records


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
    if not events:
        return None
    completed: dict[int, dt.datetime] = {}
    for item in events:
        if int(item.get("remaining", 1)) <= 0:
            ended = _parse_utc(item["utc"])
            if ended is not None:
                completed[int(item["generation"])] = ended
    ordered = sorted(completed)
    if len(ordered) < 3:
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
        fraction = min(
            1.0, max(0.0, int(latest.get("finished", 0)) / total)
        )
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
    baselines = spec.get("baselines", {})
    baseline = baselines.get(str(cell.get("baseline")), {})
    estimates = (
        baseline.get("estimates", {}) if isinstance(baseline, Mapping) else {}
    )
    try:
        per_evaluation = max(
            0.0, float(estimates.get("evaluation_seconds", 0.0))
        )
    except (TypeError, ValueError):
        per_evaluation = 0.0
    count = (
        int(cell.get("planned_evaluations", 0))
        if remaining_evaluations is None
        else max(0, int(remaining_evaluations))
    )
    return per_evaluation * count


def _confidence(values: Iterable[str]) -> str:
    ranking = {"unavailable": 0, "low": 1, "medium": 2, "high": 3}
    selected = list(values)
    if not selected:
        return "unavailable"
    return min(selected, key=lambda item: ranking.get(item, 0))


def estimate_run_timing(
    run_root: Path,
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Estimate terminal time without writing or substituting another strategy."""

    current_time = now or dt.datetime.now(dt.timezone.utc)
    started = _parse_utc(state.get("started_utc"))
    if "started_utc" not in state:
        started = _parse_utc(state.get("created_utc"))
    finished = _parse_utc(state.get("finished_utc"))
    if finished is None and str(state.get("status")) in {"completed", "failed"}:
        finished = _parse_utc(state.get("updated_utc"))
    elapsed_end = finished or current_time
    if started is None:
        elapsed = 0.0 if str(state.get("status")) == "planned" else None
    else:
        elapsed = max(0.0, (elapsed_end - started).total_seconds())
    active = active_progress(run_root, state, now=current_time)
    recent = _parse_utc(
        active.get("last_activity_utc") if active else state.get("updated_utc")
    )
    base = {
        "elapsed_seconds": elapsed,
        "active_cell_runtime_seconds": (
            None if active is None else active.get("cell_elapsed_seconds")
        ),
        "recent_activity_utc": _iso(recent),
        "inactivity_seconds": (
            None
            if recent is None
            else max(0.0, (current_time - recent).total_seconds())
        ),
    }
    status = str(state.get("status", "unknown"))
    if status == "completed":
        return {
            **base,
            "estimated_remaining_seconds": 0.0,
            "estimated_completion_utc": _iso(finished or current_time),
            "confidence": "high",
            "evidence": [{"kind": "terminal-state", "status": "completed"}],
        }
    if status == "failed":
        return {
            **base,
            "estimated_remaining_seconds": None,
            "estimated_completion_utc": None,
            "confidence": "unavailable",
            "evidence": [
                {
                    "kind": "terminal-state",
                    "status": "failed",
                    "note": (
                        "resume creates new attempts, so no completion ETA is asserted"
                    ),
                }
            ],
        }

    records = _history_records(run_root, spec, state)
    cell_specs = {str(item.get("id")): item for item in spec.get("cells", [])}
    remaining = 0.0
    confidences: list[str] = []
    evidence: list[dict[str, Any]] = []
    match_counts = {"exact": 0, "compatible": 0, "none": 0}
    active_cell = None if active is None else active.get("cell")
    for cell_id, cell in cell_specs.items():
        cell_state = state.get("cells", {}).get(cell_id, {})
        cell_status = str(cell_state.get("status", "planned"))
        if cell_status in {"collected", "failed"}:
            continue
        prior = matched_prior(cell, spec, state, records)
        if prior is not None:
            match_counts[str(prior["match"])] += 1
        else:
            match_counts["none"] += 1
        if cell_id == active_cell:
            active_elapsed = float(active.get("cell_elapsed_seconds") or 0.0)
            prior_remaining = (
                None
                if prior is None
                else max(0.0, float(prior["median_seconds"]) - active_elapsed)
            )
            attempts = cell_state.get("attempts", [])
            attempt = attempts[-1] if attempts else {}
            active_command = attempt.get("active_command")
            trend = (
                None
                if not active_command
                else _generation_trend(
                    run_root / str(active_command),
                    generations=max(1, int(cell.get("generations", 1))),
                    now=current_time,
                )
            )
            if trend is not None:
                stage_remaining = float(trend["remaining_seconds"])
                selected = (
                    stage_remaining
                    if prior_remaining is None
                    else max(prior_remaining, stage_remaining)
                )
                remaining += selected
                confidence = (
                    "medium" if prior is None else str(prior["confidence"])
                )
                confidences.append(confidence)
                evidence.append(
                    {
                        "kind": "generation-trend",
                        "cell": cell_id,
                        **trend,
                        "matched_history": prior,
                    }
                )
            elif prior_remaining is not None:
                remaining += prior_remaining
                confidences.append(str(prior["confidence"]))
                evidence.append(
                    {"kind": "matched-cell", "cell": cell_id, **prior}
                )
            else:
                planned = int(cell.get("planned_evaluations", 0))
                observed = int(active.get("evaluations") or 0)
                lower = _lower_bound_seconds(
                    spec, cell, remaining_evaluations=max(0, planned - observed)
                )
                remaining += lower
                confidences.append("low")
                evidence.append(
                    {
                        "kind": "evaluation-lower-bound",
                        "cell": cell_id,
                        "seconds": lower,
                        "note": (
                            "does not include optimizer or surrogate-training overhead"
                        ),
                    }
                )
            continue
        if cell_status == "succeeded":
            confidences.append("low")
            evidence.append(
                {
                    "kind": "collection-pending",
                    "cell": cell_id,
                    "note": (
                        "measured execution finished; postprocessing time is not inferred"
                    ),
                }
            )
        elif prior is not None:
            remaining += float(prior["median_seconds"])
            confidences.append(str(prior["confidence"]))
            evidence.append({"kind": "matched-cell", "cell": cell_id, **prior})
        else:
            lower = _lower_bound_seconds(spec, cell)
            remaining += lower
            confidences.append("low")
            evidence.append(
                {
                    "kind": "evaluation-lower-bound",
                    "cell": cell_id,
                    "seconds": lower,
                    "note": (
                        "does not include optimizer or surrogate-training overhead"
                    ),
                }
            )

    running_postprocessors = [
        item_id
        for item_id, item in state.get("postprocessors", {}).items()
        if item.get("status") == "running"
    ]
    if running_postprocessors:
        confidences.append("low")
        evidence.append(
            {
                "kind": "postprocessor-running",
                "ids": running_postprocessors[:3],
                "note": "no cross-run point estimate is available",
            }
        )
    completion = current_time + dt.timedelta(seconds=remaining)
    return {
        **base,
        "estimated_remaining_seconds": remaining,
        "estimated_completion_utc": _iso(completion),
        "confidence": _confidence(confidences),
        "matched_history": match_counts,
        "evidence": evidence[:12],
        "evidence_truncated": max(0, len(evidence) - 12),
    }


__all__ = ["active_progress", "estimate_run_timing"]
