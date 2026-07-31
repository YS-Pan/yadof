from __future__ import annotations

import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import tkinter as tk

import numpy as np
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("torch")

from matplotlib.colors import Normalize
from matplotlib.figure import Figure

from yadof.tools.surrogate_viewer.backend import (
    AuditCancelled,
    CrossGenerationErrorAudit,
    DimensionSpec,
    ErrorMatrix,
    PlotData,
    PlotRequest,
    PredictionResult,
    RealResult,
    discover_checkpoints,
    extract_curve,
    extract_plot,
    finite_curve_bounds,
    finite_plot_bounds,
    rawdata_dimensions,
    sample_real_results_by_generation,
    _check_cancelled,
)
from yadof.tools.surrogate_viewer.app import _is_widget_descendant
from yadof.tools.surrogate_viewer.report import (
    build_error_audit_report,
    build_workspace_summary,
    format_error_audit_report,
    format_workspace_summary,
)
from yadof.tools.surrogate_viewer.ui.interactive import InteractiveTab
from yadof.tools.surrogate_viewer.ui.plots import (
    HeatmapPlot,
    InteractivePlot,
)
from yadof.tools.surrogate_viewer.ui.style import ACCENT, PANEL


def _raw_item(name: str, data: np.ndarray) -> dict[str, object]:
    return _nd_raw_item(
        name,
        data,
        (
            ("Freq", np.asarray([1.0, 2.0]), "GHz"),
            ("Theta", np.asarray([-90.0, 0.0, 90.0]), "deg"),
        ),
    )


def _nd_raw_item(
    name: str,
    data: np.ndarray,
    axes: tuple[tuple[str, np.ndarray, str], ...],
) -> dict[str, object]:
    metadata = {
        "schema_version": 1,
        "rawdata_name": name,
        "axis_names": [axis_name for axis_name, _values, _unit in axes],
        "axes": [
            {
                "index": index,
                "size": data.shape[index],
                "name": axis_name,
                "values_key": f"axis_{axis_name}",
                "unit": unit,
            }
            for index, (axis_name, _values, unit) in enumerate(axes)
        ],
        "shape": list(data.shape),
    }
    item = {
        "data": data,
        "metadata": np.asarray(json.dumps(metadata)),
    }
    item.update(
        {
            f"axis_{axis_name}": values
            for axis_name, values, _unit in axes
        }
    )
    return item


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


def test_workspace_summary_has_text_and_machine_readable_json(
    tmp_path: Path,
) -> None:
    rows = (
        RealResult("g0-0", 0, 0, (1.0,), (0.0,)),
        RealResult("g1-0", 1, 0, (2.0,), (1.0,)),
    )
    dimension = DimensionSpec(
        0,
        "Freq",
        np.asarray([1.0, 2.0, 3.0]),
        "GHz",
    )
    viewer = SimpleNamespace(
        root=tmp_path,
        checkpoints=(
            SimpleNamespace(
                generation=2,
                sample_count=20,
                member_count=3,
                training_error=0.125,
                path=tmp_path / "generation_0002.json",
            ),
        ),
        generations=(0, 1),
        real_results=rows,
        results_for_generation=lambda generation: tuple(
            row for row in rows if row.generation == generation
        ),
        parameters=(
            SimpleNamespace(
                name="width",
                unit="mm",
                ranges=((1.0, 5.0),),
            ),
        ),
        objective_names=("loss",),
        rawdata_names=("gain",),
        dimensions_for_rawdata=lambda _index: (dimension,),
    )

    payload = build_workspace_summary(viewer)
    text = format_workspace_summary(payload)
    encoded = json.loads(
        format_workspace_summary(payload, output_format="json")
    )

    assert "generation 2: samples=20, members=3" in text
    assert "optimization generations: 0 (1 results), 1 (1 results)" in text
    assert "gain: Freq[3; 1..3 GHz]" in text
    assert encoded["analysis"] == "surrogate_workspace_summary"
    assert encoded["rawdata"][0]["dimensions"][0]["coordinate_max"] == 3.0


