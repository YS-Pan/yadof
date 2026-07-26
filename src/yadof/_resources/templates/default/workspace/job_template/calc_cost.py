"""Generic starter rawData-to-cost policy."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from yadof.job_template.cost_misc import (
    calculate_rawdata_cost,
)
from yadof.job_template.rawdata_contract import RawDataItem, RawDataView


OBJECTIVE_NAMES = ("objective",)


def _calculate_loaded_cost(
    loaded_items: Sequence[RawDataView],
    raw_variables: object | None,
) -> tuple[float, ...]:
    del raw_variables
    views = {view.name: view for view in loaded_items}
    value = np.asarray(views["response"].data, dtype=float)
    if value.shape != ():
        raise ValueError("response rawData must contain a scalar array")
    if not np.isfinite(value.item()):
        return (float("inf"),)
    return (float(value.item()),)


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem],
    raw_variables: object | None = None,
) -> tuple[float, ...]:
    return calculate_rawdata_cost(
        sample_rawdata,
        raw_variables,
        objective_names=OBJECTIVE_NAMES,
        calculate_loaded_cost=_calculate_loaded_cost,
    )


def get_objective_names() -> tuple[str, ...]:
    return OBJECTIVE_NAMES
