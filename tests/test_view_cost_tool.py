from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

import yadof.tools.cost_viewer as cost_viewer
import yadof.tools.view_cost as view_cost
from yadof.tools.cost_viewer import plotting
from yadof.tools.cost_viewer import style


class FakeRecordedDataApi:
    def __init__(self, history, opt_metadata=(), records=None):
        self.history = history
        self.opt_metadata = opt_metadata
        self.records = records
        self.history_calls = []
        self.progress_calls = []

    def open_historical_rawdata_snapshot(self, _workspace, *, status="completed"):
        self.history_calls.append(status)
        records_by_job = {
            str(record.get("job_name")): record
            for record in self.list_records(_workspace)
            if isinstance(record, dict)
        }
        rows = []
        max_variable_count = max(
            (
                len(item[1])
                for item in self.history
                if isinstance(item, tuple) and len(item) >= 2
            ),
            default=2,
        )
        max_variable_count = max(2, max_variable_count)
        for item in self.history:
            job_name = str(item[0]) if isinstance(item, tuple) and item else ""
            record = dict(records_by_job.get(job_name, {"job_name": job_name}))
            if isinstance(item, tuple) and len(item) >= 3:
                variables = tuple(item[1])
                record["raw_variables"] = {
                    f"x{index}": value
                    for index, value in enumerate(
                        variables + (0.0,) * (max_variable_count - len(variables))
                    )
                }
                items = (SimpleNamespace(payload={"costs": item[2]}),)
            else:
                items = ()
            rows.append((SimpleNamespace(record=record), items))
        return SimpleNamespace(
            diagnostics=(),
            segment_paths=("history",),
            iter_batches=lambda: iter(
                (SimpleNamespace(records=tuple(rows), diagnostics=()),)
            ),
        )

    def list_records(self, _workspace):
        if self.records is not None:
            return self.records
        return (
            {
                "job_name": "job_a",
                "job_metadata": {"job_static_hash": "hash_a"},
            },
            {
                "job_name": "job_b",
                "job_metadata": {"job_static_hash": "hash_a"},
            },
            {
                "job_name": "job_c",
                "job_metadata": {"job_static_hash": "hash_b"},
            },
        )

    def list_optimization_metadata(self, _workspace):
        return self.opt_metadata


class FakeCostInterpreter:
    def __init__(self):
        self.parameter_names = ("x0", "x1")
        self.objective_names = ("objective_1", "objective_2")

    def normalize_variables(self, raw_variables):
        return tuple(float(value) for value in raw_variables)

    def calculate_costs(self, samples, _raw_variables):
        return tuple(tuple(sample[0]["costs"]) for sample in samples)


@pytest.fixture(autouse=True)
def fake_task_interpreter(monkeypatch):
    @contextmanager
    def open_interpreter(_workspace):
        yield FakeCostInterpreter()

    monkeypatch.setattr(
        "yadof.tools.cost_viewer.history.job_template_api.task_cost_interpreter",
        open_interpreter,
    )


def test_build_rows_uses_recorded_data_history():
    fake_api = FakeRecordedDataApi(
        history=(
            ("job_a", (0.1, 0.2), (0.5, 0.8)),
            ("job_b", (0.2, 0.3), (0.4, 0.9)),
            ("job_c", (0.3, 0.4), (0.7, 0.3)),
        ),
        opt_metadata=(
            {"run_id": "run_a", "generation_index": 0, "created_job_names": ["job_a", "job_b"]},
            {"run_id": "run_b", "generation_index": 0, "created_job_names": ["job_c"]},
        ),
    )

    workspace = object()
    rows = view_cost.build_rows(workspace, recorded_api=fake_api)

    assert fake_api.history_calls == ["completed"]
    assert [row["job_name"] for row in rows] == ["job_a", "job_b", "job_c"]
    assert rows[0]["costs"] == pytest.approx((0.5, 0.8))
    assert rows[2]["optimization_index"] == 2
    assert rows[2]["optimization_run_id"] == "run_b"
    assert rows[2]["generation_index"] == 0
    assert rows[2]["job_static_hash"] == "hash_b"

    class FakeObjectiveApi:
        @staticmethod
        def get_objective_names(_workspace):
            return ()

    summary = view_cost.summarize_rows(
        workspace, rows, objective_api=FakeObjectiveApi
    )
    assert "rows: 3" in summary
    assert "objectives:" not in summary
    assert "objective_1" in summary
    assert "objective_2" in summary
    assert "avg. cost" in summary
    assert "Pareto front:" in summary


