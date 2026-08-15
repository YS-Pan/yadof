"""Shared resource calibration for local and HTCondor evaluation backends."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping, Sequence

from ..config import LoadedConfig
from ..recorded_data import api as recorded_data_api


_QUANTITY_RE = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([kmgt]b?|)\s*$",
    re.IGNORECASE,
)
_MEMORY_FACTORS_MIB = {
    "": 1.0,
    "k": 1.0 / 1024.0,
    "kb": 1.0 / 1024.0,
    "m": 1.0,
    "mb": 1.0,
    "g": 1024.0,
    "gb": 1024.0,
    "t": 1024.0**2,
    "tb": 1024.0**2,
}
_DISK_FACTORS_KIB = {
    "": 1.0,
    "k": 1.0,
    "kb": 1.0,
    "m": 1024.0,
    "mb": 1024.0,
    "g": 1024.0**2,
    "gb": 1024.0**2,
    "t": 1024.0**3,
    "tb": 1024.0**3,
}
_CPU_KEYS = ("resource_cpu_usage_cores", "local_average_cpu_cores", "condor_cpus_usage")
_MEMORY_KEYS = (
    "resource_memory_usage_mib",
    "local_peak_memory_usage_mib",
    "condor_memory_usage_mib",
)
_DISK_KEYS = (
    "resource_disk_usage_kib",
    "local_disk_usage_kib",
    "condor_disk_usage_kib",
)


@dataclass(frozen=True)
class ResourceCalibration:
    """Upper-tail-trimmed measurements selected from prior recorded jobs."""

    cpu_cores: float | None
    memory_mib: float | None
    disk_kib: float | None
    source: str
    sample_count: int


@dataclass(frozen=True)
class ResourceEstimate:
    """Concrete per-job estimate derived from configuration and prior evidence."""

    cpus: int
    memory_mib: int
    disk_kib: int
    source: str
    sample_count: int


def estimate_resources(
    config: LoadedConfig,
    *,
    generation_index: int | None,
    run_id: str | None,
    base_cpus: int,
    base_memory_mib: int,
    base_disk_kib: int,
    autodetect_enabled: bool,
    calibrate_cpus: bool,
    disk_multiplier: float = 1.0,
    history_records: Sequence[Mapping[str, object]] | None = None,
) -> ResourceEstimate:
    """Return one shared local/distributed per-job resource estimate."""

    cpus = max(1, int(base_cpus))
    memory_mib = max(1, int(base_memory_mib))
    disk_kib = scaled_quantity(base_disk_kib, positive_float(disk_multiplier, "disk_multiplier"))
    source = "configured_default"
    sample_count = 0

    calibration = calibration_for_generation(
        config,
        generation_index=generation_index,
        run_id=run_id,
        autodetect_enabled=autodetect_enabled,
        trim_fraction=float(config.HTCONDOR_RESOURCE_TRIM_TOP_FRACTION),
        history_records=history_records,
    )
    if calibration is not None:
        sample_count = calibration.sample_count
        bootstrap_multiplier = (
            positive_float(
                config.HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER,
                "HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER",
            )
            if generation_index == 0
            else 1.0
        )
        if calibrate_cpus and calibration.cpu_cores is not None:
            cpus = max(1, math.ceil(calibration.cpu_cores))
        if calibration.memory_mib is not None:
            memory_mib = scaled_quantity(
                calibration.memory_mib,
                bootstrap_multiplier,
            )
        if calibration.disk_kib is not None:
            disk_kib = scaled_quantity(
                calibration.disk_kib,
                bootstrap_multiplier * disk_multiplier,
            )
        source = calibration.source
    elif (
        generation_index == 0
        and autodetect_enabled
        and not bool(config.OPTIMIZE_SMOKE_TEST_ENABLED)
    ):
        bootstrap_multiplier = positive_float(
            config.HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER,
            "HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER",
        )
        memory_mib = scaled_quantity(memory_mib, bootstrap_multiplier)
        disk_kib = scaled_quantity(disk_kib, bootstrap_multiplier)
        source = "configured_smoke_fallback"
        sample_count = 1

    return ResourceEstimate(
        cpus=cpus,
        memory_mib=memory_mib,
        disk_kib=disk_kib,
        source=source,
        sample_count=sample_count,
    )


def calibration_for_generation(
    config: LoadedConfig,
    *,
    generation_index: int | None,
    run_id: str | None,
    autodetect_enabled: bool,
    trim_fraction: float,
    history_records: Sequence[Mapping[str, object]] | None = None,
) -> ResourceCalibration | None:
    """Select compatible smoke or preceding-generation resource observations."""

    if not autodetect_enabled or generation_index is None:
        return None
    if generation_index == 0 and not bool(config.OPTIMIZE_SMOKE_TEST_ENABLED):
        return None

    target_generation = None if generation_index == 0 else generation_index - 1
    cpu_values: list[float] = []
    memory_values: list[float] = []
    disk_values: list[float] = []
    records = history_records
    if records is None:
        try:
            records = recorded_data_api.list_records(config.workspace)
        except Exception:
            records = ()
    for record in records:
        if _generation_index(record.get("generation_index")) != target_generation:
            continue
        if str(record.get("status", "")).lower() != "completed":
            continue
        if (
            target_generation is not None
            and run_id is not None
            and str(record.get("run_id") or "") != str(run_id)
        ):
            continue
        metadata = record.get("job_metadata")
        if not isinstance(metadata, Mapping):
            continue
        _append_first_positive(metadata, _CPU_KEYS, cpu_values)
        _append_first_positive(metadata, _MEMORY_KEYS, memory_values)
        _append_first_positive(metadata, _DISK_KEYS, disk_values)

    if not cpu_values and not memory_values and not disk_values:
        return None
    source = (
        "smoke_calibration"
        if target_generation is None
        else f"generation_{target_generation}_calibration"
    )
    return ResourceCalibration(
        cpu_cores=_selected(cpu_values, trim_fraction=trim_fraction),
        memory_mib=_selected(memory_values, trim_fraction=trim_fraction),
        disk_kib=_selected(disk_values, trim_fraction=trim_fraction),
        source=source,
        sample_count=max(len(cpu_values), len(memory_values), len(disk_values)),
    )


def memory_quantity_mib(value: object, setting_name: str) -> int:
    return quantity_as_units(value, _MEMORY_FACTORS_MIB, setting_name)


def disk_quantity_kib(value: object, setting_name: str) -> int:
    return quantity_as_units(value, _DISK_FACTORS_KIB, setting_name)


def quantity_as_units(
    value: object,
    factors: Mapping[str, float],
    setting_name: str,
) -> int:
    match = _QUANTITY_RE.match(str(value))
    if match is None:
        raise ValueError(
            f"{setting_name} must be a positive resource quantity, got {value!r}"
        )
    factor = factors[match.group(2).lower()]
    parsed = float(match.group(1)) * factor
    if parsed <= 0.0:
        raise ValueError(f"{setting_name} must be positive, got {value!r}")
    return max(1, math.ceil(parsed))


def trimmed_high(values: Sequence[float], *, trim_fraction: float) -> float:
    """Return the maximum after discarding the configured highest fraction."""

    ordered = sorted(float(value) for value in values if float(value) > 0.0)
    if not ordered:
        raise ValueError("resource calibration requires a positive measurement")
    clean_fraction = fraction(trim_fraction)
    trim_count = min(
        len(ordered) - 1,
        math.ceil(len(ordered) * clean_fraction),
    )
    return ordered[len(ordered) - trim_count - 1]


def scaled_quantity(value: float | int, multiplier: float) -> int:
    return max(1, math.ceil(float(value) * float(multiplier)))


def positive_number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0.0 else None


def positive_float(value: object, setting_name: str) -> float:
    parsed = positive_number(value)
    if parsed is None:
        raise ValueError(f"{setting_name} must be a positive number, got {value!r}")
    return parsed


def fraction(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"resource trim fraction must be between 0 and 1, got {value!r}"
        ) from exc
    if not math.isfinite(parsed) or not 0.0 <= parsed < 1.0:
        raise ValueError(
            f"resource trim fraction must be between 0 and 1, got {value!r}"
        )
    return parsed


def _selected(values: Sequence[float], *, trim_fraction: float) -> float | None:
    return (
        trimmed_high(values, trim_fraction=trim_fraction)
        if values
        else None
    )


def _append_first_positive(
    metadata: Mapping[str, object],
    keys: Sequence[str],
    target: list[float],
) -> None:
    for key in keys:
        value = positive_number(metadata.get(key))
        if value is not None:
            target.append(value)
            return


def _generation_index(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


__all__ = [
    "calibration_for_generation",
    "disk_quantity_kib",
    "estimate_resources",
    "fraction",
    "memory_quantity_mib",
    "positive_float",
    "positive_number",
    "quantity_as_units",
    "ResourceCalibration",
    "ResourceEstimate",
    "scaled_quantity",
    "trimmed_high",
]
