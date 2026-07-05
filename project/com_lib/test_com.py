"""Pure-Python stand-in for a harder expensive simulator.

The default synthetic response mirrors the current HFSS rawData shape used by
``temp/jobs``: three pin states, S11 traces, and 3D far-field grids with Freq,
Phi, and Theta axes. A smaller generic summary/curve/surface profile is also
kept for lightweight adapter examples.

All outputs are deterministic nonlinear functions of a 20-dimensional input
vector, so the optimizer cannot solve the task by matching one or two echoed
variables.
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
PIN_STATES = (1, 2, 3)
HFSS_FREQ_AXIS = np.asarray([2.40, 2.42, 2.44, 2.46, 2.48], dtype=np.float64)
HFSS_GAIN_FREQ_AXIS = np.asarray([2.44], dtype=np.float64)
HFSS_PHI_AXIS = np.linspace(-180.0, 180.0, 73, dtype=np.float64)
HFSS_THETA_AXIS = np.linspace(-180.0, 180.0, 73, dtype=np.float64)
TARGET_PHI_DEG = 90.0
GAIN_TARGET_THETA_BY_STATE = {1: -30.0, 2: 30.0, 3: 0.0}
AXIAL_RATIO_TARGET_THETA_BY_STATE = {1: -14.0, 2: 14.0, 3: 0.0}
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
    finite = np.isfinite(x)
    if np.any(finite) and (np.nanmin(x[finite]) < 0.0 or np.nanmax(x[finite]) > 1.0):
        lo = float(np.nanmin(x[finite]))
        hi = float(np.nanmax(x[finite]))
        if hi > lo:
            x = (x - lo) / (hi - lo)
        else:
            x = np.full_like(x, 0.5, dtype=np.float64)
    x = np.where(np.isfinite(x), x, 0.5)
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


def _periodic_delta(values: np.ndarray, center: float, period: float = 360.0) -> np.ndarray:
    delta = np.asarray(values, dtype=np.float64) - float(center)
    period = abs(float(period))
    return np.minimum.reduce((np.abs(delta), np.abs(delta - period), np.abs(delta + period)))


def _gaussian(values: np.ndarray, center: float, width: float) -> np.ndarray:
    return np.exp(-0.5 * ((np.asarray(values, dtype=np.float64) - float(center)) / float(width)) ** 2)


def _periodic_gaussian(values: np.ndarray, center: float, width: float, period: float = 360.0) -> np.ndarray:
    return np.exp(-0.5 * (_periodic_delta(values, center, period) / float(width)) ** 2)


def _s11_trace(h: np.ndarray, pin_state: int) -> np.ndarray:
    freq = HFSS_FREQ_AXIS
    state_shift = 0.012 * (int(pin_state) - 2)
    center = 2.40 + 0.08 * _p(h, 20 + pin_state) + state_shift
    width = 0.012 + 0.020 * _p(h, 26 + pin_state)
    notch_depth = 2.0 + 12.0 * _p(h, 32 + pin_state)
    baseline = -3.0 - 2.8 * _p(h, 38 + pin_state)
    ripple = 0.55 * np.sin(_TWO_PI * (freq - 2.40) / 0.08 * (0.7 + _p(h, 44 + pin_state)))
    trace = baseline + ripple - notch_depth * _gaussian(freq, center, width)
    return np.asarray(trace, dtype=np.float64)


def _gain_grid(h: np.ndarray, pin_state: int) -> np.ndarray:
    freq = HFSS_GAIN_FREQ_AXIS[:, None, None]
    phi = HFSS_PHI_AXIS[None, :, None]
    theta = HFSS_THETA_AXIS[None, None, :]
    theta_target = GAIN_TARGET_THETA_BY_STATE[int(pin_state)]

    phi_width = 16.0 + 24.0 * _p(h, 50 + pin_state)
    theta_width = 13.0 + 25.0 * _p(h, 56 + pin_state)
    main_amp = 18.0 + 11.0 * _p(h, 62 + pin_state)
    side_amp = 2.0 + 6.0 * _p(h, 68 + pin_state)
    target_bias = -2.5 + 5.0 * _p(h, 74 + pin_state)

    main_lobe = main_amp * _periodic_gaussian(phi, TARGET_PHI_DEG, phi_width) * _gaussian(theta, theta_target, theta_width)
    side_lobe = side_amp * _periodic_gaussian(phi, -90.0 + 15.0 * (pin_state - 2), 38.0) * _gaussian(theta, -theta_target, 34.0)
    ripple = 1.3 * np.sin(np.deg2rad(phi * (1.0 + _p(h, 80 + pin_state)))) * np.cos(
        np.deg2rad(theta * (1.0 + _p(h, 86 + pin_state)))
    )
    freq_term = 0.35 * np.cos(_TWO_PI * (freq - 2.44) / 0.08)
    grid = -24.0 + target_bias + main_lobe + side_lobe + ripple + freq_term
    return np.asarray(grid, dtype=np.float64)


def _axial_ratio_grid(h: np.ndarray, pin_state: int) -> np.ndarray:
    freq = HFSS_FREQ_AXIS[:, None, None]
    phi = HFSS_PHI_AXIS[None, :, None]
    theta = HFSS_THETA_AXIS[None, None, :]
    theta_target = AXIAL_RATIO_TARGET_THETA_BY_STATE[int(pin_state)]

    phi_width = 12.0 + 20.0 * _p(h, 92 + pin_state)
    theta_width = 10.0 + 18.0 * _p(h, 98 + pin_state)
    freq_center = 2.40 + 0.08 * _p(h, 104 + pin_state)
    freq_width = 0.018 + 0.035 * _p(h, 110 + pin_state)
    valley_depth = 12.0 + 18.0 * _p(h, 116 + pin_state)
    target_floor = 0.35 + 4.0 * (1.0 - _p(h, 122 + pin_state))

    angular_valley = _periodic_gaussian(phi, TARGET_PHI_DEG, phi_width) * _gaussian(theta, theta_target, theta_width)
    freq_valley = _gaussian(freq, freq_center, freq_width)
    ripple = 2.0 * np.abs(np.sin(np.deg2rad(phi + theta * (0.4 + _p(h, 128 + pin_state)))))
    off_target_penalty = 7.5 * (1.0 - angular_valley) + 4.5 * (1.0 - freq_valley)
    grid = target_floor + off_target_penalty + ripple + (1.0 - angular_valley * freq_valley) * valley_depth * 0.30
    return np.asarray(np.clip(grid, 0.0, 90.0), dtype=np.float64)


def _axis_descriptor(index: int, name: str, values_key: str, unit_key: str, size: int, unit: str) -> dict[str, object]:
    return {
        "index": int(index),
        "size": int(size),
        "name": str(name),
        "values_key": str(values_key),
        "unit": str(unit),
        "unit_key": str(unit_key),
    }


def _hfss_trace_block(
    name: str,
    data: np.ndarray,
    *,
    pin_state: int,
    quantity: str,
    expression: str,
) -> dict[str, object]:
    metadata = {
        "pin_state": int(pin_state),
        "hfss_quantity": quantity,
        "schema_version": 1,
        "rawdata_name": name,
        "expression": expression,
        "report_category": "Modal Solution Data",
        "context": None,
        "setup_sweep_name": "Synthetic : Sweep",
        "primary_sweep_variable": "Freq",
        "axis_names": ["Freq"],
        "axes": [_axis_descriptor(0, "Freq", "axis_Freq", "unit_Freq", int(data.shape[0]), "GHz")],
        "shape": list(data.shape),
        "data_contract": "trace",
        "source": "test_com.evaluate_raw_data",
    }
    return {
        "arrays": {
            "data": np.asarray(data, dtype=np.float64),
            "axis_Freq": HFSS_FREQ_AXIS.copy(),
            "unit_Freq": np.asarray("GHz"),
        },
        "metadata": metadata,
    }


def _hfss_grid_block(
    name: str,
    data: np.ndarray,
    *,
    pin_state: int,
    quantity: str,
    expression: str,
    freq_axis: np.ndarray,
) -> dict[str, object]:
    metadata = {
        "pin_state": int(pin_state),
        "hfss_quantity": quantity,
        "schema_version": 1,
        "rawdata_name": name,
        "expression": expression,
        "report_category": "Far Fields",
        "context": "Infinite Sphere1",
        "setup_sweep_name": "Synthetic : Sweep",
        "primary_sweep_variable": None,
        "axis_names": ["Freq", "Phi", "Theta"],
        "axes": [
            _axis_descriptor(0, "Freq", "axis_Freq", "unit_Freq", int(data.shape[0]), "GHz"),
            _axis_descriptor(1, "Phi", "axis_Phi", "unit_Phi", int(data.shape[1]), "deg"),
            _axis_descriptor(2, "Theta", "axis_Theta", "unit_Theta", int(data.shape[2]), "deg"),
        ],
        "shape": list(data.shape),
        "data_contract": "grid",
        "source": "test_com.evaluate_raw_data",
        "active_intrinsic": {
            "Freq": float(np.asarray(freq_axis).reshape(-1)[0]),
            "Phi": float(HFSS_PHI_AXIS[0]),
            "Theta": float(HFSS_THETA_AXIS[0]),
        },
    }
    return {
        "arrays": {
            "data": np.asarray(data, dtype=np.float64),
            "axis_Freq": np.asarray(freq_axis, dtype=np.float64),
            "unit_Freq": np.asarray("GHz"),
            "axis_Phi": HFSS_PHI_AXIS.copy(),
            "unit_Phi": np.asarray("deg"),
            "axis_Theta": HFSS_THETA_AXIS.copy(),
            "unit_Theta": np.asarray("deg"),
        },
        "metadata": metadata,
    }


def _hfss_like_outputs(h: np.ndarray) -> dict[str, dict[str, object]]:
    blocks: dict[str, dict[str, object]] = {}
    for pin_state in PIN_STATES:
        s11_name = f"s11_pinState{pin_state}"
        gain_name = f"gain_lhcp_pinState{pin_state}"
        axial_name = f"axial_ratio_pinState{pin_state}"
        blocks[s11_name] = _hfss_trace_block(
            s11_name,
            _s11_trace(h, pin_state),
            pin_state=pin_state,
            quantity="s11",
            expression="dB(S(1,1))",
        )
        blocks[gain_name] = _hfss_grid_block(
            gain_name,
            _gain_grid(h, pin_state),
            pin_state=pin_state,
            quantity="realized_gain_lhcp",
            expression="dB(RealizedGainLHCP)",
            freq_axis=HFSS_GAIN_FREQ_AXIS,
        )
        blocks[axial_name] = _hfss_grid_block(
            axial_name,
            _axial_ratio_grid(h, pin_state),
            pin_state=pin_state,
            quantity="axial_ratio",
            expression="dB(AxialRatioValue)",
            freq_axis=HFSS_FREQ_AXIS,
        )
    return blocks


def _generic_outputs(h: np.ndarray) -> dict[str, dict[str, object]]:
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


def evaluate_raw_data(
    variables: Mapping[str, float] | Sequence[float],
    *,
    profile: str = "hfss_like",
) -> dict[str, dict[str, object]]:
    """Return rawData blocks generated from variables.

    The function intentionally returns raw simulation-like outputs, not cost.
    """

    x = _unit_input_vector(variables)
    h = _latent(x)
    profile_key = str(profile).strip().lower().replace("-", "_")
    if profile_key in {"hfss", "hfss_like", "newchoke"}:
        return _hfss_like_outputs(h)
    if profile_key in {"generic", "mixed", "summary_curve_surface"}:
        return _generic_outputs(h)
    raise ValueError(f"unknown test_com profile: {profile!r}")