def test_build_rows_reports_streamed_candidate_progress_before_final_total():
    progress_calls = []
    rows = view_cost.build_rows(
        object(),
        recorded_api=FakeRecordedDataApi(
            (
                ("job_a", (0.1, 0.2), (0.5, 0.8)),
                ("job_b", (0.2, 0.3), (0.4, 0.9)),
                ("job_c", (0.3, 0.4), (0.7, 0.3)),
            )
        ),
        progress=lambda completed, total, message: progress_calls.append(
            (completed, total, message)
        ),
    )

    assert len(rows) == 3
    assert progress_calls == [
        (0, None, "reinterpreting candidates"),
        (3, None, "reinterpreting candidates"),
        (3, 3, "reinterpreting candidates"),
    ]


def test_objective_names_use_job_template_names():
    class FakeObjectiveApi:
        @staticmethod
        def get_objective_names(_workspace):
            return ("cost_alpha", "cost_beta")

    rows = [{"costs": (0.5, 0.8)}]

    assert view_cost.objective_names(object(), rows, FakeObjectiveApi) == ["cost_alpha", "cost_beta"]


def test_build_rows_prefers_individual_context_over_opt_metadata():
    fake_api = FakeRecordedDataApi(
        history=(("job_a", (0.1, 0.2), (0.5, 0.8)),),
        opt_metadata=(
            {"run_id": "run_from_opt_meta", "generation_index": 1, "created_job_names": ["job_a"]},
        ),
        records=(
            {
                "job_name": "job_a",
                "run_id": "run_from_individual",
                "optimization_index": 7,
                "generation_index": 3,
                "job_metadata": {
                    "run_id": "run_from_nested_metadata",
                    "optimization_index": 2,
                    "generation_index": 1,
                    "job_static_hash": "hash_a",
                },
            },
        ),
    )

    rows = view_cost.build_rows(object(), recorded_api=fake_api)

    assert rows[0]["optimization_index"] == 7
    assert rows[0]["optimization_run_id"] == "run_from_individual"
    assert rows[0]["generation_index"] == 3
    assert rows[0]["job_static_hash"] == "hash_a"


def test_average_cost_keeps_old_combined_cost_vertical_position():
    assert view_cost._scatter_alpha(1000) == pytest.approx(0.6)
    assert view_cost._scatter_alpha(64000) == pytest.approx(0.15)

    rows = view_cost.build_rows(
        object(),
        recorded_api=FakeRecordedDataApi(
            (("job_a", (0.1,), (0.4, 0.8)),)
        ),
    )

    combined_cost = 1.2
    old_right_axis_position = combined_cost / 2.0
    assert rows[0]["average_cost"] == pytest.approx(old_right_axis_position)


def test_hypervolume_series_has_all_and_current_generation_boundaries():
    rows = [
        {
            "row_number": 1,
            "optimization_run_id": "run_a",
            "generation_index": 0,
            "costs": (0.5, 0.5),
        },
        {
            "row_number": 2,
            "optimization_run_id": "run_a",
            "generation_index": 1,
            "costs": (0.2, 0.8),
        },
        {
            "row_number": 3,
            "optimization_run_id": "run_a",
            "generation_index": 1,
            "costs": (1.1, 0.1),
        },
    ]

    x, all_hv, generation_hv, reference = view_cost.hypervolume_series(rows)

    assert x == pytest.approx([1.0, 3.0])
    assert all_hv == pytest.approx([0.25, 0.31])
    assert generation_hv == pytest.approx([0.25, 0.16])
    assert reference == pytest.approx((1.0, 1.0))
    assert all(all_hv >= generation_hv)