def test_error_audit_report_selects_quantity_and_formats_matrices(
    tmp_path: Path,
) -> None:
    audit = CrossGenerationErrorAudit(
        checkpoint_generations=(2, 4),
        optimization_generations=(1,),
        objective_names=("loss",),
        rawdata_names=("gain", "s11"),
        sample_counts=(3,),
        relative_sums=np.asarray([[[2.0], [4.0]]]),
        relative_counts=np.asarray([[[2], [2]]]),
        absolute_sums=np.asarray([[[10.0], [30.0]]]),
        absolute_counts=np.asarray([[[2], [3]]]),
        raw_relative_sums=np.asarray([[[3.0, 6.0], [0.0, 12.0]]]),
        raw_relative_counts=np.asarray([[[1, 2], [0, 2]]]),
        raw_absolute_sums=np.asarray([[[4.0, 8.0], [0.0, 20.0]]]),
        raw_absolute_counts=np.asarray([[[1, 3], [0, 3]]]),
        sample_fraction=0.25,
    )
    calls: list[dict[str, object]] = []

    def calculate_error_audit(**kwargs):
        calls.append(kwargs)
        return audit

    viewer = SimpleNamespace(
        root=tmp_path,
        objective_names=audit.objective_names,
        rawdata_names=audit.rawdata_names,
        calculate_error_audit=calculate_error_audit,
    )
    payload = build_error_audit_report(
        viewer,
        sample_fraction=0.25,
        random_seed=7,
        metric="both",
        quantity="rawdata:gain",
    )
    text = format_error_audit_report(payload)
    encoded = json.loads(
        format_error_audit_report(payload, output_format="json")
    )

    assert calls == [
        {
            "sample_fraction": 0.25,
            "random_seed": 7,
            "progress": None,
        }
    ]
    assert [item["metric"] for item in payload["matrices"]] == [
        "relative",
        "absolute",
    ]
    assert payload["matrices"][0]["values"] == [[3.0, None]]
    assert "optimization_generation\tsamples\tcheckpoint_2\tcheckpoint_4" in text
    assert "\n1\t3\t3\tn/a" in text
    assert encoded["quantity"]["selector"] == "rawdata:gain"
    assert encoded["matrices"][0]["values"] == [[3.0, None]]

    with pytest.raises(ValueError, match="available names"):
        build_error_audit_report(
            viewer,
            quantity="cost:unknown",
        )
    assert len(calls) == 1


def test_extract_curve_prefers_frequency_and_slices_other_axes_at_zero() -> None:
    data = np.asarray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    curve = extract_curve((_raw_item("gain", data),), 0)

    np.testing.assert_allclose(curve.x, [1.0, 2.0])
    np.testing.assert_allclose(curve.y, [2.0, 5.0])
    assert curve.x_label == "Freq (GHz)"
    assert curve.name == "gain"
    assert "Theta=0 deg" in curve.slice_label


def test_finite_curve_bounds_returns_ensemble_minimum_and_maximum() -> None:
    first = extract_curve((_raw_item("gain", np.ones((2, 3))),), 0)
    second = extract_curve((_raw_item("gain", np.full((2, 3), 3.0)),), 0)

    minimum, maximum = finite_curve_bounds((first, second))

    np.testing.assert_allclose(minimum, [1.0, 1.0])
    np.testing.assert_allclose(maximum, [3.0, 3.0])


def test_extract_plot_supports_scalar_and_user_selected_nd_slices() -> None:
    scalar = _nd_raw_item("scalar", np.asarray(7.5), ())
    scalar_plot = extract_plot((scalar,), 0)

    assert scalar_plot.ndim == 0
    assert float(scalar_plot.values) == 7.5
    assert rawdata_dimensions((scalar,), 0) == ()

    data = np.arange(24.0).reshape(2, 3, 4)
    item = _nd_raw_item(
        "volume",
        data,
        (
            ("Freq", np.asarray([1.0, 2.0]), "GHz"),
            ("Theta", np.asarray([-20.0, 0.0, 20.0]), "deg"),
            ("Phi", np.asarray([-30.0, -10.0, 10.0, 30.0]), "deg"),
        ),
    )
    dimensions = rawdata_dimensions((item,), 0)
    surface = extract_plot(
        (item,),
        0,
        (0, 2),
        {1: 18.0},
    )
    point = extract_plot(
        (item,),
        0,
        (),
        {0: 1.8, 1: -18.0, 2: 9.0},
    )

    assert [dimension.name for dimension in dimensions] == [
        "Freq",
        "Theta",
        "Phi",
    ]
    assert [dimension.label for dimension in surface.dimensions] == [
        "Freq (GHz)",
        "Phi (deg)",
    ]
    np.testing.assert_allclose(surface.values, data[:, 2, :])
    assert "Theta=20 deg" in surface.slice_label
    assert float(point.values) == data[1, 0, 2]
    assert point.ndim == 0

    with pytest.raises(ValueError, match="at most two"):
        extract_plot((item,), 0, (0, 1, 2))


