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
                    "execute_machine": "worker-a",
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
                    "execute_machine": "worker-b",
                    "error_type": "RuntimeError",
                    "error_message": "solver failed",
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
                    "execute_machine": "worker-a",
                    "timed_out": True,
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
    assert [row["computer"] for row in rows] == [
        "worker-a",
        "worker-b",
        "worker-a",
    ]
    assert [row["error_type"] for row in rows] == [
        None,
        "RuntimeError",
        "timeout",
    ]
    assert rows[0]["elapsed_min"] == pytest.approx(1.0)
    assert rows[1]["elapsed_min"] == pytest.approx(1.5)
    assert rows[2]["elapsed_min"] == pytest.approx(0.0)
    assert rows[2]["optimization_index"] == 2
    assert rows[2]["optimization_run_id"] == "run_b"
    assert rows[2]["generation_index"] == 0
    assert rows[2]["job_static_hash"] == "hash_b"

    summary = view_time.summarize_rows(rows)
    assert "rows: 3" in summary
    assert "errors: 2" in summary
    assert "failure rate: 66.67 %" in summary
    assert "RuntimeError" in summary
    assert "solver failed" in summary
    assert "worker-b" in summary
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


def test_build_rows_uses_execution_timing_for_failed_records_before_batch_record_time():
    fake_api = FakeRecordedDataApi(
        records=(
            {
                "job_name": "timed_out",
                "status": "timeout",
                "recorded_at": "2026-05-14T09:00:00+08:00",
                "job_metadata": {
                    "condor_execution_started_at": "2026-05-14T08:00:00+08:00",
                    "condor_execution_elapsed_sec": 600.0,
                    "runner_finished_at": "2026-05-14T08:10:01+08:00",
                    "timed_out": True,
                },
            },
            {
                "job_name": "next_generation_completed",
                "status": "completed",
                "started_at": "2026-05-14T08:20:00+08:00",
                "ended_at": "2026-05-14T08:21:00+08:00",
                "recorded_at": "2026-05-14T09:30:00+08:00",
            },
        )
    )

    rows = view_time.build_rows(object(), recorded_api=fake_api)

    assert [row["job_name"] for row in rows] == [
        "timed_out",
        "next_generation_completed",
    ]
    assert rows[0]["start"] == datetime(2026, 5, 14, 8, 0)
    assert rows[0]["end"] == datetime(2026, 5, 14, 8, 10, 1)
    assert rows[0]["event_time"] == datetime(2026, 5, 14, 8, 10, 1)
    assert rows[0]["elapsed_min"] == pytest.approx(10.0)


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


def test_computer_colors_and_error_bands_are_distinct():
    computer_colors = view_time._categorical_colors(
        ("worker-a", "worker-b", "worker-c")
    )
    error_colors = view_time._categorical_colors(
        ("RuntimeError", "timeout", "collect error"),
        hue_offset=0.08,
        saturation=0.92,
        value=0.88,
    )

    assert len(set(computer_colors.values())) == 3
    assert len(set(error_colors.values())) == 3
    assert view_time._error_band_positions(
        ("RuntimeError", "timeout", "collect error")
    ) == {
        "RuntimeError": pytest.approx(0.80),
        "timeout": pytest.approx(0.85),
        "collect error": pytest.approx(0.90),
    }
    assert view_time._error_band_positions(("timeout",)) == {
        "timeout": pytest.approx(0.85)
    }
    assert view_time.ELAPSED_DATA_TOP < view_time.ERROR_BAND_BOTTOM


