from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from project.tools import viewCost


class FakeRecordedDataApi:
    def __init__(self, history, opt_metadata=(), records=None):
        self.history = history
        self.opt_metadata = opt_metadata
        self.records = records
        self.history_calls = []

    def get_historical_results(self, *, status="completed"):
        self.history_calls.append(status)
        return self.history

    def list_records(self):
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

    def list_optimization_metadata(self):
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

    rows = viewCost.build_rows(fake_api)

    assert fake_api.history_calls == ["completed"]
    assert [row["job_name"] for row in rows] == ["job_a", "job_b", "job_c"]
    assert rows[0]["costs"] == pytest.approx((0.5, 0.8))
    assert rows[2]["optimization_index"] == 2
    assert rows[2]["optimization_run_id"] == "run_b"
    assert rows[2]["generation_index"] == 0
    assert rows[2]["job_static_hash"] == "hash_b"

    summary = viewCost.summarize_rows(rows)
    assert "rows: 3" in summary
    assert "objectives: objective_1, objective_2" in summary
    assert "Pareto front:" in summary


def test_objective_names_use_job_template_names():
    class FakeObjectiveApi:
        @staticmethod
        def get_objective_names():
            return ("cost_alpha", "cost_beta")

    rows = [{"costs": (0.5, 0.8)}]

    assert viewCost.objective_names(rows, FakeObjectiveApi) == ["cost_alpha", "cost_beta"]


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

    rows = viewCost.build_rows(fake_api)

    assert rows[0]["optimization_index"] == 7
    assert rows[0]["optimization_run_id"] == "run_from_individual"
    assert rows[0]["generation_index"] == 3
    assert rows[0]["job_static_hash"] == "hash_a"


def test_build_rows_reports_empty_recorded_data():
    fake_api = FakeRecordedDataApi(())

    with pytest.raises(viewCost.ViewCostError, match="No completed historical results"):
        viewCost.build_rows(fake_api)


def test_build_rows_wraps_recorded_data_errors():
    class BrokenRecordedDataApi:
        def get_historical_results(self, *, status="completed"):
            raise OSError("rawData archive is busy")

    with pytest.raises(viewCost.ViewCostError, match="rawData archive is busy"):
        viewCost.build_rows(BrokenRecordedDataApi())


def test_view_cost_source_does_not_reference_legacy_jsonl_inputs():
    source = Path(viewCost.__file__).read_text(encoding="utf-8")

    assert "para_cost.jsonl" not in source
    assert "optMeta.jsonl" not in source
    assert "indMeta.jsonl" not in source


def test_plot_rows_writes_png_when_matplotlib_is_available(tmp_path):
    if importlib.util.find_spec("matplotlib") is None or importlib.util.find_spec("cycler") is None:
        pytest.skip("matplotlib/cycler is not installed")

    rows = viewCost.build_rows(
        FakeRecordedDataApi(
            (
                ("job_a", (0.1, 0.2), (0.5, 0.8)),
                ("job_b", (0.2, 0.3), (0.4, 0.9)),
                ("job_c", (0.3, 0.4), (0.7, 0.3)),
            )
        )
    )

    output = viewCost.plot_rows(rows, tmp_path / "cost.png")

    assert output.is_file()
    assert output.stat().st_size > 0
