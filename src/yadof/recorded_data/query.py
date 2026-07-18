"""Workspace-explicit history queries and dynamic task interpretation."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence
import zipfile

from ..job_template import api as job_template_api
from ..job_template.rawdata_contract import (
    RawDataContractError,
    validate_rawdata_item,
)
from ..workspace import WorkspaceContext
from .manifest_store import (
    metadata_read_lock,
    read_individual_records,
)
from .paths import RecordedDataPaths
from .rawdata_store import (
    load_archive_member,
    load_archive_members_from_archive,
    rawdata_members_for_record,
)


BAD_RAWDATA_EXCEPTIONS = (
    RawDataContractError,
    FileNotFoundError,
    OSError,
    ValueError,
    KeyError,
    zipfile.BadZipFile,
)
BAD_VARIABLE_EXCEPTIONS = (KeyError, TypeError, ValueError)


def _record_snapshot(storage: RecordedDataPaths) -> tuple[dict[str, object], ...]:
    with metadata_read_lock(storage):
        return tuple(dict(record) for record in read_individual_records(storage))


def raw_variables_as_tuple(
    workspace: WorkspaceContext, raw_variables: object
) -> tuple[float, ...]:
    if isinstance(raw_variables, Mapping):
        names = job_template_api.get_parameter_names(workspace)
        return tuple(float(raw_variables[name]) for name in names)
    return tuple(float(value) for value in raw_variables)  # type: ignore[arg-type]


def get_raw_variables(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    status: str | None = None,
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    rows: list[tuple[str, tuple[float, ...]]] = []
    for record in _record_snapshot(storage):
        if status is not None and str(record.get("status")) != status:
            continue
        try:
            raw_variables = raw_variables_as_tuple(workspace, record["raw_variables"])
        except BAD_VARIABLE_EXCEPTIONS:
            continue
        rows.append((str(record["job_name"]), raw_variables))
    return tuple(rows)


def get_normalized_variables(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    status: str | None = None,
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    rows: list[tuple[str, tuple[float, ...]]] = []
    for job_name, raw_variables in get_raw_variables(
        workspace, storage, status=status
    ):
        try:
            normalized = job_template_api.normalize_variables(workspace, raw_variables)
        except BAD_VARIABLE_EXCEPTIONS:
            continue
        rows.append((job_name, normalized))
    return tuple(rows)


def get_normalized_variable_table(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    status: str | None = None,
) -> tuple[tuple[str, ...], tuple[tuple[float, ...], ...]]:
    rows = get_normalized_variables(workspace, storage, status=status)
    return (
        job_template_api.get_parameter_names(workspace),
        tuple(values for _job_name, values in rows),
    )


def get_rawdata_samples(
    storage: RecordedDataPaths,
    *,
    job_names: Sequence[str] | None = None,
    as_paths: bool = False,
    status: str | None = None,
) -> tuple[tuple[str, tuple[dict[str, object] | str, ...]], ...]:
    requested = set(str(name) for name in job_names) if job_names is not None else None
    samples: list[tuple[str, tuple[dict[str, object] | str, ...]]] = []
    with metadata_read_lock(storage):
        records = read_individual_records(storage)
        if as_paths:
            for record in records:
                name = str(record["job_name"])
                if requested is not None and name not in requested:
                    continue
                if status is not None and str(record.get("status")) != status:
                    continue
                samples.append((name, rawdata_members_for_record(record)))
            return tuple(samples)

        try:
            archive = zipfile.ZipFile(storage.rawdata_archive_path, "r")
        except BAD_RAWDATA_EXCEPTIONS:
            return ()
        with archive:
            for record in records:
                name = str(record["job_name"])
                if requested is not None and name not in requested:
                    continue
                if status is not None and str(record.get("status")) != status:
                    continue
                try:
                    items = load_archive_members_from_archive(
                        archive, rawdata_members_for_record(record)
                    )
                except BAD_RAWDATA_EXCEPTIONS:
                    continue
                samples.append((name, tuple(items)))
    return tuple(samples)


def get_raw_data(
    storage: RecordedDataPaths,
) -> tuple[tuple[dict[str, object], ...], ...]:
    return tuple(
        rawdata  # type: ignore[misc]
        for _job_name, rawdata in get_rawdata_samples(storage)
    )


def calculate_costs(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    samples = get_rawdata_samples(
        storage, job_names=job_names, as_paths=False, status=status
    )
    raw_variables_by_job = dict(
        get_raw_variables(workspace, storage, status=status)
    )
    rows: list[tuple[str, tuple[float, ...]]] = []
    for job_name, rawdata in samples:
        if job_name not in raw_variables_by_job:
            continue
        try:
            costs = job_template_api.calculate_cost(
                workspace,
                (rawdata,),
                (raw_variables_by_job[job_name],),
            )
        except BAD_RAWDATA_EXCEPTIONS:
            continue
        if costs:
            rows.append((job_name, costs[0]))
    return tuple(rows)


def get_historical_results(
    workspace: WorkspaceContext,
    storage: RecordedDataPaths,
    *,
    status: str | None = "completed",
) -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    normalized_by_job = dict(
        get_normalized_variables(workspace, storage, status=status)
    )
    costs_by_job = dict(calculate_costs(workspace, storage, status=status))
    return tuple(
        (job_name, normalized_by_job[job_name], costs_by_job[job_name])
        for job_name in normalized_by_job
        if job_name in costs_by_job
    )


def get_surrogate_training_data(
    workspace: WorkspaceContext, storage: RecordedDataPaths
) -> dict[str, object]:
    names = job_template_api.get_parameter_names(workspace)
    raw_variables_by_job = dict(
        get_raw_variables(workspace, storage, status="completed")
    )
    normalized_by_job = dict(
        get_normalized_variables(workspace, storage, status="completed")
    )
    raw_rows = get_rawdata_samples(storage, status="completed", as_paths=False)

    variables: list[tuple[float, ...]] = []
    raw_data: list[tuple[dict[str, object], ...]] = []
    for job_name, rawdata in raw_rows:
        if job_name not in normalized_by_job:
            continue
        try:
            job_template_api.calculate_cost(
                workspace,
                (rawdata,),
                (raw_variables_by_job[job_name],),
            )
        except BAD_RAWDATA_EXCEPTIONS:
            continue
        variables.append(normalized_by_job[job_name])
        raw_data.append(tuple(rawdata))  # type: ignore[arg-type]

    return {
        "parameter_names": names,
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
    diagnostics: list[dict[str, object]] = []
    for record in _record_snapshot(storage):
        job_name = str(record["job_name"])
        if requested is not None and job_name not in requested:
            continue
        if status is not None and str(record.get("status")) != status:
            continue
        for member in rawdata_members_for_record(record):
            diagnostic = _rawdata_diagnostic(storage, job_name, member)
            if include_valid or diagnostic["status"] != "valid":
                diagnostics.append(diagnostic)
    return tuple(diagnostics)


def _rawdata_diagnostic(
    storage: RecordedDataPaths, job_name: str, member: str
) -> dict[str, object]:
    base = {
        "job_name": job_name,
        "filename": Path(member).name,
        "archive_member": member,
        "path": f"{storage.rawdata_archive_path}::{member}",
    }
    try:
        with metadata_read_lock(storage):
            validate_rawdata_item(load_archive_member(storage, member))
    except RawDataContractError as exc:
        return {
            **base,
            "status": "skipped",
            "error_type": exc.error_type,
            "error_message": str(exc),
        }
    except FileNotFoundError as exc:
        return {
            **base,
            "status": "skipped",
            "error_type": "missing_file",
            "error_message": str(exc),
        }
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        return {
            **base,
            "status": "skipped",
            "error_type": "unreadable_rawdata",
            "error_message": str(exc),
        }
    return {
        **base,
        "status": "valid",
        "error_type": "",
        "error_message": "",
    }
