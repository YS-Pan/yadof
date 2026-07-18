from __future__ import annotations

import json

import numpy as np
import pytest

from yadof.job_template.rawdata_contract import (
    RAWDATA_SCHEMA_VERSION,
    RawDataContractError,
    RawDataView,
    angle_to_degrees,
    frequency_to_ghz,
    mark_axis_points,
    mark_axis_range,
    validate_rawdata_directory,
    validate_rawdata_item,
)


def _write_npz(path, *, metadata=None, values=None, add_schema_version=True, **arrays):
    payload = dict(arrays)
    if values is not None:
        payload["values"] = np.asarray(values)
    if metadata is not None:
        metadata = dict(metadata)
        if add_schema_version:
            metadata.setdefault("schema_version", RAWDATA_SCHEMA_VERSION)
        payload["metadata"] = np.asarray(json.dumps(metadata), dtype=np.str_)
    np.savez(path, **payload)
    return path


def test_validate_rawdata_item_accepts_scalar_metadata(tmp_path):
    path = _write_npz(
        tmp_path / "scalar.npz",
        metadata={"rawdata_name": "scalar", "shape": [], "axes": []},
        values=np.asarray(1.5),
    )

    loaded = validate_rawdata_item(path)

    assert np.asarray(loaded["values"]).shape == ()


def test_validate_rawdata_item_accepts_current_schema_version(tmp_path):
    path = _write_npz(
        tmp_path / "current_schema.npz",
        metadata={"schema_version": RAWDATA_SCHEMA_VERSION, "rawdata_name": "current", "shape": [1]},
        values=[1.0],
        add_schema_version=False,
    )

    loaded = validate_rawdata_item(path)

    assert np.asarray(loaded["values"]).shape == (1,)


def test_validate_rawdata_item_accepts_1d_data_key_and_axis_values(tmp_path):
    path = _write_npz(
        tmp_path / "curve.npz",
        metadata={
            "rawdata_name": "curve",
            "shape": [3],
            "axes": [{"index": 0, "size": 3, "name": "time", "values_key": "axis_0"}],
        },
        data=[1.0, 2.0, 3.0],
        axis_0=np.asarray([0.0, 0.5, 1.0]),
    )

    loaded = validate_rawdata_item(path)

    assert "data" in loaded


def test_validate_rawdata_item_accepts_2d_metadata_without_axis_name_arrays(tmp_path):
    path = _write_npz(
        tmp_path / "surface.npz",
        metadata={
            "rawdata_name": "surface",
            "shape": [2, 3],
            "axes": [
                {"index": 0, "size": 2, "name": "frequency"},
                {"index": 1, "size": 3, "name": "polarization"},
            ],
        },
        values=np.ones((2, 3)),
    )

    loaded = validate_rawdata_item(path)

    assert "values" in loaded


def test_validate_rawdata_item_accepts_nd_metadata(tmp_path):
    path = _write_npz(
        tmp_path / "tensor.npz",
        metadata={
            "rawdata_name": "tensor",
            "shape": [2, 1, 3],
            "axes": [
                {"index": 0, "size": 2, "values_key": "axis_0"},
                {"index": 1, "size": 1, "values_key": "axis_1"},
                {"index": 2, "size": 3, "values_key": "axis_2"},
            ],
        },
        values=np.zeros((2, 1, 3)),
        axis_0=np.asarray([10.0, 20.0]),
        axis_1=np.asarray([99.0]),
        axis_2=np.asarray([0.0, 0.5, 1.0]),
    )

    loaded = validate_rawdata_item(path)

    assert np.asarray(loaded["values"]).shape == (2, 1, 3)


def test_validate_rawdata_item_rejects_missing_metadata(tmp_path):
    path = _write_npz(tmp_path / "bad.npz", values=[1.0])

    with pytest.raises(RawDataContractError, match="metadata"):
        validate_rawdata_item(path)


def test_validate_rawdata_item_rejects_legacy_meta_key_without_metadata(tmp_path):
    path = tmp_path / "legacy_meta_only.npz"
    np.savez(
        path,
        values=np.asarray([1.0]),
        meta=json.dumps({"schema_version": RAWDATA_SCHEMA_VERSION, "rawdata_name": "legacy", "shape": [1]}),
    )

    with pytest.raises(RawDataContractError, match="metadata") as exc_info:
        validate_rawdata_item(path)
    assert exc_info.value.error_type == "missing_metadata"


def test_validate_rawdata_item_rejects_missing_shape(tmp_path):
    path = _write_npz(
        tmp_path / "bad_missing_shape.npz",
        metadata={"rawdata_name": "bad"},
        values=[1.0],
    )

    with pytest.raises(RawDataContractError, match="shape"):
        validate_rawdata_item(path)


def test_validate_rawdata_item_rejects_legacy_missing_schema_version(tmp_path):
    path = _write_npz(
        tmp_path / "legacy_missing_schema.npz",
        metadata={"rawdata_name": "legacy", "shape": [1]},
        values=[1.0],
        add_schema_version=False,
    )

    with pytest.raises(RawDataContractError, match="schema_version") as exc_info:
        validate_rawdata_item(path)
    assert exc_info.value.error_type == "legacy_schema"


def test_validate_rawdata_item_rejects_shape_mismatch(tmp_path):
    path = _write_npz(
        tmp_path / "bad_shape.npz",
        metadata={"rawdata_name": "bad", "shape": [2]},
        values=[1.0, 2.0, 3.0],
    )

    with pytest.raises(RawDataContractError, match="shape mismatch"):
        validate_rawdata_item(path)


