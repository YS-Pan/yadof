"""Pure-Python stand-in for an expensive simulator."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np


def _ordered_values(variables: Mapping[str, float] | Sequence[float]) -> tuple[float, ...]:
    if isinstance(variables, Mapping):
        return tuple(float(variables[name]) for name in sorted(variables))
    return tuple(float(value) for value in variables)


def evaluate_raw_data(variables: Mapping[str, float] | Sequence[float]) -> dict[str, dict[str, object]]:
    """Return rawData blocks generated from unnormalized variables.

    The function intentionally returns raw simulation-like outputs, not cost.
    """

    x0, x1, x2 = (_ordered_values(variables) + (0.0, 0.0, 0.0))[:3]
    t = np.linspace(0.0, 1.0, 128, dtype=np.float64)
    curve = np.sin(2.0 * math.pi * (1.0 + x2) * t + x0) + 0.25 * np.cos(4.0 * math.pi * t + x1)
    axis_0 = np.linspace(-1.0, 1.0, 32, dtype=np.float64)
    axis_1 = np.linspace(-1.0, 1.0, 32, dtype=np.float64)
    surface_x, surface_y = np.meshgrid(axis_0, axis_1, indexing="ij")
    surface = np.exp(-((surface_x - 0.25 * x0) ** 2 + (surface_y - 0.25 * x1) ** 2) / (0.15 + x2))
    summary = np.asarray([x0, x1, x2, float(np.max(curve)), float(np.mean(surface))], dtype=np.float64)

    return {
        "summary": {
            "arrays": {"values": summary},
            "metadata": {
                "source": "test_com.evaluate_raw_data",
                "description": "Input echoes and compact response statistics.",
                "shape": list(summary.shape),
                "axes": [
                    {
                        "index": 0,
                        "size": int(summary.shape[0]),
                        "description": "summary component",
                    }
                ],
            },
        },
        "curve": {
            "arrays": {"axis_0": t, "values": curve.astype(np.float64)},
            "metadata": {
                "source": "test_com.evaluate_raw_data",
                "shape": list(curve.shape),
                "axes": [
                    {
                        "index": 0,
                        "size": int(curve.shape[0]),
                        "name": "normalized position",
                        "values_key": "axis_0",
                    }
                ],
            },
        },
        "surface": {
            "arrays": {"axis_0": axis_0, "axis_1": axis_1, "values": surface.astype(np.float64)},
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
