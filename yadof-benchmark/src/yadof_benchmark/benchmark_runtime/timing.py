"""Frozen matched-cell timing history for read-only ETA estimation."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import RUN_FORMAT, STATE_FORMAT, RunSpec

TIMING_HISTORY_FORMAT = "yadof.benchmark.timing-history"
_MAX_HISTORY_RECORDS = 256
_MATCH_SAMPLE_LIMIT = 5


def _json_value(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _value_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def host_identity(spec: RunSpec) -> dict[str, Any]:
    """Capture the non-secret host/resource identity used for timing matching."""

    variables = sorted(
        {
            str(resource["variable"])
            for cell in spec.cells
            if isinstance((resource := cell.execution.get("resource")), Mapping)
            and isinstance(resource.get("variable"), str)
            and resource.get("variable")
        }
    )
    resources = {
        variable: (
            None
            if (value := os.environ.get(variable)) is None
            else _value_digest(str(Path(value).expanduser()))
        )
        for variable in variables
    }
    return {
        "node": platform.node(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_executable": str(spec.workflow.python),
        "resources": resources,
    }


def _duration(attempt: Mapping[str, Any]) -> float | None:
    try:
        value = float(attempt.get("runtime_seconds"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def timing_record(
    *,
    run_id: str,
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
    cell: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> dict[str, Any] | None:
    duration = _duration(attempt)
    if duration is None:
        return None
    return {
        "run_id": run_id,
        "cell": str(cell.get("id", "")),
        "comparison": str(cell.get("comparison", "")),
        "baseline": str(cell.get("baseline", "")),
        "strategy": str(cell.get("strategy", "")),
        "population": int(cell.get("population", 0)),
        "generations": int(cell.get("generations", 0)),
        "baseline_digest": str(cell.get("baseline_digest", "")),
        "strategy_digest": str(cell.get("strategy_digest", "")),
        "execution": cell.get("execution", {}),
        "workflow_digest": str(spec.get("workflow_digest", "")),
        "driver_digest": str(spec.get("driver_digest", "")),
        "python": str(spec.get("workflow", {}).get("python", "")),
        "host": state.get("host"),
        "duration_seconds": duration,
        "completed_utc": (
            attempt.get("collected_utc")
            or attempt.get("finished_utc")
            or state.get("updated_utc")
        ),
        "attempt": attempt.get("number"),
    }


def _records_from_run(run_root: Path) -> list[dict[str, Any]]:
    spec = _json_value(run_root / "spec.json")
    state = _json_value(run_root / "state.json")
    if (
        spec is None
        or state is None
        or spec.get("format") != RUN_FORMAT
        or state.get("format") != STATE_FORMAT
    ):
        return []
    cells = {str(item.get("id")): item for item in spec.get("cells", [])}
    output: list[dict[str, Any]] = []
    for cell_id, cell_state in state.get("cells", {}).items():
        if cell_state.get("status") != "collected":
            continue
        attempts = cell_state.get("attempts", [])
        if not attempts or cell_id not in cells:
            continue
        record = timing_record(
            run_id=str(state.get("run_id", run_root.name)),
            spec=spec,
            state=state,
            cell=cells[cell_id],
            attempt=attempts[-1],
        )
        if record is not None:
            output.append(record)
    return output


def build_timing_history(runs_dir: Path) -> dict[str, Any]:
    """Build a bounded immutable prior snapshot without modifying earlier runs."""

    records: list[dict[str, Any]] = []
    run_count = 0
    if runs_dir.is_dir():
        candidates = sorted(
            (path for path in runs_dir.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for run_root in candidates:
            found = _records_from_run(run_root)
            if found:
                run_count += 1
                records.extend(found)
            if len(records) >= _MAX_HISTORY_RECORDS:
                break
    records.sort(key=lambda item: str(item.get("completed_utc") or ""), reverse=True)
    return {
        "format": TIMING_HISTORY_FORMAT,
        "source_runs": run_count,
        "records": records[:_MAX_HISTORY_RECORDS],
    }


def _match_fields(
    cell: Mapping[str, Any],
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    exact: bool,
) -> dict[str, Any]:
    value = {
        "comparison": cell.get("comparison"),
        "baseline": cell.get("baseline"),
        "strategy": cell.get("strategy"),
        "population": cell.get("population"),
        "generations": cell.get("generations"),
        "baseline_digest": cell.get("baseline_digest"),
        "execution": cell.get("execution", {}),
        "python": spec.get("workflow", {}).get("python"),
        "host": state.get("host"),
    }
    if exact:
        value.update(
            {
                "strategy_digest": cell.get("strategy_digest"),
                "workflow_digest": spec.get("workflow_digest"),
                "driver_digest": spec.get("driver_digest"),
            }
        )
    return value


def _same(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def matched_prior(
    cell: Mapping[str, Any],
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
    records: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Choose exact, then compatible, same-case/same-arm timing evidence."""

    if state.get("host") is None:
        return None
    current_exact = _match_fields(cell, spec, state, exact=True)
    current_compatible = _match_fields(cell, spec, state, exact=False)
    exact: list[Mapping[str, Any]] = []
    compatible: list[Mapping[str, Any]] = []
    for record in records:
        if record.get("host") is None:
            continue
        if _same(
            {key: record.get(key) for key in current_exact}, current_exact
        ):
            exact.append(record)
        elif _same(
            {key: record.get(key) for key in current_compatible},
            current_compatible,
        ):
            compatible.append(record)
    selected = exact if exact else compatible
    if not selected:
        return None
    selected = sorted(
        selected,
        key=lambda item: str(item.get("completed_utc") or ""),
        reverse=True,
    )[:_MATCH_SAMPLE_LIMIT]
    durations = [float(item["duration_seconds"]) for item in selected]
    median = statistics.median(durations)
    mad = statistics.median(abs(value - median) for value in durations)
    relative_mad = 0.0 if median <= 0 else mad / median
    level = "exact" if exact else "compatible"
    if level == "exact" and len(durations) >= 3 and relative_mad <= 0.15:
        confidence = "high"
    elif level == "exact":
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "match": level,
        "sample_count": len(durations),
        "median_seconds": median,
        "relative_mad": relative_mad,
        "confidence": confidence,
        "runs": [str(item.get("run_id", "")) for item in selected[:3]],
    }


__all__ = [
    "TIMING_HISTORY_FORMAT",
    "build_timing_history",
    "host_identity",
    "matched_prior",
    "timing_record",
]
