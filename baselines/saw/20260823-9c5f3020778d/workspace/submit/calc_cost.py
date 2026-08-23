"""Physical response metrics mapped to independent normalized yadof costs."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from yadof.job_template.cost_misc import calculate_rawdata_cost, soft_cost
from yadof.job_template.rawdata_contract import RawDataItem, RawDataView


OBJECTIVE_NAMES = (
    "cost_passband_insertion_loss",
    "cost_passband_return_loss",
    "cost_3db_edge_error",
    "cost_near_stopband_rejection",
    "cost_outer_stopband_rejection",
)
ERROR_COST = 1.0
PASSBAND_HZ = (980.0e6, 1020.0e6)
RETURN_LOSS_BAND_HZ = (983.0e6, 1017.0e6)
NEAR_STOPBANDS_HZ = ((955.0e6, 975.0e6), (1025.0e6, 1045.0e6))
OUTER_STOPBANDS_HZ = ((850.0e6, 950.0e6), (1050.0e6, 1150.0e6))


def _curve(view: RawDataView) -> tuple[np.ndarray, np.ndarray]:
    frequency = np.asarray(view.axis_coordinates("frequency"), dtype=float).ravel()
    values = np.asarray(view.data, dtype=float).ravel()
    if frequency.shape != values.shape or frequency.size < 3:
        raise ValueError(f"{view.name} must be a non-empty frequency curve")
    if not np.all(np.isfinite(frequency)) or not np.all(np.isfinite(values)):
        raise ValueError(f"{view.name} contains non-finite data")
    return frequency, values


def _window(frequency: np.ndarray, limits: tuple[float, float]) -> np.ndarray:
    mask = (frequency >= limits[0]) & (frequency <= limits[1])
    if not np.any(mask):
        raise ValueError(f"frequency grid does not cover {limits}")
    return mask


def _worst_rejection(
    frequency: np.ndarray,
    s21_db: np.ndarray,
    windows: tuple[tuple[float, float], ...],
) -> float:
    leakage_db = max(float(np.max(s21_db[_window(frequency, limits)])) for limits in windows)
    return -leakage_db


def _three_db_edge_error_mhz(frequency: np.ndarray, s21_db: np.ndarray) -> float:
    pass_mask = _window(frequency, PASSBAND_HZ)
    pass_indices = np.flatnonzero(pass_mask)
    peak_index = int(pass_indices[np.argmax(s21_db[pass_mask])])
    threshold = float(s21_db[peak_index] - 3.0)

    above = s21_db >= threshold
    left = peak_index
    while left > 0 and above[left - 1]:
        left -= 1
    right = peak_index
    while right + 1 < above.size and above[right + 1]:
        right += 1
    if left == 0 or right == above.size - 1:
        raise ValueError("3 dB passband is not bounded by the simulated span")

    def crossing(index_below: int, index_above: int) -> float:
        x0, x1 = frequency[index_below], frequency[index_above]
        y0, y1 = s21_db[index_below], s21_db[index_above]
        return float(x0 + (threshold - y0) * (x1 - x0) / (y1 - y0))

    lower_hz = crossing(left - 1, left)
    upper_hz = crossing(right + 1, right)
    return max(abs(lower_hz - PASSBAND_HZ[0]), abs(upper_hz - PASSBAND_HZ[1])) / 1.0e6


def response_metrics(loaded_items: Sequence[RawDataView]) -> dict[str, float]:
    views = {view.name: view for view in loaded_items}
    frequency, s21_db = _curve(views["s21_db"])
    s11_frequency, s11_db = _curve(views["s11_db"])
    if not np.array_equal(frequency, s11_frequency):
        raise ValueError("S21 and S11 frequency axes differ")

    pass_mask = _window(frequency, PASSBAND_HZ)
    return_mask = _window(frequency, RETURN_LOSS_BAND_HZ)
    return {
        "passband_insertion_loss_db": -float(np.min(s21_db[pass_mask])),
        "passband_return_loss_db": -float(np.max(s11_db[return_mask])),
        "edge_error_mhz": _three_db_edge_error_mhz(frequency, s21_db),
        "near_stopband_rejection_db": _worst_rejection(
            frequency, s21_db, NEAR_STOPBANDS_HZ
        ),
        "outer_stopband_rejection_db": _worst_rejection(
            frequency, s21_db, OUTER_STOPBANDS_HZ
        ),
    }


def _calculate_loaded_cost(
    loaded_items: Sequence[RawDataView],
    raw_variables: object | None,
) -> tuple[float, ...]:
    del raw_variables
    metrics = response_metrics(loaded_items)
    return (
        soft_cost(metrics["passband_insertion_loss_db"], goal=1.5, worst=6.0, error_cost=ERROR_COST),
        soft_cost(metrics["passband_return_loss_db"], goal=12.0, worst=4.0, error_cost=ERROR_COST),
        soft_cost(metrics["edge_error_mhz"], goal=0.5, worst=15.0, error_cost=ERROR_COST),
        soft_cost(metrics["near_stopband_rejection_db"], goal=30.0, worst=8.0, error_cost=ERROR_COST),
        soft_cost(metrics["outer_stopband_rejection_db"], goal=45.0, worst=18.0, error_cost=ERROR_COST),
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


