from __future__ import annotations

import pytest

from project.job_template.calc_cost import calculate_cost
from project.job_template.rawdata_contract import RAWDATA_SCHEMA_VERSION


def _metadata(rawdata_name: str, shape, axes=()):
    data = {
        "schema_version": RAWDATA_SCHEMA_VERSION,
        "rawdata_name": rawdata_name,
        "source": "test",
        "shape": list(shape),
    }
    if axes:
        data["axes"] = list(axes)
    return data


def test_curve_and_surface_costs_use_local_observation_windows():
    sample = (
        {
            "values": [0.35, -0.45, 0.65],
            "metadata": _metadata("summary", [3]),
        },
        {
            "axis_0": [0.0, 0.5, 1.0],
            "values": [100.0, 0.0, 100.0],
            "metadata": _metadata(
                "curve",
                [3],
                [{"index": 0, "size": 3, "values_key": "axis_0"}],
            ),
        },
        {
            "axis_0": [-1.0, 0.0, 1.0],
            "axis_1": [-1.0, 0.0, 1.0],
            "values": [
                [0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
            "metadata": _metadata(
                "surface",
                [3, 3],
                [
                    {"index": 0, "size": 3, "values_key": "axis_0"},
                    {"index": 1, "size": 3, "values_key": "axis_1"},
                ],
            ),
        },
    )

    costs = calculate_cost(sample)

    assert costs[0] == pytest.approx(0.01798620996209155)
    assert costs[1] < 0.02
    assert costs[2] < 0.02
