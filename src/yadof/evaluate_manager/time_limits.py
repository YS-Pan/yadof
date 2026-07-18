"""Adaptive per-job execution limits for the HTCondor backend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
from typing import Mapping, Sequence

from ..config import LoadedConfig, load_config
from ..recorded_data import api as recorded_data_api
from ..workspace import WorkspaceContext

from .types import JobSpec


@dataclass(frozen=True)
class HTCondorTimeLimit:
    """The effective ``allowed_execute_duration`` for one submitted job."""

    seconds: int | None
    source: str
    sample_count: int


def time_limit_for_job(
    workspace: WorkspaceContext | str | Path,
    job: JobSpec,
    *,
    config: LoadedConfig | None = None,
) -> HTCondorTimeLimit:
    """Calculate one job's execution limit without changing source config.

    An unindexed job is a smoke test and deliberately has no time limit.  In
    automatic mode generation zero uses the newest successful distributed smoke
    measurement.  Later generations use the preceding generation from the same
    optimizer run after trimming the configured upper tail.
    """

    effective = load_config(workspace) if config is None else config
    generation_index = _as_generation_index(job.generation_index)
    if generation_index is None:
        return HTCondorTimeLimit(seconds=None, source="smoke_no_timeout", sample_count=0)

    configured_seconds = _positive_seconds(
        effective.HTCONDOR_JOB_TIMEOUT_SEC,
        "HTCONDOR_JOB_TIMEOUT_SEC",
    )
    mode = str(effective.HTCONDOR_JOB_TIMEOUT_MODE).strip().lower()
    if mode == "fixed":
        return HTCondorTimeLimit(
            seconds=configured_seconds,
            source="configured_fixed",
            sample_count=0,
        )
    if mode != "auto":
        raise ValueError("HTCONDOR_JOB_TIMEOUT_MODE must be 'auto' or 'fixed'")

    multiplier = _positive_float(
        effective.HTCONDOR_JOB_TIMEOUT_MULTIPLIER,
        "HTCONDOR_JOB_TIMEOUT_MULTIPLIER",
    )
    if generation_index == 0 and not _as_bool(
        effective.OPTIMIZE_SMOKE_TEST_ENABLED
    ):
        return HTCondorTimeLimit(
            seconds=max(1, math.ceil(configured_seconds * multiplier)),
            source="configured_smoke_fallback",
            sample_count=1,
        )

    durations, source = _calibration_durations(
        effective, job, generation_index=generation_index
    )
    if durations:
        trim_fraction = _fraction(
            effective.HTCONDOR_JOB_TIMEOUT_TRIM_TOP_FRACTION,
            "HTCONDOR_JOB_TIMEOUT_TRIM_TOP_FRACTION",
        )
        selected = (
            durations[-1]
            if generation_index == 0
            else _trimmed_high_duration(durations, trim_fraction=trim_fraction)
        )
        if selected is not None:
            return HTCondorTimeLimit(
                seconds=max(1, math.ceil(selected * multiplier)),
                source=source,
                sample_count=len(durations),
            )

    return HTCondorTimeLimit(
        seconds=configured_seconds,
        source="configured_fallback",
        sample_count=0,
    )


def _calibration_durations(
    config: LoadedConfig,
    job: JobSpec,
    *,
    generation_index: int,
) -> tuple[list[float], str]:
    records = recorded_data_api.list_records(config.workspace)
    if generation_index == 0:
        smoke_candidates: list[tuple[str, float]] = []
        for record in records:
            if _as_generation_index(record.get("generation_index")) is not None:
                continue
            if str(record.get("status", "")).lower() != "completed":
                continue
            if not _is_htcondor_record(record):
                continue
            duration = _duration_from_record(record)
            if duration is None or not math.isfinite(duration):
                continue
            smoke_candidates.append((str(record.get("recorded_at") or ""), duration))
        if not smoke_candidates:
            return [], "missing_smoke_calibration"
        _recorded_at, latest_duration = max(smoke_candidates, key=lambda item: item[0])
        return [latest_duration], "smoke_calibration"

    target_generation = generation_index - 1
    durations: list[float] = []
    for record in records:
        if _as_generation_index(record.get("generation_index")) != target_generation:
            continue
        if job.run_id is not None and str(record.get("run_id") or "") != str(job.run_id):
            continue
        if not _is_htcondor_record(record):
            continue
        duration = _duration_from_record(record)
        if duration is not None:
            durations.append(duration)
    return durations, f"generation_{target_generation}_calibration"


def _is_htcondor_record(record: Mapping[str, object]) -> bool:
    metadata = record.get("job_metadata")
    return isinstance(metadata, Mapping) and str(metadata.get("engine", "")).lower() == "htcondor"


def _duration_from_record(record: Mapping[str, object]) -> float | None:
    if str(record.get("status", "")).lower() == "timeout":
        return float("inf")

    metadata = record.get("job_metadata")
    if isinstance(metadata, Mapping):
        remote_wall = _nonnegative_number(metadata.get("condor_remote_wall_clock_sec"))
        if remote_wall is not None:
            suspended = _nonnegative_number(metadata.get("condor_cumulative_suspension_sec")) or 0.0
            execution_seconds = remote_wall - suspended
            if execution_seconds > 0.0:
                return execution_seconds

    started_at = record.get("started_at")
    ended_at = record.get("ended_at")
    if started_at is None or ended_at is None:
        return None
    try:
        duration = (_parse_datetime(ended_at) - _parse_datetime(started_at)).total_seconds()
    except (TypeError, ValueError):
        return None
    return duration if math.isfinite(duration) and duration > 0.0 else None


def _trimmed_high_duration(values: Sequence[float], *, trim_fraction: float) -> float | None:
    """Return the upper-tail-trimmed maximum with timeout-specific handling.

    Timed-out jobs are represented by infinity.  If their count exceeds the
    configured trim capacity, all infinities are ignored and the largest finite
    duration is used, as a finite limit is still required for the next generation.
    """

    ordered = sorted(float(value) for value in values if float(value) > 0.0)
    if not ordered:
        return None
    trim_count = min(len(ordered) - 1, math.ceil(len(ordered) * trim_fraction))
    infinity_count = sum(1 for value in ordered if not math.isfinite(value))
    if infinity_count > trim_count:
        finite_values = [value for value in ordered if math.isfinite(value)]
        return max(finite_values) if finite_values else None
    selected = ordered[len(ordered) - trim_count - 1]
    return selected if math.isfinite(selected) else None


def _parse_datetime(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _as_generation_index(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _positive_seconds(value: object, setting_name: str) -> int:
    return max(1, math.ceil(_positive_float(value, setting_name)))


def _positive_float(value: object, setting_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{setting_name} must be a positive number, got {value!r}") from exc
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{setting_name} must be a positive number, got {value!r}")
    return parsed


def _nonnegative_number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0.0 else None


def _fraction(value: object, setting_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{setting_name} must be between 0 and 1, got {value!r}") from exc
    if not math.isfinite(parsed) or not 0.0 <= parsed < 1.0:
        raise ValueError(f"{setting_name} must be between 0 and 1, got {value!r}")
    return parsed


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
