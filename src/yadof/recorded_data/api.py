"""Workspace-explicit public API for durable evaluation history."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from ..workspace import WorkspaceContext, resolve_workspace
from . import query as _query
from . import records as _records
from .paths import (
    IND_META_SCHEMA_VERSION,
    OPT_META_SCHEMA_VERSION,
    VALID_RECORD_STATUSES,
    RecordedDataPaths,
    WorkspaceLike,
    recorded_data_paths,
)


JobRecordRequest = _records.JobRecordRequest


def _context_and_storage(
    workspace: WorkspaceLike,
) -> tuple[WorkspaceContext, RecordedDataPaths]:
    context = resolve_workspace(workspace)
    return context, recorded_data_paths(context)


def record_job_result(
    workspace: WorkspaceLike,
    job_name: str,
    raw_variables: Sequence[float] | Mapping[str, float],
    rawdata_source: str | Path | Sequence[str | Path],
    job_metadata: Mapping[str, object] | None = None,
    *,
    status: str = "completed",
    overwrite: bool = False,
) -> dict[str, object]:
    """Store raw evidence for one completed or failed job without derived cost."""

    _context, storage = _context_and_storage(workspace)
    return _records.record_job_result(
        storage,
        job_name,
        raw_variables,
        rawdata_source,
        job_metadata,
        status=status,
        overwrite=overwrite,
    )


def record_job_results(
    workspace: WorkspaceLike,
    requests: Sequence[JobRecordRequest],
) -> tuple[dict[str, object], ...]:
    """Atomically store one evaluation batch without per-job archive copies."""

    _context, storage = _context_and_storage(workspace)
    return _records.record_job_results(storage, requests)


def list_records(workspace: WorkspaceLike) -> tuple[dict[str, object], ...]:
    _context, storage = _context_and_storage(workspace)
    return _records.list_records(storage)


def record_optimization_metadata(
    workspace: WorkspaceLike, metadata: Mapping[str, object]
) -> dict[str, object]:
    _context, storage = _context_and_storage(workspace)
    return _records.record_optimization_metadata(storage, metadata)


def list_optimization_metadata(
    workspace: WorkspaceLike,
) -> tuple[dict[str, object], ...]:
    _context, storage = _context_and_storage(workspace)
    return _records.list_optimization_metadata(storage)


def record_surrogate_metadata(
    workspace: WorkspaceLike, metadata: Mapping[str, object]
) -> dict[str, object]:
    _context, storage = _context_and_storage(workspace)
    return _records.record_surrogate_metadata(storage, metadata)


def list_surrogate_metadata(
    workspace: WorkspaceLike,
) -> tuple[dict[str, object], ...]:
    _context, storage = _context_and_storage(workspace)
    return _records.list_surrogate_metadata(storage)


def get_job_names(
    workspace: WorkspaceLike, *, status: str | None = None
) -> tuple[str, ...]:
    _context, storage = _context_and_storage(workspace)
    return _records.get_job_names(storage, status=status)


def get_raw_variables(
    workspace: WorkspaceLike, *, status: str | None = None
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    context, storage = _context_and_storage(workspace)
    return _query.get_raw_variables(context, storage, status=status)


def get_normalized_variables(
    workspace: WorkspaceLike, *, status: str | None = None
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    context, storage = _context_and_storage(workspace)
    return _query.get_normalized_variables(context, storage, status=status)


def get_normalized_variable_table(
    workspace: WorkspaceLike, *, status: str | None = None
) -> tuple[tuple[str, ...], tuple[tuple[float, ...], ...]]:
    context, storage = _context_and_storage(workspace)
    return _query.get_normalized_variable_table(context, storage, status=status)


def get_rawdata_samples(
    workspace: WorkspaceLike,
    *,
    job_names: Sequence[str] | None = None,
    as_paths: bool = False,
    status: str | None = None,
) -> tuple[tuple[str, tuple[dict[str, object] | str, ...]], ...]:
    _context, storage = _context_and_storage(workspace)
    return _query.get_rawdata_samples(
        storage, job_names=job_names, as_paths=as_paths, status=status
    )


def get_raw_data(
    workspace: WorkspaceLike,
) -> tuple[tuple[dict[str, object], ...], ...]:
    _context, storage = _context_and_storage(workspace)
    return _query.get_raw_data(storage)


def get_rawData(
    workspace: WorkspaceLike,
) -> tuple[tuple[dict[str, object], ...], ...]:
    return get_raw_data(workspace)


def calculate_costs(
    workspace: WorkspaceLike,
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    context, storage = _context_and_storage(workspace)
    return _query.calculate_costs(
        context, storage, job_names=job_names, status=status
    )


def get_historical_results(
    workspace: WorkspaceLike, *, status: str | None = "completed"
) -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    context, storage = _context_and_storage(workspace)
    return _query.get_historical_results(context, storage, status=status)


def get_optimization_history(
    workspace: WorkspaceLike,
) -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    return get_historical_results(workspace)


def get_historical_optimization_results(
    workspace: WorkspaceLike,
) -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    return get_historical_results(workspace)


def get_surrogate_training_data(workspace: WorkspaceLike) -> dict[str, object]:
    context, storage = _context_and_storage(workspace)
    return _query.get_surrogate_training_data(context, storage)


def get_training_data_for_surrogate(workspace: WorkspaceLike) -> dict[str, object]:
    return get_surrogate_training_data(workspace)


def get_rawdata_diagnostics(
    workspace: WorkspaceLike,
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
    include_valid: bool = False,
) -> tuple[dict[str, object], ...]:
    _context, storage = _context_and_storage(workspace)
    return _query.get_rawdata_diagnostics(
        storage,
        job_names=job_names,
        status=status,
        include_valid=include_valid,
    )


__all__ = [
    "IND_META_SCHEMA_VERSION",
    "OPT_META_SCHEMA_VERSION",
    "VALID_RECORD_STATUSES",
    "calculate_costs",
    "get_historical_optimization_results",
    "get_historical_results",
    "get_job_names",
    "get_normalized_variable_table",
    "get_normalized_variables",
    "get_optimization_history",
    "get_rawData",
    "get_raw_data",
    "get_raw_variables",
    "get_rawdata_diagnostics",
    "get_rawdata_samples",
    "get_surrogate_training_data",
    "get_training_data_for_surrogate",
    "list_optimization_metadata",
    "list_records",
    "list_surrogate_metadata",
    "record_job_result",
    "record_job_results",
    "record_optimization_metadata",
    "record_surrogate_metadata",
]
