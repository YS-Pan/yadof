"""Tolerant public queries over immutable v2 segments."""

from __future__ import annotations

from typing import Callable, Mapping, Sequence
import zipfile

from ..job_template import api as job_template_api
from ..job_template.rawdata_contract import RawDataContractError, validate_rawdata_item
from ..workspace import WorkspaceContext
from .paths import RecordedDataPaths
from .segment_store import (
    SegmentReference,
    discover_catalog,
    load_reference_rawdata,
)


TOLERATED_ROW_ERRORS = (
    FileNotFoundError,
    OSError,
    UnicodeError,
    ValueError,
    TypeError,
    KeyError,
    RawDataContractError,
    zipfile.BadZipFile,
)


def get_raw_variables(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    status: str | None = None,
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    names = tuple(job_template_api.get_parameter_names(workspace))
    rows = []
    for reference in _references(storage, status=status):
        try:
            values = _raw_variables(reference.record, names)
        except TOLERATED_ROW_ERRORS:
            continue
        rows.append((str(reference.record.get("job_name", "")), values))
    return tuple(rows)


def get_normalized_variables(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    status: str | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    raw_rows = get_raw_variables(workspace, storage, status=status)
    total = len(raw_rows)
    if progress is not None:
        progress(0, total, "normalizing variables")
    output = []
    for index, (name, values) in enumerate(raw_rows, start=1):
        try:
            normalized = job_template_api.normalize_variables(workspace, values)
        except TOLERATED_ROW_ERRORS:
            pass
        else:
            output.append((name, tuple(float(value) for value in normalized)))
        if progress is not None:
            progress(index, total, "normalizing variables")
    return tuple(output)


def get_normalized_variable_table(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    status: str | None = None,
) -> tuple[tuple[str, ...], tuple[tuple[float, ...], ...]]:
    rows = get_normalized_variables(workspace, storage, status=status)
    return (
        tuple(job_template_api.get_parameter_names(workspace)),
        tuple(values for _name, values in rows),
    )


def get_rawdata_samples(
    storage: RecordedDataPaths,
    *,
    job_names: Sequence[str] | None = None,
    as_paths: bool = False,
    status: str | None = None,
) -> tuple[tuple[str, tuple[dict[str, object] | str, ...]], ...]:
    requested = set(str(name) for name in job_names) if job_names is not None else None
    output = []
    for reference in _references(storage, status=status):
        name = str(reference.record.get("job_name", ""))
        if requested is not None and name not in requested:
            continue
        if as_paths:
            output.append(
                (
                    name,
                    tuple(
                        f"{reference.segment_path}::{member}"
                        for _filename, member, _size in reference.rawdata_members
                    ),
                )
            )
            continue
        try:
            items = load_reference_rawdata(reference)
        except TOLERATED_ROW_ERRORS:
            continue
        output.append((name, tuple(dict(item.payload) for item in items)))
    return tuple(output)


def get_raw_data(
    storage: RecordedDataPaths,
) -> tuple[tuple[dict[str, object], ...], ...]:
    return tuple(
        tuple(item for item in rawdata if isinstance(item, dict))
        for _name, rawdata in get_rawdata_samples(storage)
    )


def calculate_costs(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    requested = set(str(name) for name in job_names) if job_names is not None else None
    references = tuple(
        reference
        for reference in _references(storage, status=status)
        if requested is None
        or str(reference.record.get("job_name", "")) in requested
    )
    names = tuple(job_template_api.get_parameter_names(workspace))
    if progress is not None:
        progress(0, len(references), "calculating costs")
    output = []
    for index, reference in enumerate(references, start=1):
        try:
            items = load_reference_rawdata(reference)
            raw_variables = _raw_variables(reference.record, names)
            costs = job_template_api.calculate_cost(
                workspace,
                (tuple(item.payload for item in items),),
                (raw_variables,),
            )[0]
        except TOLERATED_ROW_ERRORS:
            pass
        else:
            output.append(
                (
                    str(reference.record.get("job_name", "")),
                    tuple(float(value) for value in costs),
                )
            )
        if progress is not None:
            progress(index, len(references), "calculating costs")
    return tuple(output)


def get_historical_results(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    status: str | None = "completed",
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    references = _references(storage, status=status)
    parameter_names = tuple(job_template_api.get_parameter_names(workspace))
    total = len(references)
    if progress is not None:
        progress(0, total, "reinterpreting history")
    output = []
    for index, reference in enumerate(references, start=1):
        try:
            raw_variables = _raw_variables(reference.record, parameter_names)
            normalized = job_template_api.normalize_variables(workspace, raw_variables)
            items = load_reference_rawdata(reference)
            costs = job_template_api.calculate_cost(
                workspace,
                (tuple(item.payload for item in items),),
                (raw_variables,),
            )[0]
        except TOLERATED_ROW_ERRORS:
            pass
        else:
            output.append(
                (
                    str(reference.record.get("job_name", "")),
                    tuple(float(value) for value in normalized),
                    tuple(float(value) for value in costs),
                )
            )
        if progress is not None:
            progress(index, total, "reinterpreting history")
    return tuple(output)


def get_surrogate_training_data(
    workspace: WorkspaceContext, storage: RecordedDataPaths
) -> dict[str, object]:
    historical = get_historical_results(workspace, storage, status="completed")
    wanted = tuple(name for name, _normalized, _costs in historical)
    samples = dict(
        get_rawdata_samples(storage, job_names=wanted, status="completed")
    )
    variables = []
    raw_data = []
    for name, normalized, _costs in historical:
        sample = samples.get(name)
        if sample is None:
            continue
        variables.append(normalized)
        raw_data.append(tuple(item for item in sample if isinstance(item, dict)))
    return {
        "parameter_names": tuple(job_template_api.get_parameter_names(workspace)),
        "normalized_variables": tuple(variables),
        "raw_data": tuple(raw_data),
    }


def get_rawdata_diagnostics(
    storage: RecordedDataPaths,
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
    include_valid: bool = False,
) -> tuple[dict[str, object], ...]:
    requested = set(str(name) for name in job_names) if job_names is not None else None
    catalog = discover_catalog(storage)
    output = [
        {
            **dict(diagnostic),
            "job_name": "",
            "status": "skipped",
        }
        for diagnostic in catalog.diagnostics
    ]
    for reference in catalog.references:
        if status is not None and str(reference.record.get("status")) != status:
            continue
        job_name = str(reference.record.get("job_name", ""))
        if requested is not None and job_name not in requested:
            continue
        try:
            items = load_reference_rawdata(reference)
            for item in items:
                validate_rawdata_item(item.payload)
        except TOLERATED_ROW_ERRORS as exc:
            output.append(
                {
                    "job_name": job_name,
                    "path": str(reference.segment_path),
                    "status": "skipped",
                    "error_type": "unreadable_rawdata",
                    "error_message": f"{type(exc).__name__}: {exc}",
                }
            )
        else:
            if not include_valid:
                continue
            for filename, member, _size in reference.rawdata_members:
                output.append(
                    {
                        "job_name": job_name,
                        "filename": filename,
                        "archive_member": member,
                        "path": f"{reference.segment_path}::{member}",
                        "status": "valid",
                        "error_type": "",
                        "error_message": "",
                    }
                )
    return tuple(output)


def _references(
    storage: RecordedDataPaths, *, status: str | None = None
) -> tuple[SegmentReference, ...]:
    return tuple(
        reference
        for reference in discover_catalog(storage).references
        if status is None or str(reference.record.get("status")) == status
    )


def _raw_variables(
    record: Mapping[str, object], names: Sequence[str]
) -> tuple[float, ...]:
    values = record.get("raw_variables")
    if not isinstance(values, Mapping):
        raise TypeError("v2 raw_variables must be a mapping")
    return tuple(float(values[name]) for name in names)


__all__ = [
    "calculate_costs",
    "get_historical_results",
    "get_normalized_variable_table",
    "get_normalized_variables",
    "get_raw_data",
    "get_raw_variables",
    "get_rawdata_diagnostics",
    "get_rawdata_samples",
    "get_surrogate_training_data",
]
