from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from project.tools import viewCost


class FakeRecordedDataApi:
    def __init__(self, history):
        self.history = history
        self.history_calls = []

    def get_historical_results(self, *, status="completed"):
        self.history_calls.append(status)
        return self.history

    def list_records(self):
        return (
            {
                "job_name": "job_a",
                "job_metadata": {"optimization_index": 1, "job_static_hash": "hash_a"},
            },
            {
                "job_name": "job_b",
                "job_metadata": {"optimization_index": 1, "job_static_hash": "hash_a"},
            },
            {
                "job_name": "job_c",
                "job_metadata": {"optimization_index": 2, "job_static_hash": "hash_b"},
            },
        )


def test_build_rows_uses_recorded_data_history():
    fake_api = FakeRecordedDataApi(
        (
            ("job_a", (0.1, 0.2), (0.5, 0.8)),
            ("job_b", (0.2, 0.3), (0.4, 0.9)),
            ("job_c", (0.3, 0.4), (0.7, 0.3)),
        )
    )

    rows = viewCost.build_rows(fake_api)

    assert fake_api.history_calls == ["completed"]
    assert [row["job_name"] for row in rows] == ["job_a", "job_b", "job_c"]
    assert rows[0]["costs"] == pytest.approx((0.5, 0.8))
    assert rows[2]["optimization_index"] == 2
    assert rows[2]["job_static_hash"] == "hash_b"

    summary = viewCost.summarize_rows(rows)
    assert "rows: 3" in summary
    assert "objectives: objective_1, objective_2" in summary
    assert "Pareto front:" in summary


def test_build_rows_reports_empty_recorded_data():
    fake_api = FakeRecordedDataApi(())

    with pytest.raises(viewCost.ViewCostError, match="No completed historical results"):
        viewCost.build_rows(fake_api)


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
