"""Frozen two-objective current-cost policy for the real canary."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from yadof.job_template.cost_misc import calculate_rawdata_cost, soft_cost
from yadof.job_template.rawdata_contract import RawDataItem, RawDataView


OBJECTIVE_NAMES = ("cost_response", "cost_inverse_response")
ERROR_COST = 1.0


def _calculate_loaded_cost(
    loaded_items: Sequence[RawDataView],
    raw_variables: object | None,
) -> tuple[float, ...]:
    del raw_variables
    views = {view.name: view for view in loaded_items}
    value = float(np.asarray(views["response"].data, dtype=float).item())
    if not np.isfinite(value):
        raise ValueError("response rawData must be finite")
    return (
        soft_cost(value, goal=0.0, worst=1.0, error_cost=ERROR_COST),
        soft_cost(1.0 - value, goal=0.0, worst=1.0, error_cost=ERROR_COST),
    )


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: object | None = None,
) -> tuple[float, ...]:
    return calculate_rawdata_cost(
        sample_rawdata,
        raw_variables,
        objective_names=OBJECTIVE_NAMES,
        calculate_loaded_cost=_calculate_loaded_cost,
        error_cost=ERROR_COST,
    )


def get_objective_names() -> tuple[str, ...]:
    return OBJECTIVE_NAMES
