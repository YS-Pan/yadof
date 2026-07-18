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
    combined = (0.5, 1.0, 2.0)
    right_ylim = view_cost._combined_axis_ylim(combined, left_ylim)
    left_position = (1.0 - left_ylim[0]) / (left_ylim[1] - left_ylim[0])
    right_position = (max(combined) - right_ylim[0]) / (right_ylim[1] - right_ylim[0])

    assert right_position == pytest.approx(left_position)


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


def test_view_cost_uses_larger_plot_fonts():
    assert view_cost.PLOT_FONT_SIZE == 14
    assert view_cost.PLOT_LEGEND_FONT_SIZE == 12


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


def test_view_cost_has_a_package_entrypoint():
    assert Path(view_cost.__file__).name == "view_cost.py"
