"""Dynamic rawData-to-cost calculation for the default test task."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .rawdata_contract import load_rawdata_item, metadata_from_item, validate_rawdata_item

RawDataItem = Mapping[str, object] | str | Path
OBJECTIVE_NAMES = ("default_cost",)


def get_objective_names() -> tuple[str, ...]:
    return tuple(OBJECTIVE_NAMES)


def get_objective_count() -> int:
    return len(OBJECTIVE_NAMES)


def calculate_cost(sample_rawdata: Sequence[RawDataItem]) -> tuple[float, ...]:
    """Calculate objective values for one sample from in-memory or file rawData."""

    by_name: dict[str, dict[str, object]] = {}
    for item in sample_rawdata:
        loaded = validate_rawdata_item(load_rawdata_item(item))
        name = str(metadata_from_item(loaded).get("rawdata_name") or len(by_name))
        by_name[name] = loaded

    summary_values = np.asarray(by_name.get("summary", {}).get("values", ()), dtype=float).ravel()
    curve_values = np.asarray(by_name.get("curve", {}).get("values", ()), dtype=float).ravel()
    surface_values = np.asarray(by_name.get("surface", {}).get("values", ()), dtype=float).ravel()

    if summary_values.size < 3 or curve_values.size == 0 or surface_values.size == 0:
        return (float("inf"),)

    x0, x1, x2 = summary_values[:3]
    target_penalty = (x0 - 0.35) ** 2 + (x1 + 0.45) ** 2 + 0.2 * (x2 - 0.65) ** 2
    curve_penalty = float(np.mean(np.abs(curve_values)))
    surface_reward = float(np.mean(surface_values))
    return (float(target_penalty + 0.05 * curve_penalty + 0.1 * (1.0 - surface_reward)),)


def calculate_costs(samples: Sequence[Sequence[RawDataItem]]) -> tuple[tuple[float, ...], ...]:
    return tuple(calculate_cost(sample) for sample in samples)
