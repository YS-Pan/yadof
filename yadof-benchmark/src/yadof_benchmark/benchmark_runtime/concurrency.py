"""Host-adaptive simulator concurrency resolution."""
from __future__ import annotations

import math
from typing import Any, Mapping

import psutil

from .contracts import BenchmarkError

SIMULATION_CONCURRENCY_FIELDS = frozenset({"physical_core_multiplier"})
PHYSICAL_CORE_DETECTION_SOURCE = "psutil.cpu_count(logical=False)"


def validate_physical_core_multiplier(value: Any, *, label: str) -> float:
    """Return one finite positive physical-core multiplier."""

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise BenchmarkError(f"{label} must be a finite positive number")
    return float(value)


def detect_physical_cores() -> int:
    """Detect the host's positive physical CPU core count."""

    detected = psutil.cpu_count(logical=False)
    if isinstance(detected, bool) or not isinstance(detected, int) or detected <= 0:
        raise BenchmarkError(
            "cannot detect a positive physical CPU core count with "
            f"{PHYSICAL_CORE_DETECTION_SOURCE}"
        )
    return detected


def resolve_simulation_concurrency(
    execution: Mapping[str, Any],
    *,
    physical_cores: int | None = None,
) -> dict[str, Any] | None:
    """Resolve a baseline multiplier into a host-specific worker count."""

    value = execution.get("simulation_concurrency")
    if not isinstance(value, Mapping):
        return None
    multiplier = validate_physical_core_multiplier(
        value.get("physical_core_multiplier"),
        label="execution.simulation_concurrency.physical_core_multiplier",
    )
    detected = detect_physical_cores() if physical_cores is None else physical_cores
    if isinstance(detected, bool) or not isinstance(detected, int) or detected <= 0:
        raise BenchmarkError("physical_cores must be a positive integer")
    resolved = max(1, math.floor(detected * multiplier))
    return {
        "physical_core_detection": PHYSICAL_CORE_DETECTION_SOURCE,
        "physical_cores": detected,
        "physical_core_multiplier": multiplier,
        "resolved_max_workers": resolved,
        "rounding": "floor",
    }


__all__ = [
    "PHYSICAL_CORE_DETECTION_SOURCE",
    "SIMULATION_CONCURRENCY_FIELDS",
    "detect_physical_cores",
    "resolve_simulation_concurrency",
    "validate_physical_core_multiplier",
]
