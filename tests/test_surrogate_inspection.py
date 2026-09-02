from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("torch")

from yadof.tools.surrogate_viewer import inspection as inspection_module
from yadof.tools.surrogate_viewer.backend import (
    CheckpointInfo,
    ParameterSpec,
    PlotData,
    PredictionResult,
    RealResult,
    rawdata_dimensions,
)
from yadof.tools.surrogate_viewer.errors import (
    SurrogateToolError,
    format_surrogate_error,
    normalize_surrogate_error,
)
from yadof.tools.surrogate_viewer.inspection import (
    INLINE_GRID_SCALAR_LIMIT,
    build_case_inspection,
    export_case_inspection,
    render_case_inspection,
)


def _raw_item(
    name: str,
    values: np.ndarray,
    axes: tuple[tuple[str, np.ndarray, str], ...],
) -> dict[str, object]:
    data = np.asarray(values, dtype=float)
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
    item: dict[str, object] = {
        "data": data,
        "metadata": np.asarray(json.dumps(metadata)),
    }
    item.update(
        {
            f"axis_{axis_name}": np.asarray(coordinates, dtype=float)
            for axis_name, coordinates, _unit in axes
        }
    )
    return item


def _viewer(
    tmp_path: Path,
    prediction_values: np.ndarray,
    axes: tuple[tuple[str, np.ndarray, str], ...],
    *,
    truth_values: np.ndarray | None = None,
    off_grid: bool = False,
    predicted_cost: float = 2.5,
    true_cost: float = 2.0,
) -> SimpleNamespace:
    tmp_path.mkdir(parents=True, exist_ok=True)
    rawdata_name = "response"
    prediction_item = _raw_item(rawdata_name, prediction_values, axes)
    truth_item = _raw_item(
        rawdata_name,
        np.asarray(prediction_values) + 0.5
        if truth_values is None
        else truth_values,
        axes,
    )
    lower_item = _raw_item(
        rawdata_name,
        np.asarray(prediction_values) - 1.0,
        axes,
    )
    upper_item = _raw_item(
        rawdata_name,
        np.asarray(prediction_values) + 1.0,
        axes,
    )
    dimensions = rawdata_dimensions((prediction_item,), 0)
    checkpoint_payload = {
        "surrogate_method": "conditional_inr",
        "training_policy": "real_field_balanced",
        "state_signature": "a" * 64,
        "strategy_signature": "f" * 64,
        "run_namespace": "strategy-" + "f" * 16,
        "component_namespace": "conditional-inr",
        "publication_id": "00000000000000000009_" + "b" * 32,
    }
    checkpoint_path = tmp_path / "generation_0009.json"
    checkpoint_path.write_text(json.dumps(checkpoint_payload), encoding="utf-8")
    checkpoint = CheckpointInfo(
        generation=9,
        path=checkpoint_path,
        sample_count=37,
        member_count=2,
        payload=checkpoint_payload,
    )
    real_result = RealResult(
        job_name="job-7",
        generation=3,
        population_index=7,
        raw_values=(12.0,),
        normalized_values=(0.25,),
    )

    def predict_one(
        checkpoint_generation: int,
        normalized_values: tuple[float, ...],
        *,
        true_job_name: str | None,
        plot_request,
    ) -> PredictionResult:
        assert checkpoint_generation == 9
        assert normalized_values == (0.25,)
        assert true_job_name == "job-7"
        if off_grid:
            plotted = tuple(
                dimensions[index]
                for index in plot_request.plotted_dimensions
            )
            shape = tuple(
                np.asarray(dimension.coordinates).size
                for dimension in plotted
            )
            direct_values = np.arange(
                max(1, int(np.prod(shape, dtype=int))),
                dtype=float,
            ).reshape(shape)

            def direct_plot(offset: float) -> PlotData:
                return PlotData(
                    name=rawdata_name,
                    dimensions=plotted,
                    values=direct_values + offset,
                    slice_label="off-grid query",
                )

            predicted_plot = direct_plot(10.0)
            member_plots = (direct_plot(9.0), direct_plot(11.0))
        else:
            predicted_plot = None
            member_plots = ()
        return PredictionResult(
            checkpoint_generation=9,
            normalized_values=(0.25,),
            raw_values=(12.0,),
            predicted_sample=(prediction_item,),
            member_samples=((lower_item,), (upper_item,)),
            predicted_costs=(predicted_cost,),
            true_sample=(truth_item,),
            true_costs=(true_cost,),
            true_job_name=true_job_name,
            predicted_plot=predicted_plot,
            member_plots=member_plots,
        )

    return SimpleNamespace(
        root=tmp_path,
        strategy_signature="f" * 64,
        run_namespace="strategy-" + "f" * 16,
        component_namespace="conditional-inr",
        checkpoints=(checkpoint,),
        real_results=(real_result,),
        rawdata_names=(rawdata_name,),
        parameters=(ParameterSpec("length", "mm", ((0.0, 20.0),)),),
        objective_names=("loss",),
        dimensions_for_rawdata=lambda _index: dimensions,
        predict_one=predict_one,
    )


