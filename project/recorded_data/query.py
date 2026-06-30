from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence
import zipfile

try:
    from project.job_template import api as job_template_api
except ImportError:  # Allows running from inside the project package directory.
    from ..job_template import api as job_template_api

from .manifest_store import read_individual_records
from . import paths
from .rawdata_store import (
    load_archive_member,
    load_archive_members_from_archive,
    rawdata_items_for_record,
    rawdata_members_for_record,
)

try:
    from project.job_template.rawdata_contract import RawDataContractError, validate_rawdata_item
except ImportError:  # Allows running from inside the project package directory.
    from ..job_template.rawdata_contract import RawDataContractError, validate_rawdata_item


BAD_RAWDATA_EXCEPTIONS = (RawDataContractError, FileNotFoundError, OSError, ValueError, KeyError, zipfile.BadZipFile)
BAD_VARIABLE_EXCEPTIONS = (KeyError, TypeError, ValueError)


def raw_variables_as_tuple(raw_variables: object) -> tuple[float, ...]:
    if isinstance(raw_variables, Mapping):
        names = job_template_api.get_parameter_names()
        return tuple(float(raw_variables[name]) for name in names)
    return tuple(float(value) for value in raw_variables)  # type: ignore[arg-type]


def get_raw_variables(*, status: str | None = None) -> tuple[tuple[str, tuple[float, ...]], ...]:
    records = read_individual_records()
    rows: list[tuple[str, tuple[float, ...]]] = []
    for record in records:
        if status is not None and str(record.get("status")) != status:
            continue
        try:
            raw_variables = raw_variables_as_tuple(record["raw_variables"])
        except BAD_VARIABLE_EXCEPTIONS:
            continue
        rows.append((str(record["job_name"]), raw_variables))
    return tuple(rows)


def get_normalized_variables(*, status: str | None = None) -> tuple[tuple[str, tuple[float, ...]], ...]:
    rows: list[tuple[str, tuple[float, ...]]] = []
    for job_name, raw_variables in get_raw_variables(status=status):
        try:
            normalized = job_template_api.normalize_variables(raw_variables)
        except BAD_VARIABLE_EXCEPTIONS:
            continue
        rows.append((job_name, normalized))
    return tuple(rows)


def get_normalized_variable_table(*, status: str | None = None) -> tuple[tuple[str, ...], tuple[tuple[float, ...], ...]]:
    rows = get_normalized_variables(status=status)
    return job_template_api.get_parameter_names(), tuple(values for _job_name, values in rows)


def get_rawdata_samples(
    *,
    job_names: Sequence[str] | None = None,
    as_paths: bool = False,
    status: str | None = None,
) -> tuple[tuple[str, tuple[dict[str, object] | str, ...]], ...]:
    requested = set(str(name) for name in job_names) if job_names is not None else None
    records = read_individual_records()
    samples = []
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
        archive = zipfile.ZipFile(paths.RAWDATA_ARCHIVE_PATH, "r")
    except BAD_RAWDATA_EXCEPTIONS:
        return ()
    with archive:
        for record in records:
            name = str(record["job_name"])
            if requested is not None and name not in requested:
                continue
            if status is not None and str(record.get("status")) != status:
                continue
            members = rawdata_members_for_record(record)
            try:
                items = load_archive_members_from_archive(archive, members)
            except BAD_RAWDATA_EXCEPTIONS:
                continue
            samples.append((name, tuple(items)))
    return tuple(samples)


def get_raw_data() -> tuple[tuple[dict[str, object], ...], ...]:
    return tuple(rawdata for _job_name, rawdata in get_rawdata_samples())


def calculate_costs(
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    samples = get_rawdata_samples(job_names=job_names, as_paths=False, status=status)
    raw_variables_by_job = dict(get_raw_variables(status=status))
    rows: list[tuple[str, tuple[float, ...]]] = []
    for job_name, rawdata in samples:
        if job_name not in raw_variables_by_job:
            continue
        try:
            costs = job_template_api.calculate_cost((rawdata,), (raw_variables_by_job[job_name],))
        except BAD_RAWDATA_EXCEPTIONS:
            continue
        if costs:
            rows.append((job_name, costs[0]))
    return tuple(rows)


def get_historical_results(*, status: str | None = "completed") -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    normalized_by_job = dict(get_normalized_variables(status=status))
    costs_by_job = dict(calculate_costs(status=status))
    return tuple(
        (job_name, normalized_by_job[job_name], costs_by_job[job_name])
        for job_name in normalized_by_job
        if job_name in costs_by_job
    )


def get_surrogate_training_data() -> dict[str, object]:
    names = job_template_api.get_parameter_names()
    raw_variables_by_job = dict(get_raw_variables(status="completed"))
    normalized_by_job = dict(get_normalized_variables(status="completed"))
    raw_rows = get_rawdata_samples(status="completed", as_paths=False)

    variables: list[tuple[float, ...]] = []
    raw_data: list[tuple[dict[str, object], ...]] = []
    for job_name, rawdata in raw_rows:
        if job_name not in normalized_by_job:
            continue
        try:
            job_template_api.calculate_cost((rawdata,), (raw_variables_by_job[job_name],))
        except BAD_RAWDATA_EXCEPTIONS:
            continue
        variables.append(normalized_by_job[job_name])
        raw_data.append(tuple(rawdata))

    return {
        "parameter_names": names,
        "normalized_variables": tuple(variables),
        "raw_data": tuple(raw_data),
    }


def get_rawdata_diagnostics(
    *,
    job_names: Sequence[str] | None = None,
    status: str | None = "completed",
    include_valid: bool = False,
) -> tuple[dict[str, object], ...]:
    requested = set(str(name) for name in job_names) if job_names is not None else None
    diagnostics: list[dict[str, object]] = []
    for record in read_individual_records():
        job_name = str(record["job_name"])
        if requested is not None and job_name not in requested:
            continue
        if status is not None and str(record.get("status")) != status:
            continue
        for member in rawdata_members_for_record(record):
            diagnostic = _rawdata_diagnostic(job_name, member)
            if include_valid or diagnostic["status"] != "valid":
                diagnostics.append(diagnostic)
    return tuple(diagnostics)


def _rawdata_diagnostic(job_name: str, member: str) -> dict[str, object]:
    base = {
        "job_name": job_name,
        "filename": Path(member).name,
        "archive_member": member,
        "path": f"{paths.RAWDATA_ARCHIVE_PATH}::{member}",
    }
    try:
        validate_rawdata_item(load_archive_member(member))
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
