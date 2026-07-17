"""Yadof-managed memory and disk retries for held HTCondor jobs.

HTCondor is responsible only for enforcing one concrete resource request.  When a
job is held because it exceeded memory or disk, the submit side removes that held
cluster, doubles the exhausted request, and submits a fresh cluster for the same
prepared individual.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shutil
from typing import Literal, Mapping

try:
    from project.config import all as project_config
except ImportError:  # Allows running from inside the project package directory.
    from ..config import all as project_config

from .config import (
    CONDOR_CLUSTER_ID_FILE_NAME,
    CONDOR_LOG_FILE_NAME,
    CONDOR_STDERR_FILE_NAME,
    CONDOR_STDOUT_FILE_NAME,
    CONDOR_SUBMIT_STDERR_FILE_NAME,
    CONDOR_SUBMIT_STDOUT_FILE_NAME,
    INDIVIDUAL_METADATA_FILE_NAME,
    RAW_DATA_DIR_NAME,
    RAW_DATA_TRANSFER_ZIP_NAME,
)
from .resource_requests import HTCondorResourceRequest


ResourceKind = Literal["memory", "disk"]

_RESOURCE_HOLD_CODE = 34
_RESOURCE_HOLD_SUBCODES: dict[int, ResourceKind] = {102: "memory", 104: "disk"}
_RETRY_FILE_ARTIFACTS = (
    CONDOR_CLUSTER_ID_FILE_NAME,
    CONDOR_LOG_FILE_NAME,
    CONDOR_STDERR_FILE_NAME,
    CONDOR_STDOUT_FILE_NAME,
    CONDOR_SUBMIT_STDERR_FILE_NAME,
    CONDOR_SUBMIT_STDOUT_FILE_NAME,
    INDIVIDUAL_METADATA_FILE_NAME,
    f"{INDIVIDUAL_METADATA_FILE_NAME}.tmp",
    RAW_DATA_TRANSFER_ZIP_NAME,
    f"{RAW_DATA_TRANSFER_ZIP_NAME}.tmp",
    "batch.log",
    "cost.json",
)
_RETRY_DIRECTORY_ARTIFACTS = (RAW_DATA_DIR_NAME, "._home", "._appdata", "._localappdata", "._tmp")


@dataclass(frozen=True)
class YadofResourceRetryState:
    """Resource request and completed retry history for one individual."""

    request: HTCondorResourceRequest
    max_retries_per_resource: int
    memory_retry_count: int = 0
    disk_retry_count: int = 0
    history: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class YadofResourceRetryDecision:
    """Decision for one resource-limit hold after its old cluster is removed."""

    resource: ResourceKind
    should_retry: bool
    state: YadofResourceRetryState


def new_resource_retry_state(request: HTCondorResourceRequest) -> YadofResourceRetryState:
    limit = _nonnegative_int(
        getattr(project_config, "YADOF_RESOURCE_RETRY_DOUBLINGS", 4),
        "YADOF_RESOURCE_RETRY_DOUBLINGS",
    )
    return YadofResourceRetryState(request=request, max_retries_per_resource=limit)


def resource_hold_kind(hold_info: Mapping[str, object]) -> ResourceKind | None:
    """Classify the standard HTCondor out-of-memory/out-of-disk hold codes."""

    code = _as_int(hold_info.get("condor_hold_reason_code"))
    subcode = _as_int(hold_info.get("condor_hold_reason_subcode"))
    if code != _RESOURCE_HOLD_CODE or subcode is None:
        return None
    return _RESOURCE_HOLD_SUBCODES.get(subcode)


def decide_resource_retry(
    state: YadofResourceRetryState,
    *,
    hold_info: Mapping[str, object],
    resource_usage: Mapping[str, object],
    cluster_id: int | None,
) -> YadofResourceRetryDecision | None:
    """Return the next doubled request, or an exhausted terminal decision."""

    resource = resource_hold_kind(hold_info)
    if resource is None:
        return None

    retry_count = state.memory_retry_count if resource == "memory" else state.disk_retry_count
    exhausted = retry_count >= state.max_retries_per_resource
    event: dict[str, object] = {
        "action": "exhausted" if exhausted else "retry",
        "resource": resource,
        "cluster_id": cluster_id,
        "hold_reason_code": _RESOURCE_HOLD_CODE,
        "hold_reason_subcode": 102 if resource == "memory" else 104,
        "hold_reason": str(hold_info.get("condor_hold_reason") or ""),
        "requested_memory_mib": state.request.memory_mib,
        "requested_disk_kib": state.request.disk_kib,
        "retry_limit_per_resource": state.max_retries_per_resource,
    }
    _copy_if_number(resource_usage, "condor_memory_usage_mib", event, "observed_memory_mib")
    _copy_if_number(resource_usage, "condor_disk_usage_kib", event, "observed_disk_kib")

    if exhausted:
        next_state = replace(state, history=state.history + (event,))
        return YadofResourceRetryDecision(resource=resource, should_retry=False, state=next_state)

    if resource == "memory":
        next_request = replace(state.request, memory_mib=state.request.memory_mib * 2)
        event["next_requested_memory_mib"] = next_request.memory_mib
        next_state = replace(
            state,
            request=next_request,
            memory_retry_count=state.memory_retry_count + 1,
            history=state.history + (event,),
        )
    else:
        next_request = replace(state.request, disk_kib=state.request.disk_kib * 2)
        event["next_requested_disk_kib"] = next_request.disk_kib
        next_state = replace(
            state,
            request=next_request,
            disk_retry_count=state.disk_retry_count + 1,
            history=state.history + (event,),
        )
    return YadofResourceRetryDecision(resource=resource, should_retry=True, state=next_state)


def resource_retry_metadata(state: YadofResourceRetryState) -> dict[str, object]:
    last_event = state.history[-1] if state.history else {}
    exhausted = last_event.get("action") == "exhausted"
    metadata: dict[str, object] = {
        "yadof_resource_retry_limit_per_resource": state.max_retries_per_resource,
        "yadof_resource_retry_memory_count": state.memory_retry_count,
        "yadof_resource_retry_disk_count": state.disk_retry_count,
        "yadof_resource_retry_total_count": state.memory_retry_count + state.disk_retry_count,
        "yadof_resource_retry_history": [dict(event) for event in state.history],
        "yadof_resource_retry_exhausted": exhausted,
    }
    if exhausted:
        metadata["yadof_resource_retry_exhausted_resource"] = last_event.get("resource")
    return metadata


def reset_job_for_resource_retry(job_dir: Path) -> None:
    """Remove only attempt outputs that would contaminate a fresh submission."""

    job_dir = Path(job_dir)
    for name in _RETRY_FILE_ARTIFACTS:
        (job_dir / name).unlink(missing_ok=True)
    for name in _RETRY_DIRECTORY_ARTIFACTS:
        path = job_dir / name
        if path.exists():
            shutil.rmtree(path)


def _copy_if_number(
    source: Mapping[str, object], source_key: str, target: dict[str, object], target_key: str
) -> None:
    value = source.get(source_key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        target[target_key] = value


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nonnegative_int(value: object, setting_name: str) -> int:
    parsed = _as_int(value)
    if parsed is None or parsed < 0:
        raise ValueError(f"{setting_name} must be a non-negative integer, got {value!r}")
    return parsed