def _build(viewer: SimpleNamespace, **overrides) -> object:
    options = {
        "job_name": "job-7",
        "rawdata_name": "response",
    }
    options.update(overrides)
    return build_case_inspection(viewer, **options)


def _error_code(call) -> str:
    with pytest.raises(SurrogateToolError) as caught:
        call()
    return caught.value.code


def test_inspection_resolves_both_real_selectors_and_default_query(
    tmp_path: Path,
) -> None:
    axes = (
        ("Freq", np.asarray([1.0, 2.0]), "GHz"),
        ("Theta", np.asarray([-1.0, 0.0, 1.0]), "deg"),
    )
    viewer = _viewer(tmp_path, np.arange(6.0).reshape(2, 3), axes)

    by_position = _build(
        viewer,
        job_name=None,
        real_generation=3,
        population_index=7,
    )
    by_job = _build(viewer)

    payload = by_position.payload
    assert payload["schema_version"] == 1
    assert payload["analysis"] == "surrogate_case_inspection"
    assert payload["checkpoint"]["generation"] == 9
    assert payload["checkpoint"]["sample_count"] == 37
    assert payload["checkpoint"]["member_count"] == 2
    assert len(payload["checkpoint"]["manifest_sha256"]) == 64
    assert payload["real_result"]["job_name"] == "job-7"
    assert payload["parameters"] == [
        {
            "name": "length",
            "unit": "mm",
            "raw_value": 12.0,
            "normalized_value": 0.25,
        }
    ]
    assert payload["query"]["plot_dimension_source"] == "default"
    assert payload["query"]["plot_dimensions"][0]["name"] == "Freq"
    assert payload["query"]["fixed_coordinates"] == [
        {
            "index": 1,
            "name": "Theta",
            "unit": "deg",
            "requested_value": 0.0,
            "value": 0.0,
            "source": "default",
            "on_grid": True,
        }
    ]
    assert payload["query"]["on_grid"] is True
    assert payload["error_summary"]["finite_count"] == 2
    assert payload["objectives"][0]["absolute_error"] == 0.5
    assert by_job.payload["real_result"]["selector"] == {
        "type": "job_name",
        "job_name": "job-7",
    }


def test_inspection_rejects_missing_ambiguous_and_invalid_real_selectors(
    tmp_path: Path,
) -> None:
    axes = (("Freq", np.asarray([1.0, 2.0]), "GHz"),)
    viewer = _viewer(tmp_path, np.asarray([1.0, 2.0]), axes)

    assert _error_code(
        lambda: _build(viewer, job_name="missing")
    ) == "REAL_RESULT_NOT_FOUND"

    viewer.real_results = (*viewer.real_results, viewer.real_results[0])
    assert _error_code(lambda: _build(viewer)) == "REAL_RESULT_AMBIGUOUS"
    viewer.real_results = viewer.real_results[:1]

    assert _error_code(
        lambda: _build(
            viewer,
            job_name=None,
            real_generation=3,
            population_index=None,
        )
    ) == "INVALID_REAL_RESULT_SELECTOR"
    assert _error_code(
        lambda: _build(
            viewer,
            real_generation=3,
            population_index=7,
        )
    ) == "INVALID_REAL_RESULT_SELECTOR"


