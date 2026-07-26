from __future__ import annotations

from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import pytest

import yadof.tools.view_cost as view_cost
import yadof.tools.view_time as view_time


class FakeRecordedDataApi:
    def __init__(self, records, opt_metadata=()):
        self.records = records
        self.opt_metadata = opt_metadata
        self.list_calls = 0

    def list_records(self, _workspace):
        self.list_calls += 1
        return self.records

    def list_optimization_metadata(self, _workspace):
        return self.opt_metadata


def test_build_rows_uses_recorded_data_individual_metadata_records():
    fake_api = FakeRecordedDataApi(
        records=(
            {
                "job_name": "job_a",
                "status": "completed",
                "started_at": "2026-05-14T08:00:00+08:00",
                "ended_at": "2026-05-14T08:01:00+08:00",
                "recorded_at": "2026-05-14T00:01:30+00:00",
                "job_metadata": {
                    "started_at": "2026-05-14T08:00:00+08:00",
                    "ended_at": "2026-05-14T08:01:00+08:00",
                    "job_static_hash": "hash_a",
                },
            },
            {
                "job_name": "job_b",
                "status": "error",
                "started_at": "2026-05-14T08:02:00+08:00",
                "ended_at": "2026-05-14T08:03:30+08:00",
                "recorded_at": "2026-05-14T00:03:00+00:00",
                "job_metadata": {
                    "started_at": "2026-05-14T08:02:00+08:00",
                    "ended_at": "2026-05-14T08:03:30+08:00",
                    "job_static_hash": "hash_a",
                },
            },
            {
                "job_name": "job_c",
                "status": "timeout",
                "failed_at": "2026-05-14T08:04:00+08:00",
                "recorded_at": "2026-05-14T00:04:00+00:00",
                "job_metadata": {
                    "failed_at": "2026-05-14T08:04:00+08:00",
                    "job_static_hash": "hash_b",
                },
            },
        ),
        opt_metadata=(
            {"run_id": "run_a", "generation_index": 0, "created_job_names": ["job_a", "job_b"]},
            {"run_id": "run_b", "generation_index": 0, "created_job_names": ["job_c"]},
        ),
    )

    rows = view_time.build_rows(object(), recorded_api=fake_api)

    assert fake_api.list_calls == 1
    assert [row["job_name"] for row in rows] == ["job_a", "job_b", "job_c"]
    assert [row["status"] for row in rows] == ["completed", "error", "timeout"]
    assert [row["success"] for row in rows] == [True, False, False]
    assert rows[0]["elapsed_min"] == pytest.approx(1.0)
    assert rows[1]["elapsed_min"] == pytest.approx(1.5)
    assert rows[2]["elapsed_min"] == pytest.approx(0.0)
    assert rows[2]["optimization_index"] == 2
    assert rows[2]["optimization_run_id"] == "run_b"
    assert rows[2]["generation_index"] == 0
    assert rows[2]["job_static_hash"] == "hash_b"

    summary = view_time.summarize_rows(rows)
    assert "rows: 3" in summary
    assert "failure rate" not in summary
    assert "status counts:" in summary


def test_build_rows_prefers_top_level_workflow_timing_and_context():
    fake_api = FakeRecordedDataApi(
        records=(
            {
                "job_name": "job_a",
                "status": "completed",
                "started_at": "2026-05-14T00:00:00+00:00",
                "ended_at": "2026-05-14T00:02:00+00:00",
                "run_id": "run_from_individual",
                "optimization_index": 7,
                "generation_index": 3,
                "job_metadata": {
                    "started_at": "2026-05-14T00:00:00+00:00",
                    "ended_at": "2026-05-14T00:20:00+00:00",
                    "run_id": "run_from_nested_metadata",
                    "optimization_index": 2,
                    "generation_index": 1,
                    "job_static_hash": "hash_a",
                },
            },
        ),
        opt_metadata=(
            {"run_id": "run_from_opt_meta", "generation_index": 1, "created_job_names": ["job_a"]},
        ),
    )

    rows = view_time.build_rows(object(), recorded_api=fake_api)

    assert rows[0]["elapsed_min"] == pytest.approx(2.0)
    assert rows[0]["optimization_index"] == 7
    assert rows[0]["optimization_run_id"] == "run_from_individual"
    assert rows[0]["generation_index"] == 3
    assert rows[0]["job_static_hash"] == "hash_a"


def test_build_rows_can_filter_completed_records():
    fake_api = FakeRecordedDataApi(
        (
            {
                "job_name": "job_a",
                "status": "completed",
                "recorded_at": "2026-05-14T00:01:00+00:00",
            },
            {
                "job_name": "job_b",
                "status": "error",
                "recorded_at": "2026-05-14T00:02:00+00:00",
            },
        )
    )

    rows = view_time.build_rows(object(), recorded_api=fake_api, status="completed")

    assert [row["job_name"] for row in rows] == ["job_a"]


