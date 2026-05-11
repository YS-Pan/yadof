"""Public API for storing and reading evaluation records.

External modules should import this file only. The implementation is split
across private module-level helpers so this public API stays small and stable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from . import paths
from . import query as _query
from . import records as _records

MODULE_DIR = paths.MODULE_DIR
MANIFEST_PATH = paths.MANIFEST_PATH
RAWDATA_ROOT = paths.RAWDATA_ROOT
MANIFEST_SCHEMA_VERSION = paths.MANIFEST_SCHEMA_VERSION
VALID_RECORD_STATUSES = paths.VALID_RECORD_STATUSES


def _sync_paths() -> None:
    paths.configure(
        module_dir=MODULE_DIR,
        manifest_path=MANIFEST_PATH,
        rawdata_root=RAWDATA_ROOT,
    )


def record_job_result(
    job_name: str,
    raw_variables: Sequence[float] | Mapping[str, float],
    rawdata_source: str | Path | Sequence[str | Path],
    job_metadata: Mapping[str, object] | None = None,
    *,
    status: str = "completed",
    overwrite: bool = False,
) -> dict[str, object]:
    """Store one completed or failed job without saving derived cost."""

    _sync_paths()
    return _records.record_job_result(
        job_name,
        raw_variables,
        rawdata_source,
        job_metadata,
        status=status,
        overwrite=overwrite,
    )


def list_records() -> tuple[dict[str, object], ...]:
    _sync_paths()
    return _records.list_records()


def get_job_names(*, status: str | None = None) -> tuple[str, ...]:
    _sync_paths()
    return _records.get_job_names(status=status)


def get_raw_variables(*, status: str | None = None) -> tuple[tuple[str, tuple[float, ...]], ...]:
    _sync_paths()
    return _query.get_raw_variables(status=status)


def get_normalized_variables(*, status: str | None = None) -> tuple[tuple[str, tuple[float, ...]], ...]:
    _sync_paths()
    return _query.get_normalized_variables(status=status)


def get_normalized_variable_table(*, status: str | None = None) -> tuple[tuple[str, ...], tuple[tuple[float, ...], ...]]:
    _sync_paths()
    return _query.get_normalized_variable_table(status=status)


def get_rawdata_samples(
    *,
    job_names: Sequence[str] | None = None,
    as_paths: bool = False,
    status: str | None = None,
) -> tuple[tuple[str, tuple[dict[str, object] | Path, ...]], ...]:
    _sync_paths()
    return _query.get_rawdata_samples(job_names=job_names, as_paths=as_paths, status=status)


def get_raw_data() -> tuple[tuple[dict[str, object], ...], ...]:
    _sync_paths()
    return _query.get_raw_data()


def get_rawData() -> tuple[tuple[dict[str, object], ...], ...]:
    return get_raw_data()


def calculate_costs(
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    _sync_paths()
    return _query.calculate_costs(job_names=job_names, status=status)


def get_historical_results(*, status: str | None = "completed") -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    _sync_paths()
    return _query.get_historical_results(status=status)


def get_optimization_history() -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    return get_historical_results()


def get_historical_optimization_results() -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    return get_historical_results()


def get_surrogate_training_data() -> dict[str, object]:
    _sync_paths()
    return _query.get_surrogate_training_data()


def get_training_data_for_surrogate() -> dict[str, object]:
    return get_surrogate_training_data()


def get_rawdata_diagnostics(
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
    include_valid: bool = False,
) -> tuple[dict[str, object], ...]:
    _sync_paths()
    return _query.get_rawdata_diagnostics(job_names=job_names, status=status, include_valid=include_valid)
