from __future__ import annotations

import json
from pathlib import Path
from threading import Event

import numpy as np
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("torch")

from yadof.tools.surrogate_viewer.backend import (
    AuditCancelled,
    CrossGenerationErrorAudit,
    RealResult,
    discover_checkpoints,
    extract_curve,
    finite_curve_statistics,
    sample_real_results_by_generation,
    _check_cancelled,
)
from yadof.tools.surrogate_viewer.app import _is_widget_descendant


def _raw_item(name: str, data: np.ndarray) -> dict[str, object]:
    metadata = {
        "schema_version": 1,
        "rawdata_name": name,
        "axis_names": ["Freq", "Theta"],
        "axes": [
            {
                "index": 0,
                "size": data.shape[0],
                "name": "Freq",
                "values_key": "axis_Freq",
                "unit": "GHz",
            },
            {
                "index": 1,
                "size": data.shape[1],
                "name": "Theta",
                "values_key": "axis_Theta",
                "unit": "deg",
            },
        ],
        "shape": list(data.shape),
    }
    return {
        "data": data,
        "axis_Freq": np.asarray([1.0, 2.0]),
        "axis_Theta": np.asarray([-90.0, 0.0, 90.0]),
        "metadata": np.asarray(json.dumps(metadata)),
    }


def test_discover_checkpoints_sorts_and_skips_bad_json(tmp_path: Path) -> None:
    (tmp_path / "generation_0003.json").write_text(
        json.dumps(
            {
                "generation_index": 3,
                "sample_count": 20,
                "member_count": 2,
                "schema": {"flat_dim": 1},
                "parameter_names": ["x"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "generation_0001.json").write_text(
        json.dumps(
            {
                "generation_index": 1,
                "sample_count": 10,
                "train_history": {"member_count": 4},
                "mean_relative_error": 0.25,
                "schema": {"flat_dim": 1},
                "parameter_names": ["x"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "generation_broken.json").write_text("{", encoding="utf-8")

    checkpoints = discover_checkpoints(tmp_path)

    assert [item.generation for item in checkpoints] == [1, 3]
    assert checkpoints[0].member_count == 4
    assert checkpoints[0].training_error == 0.25


def test_extract_curve_prefers_frequency_and_slices_other_axes_at_zero() -> None:
    data = np.asarray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    curve = extract_curve((_raw_item("gain", data),), 0)

    np.testing.assert_allclose(curve.x, [1.0, 2.0])
    np.testing.assert_allclose(curve.y, [2.0, 5.0])
    assert curve.x_label == "Freq (GHz)"
    assert curve.name == "gain"
    assert "Theta=0 deg" in curve.slice_label


def test_finite_curve_statistics_returns_ensemble_mean_and_std() -> None:
    first = extract_curve((_raw_item("gain", np.ones((2, 3))),), 0)
    second = extract_curve((_raw_item("gain", np.full((2, 3), 3.0)),), 0)

    mean, std = finite_curve_statistics((first, second))

    np.testing.assert_allclose(mean, [2.0, 2.0])
    np.testing.assert_allclose(std, [1.0, 1.0])


def test_tcl_only_combobox_popup_is_not_treated_as_parameter_canvas() -> None:
    """A ttk popdown may be a Tcl path string with no Python widget object."""

    ancestor = object()

    assert not _is_widget_descendant(".combobox.popdown.f.l", ancestor)


def test_error_audit_switches_metrics_from_small_aggregates() -> None:
    audit = CrossGenerationErrorAudit(
        checkpoint_generations=(2, 4),
        optimization_generations=(1,),
        objective_names=("a", "b"),
        rawdata_names=("gain", "s11"),
        sample_counts=(3,),
        relative_sums=np.asarray([[[2.0, 6.0], [4.0, 12.0]]]),
        relative_counts=np.asarray([[[2, 3], [2, 4]]]),
        absolute_sums=np.asarray([[[10.0, 20.0], [30.0, 40.0]]]),
        absolute_counts=np.asarray([[[2, 2], [3, 4]]]),
        raw_relative_sums=np.asarray([[[3.0, 6.0], [8.0, 12.0]]]),
        raw_relative_counts=np.asarray([[[1, 2], [2, 2]]]),
        raw_absolute_sums=np.asarray([[[4.0, 8.0], [10.0, 20.0]]]),
        raw_absolute_counts=np.asarray([[[1, 3], [2, 3]]]),
        sample_fraction=0.1,
    )

    relative_all = audit.matrix(metric="relative")
    relative_b = audit.matrix(
        metric="relative",
        quantity_index=1,
    )
    absolute_all = audit.matrix(metric="absolute")
    relative_raw = audit.matrix(
        metric="relative",
        quantity_kind="rawdata",
    )
    relative_gain = audit.matrix(
        metric="relative",
        quantity_kind="rawdata",
        quantity_index=0,
    )

    np.testing.assert_allclose(relative_all.values, [[8.0 / 5.0, 16.0 / 6.0]])
    np.testing.assert_allclose(relative_b.values, [[2.0, 3.0]])
    np.testing.assert_allclose(absolute_all.values, [[7.5, 10.0]])
    np.testing.assert_allclose(relative_raw.values, [[3.0, 5.0]])
    np.testing.assert_allclose(relative_gain.values, [[3.0, 4.0]])
    assert relative_gain.metric_label.endswith("rawData · gain")
    assert audit.memory_bytes == 256


def test_sampling_is_independent_per_generation_and_never_empty() -> None:
    rows = tuple(
        RealResult(
            job_name=f"g{generation}-{index}",
            generation=generation,
            population_index=index,
            raw_values=(float(index),),
            normalized_values=(float(index) / 10.0,),
        )
        for generation, size in ((0, 10), (1, 11))
        for index in range(size)
    )

    selected = sample_real_results_by_generation(
        rows,
        0.1,
        random_seed=42,
    )

    assert sum(item.generation == 0 for item in selected) == 1
    assert sum(item.generation == 1 for item in selected) == 2
    assert len({item.job_name for item in selected}) == 3


def test_preexisting_stop_request_cancels_audit_work() -> None:
    stop = Event()
    stop.set()

    with pytest.raises(AuditCancelled):
        _check_cancelled(stop)
