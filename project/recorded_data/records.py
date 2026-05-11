from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping, Sequence

from . import paths
from .manifest_store import (
    canonical_status,
    find_record,
    manifest_lock,
    read_manifest,
    record_list,
    write_manifest_unlocked,
)
from .rawdata_store import metadata_from_npz, source_files
from .utils import now_utc_text


def safe_job_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
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

    if isinstance(raw_variables, Mapping):
        variable_payload: object = {str(key): float(value) for key, value in raw_variables.items()}
    else:
        variable_payload = [float(value) for value in raw_variables]

    with manifest_lock():
        manifest = read_manifest()
        records = record_list(manifest)
        if find_record(records, clean_job_name) is not None and not overwrite:
            raise ValueError(f"record already exists for job {clean_job_name!r}")

        job_rawdata_dir = paths.RAWDATA_ROOT / clean_job_name
        if job_rawdata_dir.exists() and overwrite:
            shutil.rmtree(job_rawdata_dir)
        job_rawdata_dir.mkdir(parents=True, exist_ok=True)

        rawdata_files: list[str] = []
        rawdata_metadata: dict[str, object] = {}
        for source_file in source_paths:
            if not source_file.exists():
                raise FileNotFoundError(source_file)
            destination = job_rawdata_dir / source_file.name
            shutil.copy2(source_file, destination)
            rawdata_files.append(destination.name)
            rawdata_metadata[destination.name] = metadata_from_npz(destination)

        record = {
            "job_name": clean_job_name,
            "status": clean_status,
            "raw_variables": variable_payload,
            "rawdata_files": rawdata_files,
            "rawdata_metadata": rawdata_metadata,
            "job_metadata": safe_job_metadata(job_metadata),
            "recorded_at": now_utc_text(),
        }

        records[:] = [item for item in records if str(item.get("job_name")) != clean_job_name]
        records.append(record)
        write_manifest_unlocked(manifest)
        return record


def list_records() -> tuple[dict[str, object], ...]:
    return tuple(dict(record) for record in record_list(read_manifest()))


def get_job_names(*, status: str | None = None) -> tuple[str, ...]:
    records = record_list(read_manifest())
    return tuple(
        str(record["job_name"])
        for record in records
        if status is None or str(record.get("status")) == status
    )
