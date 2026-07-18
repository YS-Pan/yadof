"""Adaptive HTCondor memory and disk request calculation.

CPU requests intentionally remain a user-selected scheduler policy.  Memory and
disk requests are recalculated from resource measurements already recorded with
the preceding smoke test or optimization generation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from pathlib import Path
from typing import Mapping, Sequence

from ..config import LoadedConfig, load_config
from ..recorded_data import api as recorded_data_api
from ..workspace import WorkspaceContext

from .config import htcondor_request_cpus, htcondor_request_disk, htcondor_request_memory
from .types import JobSpec


_QUANTITY_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([kmgt]b?|)\s*$", re.IGNORECASE)
_MEMORY_FACTORS_MIB = {"": 1.0, "k": 1.0 / 1024.0, "kb": 1.0 / 1024.0, "m": 1.0, "mb": 1.0, "g": 1024.0, "gb": 1024.0, "t": 1024.0**2, "tb": 1024.0**2}
_DISK_FACTORS_KIB = {"": 1.0, "k": 1.0, "kb": 1.0, "m": 1024.0, "mb": 1024.0, "g": 1024.0**2, "gb": 1024.0**2, "t": 1024.0**3, "tb": 1024.0**3}


@dataclass(frozen=True)
class HTCondorResourceRequest:
    """One concrete resource request emitted into a generated submit file."""

    cpus: int
    memory_mib: int
    disk_kib: int
    source: str
    sample_count: int

    @property
    def memory_text(self) -> str:
        return f"{self.memory_mib}MB"

    @property
    def disk_text(self) -> str:
        return f"{self.disk_kib}KB"

def request_for_job(
    workspace: WorkspaceContext | str | Path,
    job: JobSpec,
    *,
    config: LoadedConfig | None = None,
) -> HTCondorResourceRequest:
    """Return the initial CPU, memory, and disk values for one Condor job.

    A normal distributed smoke test has no ``generation_index``.  Generation zero
    consumes those smoke-test measurements; later generations consume only the
    preceding generation from the same optimizer run.  Missing measurements leave
    the user-configured bootstrap values in effect.
    """

    effective = load_config(workspace) if config is None else config
    base_memory_mib = _quantity_as_units(htcondor_request_memory(effective), _MEMORY_FACTORS_MIB, "HTCONDOR_REQUEST_MEMORY")
    base_disk_kib = _quantity_as_units(htcondor_request_disk(effective), _DISK_FACTORS_KIB, "HTCONDOR_REQUEST_DISK")
    disk_multiplier = _positive_float(effective.HTCONDOR_REQUEST_DISK_MULTIPLIER, "HTCONDOR_REQUEST_DISK_MULTIPLIER")
    memory_mib = base_memory_mib
    disk_kib = _scaled_quantity(base_disk_kib, disk_multiplier)
    source = "configured_default"
    sample_count = 0

    measurements, calibration_source = _calibration_measurements(effective, job)
    if measurements is not None:
        memory_values, disk_values = measurements
        sample_count = max(len(memory_values), len(disk_values))
        bootstrap_multiplier = (
            _positive_float(
                effective.HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER,
                "HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER",
            )
            if _generation_index(job) == 0
            else 1.0
        )
        if memory_values:
            memory_mib = _scaled_quantity(
                _trimmed_high(
                    memory_values,
                    trim_fraction=float(effective.HTCONDOR_RESOURCE_TRIM_TOP_FRACTION),
                ),
                bootstrap_multiplier,
            )
        if disk_values:
            disk_kib = _scaled_quantity(
                _trimmed_high(
                    disk_values,
                    trim_fraction=float(effective.HTCONDOR_RESOURCE_TRIM_TOP_FRACTION),
                ),
                bootstrap_multiplier * disk_multiplier,
            )
        source = calibration_source
    elif (
        _generation_index(job) == 0
        and _as_bool(effective.HTCONDOR_RESOURCE_AUTODETECT_ENABLED)
        and not _as_bool(effective.OPTIMIZE_SMOKE_TEST_ENABLED)
    ):
        bootstrap_multiplier = _positive_float(
            effective.HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER,
            "HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER",
        )
        memory_mib = _scaled_quantity(base_memory_mib, bootstrap_multiplier)
        disk_kib = _scaled_quantity(base_disk_kib, bootstrap_multiplier * disk_multiplier)
        source = "configured_smoke_fallback"
        sample_count = 1

    return HTCondorResourceRequest(
        cpus=max(1, int(htcondor_request_cpus(effective))),
        memory_mib=memory_mib,
        disk_kib=disk_kib,
        source=source,
        sample_count=sample_count,
    )


def _calibration_measurements(
    config: LoadedConfig, job: JobSpec
) -> tuple[tuple[list[float], list[float]] | None, str]:
    if not _as_bool(config.HTCONDOR_RESOURCE_AUTODETECT_ENABLED):
        return None, "autodetect_disabled"
    generation_index = _generation_index(job)
    if generation_index is None:
        return None, "smoke_default"
    if generation_index == 0 and not _as_bool(
        config.OPTIMIZE_SMOKE_TEST_ENABLED
    ):
        return None, "smoke_disabled"

    target_generation = None if generation_index == 0 else generation_index - 1
    memory_values: list[float] = []
    disk_values: list[float] = []
    for record in recorded_data_api.list_records(config.workspace):
        if not _is_matching_calibration_record(record, job=job, target_generation=target_generation):
            continue
        metadata = record.get("job_metadata")
        if not isinstance(metadata, Mapping) or str(metadata.get("engine", "")).lower() != "htcondor":
            continue
        memory = _as_positive_number(metadata.get("condor_memory_usage_mib"))
        disk = _as_positive_number(metadata.get("condor_disk_usage_kib"))
        if memory is not None:
            memory_values.append(memory)
        if disk is not None:
            disk_values.append(disk)

    if not memory_values and not disk_values:
        return None, "missing_calibration"
    if target_generation is None:
        return (memory_values, disk_values), "smoke_calibration"
    return (memory_values, disk_values), f"generation_{target_generation}_calibration"


def _is_matching_calibration_record(
    record: Mapping[str, object], *, job: JobSpec, target_generation: int | None
) -> bool:
    record_generation = _as_generation_index(record.get("generation_index"))
    if record_generation != target_generation:
        return False
    if target_generation is None:
        return True
    if job.run_id is None:
        return True
    return str(record.get("run_id") or "") == str(job.run_id)


def _generation_index(job: JobSpec) -> int | None:
    return _as_generation_index(job.generation_index)


def _as_generation_index(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _trimmed_high(values: Sequence[float], *, trim_fraction: float) -> float:
    """Return the maximum after discarding the configured highest fraction."""

    ordered = sorted(float(value) for value in values if float(value) > 0.0)
    if not ordered:
        raise ValueError("resource calibration requires at least one positive measurement")
    clean_fraction = _fraction(trim_fraction)
    trim_count = min(len(ordered) - 1, math.ceil(len(ordered) * clean_fraction))
    return ordered[len(ordered) - trim_count - 1]


def _quantity_as_units(value: object, factors: Mapping[str, float], setting_name: str) -> int:
    match = _QUANTITY_RE.match(str(value))
    if match is None:
        raise ValueError(f"{setting_name} must be a positive HTCondor quantity, got {value!r}")
    factor = factors[match.group(2).lower()]
    parsed = float(match.group(1)) * factor
    if parsed <= 0.0:
        raise ValueError(f"{setting_name} must be positive, got {value!r}")
    return max(1, math.ceil(parsed))


def _scaled_quantity(value: float | int, multiplier: float) -> int:
    return max(1, math.ceil(float(value) * multiplier))


def _as_positive_number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0.0 else None


def _positive_float(value: object, setting_name: str) -> float:
    parsed = _as_positive_number(value)
    if parsed is None:
        raise ValueError(f"{setting_name} must be a positive number, got {value!r}")
    return parsed


def _fraction(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"HTCONDOR_RESOURCE_TRIM_TOP_FRACTION must be between 0 and 1, got {value!r}") from exc
    if not math.isfinite(parsed) or not 0.0 <= parsed < 1.0:
        raise ValueError(f"HTCONDOR_RESOURCE_TRIM_TOP_FRACTION must be between 0 and 1, got {value!r}")
    return parsed


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
