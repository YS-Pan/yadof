"""Validate resource-only decisions for newly admitted benchmark cells."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from .concurrency import validate_physical_core_multiplier
from .contracts import BenchmarkError

CapacityPolicy = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def validate_capacity_decision(
    value: Mapping[str, Any],
    *,
    maximum_cells: int,
    baselines: Mapping[str, Any],
) -> dict[str, Any]:
    """Accept only cell slots and per-baseline physical-core multipliers."""
    allowed = {"cell_concurrency", "baseline_physical_core_multipliers", "reason"}
    if not isinstance(value, Mapping) or set(value) - allowed:
        raise BenchmarkError("capacity policy may return only cell_concurrency, baseline_physical_core_multipliers, and reason")
    cells = value.get("cell_concurrency", maximum_cells)
    if isinstance(cells, bool) or not isinstance(cells, int) or not 1 <= cells <= maximum_cells:
        raise BenchmarkError(f"capacity cell_concurrency must be an integer between 1 and {maximum_cells}")
    multipliers = value.get("baseline_physical_core_multipliers", {})
    if not isinstance(multipliers, Mapping):
        raise BenchmarkError("baseline_physical_core_multipliers must be a mapping")
    resolved = {}
    for baseline_id, multiplier in multipliers.items():
        if baseline_id not in baselines:
            raise BenchmarkError(f"capacity policy names an unknown baseline: {baseline_id!r}")
        execution = baselines[baseline_id].get("execution", {})
        if execution.get("mode") not in {"fast", "local"}:
            raise BenchmarkError(f"capacity multiplier requires a fast/local baseline: {baseline_id!r}")
        resolved[baseline_id] = validate_physical_core_multiplier(
            multiplier, label=f"capacity multiplier for {baseline_id}"
        )
    reason = value.get("reason", "")
    if not isinstance(reason, str) or len(reason) > 2000:
        raise BenchmarkError("capacity reason must be a string of at most 2000 characters")
    return {"cell_concurrency": cells,
            "baseline_physical_core_multipliers": resolved, "reason": reason}


def cell_with_capacity(cell: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the frozen scientific cell intact while applying its admission capacity."""
    effective = deepcopy(dict(cell))
    multipliers = decision["baseline_physical_core_multipliers"]
    if cell["baseline"] in multipliers:
        effective["execution"]["simulation_concurrency"] = {
            "physical_core_multiplier": multipliers[cell["baseline"]]
        }
    return effective


__all__ = ["CapacityPolicy", "cell_with_capacity", "validate_capacity_decision"]