def test_validate_rawdata_item_rejects_axes_mapping(tmp_path):
    path = _write_npz(
        tmp_path / "bad_axes_mapping.npz",
        metadata={"rawdata_name": "bad", "shape": [3], "axes": {"time": "seconds"}},
        values=[1.0, 2.0, 3.0],
    )

    with pytest.raises(RawDataContractError, match="sequence"):
        validate_rawdata_item(path)


def test_validate_rawdata_item_rejects_axes_length_mismatch(tmp_path):
    path = _write_npz(
        tmp_path / "bad_axes_length.npz",
        metadata={"rawdata_name": "bad", "shape": [2, 2], "axes": [{"index": 0, "size": 2}]},
        values=np.ones((2, 2)),
    )

    with pytest.raises(RawDataContractError, match="axes length"):
        validate_rawdata_item(path)


def test_validate_rawdata_item_rejects_axes_out_of_order(tmp_path):
    path = _write_npz(
        tmp_path / "bad_axes_order.npz",
        metadata={
            "rawdata_name": "bad",
            "shape": [2, 2],
            "axes": [{"index": 1, "size": 2}, {"index": 0, "size": 2}],
        },
        values=np.ones((2, 2)),
    )

    with pytest.raises(RawDataContractError, match="ordered by index"):
        validate_rawdata_item(path)


def test_validate_rawdata_item_rejects_axis_value_length_mismatch(tmp_path):
    path = _write_npz(
        tmp_path / "bad_axis_values.npz",
        metadata={
            "rawdata_name": "bad",
            "shape": [3],
            "axes": [{"index": 0, "size": 3, "values_key": "axis_0"}],
        },
        values=[1.0, 2.0, 3.0],
        axis_0=np.asarray([0.0, 1.0]),
    )

    with pytest.raises(RawDataContractError, match="values length mismatch"):
        validate_rawdata_item(path)


def test_validate_rawdata_directory_requires_flat_directory(tmp_path):
    raw_dir = tmp_path / "rawData"
    raw_dir.mkdir()
    (raw_dir / "nested").mkdir()

    with pytest.raises(RawDataContractError, match="flat"):
        validate_rawdata_directory(raw_dir)


def test_rawdata_view_exposes_named_axes_and_selects_multidimensional_data(tmp_path):
    path = _write_npz(
        tmp_path / "surface.npz",
        metadata={
            "rawdata_name": "surface",
            "shape": [2, 3],
            "axis_names": ["Freq", "Theta"],
            "axes": [
                {"index": 0, "size": 2, "name": "Freq", "values_key": "axis_Freq", "unit": "GHz"},
                {"index": 1, "size": 3, "name": "Theta", "values_key": "axis_Theta", "unit": "deg"},
            ],
        },
        data=np.asarray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
        axis_Freq=np.asarray([2.4, 2.5]),
        axis_Theta=np.asarray([-30.0, 0.0, 30.0]),
    )

    view = RawDataView.from_item(path)
    frequency_cut = view.select("Freq", 2.5, 0.01)
    selected = frequency_cut.select("Theta", 30.0, 0.1, period=360.0)

    assert view.name == "surface"
    assert view.data_key == "data"
    assert view.axis_names == ("Freq", "Theta")
    assert view.axis("Freq")[1] == "GHz"
    assert frequency_cut.axis("Theta")[0].tolist() == [-30.0, 0.0, 30.0]
    assert float(selected.data) == 6.0


def test_rawdata_view_range_indices_support_unit_conversion(tmp_path):
    path = _write_npz(
        tmp_path / "curve.npz",
        metadata={
            "rawdata_name": "curve",
            "shape": [4],
            "axis_names": ["Freq"],
            "axes": [{"index": 0, "size": 4, "name": "Freq", "values_key": "axis_Freq", "unit": "MHz"}],
        },
        data=np.asarray([1.0, 2.0, 3.0, 4.0]),
        axis_Freq=np.asarray([2300.0, 2400.0, 2480.0, 2600.0]),
    )

    view = RawDataView.from_item(path)
    indices = view.range_indices("Freq", 2.4, 2.48, converter=lambda values, _unit: values * 1e-3)

    assert indices.tolist() == [1, 2]


def test_rawdata_unit_converters():
    assert frequency_to_ghz(np.asarray([2400.0]), "MHz").tolist() == [2.4]
    assert angle_to_degrees(np.asarray([np.pi]), "rad").tolist() == pytest.approx([180.0])


def test_rawdata_axis_markers_apply_ranges_and_periodic_points(tmp_path):
    path = _write_npz(
        tmp_path / "surface.npz",
        metadata={
            "rawdata_name": "surface",
            "shape": [3, 3],
            "axis_names": ["Freq", "Theta"],
            "axes": [
                {"index": 0, "size": 3, "name": "Freq", "values_key": "axis_Freq", "unit": "GHz"},
                {"index": 1, "size": 3, "name": "Theta", "values_key": "axis_Theta", "unit": "deg"},
            ],
        },
        data=np.zeros((3, 3)),
        axis_Freq=np.asarray([2.3, 2.4, 2.5]),
        axis_Theta=np.asarray([-30.0, 0.0, 30.0]),
    )
    view = RawDataView.from_item(path)
    range_weights = np.zeros((3, 3))
    point_weights = np.zeros((3, 3))

    mark_axis_range(range_weights, view, "Freq", 2.4, 2.5, 2.0)
    mark_axis_points(point_weights, view, "Theta", (-30.0, 30.0), 0.1, 3.0, period=360.0)

    assert range_weights.tolist() == [[0.0, 0.0, 0.0], [2.0, 2.0, 2.0], [2.0, 2.0, 2.0]]
    assert point_weights.tolist() == [[3.0, 0.0, 3.0], [3.0, 0.0, 3.0], [3.0, 0.0, 3.0]]