def test_hypervolume_passes_only_cumulative_pareto_points_to_indicator(monkeypatch):
    from pymoo.indicators import hv as hv_module

    calls = []

    class CapturingHV:
        def __init__(self, *, ref_point):
            self.ref_point = ref_point

        def do(self, points):
            calls.append(points.copy())
            return 0.0

    monkeypatch.setattr(hv_module, "HV", CapturingHV)
    rows = [
        {"row_number": 1, "generation_index": 0, "costs": (0.4, 0.4)},
        {"row_number": 2, "generation_index": 0, "costs": (0.7, 0.7)},
        {"row_number": 3, "generation_index": 1, "costs": (0.3, 0.5)},
        {"row_number": 4, "generation_index": 1, "costs": (0.8, 0.8)},
    ]

    view_cost.hypervolume_series(rows)

    assert [len(points) for points in calls] == [1, 1, 1, 2]
    assert all(
        points.tolist() != [[0.4, 0.4], [0.7, 0.7]] for points in calls
    )


def test_generation_regions_restart_per_run_and_skip_rows_without_generation():
    rows = [
        {"row_number": 1, "optimization_run_id": "run_a", "generation_index": 0},
        {"row_number": 2, "optimization_run_id": "run_a", "generation_index": 0},
        {"row_number": 3, "optimization_run_id": "run_a", "generation_index": 1},
        {"row_number": 4, "optimization_run_id": "run_a", "generation_index": 1},
        {"row_number": 5, "optimization_run_id": "run_b", "generation_index": 0},
        {"row_number": 6, "optimization_run_id": None, "generation_index": None},
        {"row_number": 7, "optimization_run_id": "run_b", "generation_index": 1},
    ]

    assert view_cost._generation_regions(rows) == [
        (0, 0.5, 2.5),
        (1, 2.5, 4.5),
        (0, 4.5, 5.5),
        (1, 6.5, 7.5),
    ]


def test_generation_regions_stagger_labels_and_shade_only_odd_ones():
    class FakeAxis:
        def __init__(self):
            self.spans = []
            self.labels = []
            self.transform = object()

        def get_xaxis_transform(self):
            return self.transform

        def axvspan(self, left, right, **kwargs):
            self.spans.append((left, right, kwargs))

        def text(self, x, y, label, **kwargs):
            self.labels.append((x, y, label, kwargs))

    axis = FakeAxis()
    regions = [(0, 0.5, 2.5), (1, 2.5, 4.5), (2, 4.5, 6.5)]

    view_cost._draw_generation_regions(axis, regions)

    assert [label[2] for label in axis.labels] == ["0", "1", "2"]
    assert [label[1] for label in axis.labels] == pytest.approx(
        [0.98, 0.93, 0.98]
    )
    assert all(label[3]["transform"] is axis.transform for label in axis.labels)
    assert all(label[3]["fontsize"] == 8 for label in axis.labels)
    assert axis.spans == [
        (
            2.5,
            4.5,
            {
                "facecolor": "black",
                "edgecolor": "none",
                "alpha": pytest.approx(0.1),
                "zorder": 0,
            },
        )
    ]


def test_build_rows_reports_empty_recorded_data():
    fake_api = FakeRecordedDataApi(())

    with pytest.raises(view_cost.ViewCostError, match="No completed historical results"):
        view_cost.build_rows(object(), recorded_api=fake_api)


def test_build_rows_skips_unplottable_history_rows_and_reports_them():
    fake_api = FakeRecordedDataApi(
        (
            ("good_a", (0.1, 0.2), (0.5, 0.8)),
            ("bad_cost", (0.2, 0.3), (float("inf"), 0.7)),
            ("bad_variables", (float("nan"), 0.4), (0.4, 0.6)),
            ("empty_costs", (0.4, 0.5), ()),
            ("wrong_width", (0.5, 0.6), (0.3,)),
            ("overflow", (0.6, 0.7), (1e308, 1e308)),
            ("good_b", (0.7, 0.8), (0.2, 0.4)),
            ("unexpected_shape",),
        )
    )
    issues = []

    rows = view_cost.build_rows(object(), recorded_api=fake_api, issues=issues)
    summary = view_cost.summarize_rows(object(), rows, issues=issues)

    assert [row["job_name"] for row in rows] == ["good_a", "good_b"]
    assert [row["row_number"] for row in rows] == [1, 7]
    assert [row["average_cost"] for row in rows] == pytest.approx([0.65, 0.3])
    assert len(issues) == 6
    assert any("bad_cost" in issue and "non-finite" in issue for issue in issues)
    assert any("wrong_width" in issue and "expected 2 objectives" in issue for issue in issues)
    assert any("overflow" in issue and "average cost is non-finite" in issue for issue in issues)
    assert "rows: 2" in summary
    assert "ignored issues: 6" in summary


