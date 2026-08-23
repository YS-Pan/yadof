"""Antenna-like response objectives for the synthetic ``test_com`` fields."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from yadof.job_template.cost_misc import calculate_rawdata_cost, soft_cost
from yadof.job_template.rawdata_contract import (
    RawDataItem,
    RawDataView,
    angle_to_degrees,
)


OBJECTIVE_NAMES = (
    "cost_s11_band",
    "cost_gain_coverage",
    "cost_back_lobe",
    "cost_axial_ratio",
)
ERROR_COST = 1.0
PIN_STATES = (1, 2, 3)
TARGET_PHI_DEG = 90.0
TARGET_FREQ_GHZ = 2.44
ANGLE_TOLERANCE_DEG = 3.0
GAIN_COVERAGE_DEG = (-60.0, 60.0)
BACK_LOBE_DEG = ((-180.0, -150.0), (150.0, 180.0))


def _by_name(views: Sequence[RawDataView], prefix: str) -> tuple[RawDataView, ...]:
    selected = tuple(view for view in views if view.name.startswith(prefix))
    if len(selected) != len(PIN_STATES):
        raise ValueError(f"expected three {prefix!r} rawData fields")
    return selected


def _gain_theta_curve(view: RawDataView) -> tuple[np.ndarray, np.ndarray]:
    phi = view.nearest_index(
        "Phi", TARGET_PHI_DEG, ANGLE_TOLERANCE_DEG,
        period=360.0, converter=angle_to_degrees,
    )
    frequency = view.nearest_index("Freq", TARGET_FREQ_GHZ, 0.02)
    theta = np.asarray(view.axis_coordinates("Theta"), dtype=float)
    values = np.asarray(view.data, dtype=float)[frequency, phi, :]
    return theta, values


def _axial_value(view: RawDataView) -> float:
    phi = view.nearest_index(
        "Phi", TARGET_PHI_DEG, ANGLE_TOLERANCE_DEG,
        period=360.0, converter=angle_to_degrees,
    )
    theta = view.nearest_index(
        "Theta", 0.0, 6.0, period=360.0, converter=angle_to_degrees,
    )
    return float(np.max(np.asarray(view.data, dtype=float)[:, phi, theta]))


def _calculate_loaded_cost(
    loaded_items: Sequence[RawDataView], raw_variables: object | None,
) -> tuple[float, ...]:
    del raw_variables
    s11 = _by_name(loaded_items, "s11")
    gain = _by_name(loaded_items, "gain_lhcp")
    axial = _by_name(loaded_items, "axial_ratio")
    worst_s11 = max(float(np.max(np.asarray(view.data, dtype=float))) for view in s11)
    coverage: list[float] = []
    back_lobe: list[float] = []
    for view in gain:
        theta, values = _gain_theta_curve(view)
        coverage_mask = (theta >= GAIN_COVERAGE_DEG[0]) & (theta <= GAIN_COVERAGE_DEG[1])
        back_mask = np.zeros(theta.shape, dtype=bool)
        for lower, upper in BACK_LOBE_DEG:
            back_mask |= (theta >= lower) & (theta <= upper)
        if not np.any(coverage_mask) or not np.any(back_mask):
            raise ValueError("gain grid does not cover synthetic objective windows")
        coverage.append(float(np.min(values[coverage_mask])))
        back_lobe.append(float(np.max(values[back_mask])))
    return (
        soft_cost(worst_s11, goal=-12.0, worst=-3.0, error_cost=ERROR_COST),
        soft_cost(min(coverage), goal=7.0, worst=0.0, error_cost=ERROR_COST),
        soft_cost(max(back_lobe), goal=-5.0, worst=5.0, error_cost=ERROR_COST),
        soft_cost(max(_axial_value(view) for view in axial), goal=2.0, worst=18.0, error_cost=ERROR_COST),
    )


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem], raw_variables: object | None = None,
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

