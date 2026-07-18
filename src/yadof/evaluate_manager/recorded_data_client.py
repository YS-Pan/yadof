"""Adapt packaged job results to workspace-local recorded data."""

from __future__ import annotations

from pathlib import Path

from ..recorded_data import api as recorded_data_api
from ..workspace import WorkspaceContext
from .types import JobResult


def record_result(
    workspace: WorkspaceContext, result: JobResult
) -> tuple[float, ...] | None:
    """Persist one result and derive its cost from the current workspace task."""

    recorded_status = "completed" if result.status == "done" else result.status
    recorded_data_api.record_job_result(
        workspace,
        result.job_name,
        result.unnormalized_variables,
        tuple(Path(path) for path in result.raw_data_paths),
        dict(result.metadata),
        status=recorded_status,
    )
    if result.status != "done":
        return None

    for job_name, costs in recorded_data_api.calculate_costs(
        workspace,
        job_names=(result.job_name,),
        status=None,
    ):
        if job_name == result.job_name:
            return tuple(float(value) for value in costs)
    raise RuntimeError(
        f"recorded job {result.job_name!r} has no dynamically calculable cost"
    )


__all__ = ["record_result"]
