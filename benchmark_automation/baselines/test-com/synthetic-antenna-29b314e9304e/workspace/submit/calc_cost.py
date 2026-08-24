"""State-aligned antenna objectives for the rugged synthetic benchmark task."""

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
    "cost_s11_resonance",
    "cost_beam_gain",
    "cost_back_lobe",
    "cost_axial_ratio_at_2p44",
)
ERROR_COST = 1.0
PIN_STATES = (1, 2, 3)
TARGET_PHI_DEG = 90.0
TARGET_FREQ_GHZ = 2.44
ANGLE_TOLERANCE_DEG = 3.0
BACK_LOBE_DEG = ((-180.0, -150.0), (150.0, 180.0))
GAIN_TARGET_THETA_BY_STATE = {1: -30.0, 2: 30.0, 3: 0.0}
AXIAL_RATIO_TARGET_THETA_BY_STATE = {1: -14.0, 2: 14.0, 3: 0.0}

# The model maps its ideal Pareto direction plus shared rugged design loss into
# these physical metrics. Positions 0.12 and 0.92 are the fixed goal/worst anchors;
# positions outside that interval remain ordered in soft_cost's algebraic tails.
S11_RESONANCE_GOAL_DB = -8.5
S11_RESONANCE_WORST_DB = -5.5
BEAM_GAIN_GOAL_DB = -1.0
BEAM_GAIN_WORST_DB = -5.0
BACK_LOBE_GOAL_DB = -23.5
BACK_LOBE_WORST_DB = -20.5
AXIAL_RATIO_GOAL_DB = 7.0
AXIAL_RATIO_WORST_DB = 17.0


def _by_name(views: Sequence[RawDataView], prefix: str) -> tuple[RawDataView, ...]:
    selected = tuple(view for view in views if view.name.startswith(prefix))
    if len(selected) != len(PIN_STATES):
        raise ValueError(f"expected three {prefix!r} rawData fields")
    return selected


def _gain_theta_curve(view: RawDataView) -> tuple[np.ndarray, np.ndarray]:
    phi = view.nearest_index(
        "Phi",
        TARGET_PHI_DEG,
        ANGLE_TOLERANCE_DEG,
        period=360.0,
        converter=angle_to_degrees,
    )
    frequency = view.nearest_index("Freq", TARGET_FREQ_GHZ, 0.02)
    theta = np.asarray(view.axis_coordinates("Theta"), dtype=float)
    values = np.asarray(view.data, dtype=float)[frequency, phi, :]
    return theta, values


def _pin_state(view: RawDataView) -> int:
    for pin_state in PIN_STATES:
        if view.name.endswith(str(pin_state)):
            return pin_state
    raise ValueError(f"cannot identify pin state from rawData name {view.name!r}")


def _axial_value(view: RawDataView) -> float:
    phi = view.nearest_index(
        "Phi",
        TARGET_PHI_DEG,
        ANGLE_TOLERANCE_DEG,
        period=360.0,
        converter=angle_to_degrees,
    )
    theta = view.nearest_index(
        "Theta",
        AXIAL_RATIO_TARGET_THETA_BY_STATE[_pin_state(view)],
        ANGLE_TOLERANCE_DEG,
        period=360.0,
        converter=angle_to_degrees,
    )
    frequency = view.nearest_index("Freq", TARGET_FREQ_GHZ, 0.02)
    return float(np.asarray(view.data, dtype=float)[frequency, phi, theta])


def _calculate_loaded_cost(
    loaded_items: Sequence[RawDataView], raw_variables: object | None
) -> tuple[float, ...]:
    del raw_variables
    s11 = _by_name(loaded_items, "s11")
    gain = _by_name(loaded_items, "gain_lhcp")
    axial = _by_name(loaded_items, "axial_ratio")
    worst_s11_resonance = max(
        float(np.min(np.asarray(view.data, dtype=float))) for view in s11
    )
    beam_gain: list[float] = []
    back_lobe: list[float] = []
    for view in gain:
        theta, values = _gain_theta_curve(view)
        target = GAIN_TARGET_THETA_BY_STATE[_pin_state(view)]
        target_index = int(np.argmin(np.abs(theta - target)))
        if abs(float(theta[target_index]) - target) > ANGLE_TOLERANCE_DEG:
            raise ValueError(f"gain grid does not cover target theta {target}")
        back_mask = np.zeros(theta.shape, dtype=bool)
        for lower, upper in BACK_LOBE_DEG:
            back_mask |= (theta >= lower) & (theta <= upper)
        if not np.any(back_mask):
            raise ValueError("gain grid does not cover synthetic back-lobe windows")
        beam_gain.append(float(values[target_index]))
        back_lobe.append(float(np.max(values[back_mask])))
    return (
        soft_cost(
            worst_s11_resonance,
            goal=S11_RESONANCE_GOAL_DB,
            worst=S11_RESONANCE_WORST_DB,
            error_cost=ERROR_COST,
        ),
        soft_cost(
            min(beam_gain),
            goal=BEAM_GAIN_GOAL_DB,
            worst=BEAM_GAIN_WORST_DB,
            error_cost=ERROR_COST,
        ),
        soft_cost(
            max(back_lobe),
            goal=BACK_LOBE_GOAL_DB,
            worst=BACK_LOBE_WORST_DB,
            error_cost=ERROR_COST,
        ),
        soft_cost(
            max(_axial_value(view) for view in axial),
            goal=AXIAL_RATIO_GOAL_DB,
            worst=AXIAL_RATIO_WORST_DB,
            error_cost=ERROR_COST,
        ),
    )


def calculate_cost(
    sample_rawdata: Sequence[RawDataItem], raw_variables: object | None = None
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
