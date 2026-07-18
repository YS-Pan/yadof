"""Generic starter rawData-to-cost policy."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from yadof.job_template import RawDataView


def calculate_cost(
    sample_rawdata: Iterable[object],
    raw_variables: object | None = None,
) -> tuple[float, ...]:
    del raw_variables
    for item in sample_rawdata:
        view = RawDataView.from_item(item)
        if view.name == "response":
            value = np.asarray(view.data, dtype=float)
            if value.shape != () or not np.isfinite(value.item()):
                return (float("inf"),)
            return (float(value.item()),)
    return (float("inf"),)


def get_objective_names() -> tuple[str, ...]:
    return ("objective",)


def get_objective_count() -> int:
    return len(get_objective_names())