def test_inspection_reports_checkpoint_rawdata_and_plot_request_errors(
    tmp_path: Path,
) -> None:
    axes = (
        ("x", np.asarray([0.0, 1.0]), "m"),
        ("y", np.asarray([-1.0, 1.0]), "m"),
        ("z", np.asarray([0.0, 2.0]), "m"),
    )
    viewer = _viewer(tmp_path, np.arange(8.0).reshape(2, 2, 2), axes)

    checkpoints = viewer.checkpoints
    viewer.checkpoints = ()
    assert _error_code(lambda: _build(viewer)) == "NO_COMPATIBLE_CHECKPOINT"
    viewer.checkpoints = checkpoints
    assert _error_code(
        lambda: _build(viewer, checkpoint_generation=8)
    ) == "CHECKPOINT_NOT_FOUND"
    with pytest.raises(SurrogateToolError) as missing_rawdata:
        _build(viewer, rawdata_name="missing")
    assert missing_rawdata.value.code == "RAWDATA_NOT_FOUND"
    assert missing_rawdata.value.details["available_names"] == ["response"]
    assert _error_code(
        lambda: _build(viewer, plot_dimension_names=("missing",))
    ) == "INVALID_PLOT_REQUEST"
    assert _error_code(
        lambda: _build(
            viewer,
            plot_dimension_names=("x", "y", "z"),
        )
    ) == "INVALID_PLOT_REQUEST"
    assert _error_code(
        lambda: _build(
            viewer,
            plot_dimension_names=("x",),
            fixed_coordinates=(("x", 0.0),),
        )
    ) == "INVALID_PLOT_REQUEST"
    assert _error_code(
        lambda: _build(
            viewer,
            fixed_coordinates=(("missing", 0.0),),
        )
    ) == "INVALID_PLOT_REQUEST"


@pytest.mark.parametrize(
    ("values", "axes", "plot_dimensions", "expected_shape"),
    (
        (np.asarray(2.0), (), (), ()),
        (
            np.asarray([1.0, 2.0, 3.0]),
            (("distance", np.asarray([0.0, 1.0, 2.0]), "m"),),
            (),
            (3,),
        ),
        (
            np.arange(6.0).reshape(2, 3),
            (
                ("x", np.asarray([0.0, 1.0]), "m"),
                ("y", np.asarray([-1.0, 0.0, 1.0]), "m"),
            ),
            ("x", "y"),
            (2, 3),
        ),
    ),
    ids=("scalar", "curve", "surface"),
)
def test_inspection_supports_zero_one_and_two_dimensional_slices(
    tmp_path: Path,
    values: np.ndarray,
    axes: tuple[tuple[str, np.ndarray, str], ...],
    plot_dimensions: tuple[str, ...],
    expected_shape: tuple[int, ...],
) -> None:
    viewer = _viewer(tmp_path, values, axes)

    result = _build(viewer, plot_dimension_names=plot_dimensions)

    assert result.prediction.shape == expected_shape
    assert result.payload["query"]["slice_rank"] == len(expected_shape)
    assert result.payload["query"]["shape"] == list(expected_shape)
    json.dumps(result.payload, allow_nan=False)


def test_off_grid_query_omits_truth_and_error_with_warning(tmp_path: Path) -> None:
    axes = (
        ("Freq", np.asarray([1.0, 2.0]), "GHz"),
        ("Theta", np.asarray([-1.0, 1.0]), "deg"),
    )
    viewer = _viewer(
        tmp_path,
        np.arange(4.0).reshape(2, 2),
        axes,
        off_grid=True,
    )

    result = _build(
        viewer,
        plot_dimension_names=("Freq",),
        fixed_coordinates=(("Theta", 0.25),),
    )

    assert result.payload["query"]["on_grid"] is False
    assert result.payload["query"]["mode"] == "off_grid"
    assert result.payload["truth"] is None
    assert result.payload["error_summary"] is None
    assert result.truth is None
    assert any("off-grid" in warning for warning in result.payload["warnings"])


