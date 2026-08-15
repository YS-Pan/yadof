"""Record-envelope creation, direct publication, and immutable events."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Mapping, Sequence
import uuid

from ..job_template import api as job_template_api
from ..workspace import WorkspaceContext
from .campaign_lock import CampaignLock
from .paths import RecordedDataPaths, VALID_RECORD_STATUSES
from .rawdata import RawDataSource, own_rawdata_source, reservation_bytes
from .segment_store import (
    CatalogSnapshot,
    RecordEnvelope,
    candidate_identity,
    discover_catalog,
    next_sequence_by_directory,
    publish_segment,
    segment_counter_key,
)
from .utils import json_ready, now_utc_text


JobRecordRequest = tuple[
    str,
    Sequence[float] | Mapping[str, float],
    RawDataSource,
    Mapping[str, object] | None,
    str,
]


def build_envelope(
    workspace: WorkspaceContext,
    job_name: str,
    raw_variables: Sequence[float] | Mapping[str, float],
    rawdata_source: RawDataSource,
    job_metadata: Mapping[str, object] | None = None,
    *,
    status: str = "completed",
) -> RecordEnvelope:
    clean_name = str(job_name).strip()
    if not clean_name or "/" in clean_name or "\\" in clean_name:
        raise ValueError("job_name must be non-empty and contain no path separator")
    clean_status = canonical_status(status)
    variable_payload = named_raw_variables(
        workspace, raw_variables, allow_partial=clean_status != "completed"
    )
    items = own_rawdata_source(rawdata_source)
    return build_owned_envelope(
        workspace,
        clean_name,
        variable_payload,
        items,
        job_metadata,
        status=clean_status,
    )


def build_owned_envelope(
    workspace: WorkspaceContext,
    job_name: str,
    raw_variables: Sequence[float] | Mapping[str, float],
    items,
    job_metadata: Mapping[str, object] | None = None,
    *,
    status: str = "completed",
) -> RecordEnvelope:
    """Build an envelope without reloading/copying already owned rawData."""

    clean_name = str(job_name).strip()
    clean_status = canonical_status(status)
    variable_payload = named_raw_variables(
        workspace, raw_variables, allow_partial=clean_status != "completed"
    )
    items = tuple(items)
    if clean_status == "completed" and not items:
        raise ValueError("completed result must contain rawData")
    metadata = safe_metadata(job_metadata)
    record: dict[str, object] = {
        "job_name": clean_name,
        "status": clean_status,
        "raw_variables": variable_payload,
        "rawdata_files": [item.filename for item in items],
        "recorded_at": now_utc_text(),
    }
    _promote_individual_metadata(record, metadata)
    record["job_metadata"] = metadata
    identity = candidate_identity(record)
    encoded_metadata = json.dumps(json_ready(record), default=str).encode("utf-8")
    return RecordEnvelope(
        identity,
        record,
        items,
        reservation_bytes(items, len(encoded_metadata)),
    )


def publish_direct(
    storage: RecordedDataPaths,
    envelopes: Sequence[RecordEnvelope],
) -> tuple[dict[str, object], ...]:
    """Publish explicit API writes without the campaign background recorder."""

    if not envelopes:
        return ()
    lock = CampaignLock(storage.campaign_lock_path)
    lock.acquire()
    try:
        catalog = discover_catalog(storage)
        existing = {reference.candidate_id for reference in catalog.references}
        input_ids: set[str] = set()
        duplicates = []
        for envelope in envelopes:
            if (
                envelope.candidate_id in existing
                or envelope.candidate_id in input_ids
            ):
                duplicates.append(envelope.record.get("job_name"))
            input_ids.add(envelope.candidate_id)
        if duplicates:
            raise ValueError(
                "record already exists for job(s): "
                + ", ".join(repr(str(name)) for name in duplicates)
            )
        counters = next_sequence_by_directory(storage)
        offset = 0
        while offset < len(envelopes):
            first = envelopes[offset]
            group: list[RecordEnvelope] = []
            while offset < len(envelopes):
                candidate = envelopes[offset]
                if (
                    len(group) >= 16
                    or candidate.run_id != first.run_id
                    or candidate.generation_index != first.generation_index
                ):
                    break
                group.append(candidate)
                offset += 1
            key = segment_counter_key(first.run_id, first.generation_index)
            sequence = counters.get(key, 0)
            publish_segment(storage, group, sequence=sequence)
            counters[key] = sequence + 1
        return tuple(dict(envelope.record) for envelope in envelopes)
    finally:
        lock.release()


def list_records(storage: RecordedDataPaths) -> tuple[dict[str, object], ...]:
    return tuple(dict(reference.record) for reference in discover_catalog(storage).references)


def get_job_names(
    storage: RecordedDataPaths, *, status: str | None = None
) -> tuple[str, ...]:
    return tuple(
        str(record["job_name"])
        for record in list_records(storage)
        if status is None or str(record.get("status")) == status
    )


def record_optimization_metadata(
    storage: RecordedDataPaths, metadata: Mapping[str, object]
) -> dict[str, object]:
    record = {
        "recorded_at": now_utc_text(),
        **safe_metadata(metadata),
    }
    _publish_event(storage, record)
    return record


def record_surrogate_metadata(
    storage: RecordedDataPaths, metadata: Mapping[str, object]
) -> dict[str, object]:
    return record_optimization_metadata(
        storage, {"record_type": "surrogate_training", **dict(metadata)}
    )


def list_optimization_metadata(
    storage: RecordedDataPaths,
) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    try:
        paths = tuple(
            sorted(
                storage.metadata_directory.rglob("event_*.json"),
                key=lambda item: item.as_posix().casefold(),
            )
        )
    except OSError:
        return ()
    for path in paths:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            records.append(loaded)
    return tuple(records)


def list_surrogate_metadata(
    storage: RecordedDataPaths,
) -> tuple[dict[str, object], ...]:
    return tuple(
        record
        for record in list_optimization_metadata(storage)
        if str(record.get("record_type")) == "surrogate_training"
    )


def named_raw_variables(
    workspace: WorkspaceContext,
    raw_variables: Sequence[float] | Mapping[str, float],
    *,
    allow_partial: bool = False,
) -> dict[str, float]:
    names = tuple(job_template_api.get_parameter_names(workspace))
    if isinstance(raw_variables, Mapping):
        missing = [name for name in names if name not in raw_variables]
        if missing and not allow_partial:
            raise ValueError(
                "raw_variables is missing parameter(s): " + ", ".join(missing)
            )
        return {
            name: float(raw_variables[name])
            for name in names
            if name in raw_variables
        }
    values = tuple(float(value) for value in raw_variables)
    if len(values) != len(names) and not allow_partial:
        raise ValueError(f"expected {len(names)} raw variables, got {len(values)}")
    return dict(zip(names, values))


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


def canonical_status(status: str) -> str:
    clean = str(status).strip().lower()
    if clean == "done":
        clean = "completed"
    if clean not in VALID_RECORD_STATUSES:
        raise ValueError(f"status must be one of {VALID_RECORD_STATUSES!r}")
    return clean


def catalog_snapshot(storage: RecordedDataPaths) -> CatalogSnapshot:
    return discover_catalog(storage)


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


def _promote_individual_metadata(
    record: dict[str, object], metadata: dict[str, object]
) -> None:
    for key in (
        "run_id",
        "campaign_id",
        "optimization_index",
        "generation_index",
        "population_index",
        "started_at",
        "ended_at",
        "interpretation_fingerprint",
        "evaluation_fingerprint",
        "task_snapshot_id",
    ):
        if key in metadata:
            record[key] = metadata.pop(key)


def _publish_event(storage: RecordedDataPaths, record: Mapping[str, object]) -> None:
    record_type = str(record.get("record_type") or "event")
    safe_type = "".join(
        character if character.isalnum() or character in "_.-" else "_"
        for character in record_type
    )
    directory = storage.metadata_directory / safe_type
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"event_{now_utc_text().replace(':', '').replace('+', '_')}_{uuid.uuid4().hex}.json"
    destination = directory / filename
    fd, temporary_name = tempfile.mkstemp(
        prefix=f"{filename}.", suffix=".tmp", dir=str(directory)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                json_ready(record),
                stream,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            stream.write("\n")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


__all__ = [
    "JobRecordRequest",
    "build_envelope",
    "build_owned_envelope",
    "canonical_status",
    "catalog_snapshot",
    "get_job_names",
    "list_optimization_metadata",
    "list_records",
    "list_surrogate_metadata",
    "named_raw_variables",
    "publish_direct",
    "record_optimization_metadata",
    "record_surrogate_metadata",
    "safe_metadata",
]
