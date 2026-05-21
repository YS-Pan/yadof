"""Pure-Python stand-in for a harder expensive simulator.

The synthetic response borrows the mixed-output shape from
``reference/20260418 shorten/code/problem.py``: scalar-like summaries, multiple
curves, and one surface. All outputs are deterministic nonlinear functions of a
20-dimensional input vector, so the optimizer cannot solve the task by matching
one or two echoed variables.
"""

from __future__ import annotations

import math
import re
from typing import Mapping, Sequence

import numpy as np

INPUT_DIM = 20
LATENT_DIM = 160
CURVE_POINTS = 160
SURFACE_SHAPE = (48, 48)
_TWO_PI = 2.0 * math.pi
_NAME_RE = re.compile(r"^x(\d+)$")

_RNG = np.random.default_rng(20260418)
_W = _RNG.normal(size=(LATENT_DIM, INPUT_DIM)).astype(np.float64) / math.sqrt(INPUT_DIM)
_B = _RNG.normal(scale=0.45, size=(LATENT_DIM,)).astype(np.float64)


def _ordered_values(variables: Mapping[str, float] | Sequence[float]) -> tuple[float, ...]:
    if isinstance(variables, Mapping):
        return tuple(float(variables[name]) for name in sorted(variables, key=_variable_sort_key))
    return tuple(float(value) for value in variables)


def _variable_sort_key(name: str) -> tuple[int, int | str]:
    match = _NAME_RE.match(str(name))
    if match:
        return (0, int(match.group(1)))
    return (1, str(name))


def _unit_input_vector(variables: Mapping[str, float] | Sequence[float]) -> np.ndarray:
    values = list(_ordered_values(variables))
    if len(values) < INPUT_DIM:
        values.extend([0.5] * (INPUT_DIM - len(values)))
    x = np.asarray(values[:INPUT_DIM], dtype=np.float64)
    return np.clip(x, 0.0, 1.0)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-values))


def _latent(x: np.ndarray) -> np.ndarray:
    return _sigmoid(3.4 * (_W @ x + _B))


def _p(h: np.ndarray, index: int) -> float:
    return float(h[int(index) % LATENT_DIM])


def _scalar_outputs(h: np.ndarray) -> np.ndarray:
    scalar0 = (
        0.10
        + 0.55 * _p(h, 0)
        + 0.18 * _p(h, 7)
        + 0.10 * _p(h, 23)
        + 0.06 * math.sin(_TWO_PI * _p(h, 47))
    )
    scalar1 = (
        0.12
        + 0.50 * (1.0 - _p(h, 1))
        + 0.18 * _p(h, 11)
        + 0.08 * (1.0 - _p(h, 29))
        + 0.05 * math.cos(_TWO_PI * _p(h, 53))
    )
    return np.clip(np.asarray([scalar0, scalar1], dtype=np.float64), 0.0, 1.0)


def _curve_outputs(h: np.ndarray, t: np.ndarray) -> np.ndarray:
    center0 = 0.08 + 0.84 * _p(h, 2)
    width0 = 0.018 + 0.052 * _p(h, 3)
    amp0 = 0.25 + 0.65 * _p(h, 4)
    freq0 = 0.8 + 2.2 * _p(h, 31)
    phase0 = _p(h, 37)
    curve0 = (
        0.22
        + 0.07 * np.sin(_TWO_PI * (freq0 * t + phase0))
        + amp0 * np.exp(-0.5 * ((t - center0) / width0) ** 2)
        - 0.10 * np.exp(-0.5 * ((t - (1.0 - center0)) / (0.035 + 0.030 * _p(h, 41))) ** 2)
    )

    center1 = 0.08 + 0.84 * _p(h, 5)
    width1 = 0.020 + 0.055 * _p(h, 6)
    valley_amp = 0.20 + 0.55 * _p(h, 12)
    peak_amp = 0.04 + 0.30 * _p(h, 18)
    freq1 = 1.0 + 1.8 * _p(h, 43)
    phase1 = _p(h, 59)
    curve1 = (
        0.48
        + 0.08 * np.cos(_TWO_PI * (freq1 * t + phase1))
        - valley_amp * np.exp(-0.5 * ((t - center1) / width1) ** 2)
        + peak_amp * np.exp(-0.5 * ((t - (1.0 - center1)) / (0.025 + 0.040 * _p(h, 61))) ** 2)
    )

    return np.clip(np.stack([curve0, curve1], axis=0), 0.0, 1.0).astype(np.float64)