def test_json_is_finite_null_safe_and_large_arrays_are_bounded(
    tmp_path: Path,
) -> None:
    small_axes = (("x", np.arange(4.0), "m"),)
    small = _viewer(
        tmp_path / "small",
        np.asarray([np.nan, np.inf, -np.inf, 4.0]),
        small_axes,
        truth_values=np.asarray([1.0, 2.0, np.nan, 1.0]),
        predicted_cost=np.inf,
        true_cost=np.nan,
    )
    small_result = _build(small)
    encoded = json.dumps(small_result.payload, allow_nan=False)
    decoded = json.loads(encoded)

    assert decoded["prediction"]["values"] == [None, None, None, 4.0]
    assert decoded["prediction"]["finite_count"] == 1
    assert decoded["error_summary"]["finite_count"] == 1
    assert decoded["objectives"][0] == {
        "name": "loss",
        "predicted": None,
        "true": None,
        "absolute_error": None,
    }
    assert "NaN" not in encoded
    assert "Infinity" not in encoded

    rows, columns = 65, 64
    large_axes = (
        ("x", np.arange(rows, dtype=float), "m"),
        ("y", np.arange(columns, dtype=float), "m"),
    )
    large = _viewer(
        tmp_path / "large",
        np.arange(rows * columns, dtype=float).reshape(rows, columns),
        large_axes,
    )
    large_result = _build(
        large,
        plot_dimension_names=("x", "y"),
    )

    assert rows * columns > INLINE_GRID_SCALAR_LIMIT
    assert large_result.payload["prediction"]["values_omitted"] is True
    assert large_result.payload["prediction"]["values"] is None
    assert all(
        dimension["coordinates_omitted"] is True
        for dimension in large_result.payload["query"]["plot_dimensions"]
    )
    assert any("--output" in warning for warning in large_result.payload["warnings"])


def test_render_without_output_does_not_write_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    axes = (("x", np.asarray([0.0, 1.0]), "m"),)
    viewer = _viewer(tmp_path, np.asarray([1.0, 2.0]), axes)
    before = {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
    }
    monkeypatch.setattr(
        inspection_module,
        "SurrogateWorkspace",
        lambda _workspace: viewer,
    )

    rendered = render_case_inspection(
        tmp_path,
        job_name="job-7",
        rawdata_name="response",
        output_format="json",
    )

    assert json.loads(rendered)["artifacts"]["files"] == []
    assert {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
    } == before


