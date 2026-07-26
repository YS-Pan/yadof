from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import yadof.tools.view_cost as view_cost


class FakeRecordedDataApi:
    def __init__(self, history, opt_metadata=(), records=None):
        self.history = history
        self.opt_metadata = opt_metadata
        self.records = records
        self.history_calls = []

    def get_historical_results(self, _workspace, *, status="completed"):
        self.history_calls.append(status)
        return self.history

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
    assert "objectives: objective_1, objective_2" in summary
    assert "Pareto front:" in summary


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


def test_plot_scaling_helpers_keep_dense_points_readable_and_axes_aligned():
    assert view_cost._scatter_alpha(1000) == pytest.approx(0.6)
    assert view_cost._scatter_alpha(64000) == pytest.approx(0.15)

    left_ylim = (0.0, 1.05)
    right_ylim = view_cost._combined_axis_ylim(left_ylim, objective_count=2)
    left_position = (1.0 - left_ylim[0]) / (left_ylim[1] - left_ylim[0])
    right_position = (2.0 - right_ylim[0]) / (right_ylim[1] - right_ylim[0])
    left_ticks, right_ticks = view_cost._aligned_combined_ticks(
        (-0.2, 0.0, 0.5, 1.0, 1.2),
        left_ylim,
        objective_count=2,
    )

    assert right_position == pytest.approx(left_position)
    assert left_ticks == pytest.approx([0.0, 0.5, 1.0])
    assert right_ticks == pytest.approx([0.0, 1.0, 2.0])


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


def test_generation_regions_label_every_generation_and_shade_only_odd_ones():
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
    assert all(label[1] == pytest.approx(0.98) for label in axis.labels)
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


def test_build_rows_wraps_recorded_data_errors():
    class BrokenRecordedDataApi:
        def get_historical_results(self, _workspace, *, status="completed"):
            raise OSError("rawData archive is busy")

    with pytest.raises(view_cost.ViewCostError, match="rawData archive is busy"):
        view_cost.build_rows(object(), recorded_api=BrokenRecordedDataApi())


def test_view_cost_source_does_not_reference_legacy_jsonl_inputs():
    source = Path(view_cost.__file__).read_text(encoding="utf-8")

    assert "para_cost.jsonl" not in source
    assert "optMeta.jsonl" not in source
    assert "indMeta.jsonl" not in source
    assert "sys.path" not in source
    assert source.count("linewidths=PARETO_EDGE_LINE_WIDTH") == 2


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
    assert view_cost.COMBINED_TREND_LINE_WIDTH == pytest.approx(4.0)
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
        FakeSourceAxis(["Combined cost", "Hash change"]),
    )

    view_cost._add_split_legends(axis, sources)

    assert [call[0] for call in axis.calls] == [
        ["cost_a", "Combined cost"],
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
        view_cost,
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
