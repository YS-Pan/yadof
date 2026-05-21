from __future__ import annotations

from project.job_template.calc_cost import calculate_cost, rawdata_importance_weights
from project.job_template.rawdata_contract import RAWDATA_SCHEMA_VERSION


def _metadata(rawdata_name: str, shape, axes, *, pin_state: int | None = None):
    data = {
        "schema_version": RAWDATA_SCHEMA_VERSION,
        "rawdata_name": rawdata_name,
        "source": "test",
        "shape": list(shape),
        "axis_names": [axis["name"] for axis in axes],
        "axes": list(axes),
    }
    if pin_state is not None:
        data["pin_state"] = pin_state
    return data


def _s11_item(pin_state: int):
    axes = [{"index": 0, "size": 5, "name": "Freq", "values_key": "axis_Freq", "unit": "GHz"}]
    return {
        "axis_Freq": [2.30, 2.39, 2.44, 2.49, 2.60],
        "unit_Freq": "GHz",
        "data": [-3.0, -3.0, -12.0, -3.0, -3.0],
        "metadata": _metadata(f"s11_pinState{pin_state}", [5], axes, pin_state=pin_state),
    }


def _gain_item(pin_state: int, values):
    axes = [{"index": 0, "size": 3, "name": "Theta", "values_key": "axis_Theta", "unit": "deg"}]
    return {
        "axis_Theta": [-30.0, 0.0, 30.0],
        "unit_Theta": "deg",
        "data": list(values),
        "metadata": _metadata(f"gain_pinState{pin_state}", [3], axes, pin_state=pin_state),
    }


def _good_sample():
    return (
        *(_s11_item(state) for state in (1, 2, 3, 4)),
        _gain_item(1, [7.0, 0.0, 0.0]),
        _gain_item(2, [0.0, 0.0, 7.0]),
        _gain_item(3, [7.0, -15.0, 7.0]),
        _gain_item(4, [0.0, 8.0, 0.0]),
    )


def test_hfss_costs_use_reference_objectives():
    costs = calculate_cost(_good_sample())

    assert len(costs) == 4
    assert all(0.0 <= value <= 1.0 for value in costs)
    assert all(value < 0.03 for value in costs)


def test_rawdata_importance_weights_emphasize_hfss_observation_windows():
    weights = rawdata_importance_weights(_good_sample(), floor=0.25, boost=2.0)

    assert float(weights[0]["data"][2]) > float(weights[0]["data"][0])
    assert float(weights[4]["data"][0]) > 2.0
    assert float(weights[4]["data"][1]) > 2.0
    assert float(weights[4]["data"][2]) > 2.0

