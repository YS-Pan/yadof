from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from ..recorded_data import api as recorded_api
from ..workspace import WorkspaceContext
from .gpsaf import OptimizationResult


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def new_run_id() -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    return f"opt_{stamp}_{uuid4().hex[:8]}"


def job_names(workspace: WorkspaceContext) -> tuple[str, ...]:
    try:
        return tuple(str(name) for name in recorded_api.get_job_names(workspace))
    except Exception:
        return ()


def next_optimization_index(workspace: WorkspaceContext) -> int:
    try:
        rows = tuple(
            row
            for row in recorded_api.list_optimization_metadata(workspace)
            if isinstance(row, dict)
        )
    except Exception:
        return 0
    explicit = []
    run_ids: list[str] = []
    for row in rows:
        try:
            explicit.append(int(row["optimization_index"]))
        except (KeyError, TypeError, ValueError):
            run_id = row.get("run_id")
            if run_id not in (None, "") and str(run_id) not in run_ids:
                run_ids.append(str(run_id))
    if explicit:
        return max(explicit) + 1
    return len(run_ids)


def created_job_names(before: tuple[str, ...], after: tuple[str, ...]) -> tuple[str, ...]:
    before_counts: dict[str, int] = {}
    for name in before:
        before_counts[name] = before_counts.get(name, 0) + 1

    created = []
    for name in after:
        count = before_counts.get(name, 0)
        if count > 0:
            before_counts[name] = count - 1
        else:
            created.append(name)
    return tuple(created)


def record_generation_metadata(
    workspace: WorkspaceContext,
    *,
    run_id: str,
    optimization_index: int,
    result: OptimizationResult,
    started_at: str,
    ended_at: str,
    jobs_before: tuple[str, ...],
    jobs_after: tuple[str, ...],
) -> dict[str, object]:
    data = {
        "record_type": "generation",
        "run_id": str(run_id),
        "optimization_index": int(optimization_index),
        "generation_index": int(result.generation_index),
        "source": str(result.source),
        "surrogate_used": bool(result.surrogate_used),
        "history_count": int(result.history_count),
        "population_size": int(len(result.population)),
        "created_job_names": list(created_job_names(jobs_before, jobs_after)),
        "started_at": str(started_at),
        "ended_at": str(ended_at),
        "diagnostics": {
            key: value
            for key, value in result.diagnostics.items()
            if key not in {"costs", "pred_costs", "cost_intervals"}
        },
    }
    return recorded_api.record_optimization_metadata(workspace, data)
