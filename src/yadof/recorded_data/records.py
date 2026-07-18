"""Record raw evaluation evidence and optimization metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from .manifest_store import (
    append_individual_record_unlocked,
    append_optimization_metadata_unlocked,
    canonical_status,
    find_record,
    metadata_lock,
    metadata_read_lock,
    read_individual_records,
    read_optimization_metadata,
    write_individual_records_unlocked,
)
from .paths import RecordedDataPaths, IND_META_SCHEMA_VERSION, OPT_META_SCHEMA_VERSION
from .rawdata_store import source_files, write_rawdata_files
from .utils import now_utc_text


def safe_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
    forbidden = {
        "cost",
        "costs",
        "objective_costs",
        "created_at",
        "normalized_variables",
        "normalized_variable_table",
        "variables",
        "raw_variables",
        "unnormalized_variables",
    }
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
    storage: RecordedDataPaths,
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
    if "/" in clean_job_name or "\\" in clean_job_name:
        raise ValueError("job_name must not contain path separators")

    clean_status = canonical_status(status)
    source_paths = source_files(rawdata_source)
    if any(path.suffix.lower() != ".npz" for path in source_paths):
        raise ValueError("rawdata_source must contain only .npz files")
    for source_file in source_paths:
        if not source_file.is_file():
            raise FileNotFoundError(source_file)

    if isinstance(raw_variables, Mapping):
        variable_payload: object = {
            str(key): float(value) for key, value in raw_variables.items()
        }
    else:
        variable_payload = [float(value) for value in raw_variables]

    with metadata_lock(storage):
        records = read_individual_records(storage)
        if find_record(records, clean_job_name) is not None and not overwrite:
            raise ValueError(f"record already exists for job {clean_job_name!r}")

        if overwrite:
            records = [
                item
                for item in records
                if str(item.get("job_name")) != clean_job_name
            ]

        rawdata_files, rawdata_metadata = write_rawdata_files(
            storage, clean_job_name, source_paths
        )
        clean_metadata = safe_metadata(job_metadata)
        record = {
            "schema_version": IND_META_SCHEMA_VERSION,
            "job_name": clean_job_name,
            "status": clean_status,
            "raw_variables": variable_payload,
            "rawdata_files": rawdata_files,
            "rawdata_metadata": rawdata_metadata,
            "recorded_at": now_utc_text(),
        }
        _promote_individual_metadata(record, clean_metadata)
        record["job_metadata"] = clean_metadata

        if overwrite:
            records.append(record)
            write_individual_records_unlocked(storage, records)
        else:
            append_individual_record_unlocked(storage, record)
        return record


def record_optimization_metadata(
    storage: RecordedDataPaths, metadata: Mapping[str, object]
) -> dict[str, object]:
    record = {
        "schema_version": OPT_META_SCHEMA_VERSION,
        "recorded_at": now_utc_text(),
        **safe_metadata(metadata),
    }
    with metadata_lock(storage):
        append_optimization_metadata_unlocked(storage, record)
    return record


def record_surrogate_metadata(
    storage: RecordedDataPaths, metadata: Mapping[str, object]
) -> dict[str, object]:
    payload = {"record_type": "surrogate_training", **dict(metadata)}
    payload.setdefault("record_type", "surrogate_training")
    return record_optimization_metadata(storage, payload)


def list_surrogate_metadata(
    storage: RecordedDataPaths,
) -> tuple[dict[str, object], ...]:
    return tuple(
        record
        for record in list_optimization_metadata(storage)
        if str(record.get("record_type")) == "surrogate_training"
    )


def list_records(storage: RecordedDataPaths) -> tuple[dict[str, object], ...]:
    with metadata_read_lock(storage):
        return tuple(dict(record) for record in read_individual_records(storage))


def list_optimization_metadata(
    storage: RecordedDataPaths,
) -> tuple[dict[str, object], ...]:
    with metadata_read_lock(storage):
        return tuple(
            dict(record) for record in read_optimization_metadata(storage)
        )


def get_job_names(
    storage: RecordedDataPaths, *, status: str | None = None
) -> tuple[str, ...]:
    records = list_records(storage)
    return tuple(
        str(record["job_name"])
        for record in records
        if status is None or str(record.get("status")) == status
    )


def _promote_individual_metadata(
    record: dict[str, object], metadata: dict[str, object]
) -> None:
    for key in (
        "run_id",
        "optimization_index",
        "generation_index",
        "population_index",
        "started_at",
        "ended_at",
    ):
        if key in metadata:
            record[key] = metadata.pop(key)