def test_build_rows_ignores_optional_annotation_errors():
    class BrokenAnnotationApi(FakeRecordedDataApi):
        def list_optimization_metadata(self, _workspace):
            raise ValueError("optimization metadata is malformed")

    issues = []
    rows = view_cost.build_rows(
        object(),
        recorded_api=BrokenAnnotationApi(
            (("job_a", (0.1, 0.2), (0.5, 0.8)),)
        ),
        issues=issues,
    )

    assert rows[0]["optimization_index"] is None
    assert rows[0]["generation_index"] is None
    assert len(issues) == 1
    assert "optimization metadata annotations were ignored" in issues[0]


def test_objective_names_fall_back_when_task_names_cannot_be_read():
    class BrokenObjectiveApi:
        @staticmethod
        def get_objective_names(_workspace):
            raise ValueError("task names are unavailable")

    rows = [{"costs": (0.5, 0.8)}]

    assert view_cost.objective_names(
        object(), rows, BrokenObjectiveApi
    ) == ["objective_1", "objective_2"]


def test_build_rows_wraps_recorded_data_errors():
    class BrokenRecordedDataApi:
        def open_historical_rawdata_snapshot(self, _workspace, *, status="completed"):
            raise OSError("rawData archive is busy")

    with pytest.raises(view_cost.ViewCostError, match="rawData archive is busy"):
        view_cost.build_rows(object(), recorded_api=BrokenRecordedDataApi())


def test_view_cost_source_does_not_reference_legacy_jsonl_inputs():
    package_root = Path(cost_viewer.__file__).parent
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in package_root.glob("*.py")
    )

    assert "para_cost.jsonl" not in source
    assert "optMeta.jsonl" not in source
    assert "indMeta.jsonl" not in source
    assert "sys.path" not in source
    assert source.count("linewidths=PARETO_EDGE_LINE_WIDTH") == 2


def test_hypervolume_is_rendered_as_a_bounded_translucent_polyline_band():
    source = Path(plotting.__file__).read_text(encoding="utf-8")

    assert "fill_between(" in source
    assert "step=\"post\"" not in source
    assert 'edgecolor="none"' in source
    assert source.count("ax2.plot(") == 1
    assert "for boundary in (generation_hv, all_hv):" in source
    assert "linewidth=HV_BOUNDARY_LINE_WIDTH" in source
    assert "alpha=HV_BOUNDARY_LINE_ALPHA" in source
    assert style.HV_SHADE_LABEL == "HV (all & current gen.)"
    assert style.HV_BOUNDARY_LINE_WIDTH == pytest.approx(1.0)
    assert style.HV_BOUNDARY_LINE_ALPHA == pytest.approx(0.5)
    assert style.GENERATION_LABEL_STAGGER == pytest.approx(0.05)