def test_generation_regions_use_time_midpoints_and_restart_per_run():
    start = datetime(2026, 5, 14, 8, 0, 0)
    rows = [
        {
            "start": start + timedelta(minutes=index),
            "optimization_run_id": "run_a" if index < 4 else "run_b",
            "generation_index": index // 2 if index < 4 else 0,
        }
        for index in range(5)
    ]

    assert view_time._generation_regions(rows) == [
        (
            0,
            start - timedelta(seconds=30),
            start + timedelta(minutes=1, seconds=30),
        ),
        (
            1,
            start + timedelta(minutes=1, seconds=30),
            start + timedelta(minutes=3, seconds=30),
        ),
        (
            0,
            start + timedelta(minutes=3, seconds=30),
            start + timedelta(minutes=4, seconds=30),
        ),
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

    start = datetime(2026, 5, 14, 8, 0, 0)
    regions = [
        (0, start, start + timedelta(minutes=1)),
        (1, start + timedelta(minutes=1), start + timedelta(minutes=2)),
    ]
    axis = FakeAxis()

    view_time._draw_generation_regions(axis, regions)

    assert [label[2] for label in axis.labels] == ["0", "1"]
    assert all(label[1] == pytest.approx(0.98) for label in axis.labels)
    assert all(label[3]["transform"] is axis.transform for label in axis.labels)
    assert all(label[3]["fontsize"] == 8 for label in axis.labels)
    assert axis.spans == [
        (
            start + timedelta(minutes=1),
            start + timedelta(minutes=2),
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

    with pytest.raises(view_time.ViewTimeError, match="No recorded timing rows"):
        view_time.build_rows(object(), recorded_api=fake_api)


def test_view_time_source_does_not_reference_legacy_jsonl_inputs():
    source = Path(view_time.__file__).read_text(encoding="utf-8")

    assert "indMeta.jsonl" not in source
    assert "para_cost.jsonl" not in source
    assert "optMeta.jsonl" not in source
    assert "sys.path" not in source
    assert "alpha=TREND_LINE_ALPHA" in source
    assert "FAIL_RATE_COLOR" not in source
    assert "Failure rate (%)" not in source


def test_view_time_plot_style_stays_aligned_to_view_cost():
    aligned_names = (
        "PLOT_FIGSIZE",
        "PLOT_DPI",
        "PLOT_FONT_SIZE",
        "PLOT_TITLE_FONT_SIZE",
        "PLOT_TICK_FONT_SIZE",
        "PLOT_LEGEND_FONT_SIZE",
        "PLOT_LEGEND_FRAME_ALPHA",
        "PLOT_LEGEND_EDGE_PAD",
        "PLOT_LEGEND_GAP",
        "PLOT_GENERATION_FONT_SIZE",
        "PLOT_TIGHT_LAYOUT_PAD",
        "AXIS_LINE_WIDTH",
        "TREND_LINE_WIDTH",
        "TREND_LINE_ALPHA",
        "EVENT_LINE_ALPHA",
        "EVENT_LINE_WIDTH",
        "EVENT_DASH_LENGTH",
        "OPT_LINE_STYLE",
        "HASH_LINE_STYLE",
        "GRID_LINE_WIDTH",
        "SCATTER_MARKER_SIZE",
        "SCATTER_EDGE_LINE_WIDTH",
        "GENERATION_SHADE_COLOR",
        "GENERATION_SHADE_ALPHA",
        "GENERATION_LABEL_Y",
        "OPT_LINE_LABEL",
        "HASH_LINE_LABEL",
    )

    assert {
        name: getattr(view_time, name)
        for name in aligned_names
    } == {
        name: getattr(view_cost, name)
        for name in aligned_names
    }


def test_view_time_splits_data_and_event_legends():
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
        FakeSourceAxis(["completed", "Opt. start"]),
        FakeSourceAxis(["Hash change"]),
    )

    view_time._add_split_legends(axis, sources)

    assert [call[0] for call in axis.calls] == [
        ["completed"],
        ["Opt. start", "Hash change"],
    ]
    assert axis.calls[0][1]["framealpha"] == pytest.approx(0.6)
    assert axis.calls[1][1]["framealpha"] == pytest.approx(0.6)
    assert axis.calls[0][1]["bbox_to_anchor"] == pytest.approx((0.015, 0.015))
    assert axis.calls[1][1]["bbox_to_anchor"] == pytest.approx((0.31, 0.015))
    assert axis.added == [axis.calls[0][2]]


def test_plot_rows_writes_png_when_matplotlib_is_available(tmp_path):
    if importlib.util.find_spec("matplotlib") is None:
        pytest.skip("matplotlib is not installed")

    rows = view_time.build_rows(
        object(),
        recorded_api=FakeRecordedDataApi(
            (
                {
                    "job_name": "job_a",
                    "status": "completed",
                    "started_at": "2026-05-14T08:00:00+08:00",
                    "ended_at": "2026-05-14T08:01:00+08:00",
                    "recorded_at": "2026-05-14T00:01:00+00:00",
                    "job_metadata": {
                        "started_at": "2026-05-14T08:00:00+08:00",
                        "ended_at": "2026-05-14T08:01:00+08:00",
                    },
                },
                {
                    "job_name": "job_b",
                    "status": "error",
                    "started_at": "2026-05-14T08:02:00+08:00",
                    "ended_at": "2026-05-14T08:02:30+08:00",
                    "recorded_at": "2026-05-14T00:02:00+00:00",
                    "job_metadata": {
                        "started_at": "2026-05-14T08:02:00+08:00",
                        "ended_at": "2026-05-14T08:02:30+08:00",
                    },
                },
            )
        )
    )

    output = view_time.plot_rows(object(), rows, tmp_path / "time.png")

    assert output.is_file()
    assert output.stat().st_size > 0
    from matplotlib import image as matplotlib_image

    assert matplotlib_image.imread(output).shape[:2] == (2100, 3300)


def test_view_time_has_a_package_entrypoint():
    assert Path(view_time.__file__).name == "view_time.py"