def test_finite_plot_bounds_supports_two_dimensional_member_surfaces() -> None:
    first = _raw_item("gain", np.ones((2, 3)))
    second = _raw_item("gain", np.full((2, 3), 3.0))
    plots = (
        extract_plot((first,), 0, (0, 1)),
        extract_plot((second,), 0, (0, 1)),
    )

    minimum, maximum = finite_plot_bounds(plots)

    np.testing.assert_allclose(minimum, np.ones((2, 3)))
    np.testing.assert_allclose(maximum, np.full((2, 3), 3.0))


def test_off_grid_query_keeps_stored_grid_predictions_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import torch

    from yadof.surrogate import runtime
    from yadof.surrogate.modeling import INRTrainConfig
    from yadof.surrogate.types import (
        RawArraySlot,
        RawDataSchema,
        TargetScaler,
    )

    item = _nd_raw_item(
        "response",
        np.asarray([0.0, 0.0]),
        (("Freq", np.asarray([0.0, 10.0]), "GHz"),),
    )
    schema = RawDataSchema(
        templates=(item,),
        modeled_slots=(
            RawArraySlot(
                item_index=0,
                key="data",
                shape=(2,),
                dtype="float64",
                start=0,
                end=2,
                field_id=0,
            ),
        ),
        flat_dim=2,
        coord_table=np.asarray([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32),
        field_ids=np.asarray([0, 0], dtype=np.int64),
    )
    scaler = TargetScaler(
        mean=np.asarray([10.0, 20.0], dtype=np.float32),
        scale=np.asarray([2.0, 4.0], dtype=np.float32),
    )

    def fake_predict(**kwargs) -> np.ndarray:
        matrix = np.asarray(kwargs["X"], dtype=np.float32)
        coordinates = np.asarray(
            kwargs["coord_table"],
            dtype=np.float32,
        )[:, 0]
        first = matrix[:, 0, None] + coordinates[None, :]
        return np.stack((first, first + 1.0), axis=0)

    monkeypatch.setattr(
        runtime,
        "predict_conditional_inr_members",
        fake_predict,
    )
    normalized = ((0.25,),)
    legacy_scaled = fake_predict(
        X=np.asarray(normalized, dtype=np.float32),
        coord_table=schema.coord_table,
    )
    legacy_physical = scaler.inverse_members(legacy_scaled)

    stored_grid = runtime.predict_rawdata_slot_members_at_coordinates(
        model=object(),
        schema=schema,
        scaler=scaler,
        train_cfg=INRTrainConfig(),
        device=torch.device("cpu"),
        normalized_rows=normalized,
        item_index=0,
        key="data",
        axis_coordinates=(np.asarray([0.0, 10.0]),),
    )
    midpoint = runtime.predict_rawdata_slot_members_at_coordinates(
        model=object(),
        schema=schema,
        scaler=scaler,
        train_cfg=INRTrainConfig(),
        device=torch.device("cpu"),
        normalized_rows=normalized,
        item_index=0,
        key="data",
        axis_coordinates=(np.asarray([5.0]),),
    )

    np.testing.assert_array_equal(stored_grid, legacy_physical)
    np.testing.assert_allclose(midpoint[:, 0, 0], [15.75, 18.75])
    np.testing.assert_array_equal(
        schema.coord_table,
        np.asarray([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32),
    )
    np.testing.assert_array_equal(scaler.mean, [10.0, 20.0])


def test_two_dimensional_plot_is_a_filled_contour_without_line_overlay() -> None:
    plot = PlotData(
        name="surface",
        dimensions=(
            DimensionSpec(0, "x", np.asarray([0.0, 1.0]), "m"),
            DimensionSpec(1, "y", np.asarray([0.0, 1.0, 2.0]), "s"),
        ),
        values=np.arange(6.0).reshape(2, 3),
        slice_label="",
    )
    axis = Figure().add_subplot()

    artist = InteractivePlot._draw_surface(
        axis,
        plot,
        Normalize(vmin=0.0, vmax=5.0),
        "prediction",
    )

    assert artist.filled
    assert axis.get_xlabel() == "x (m)"
    assert axis.get_ylabel() == "y (s)"
    assert not axis.lines


def test_interactive_tab_lists_dimensions_and_enforces_two_axis_limit() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display is unavailable: {exc}")
    root.withdraw()
    try:
        item = _nd_raw_item(
            "volume",
            np.arange(24.0).reshape(2, 3, 4),
            (
                ("Freq", np.asarray([1.0, 2.0]), "GHz"),
                ("Theta", np.asarray([-20.0, 0.0, 20.0]), "deg"),
                ("Phi", np.asarray([-30.0, -10.0, 10.0, 30.0]), "deg"),
            ),
        )
        default_real = RealResult(
            job_name="job-0",
            generation=0,
            population_index=0,
            raw_values=(),
            normalized_values=(),
        )
        workspace = SimpleNamespace(
            checkpoints=(
                SimpleNamespace(label="Generation 1", generation=1),
            ),
            generations=(0,),
            rawdata_names=("volume",),
            parameters=(),
            objective_names=("cost",),
            denormalize=lambda _values: (),
            results_for_generation=lambda _generation: (default_real,),
            dimensions_for_rawdata=lambda _index: rawdata_dimensions(
                (item,),
                0,
            ),
        )
        prediction_requests: list[None] = []
        tab = InteractiveTab(
            root,
            on_prediction_request=lambda: prediction_requests.append(None),
        )
        tab.load_workspace(workspace)
        prediction = PredictionResult(
            checkpoint_generation=1,
            normalized_values=(),
            raw_values=(),
            predicted_sample=(item,),
            member_samples=((item,),),
            predicted_costs=(1.0,),
        )
        tab.show_prediction(prediction)

        assert [dimension.name for dimension in tab._dimension_specs] == [
            "Freq",
            "Theta",
            "Phi",
        ]
        assert [
            variable.get()
            for variable in tab._dimension_plot_vars
        ] == [True, False, False]
        assert tab.dimension_toggles[0].cget("text").startswith("✓")
        assert tab.dimension_toggles[1].cget("text").startswith("□")
        assert tab.auto_refresh_toggle.cget("text") == "✓  Auto refresh"
        assert tab.auto_refresh_toggle.cget("background") == ACCENT
        assert tab.real_generation_var.get() == "0"
        assert tab.real_result_var.get() == default_real.label
        assert tab.prediction_inputs()[2] == default_real.job_name
        request = tab.prediction_inputs()[3]
        assert isinstance(request, PlotRequest)
        assert request.plotted_dimensions == (0,)
        assert request.fixed_map == {1: 0.0, 2: -10.0}
        assert tuple(tab._dimension_grid_combos[1]["values"]) == (
            "-20",
            "0",
            "20",
        )

        tab._dimension_fixed_vars[1].set("7.5")
        tab._fixed_dimension_changed(1)
        assert tab._dimension_fixed_vars[1].get() == "7.5"
        assert tab._dimension_grid_combos[1].get() == ""
        assert tab.prediction_inputs()[3].fixed_map[1] == 7.5
        assert prediction_requests

        tab.auto_refresh_toggle.invoke()
        assert not tab.auto_refresh_var.get()
        assert tab.auto_refresh_toggle.cget("text") == "□  Auto refresh"
        assert tab.auto_refresh_toggle.cget("background") == PANEL

        tab._dimension_plot_vars[1].set(True)
        tab._dimension_selection_changed(1)
        tab.show_prediction(prediction)
        assert tab.plot.curve_ax.get_xlabel() == "Freq (GHz)"
        assert tab.plot.curve_ax.get_ylabel() == "Theta (deg)"

        tab._dimension_plot_vars[2].set(True)
        tab._dimension_selection_changed(2)
        assert not tab._dimension_plot_vars[2].get()
        assert tab.dimension_toggles[2].cget("text").startswith("□")
    finally:
        root.destroy()


def test_heatmap_cells_touch_without_grid_edges() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display is unavailable: {exc}")
    root.withdraw()
    try:
        plot = HeatmapPlot(root)
        plot.draw(
            ErrorMatrix(
                checkpoint_generations=(1, 2),
                optimization_generations=(3, 4),
                values=np.asarray([[0.1, 0.2], [0.3, 0.4]]),
                metric_label="Mean relative error · all costs",
                sample_counts=(1, 1),
            )
        )

        mesh = plot.ax.collections[0]
        np.testing.assert_allclose(mesh.get_linewidths(), 0.0)
        assert mesh.get_edgecolors().size == 0
    finally:
        root.destroy()


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