def test_view_cost_plot_style_contract():
    assert view_cost.PLOT_FIGSIZE == (5.5, 3.5)
    assert view_cost.PLOT_DPI == 600
    assert view_cost.PLOT_FONT_SIZE == 10
    assert view_cost.PLOT_TITLE_FONT_SIZE == 11
    assert view_cost.PLOT_TICK_FONT_SIZE == 8
    assert view_cost.PLOT_LEGEND_FONT_SIZE == 7
    assert view_cost.PLOT_LEGEND_FRAME_ALPHA == pytest.approx(0.6)
    assert view_cost.PLOT_LEGEND_EDGE_PAD == pytest.approx(0.015)
    assert view_cost.TREND_LINE_WIDTH == pytest.approx(2.0)
    assert view_cost.TREND_LINE_ALPHA == pytest.approx(0.25)
    assert view_cost.AVG_TREND_LINE_WIDTH == pytest.approx(4.0)
    assert view_cost.HV_SHADE_ALPHA == pytest.approx(0.2)
    assert view_cost.EVENT_LINE_ALPHA == pytest.approx(0.25)
    assert view_cost.EVENT_LINE_WIDTH == pytest.approx(1.2)
    assert view_cost.GRID_LINE_WIDTH == pytest.approx(0.4)
    assert view_cost.SCATTER_MARKER_SIZE == pytest.approx(3.0)
    assert view_cost.SCATTER_EDGE_LINE_WIDTH == pytest.approx(0.4)
    assert view_cost.PARETO_MARKER_AREA == pytest.approx(60.0)
    assert view_cost.PARETO_EDGE_LINE_WIDTH == pytest.approx(0.75)
    assert view_cost.OPT_LINE_LABEL == "Opt. start"
    assert view_cost.HASH_LINE_LABEL == "Hash change"
    assert view_cost.OPT_LINE_STYLE == (0.0, (4.0, 4.0))
    assert view_cost.HASH_LINE_STYLE == (4.0, (4.0, 4.0))


def test_view_cost_splits_data_and_event_legends():
    class FakeBBox:
        x1 = 0.3

        def transformed(self, _transform):
            return self

    class FakeArtist:
        def get_window_extent(self, _renderer):
            return FakeBBox()

    class FakeCanvas:
        def draw(self):
            return None

        def get_renderer(self):
            return object()

    class FakeTransform:
        def inverted(self):
            return self

    class FakeSourceAxis:
        def __init__(self, labels):
            self.labels = labels

        def get_legend_handles_labels(self):
            return [object() for _ in self.labels], self.labels

    class FakeLegendAxis:
        def __init__(self):
            self.calls = []
            self.added = []
            self.figure = type("FakeFigure", (), {"canvas": FakeCanvas()})()
            self.transAxes = FakeTransform()

        def legend(self, _handles, labels, **kwargs):
            artist = FakeArtist()
            self.calls.append((labels, kwargs, artist))
            return artist

        def add_artist(self, artist):
            self.added.append(artist)

    axis = FakeLegendAxis()
    sources = (
        FakeSourceAxis(["cost_a", "Opt. start"]),
        FakeSourceAxis(["avg. cost", "Hash change"]),
    )

    view_cost._add_split_legends(axis, sources)

    assert [call[0] for call in axis.calls] == [
        ["cost_a", "avg. cost"],
        ["Opt. start", "Hash change"],
    ]
    assert axis.calls[0][1]["framealpha"] == pytest.approx(0.6)
    assert axis.calls[1][1]["framealpha"] == pytest.approx(0.6)
    assert axis.calls[0][1]["bbox_to_anchor"] == pytest.approx((0.015, 0.015))
    assert axis.calls[1][1]["bbox_to_anchor"] == pytest.approx((0.31, 0.015))
    assert axis.added == [axis.calls[0][2]]


def test_plot_rows_writes_png_when_matplotlib_is_available(tmp_path, monkeypatch):
    if importlib.util.find_spec("matplotlib") is None or importlib.util.find_spec("cycler") is None:
        pytest.skip("matplotlib/cycler is not installed")

    rows = view_cost.build_rows(
        object(),
        recorded_api=FakeRecordedDataApi(
            (
                ("job_a", (0.1, 0.2), (0.5, 0.8)),
                ("job_b", (0.2, 0.3), (0.4, 0.9)),
                ("job_c", (0.3, 0.4), (0.7, 0.3)),
            )
        )
    )

    monkeypatch.setattr(
        plotting,
        "objective_names",
        lambda _workspace, _rows, _objective_api: ["objective_1", "objective_2"],
    )
    output = view_cost.plot_rows(object(), rows, tmp_path / "cost.png")

    assert output.is_file()
    assert output.stat().st_size > 0
    from matplotlib import image as matplotlib_image

    assert matplotlib_image.imread(output).shape[:2] == (2100, 3300)


def test_view_cost_has_a_package_entrypoint():
    assert Path(view_cost.__file__).name == "view_cost.py"
    assert Path(cost_viewer.__file__).name == "__init__.py"
    assert view_cost.view_cost is cost_viewer.view_cost