def _surface_output(h: np.ndarray, axis_0: np.ndarray, axis_1: np.ndarray) -> np.ndarray:
    u, v = np.meshgrid(axis_0, axis_1, indexing="ij")
    center_u = 0.08 + 0.84 * _p(h, 8)
    center_v = 0.08 + 0.84 * _p(h, 9)
    sigma_u = 0.022 + 0.060 * _p(h, 10)
    sigma_v = 0.022 + 0.060 * _p(h, 13)
    peak_amp = 0.24 + 0.66 * _p(h, 14)
    pit_amp = 0.05 + 0.30 * _p(h, 15)
    freq_u = 0.8 + 2.0 * _p(h, 67)
    freq_v = 0.8 + 2.0 * _p(h, 71)
    phase_u = _p(h, 73)
    phase_v = _p(h, 79)

    peak = peak_amp * np.exp(-0.5 * (((u - center_u) / sigma_u) ** 2 + ((v - center_v) / sigma_v) ** 2))
    pit = pit_amp * np.exp(
        -0.5
        * (
            ((u - (1.0 - center_u)) / (0.55 * sigma_u + 0.025)) ** 2
            + ((v - (1.0 - center_v)) / (0.55 * sigma_v + 0.025)) ** 2
        )
    )
    ripple = 0.07 * np.sin(_TWO_PI * (freq_u * u + phase_u)) * np.cos(_TWO_PI * (freq_v * v + phase_v))
    surface = 0.24 + ripple + peak - 0.65 * pit
    return np.clip(surface, 0.0, 1.0).astype(np.float64)


def evaluate_raw_data(variables: Mapping[str, float] | Sequence[float]) -> dict[str, dict[str, object]]:
    """Return rawData blocks generated from unnormalized variables.

    The function intentionally returns raw simulation-like outputs, not cost.
    """

    x = _unit_input_vector(variables)
    h = _latent(x)
    curve_axis = np.linspace(0.0, 1.0, CURVE_POINTS, dtype=np.float64)
    surface_axis_0 = np.linspace(0.0, 1.0, SURFACE_SHAPE[0], dtype=np.float64)
    surface_axis_1 = np.linspace(0.0, 1.0, SURFACE_SHAPE[1], dtype=np.float64)
    summary = _scalar_outputs(h)
    curve = _curve_outputs(h, curve_axis)
    surface = _surface_output(h, surface_axis_0, surface_axis_1)

    return {
        "summary": {
            "arrays": {"values": summary},
            "metadata": {
                "source": "test_com.evaluate_raw_data",
                "description": "Two nonlinear scalar response channels.",
                "shape": list(summary.shape),
                "axes": [
                    {
                        "index": 0,
                        "size": int(summary.shape[0]),
                        "description": "scalar response channel",
                    }
                ],
            },
        },
        "curve": {
            "arrays": {
                "axis_0": np.asarray([0.0, 1.0], dtype=np.float64),
                "axis_1": curve_axis,
                "values": curve.astype(np.float64),
            },
            "metadata": {
                "source": "test_com.evaluate_raw_data",
                "shape": list(curve.shape),
                "axes": [
                    {
                        "index": 0,
                        "size": int(curve.shape[0]),
                        "name": "curve channel",
                        "values_key": "axis_0",
                    },
                    {
                        "index": 1,
                        "size": int(curve.shape[1]),
                        "name": "normalized position",
                        "values_key": "axis_1",
                    },
                ],
            },
        },
        "surface": {
            "arrays": {"axis_0": surface_axis_0, "axis_1": surface_axis_1, "values": surface.astype(np.float64)},
            "metadata": {
                "source": "test_com.evaluate_raw_data",
                "shape": list(surface.shape),
                "axes": [
                    {
                        "index": 0,
                        "size": int(surface.shape[0]),
                        "name": "normalized x",
                        "values_key": "axis_0",
                    },
                    {
                        "index": 1,
                        "size": int(surface.shape[1]),
                        "name": "normalized y",
                        "values_key": "axis_1",
                    },
                ],
            },
        },
    }
