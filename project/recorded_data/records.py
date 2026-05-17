from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from . import paths
from .manifest_store import (
    append_individual_record_unlocked,
    append_optimization_metadata_unlocked,
    canonical_status,
    find_record,
    metadata_lock,
    read_individual_records,
    read_optimization_metadata,
    write_individual_records_unlocked,
)
from .rawdata_store import append_rawdata_files, remove_archive_members_for_job, source_files
from .utils import now_utc_text


def safe_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
    forbidden = {"cost", "costs", "objective_costs", "normalized_variables", "normalized_variable_table"}
    return {
        str(key): _safe_metadata_value(value, forbidden)
        for key, value in dict(metadata or {}).items()
        if str(key) not in forbidden
    }


def _safe_metadata_value(value: object, forbidden: set[str]) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _safe_metadata_value(item, forbidden)
            for key, item in value.items()
            if str(key) not in forbidden
        }
    if isinstance(value, (list, tuple)):
        return [_safe_metadata_value(item, forbidden) for item in value]
    return value


def record_job_result(
    job_name: str,
    raw_variables: Sequence[float] | Mapping[str, float],
    rawdata_source: str | Path | Sequence[str | Path],
    job_metadata: Mapping[str, object] | None = None,
    *,
    status: str = "completed",
    overwrite: bool = False,
) -> dict[str, object]:
    clean_job_name = str(job_name).strip()
    if not clean_job_name:
        raise ValueError("job_name must not be empty")

    clean_status = canonical_status(status)
    source_paths = source_files(rawdata_source)
    if any(path.suffix.lower() != ".npz" for path in source_paths):
        raise ValueError("rawdata_source must contain only .npz files")
    for source_file in source_paths:
        if not source_file.exists():
            raise FileNotFoundError(source_file)

    if isinstance(raw_variables, Mapping):
        variable_payload: object = {str(key): float(value) for key, value in raw_variables.items()}
    else:
        variable_payload = [float(value) for value in raw_variables]

    with metadata_lock():
        records = read_individual_records()
        if find_record(records, clean_job_name) is not None and not overwrite:
            raise ValueError(f"record already exists for job {clean_job_name!r}")

        if overwrite:
            records = [item for item in records if str(item.get("job_name")) != clean_job_name]
            remove_archive_members_for_job(clean_job_name)

        rawdata_files, rawdata_metadata = append_rawdata_files(clean_job_name, source_paths)
        record = {
            "schema_version": paths.IND_META_SCHEMA_VERSION,
            "job_name": clean_job_name,
            "status": clean_status,
            "raw_variables": variable_payload,
            "rawdata_files": rawdata_files,
            "rawdata_metadata": rawdata_metadata,
            "job_metadata": safe_metadata(job_metadata),
            "recorded_at": now_utc_text(),
        }

        if overwrite:
            records.append(record)
            write_individual_records_unlocked(records)
        else:
            append_individual_record_unlocked(record)
        return record


def record_optimization_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    record = {
        "schema_version": paths.OPT_META_SCHEMA_VERSION,
        "recorded_at": now_utc_text(),
        **safe_metadata(metadata),
    }
    with metadata_lock():
        append_optimization_metadata_unlocked(record)
    return record


def list_records() -> tuple[dict[str, object], ...]:
    return tuple(dict(record) for record in read_individual_records())


def list_optimization_metadata() -> tuple[dict[str, object], ...]:
    return tuple(dict(record) for record in read_optimization_metadata())


def get_job_names(*, status: str | None = None) -> tuple[str, ...]:
    records = read_individual_records()
    return tuple(
        str(record["job_name"])
        for record in records
        if status is None or str(record.get("status")) == status
    )