@pytest.mark.parametrize(
    ("values", "axes", "plot_dimensions", "has_curve"),
    (
        (np.asarray(2.0), (), (), False),
        (
            np.asarray([1.0, 2.0, 3.0]),
            (("x", np.asarray([0.0, 1.0, 2.0]), "m"),),
            (),
            True,
        ),
        (
            np.arange(6.0).reshape(2, 3),
            (
                ("x", np.asarray([0.0, 1.0]), "m"),
                ("y", np.asarray([-1.0, 0.0, 1.0]), "m"),
            ),
            ("x", "y"),
            False,
        ),
    ),
    ids=("scalar", "curve", "surface"),
)
def test_headless_export_writes_readable_hashed_artifacts_for_each_rank(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    values: np.ndarray,
    axes: tuple[tuple[str, np.ndarray, str], ...],
    plot_dimensions: tuple[str, ...],
    has_curve: bool,
) -> None:
    pytest.importorskip("matplotlib")
    case_root = tmp_path / "case"
    viewer = _viewer(case_root, values, axes)
    inspection = _build(viewer, plot_dimension_names=plot_dimensions)
    output = tmp_path / "evidence"
    original_import = builtins.__import__

    def reject_gui_imports(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tkinter" or name.startswith("tkinter."):
            raise AssertionError(f"headless renderer imported {name}")
        if "backend_tkagg" in name:
            raise AssertionError(f"headless renderer imported {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_gui_imports)
    payload = export_case_inspection(inspection, output)

    expected = {"manifest.json", "data.npz", "plot.png"}
    if has_curve:
        expected.add("curve.csv")
    assert {path.name for path in output.iterdir()} == expected
    assert (output / "plot.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    from matplotlib import image as matplotlib_image

    assert matplotlib_image.imread(output / "plot.png").ndim in {2, 3}
    with np.load(output / "data.npz", allow_pickle=False) as archive:
        np.testing.assert_allclose(archive["prediction"], inspection.prediction)
        assert tuple(archive["coordinate_names"].tolist()) == (
            inspection.dimension_names
        )
    if has_curve:
        assert (output / "curve.csv").read_text(encoding="utf-8").startswith(
            "coordinate,prediction,truth,ensemble_minimum,ensemble_maximum\n"
        )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == payload
    assert manifest["artifacts"]["manifest"] == {"path": "manifest.json"}
    for artifact in manifest["artifacts"]["files"]:
        artifact_path = output / artifact["path"]
        assert artifact_path.stat().st_size == artifact["size_bytes"]
        assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == (
            artifact["sha256"]
        )


def test_export_refuses_nonempty_output_without_overwriting(tmp_path: Path) -> None:
    axes = (("x", np.asarray([0.0, 1.0]), "m"),)
    viewer = _viewer(tmp_path / "case", np.asarray([1.0, 2.0]), axes)
    inspection = _build(viewer)
    output = tmp_path / "occupied"
    output.mkdir()
    existing = output / "keep.txt"
    existing.write_text("keep", encoding="utf-8")

    with pytest.raises(SurrogateToolError) as caught:
        export_case_inspection(inspection, output)

    assert caught.value.code == "OUTPUT_CONFLICT"
    assert existing.read_text(encoding="utf-8") == "keep"
    assert tuple(output.iterdir()) == (existing,)


def test_failed_render_leaves_no_manifest_or_apparently_complete_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.tools.surrogate_viewer import renderer

    axes = (("x", np.asarray([0.0, 1.0]), "m"),)
    viewer = _viewer(tmp_path / "case", np.asarray([1.0, 2.0]), axes)
    inspection = _build(viewer)
    output = tmp_path / "failed-evidence"

    def fail_render(*_args, **_kwargs):
        raise RuntimeError("controlled renderer failure")

    monkeypatch.setattr(renderer, "render_case_plot", fail_render)
    with pytest.raises(SurrogateToolError) as caught:
        export_case_inspection(inspection, output)

    assert caught.value.code == "RENDER_FAILED"
    assert not (output / "manifest.json").exists()
    assert not output.exists()


def test_output_publication_failure_is_typed_and_leaves_no_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.tools.surrogate_viewer import renderer

    axes = (("x", np.asarray([0.0, 1.0]), "m"),)
    viewer = _viewer(tmp_path / "case", np.asarray([1.0, 2.0]), axes)
    inspection = _build(viewer)
    output = tmp_path / "failed-publication"

    monkeypatch.setattr(renderer, "render_case_plot", lambda *_args, **_kwargs: None)

    def fail_publication(*_args, **_kwargs):
        raise OSError("controlled publication failure")

    monkeypatch.setattr(
        inspection_module,
        "_publish_exclusive",
        fail_publication,
    )
    with pytest.raises(SurrogateToolError) as caught:
        export_case_inspection(inspection, output)

    assert caught.value.code == "OUTPUT_WRITE_FAILED"
    assert caught.value.details["stage"] == "publish artifacts"
    assert not (output / "manifest.json").exists()
    assert not output.exists()


def test_structured_errors_are_standard_json_and_dependency_typed() -> None:
    missing = ModuleNotFoundError("No module named 'torch'", name="torch")
    normalized = normalize_surrogate_error(missing, operation="inspect")

    assert normalized.code == "MISSING_OPTIONAL_DEPENDENCY"
    payload = json.loads(
        format_surrogate_error(normalized, output_format="json")
    )
    assert payload["schema_version"] == 1
    assert payload["analysis"] == "surrogate_tool_error"
    assert payload["error"]["details"] == {
        "operation": "inspect",
        "dependency": "torch",
    }
    assert payload["error"]["hints"]