def test_computer_name_prefers_worker_identity_then_condor_log_fallback():
    assert (
        view_time._computer_name(
            {},
            {
                "execute_machine": "worker-reported",
                "condor_execute_machine": "scheduler-observed",
            },
        )
        == "worker-reported"
    )
    assert (
        view_time._computer_name(
            {},
            {"condor_execute_machine": "scheduler-observed"},
        )
        == "scheduler-observed"
    )
    assert (
        view_time._computer_name(
            {"status": "timeout"},
            {
                "condor_log_tail": (
                    "001 (81.000.000) 2026-07-24 03:00:00 "
                    "Job executing on host: "
                    "<192.0.2.81:9618?alias=historical-worker&sock=startd>\n"
                    "\tSlotName: slot1_1@historical-worker\n"
                    "...\n"
                    "009 (81.000.000) 2026-07-24 04:00:00 "
                    "Job was aborted.\n"
                )
            },
        )
        == "historical-worker"
    )
    assert (
        view_time._computer_name(
            {"status": "timeout"},
            {
                "condor_log_tail": (
                    "000 (82.000.000) 2026-07-24 03:00:00 "
                    "Job submitted from host: <submit-host>\n"
                    "009 (82.000.000) 2026-07-24 04:00:00 "
                    "Job was aborted.\n"
                )
            },
        )
        == "unknown"
    )
    assert view_time._computer_name({}, {}) == "unknown"


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
    assert "FAIL_RATE_COLOR" in source
    assert "Failure rate (%)" in source
    assert "execute_machine" in source
    assert "edgecolors=ring_color" in source
    assert "label=error_type" not in source
    assert "computer:" not in source
    assert view_time.FAIL_RATE_LINE_ALPHA == pytest.approx(0.1)
    assert view_time.ERROR_LABEL_X == pytest.approx(0.015)


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
        FakeSourceAxis(["worker-a (avg. 1.00 min)", "avg. time", "Opt. start"]),
        FakeSourceAxis(["avg. failure rate", "Hash change"]),
    )

    view_time._add_split_legends(axis, sources)

    assert [call[0] for call in axis.calls] == [
        ["worker-a (avg. 1.00 min)", "avg. time", "avg. failure rate"],
        ["Opt. start", "Hash change"],
    ]
    assert axis.calls[0][1]["framealpha"] == pytest.approx(0.6)
    assert axis.calls[1][1]["framealpha"] == pytest.approx(0.6)
    assert axis.calls[0][1]["bbox_to_anchor"] == pytest.approx((0.015, 0.015))
    assert axis.calls[1][1]["bbox_to_anchor"] == pytest.approx((0.31, 0.015))
    assert axis.added == [axis.calls[0][2]]


def test_plot_rows_writes_png_when_matplotlib_is_available(
    tmp_path, monkeypatch
):
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
                        "execute_machine": "worker-a",
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
                        "execute_machine": "worker-b",
                        "error_type": "RuntimeError",
                        "error_message": "solver failed",
                    },
                },
                {
                    "job_name": "job_c",
                    "status": "timeout",
                    "started_at": "2026-05-14T08:03:00+08:00",
                    "failed_at": "2026-05-14T08:04:00+08:00",
                    "recorded_at": "2026-05-14T00:04:00+00:00",
                    "job_metadata": {
                        "started_at": "2026-05-14T08:03:00+08:00",
                        "failed_at": "2026-05-14T08:04:00+08:00",
                        "execute_machine": "worker-c",
                        "timed_out": True,
                    },
                },
                {
                    "job_name": "job_d",
                    "status": "error",
                    "started_at": "2026-05-14T08:05:00+08:00",
                    "ended_at": "2026-05-14T08:05:20+08:00",
                    "recorded_at": "2026-05-14T00:05:20+00:00",
                    "job_metadata": {
                        "started_at": "2026-05-14T08:05:00+08:00",
                        "ended_at": "2026-05-14T08:05:20+08:00",
                        "execute_machine": "worker-a",
                        "failure_stage": "collect",
                        "error": "missing rawData.zip",
                    },
                },
            )
        )
    )

    captured = {}

    def capture_plot_contract(axis, axes):
        labels = []
        for source_axis in axes:
            labels.extend(source_axis.get_legend_handles_labels()[1])
        captured["labels"] = labels
        captured["error_texts"] = {
            text.get_text(): text for text in axis.texts
        }
        captured["failure_lines"] = tuple(
            line
            for line in axes[1].lines
            if line.get_label().startswith("avg. failure rate")
        )

    monkeypatch.setattr(view_time, "_add_split_legends", capture_plot_contract)
    output = view_time.plot_rows(object(), rows, tmp_path / "time.png")

    assert output.is_file()
    assert output.stat().st_size > 0
    from matplotlib import image as matplotlib_image

    assert matplotlib_image.imread(output).shape[:2] == (2100, 3300)
    assert "worker-a (avg. 1.00 min)" in captured["labels"]
    assert "worker-b (avg. n/a)" in captured["labels"]
    assert "worker-c (avg. n/a)" in captured["labels"]
    for error_type in ("RuntimeError", "timeout", "collect error"):
        error_text = captured["error_texts"][error_type]
        assert error_text.get_position()[0] == pytest.approx(0.015)
        assert error_text.get_horizontalalignment() == "left"
        assert error_text.get_verticalalignment() == "center"
    assert len(captured["failure_lines"]) == 1
    assert captured["failure_lines"][0].get_alpha() == pytest.approx(0.1)


def test_view_time_has_a_package_entrypoint():
    assert Path(view_time.__file__).name == "view_time.py"
