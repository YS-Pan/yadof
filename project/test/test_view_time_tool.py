from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from project.tools import viewTime


class FakeRecordedDataApi:
    def __init__(self, records, opt_metadata=()):
        self.records = records
        self.opt_metadata = opt_metadata
        self.list_calls = 0

    def list_records(self):
        self.list_calls += 1
        return self.records

    def list_optimization_metadata(self):
        return self.opt_metadata


def test_build_rows_uses_recorded_data_individual_metadata_records():
    fake_api = FakeRecordedDataApi(
        records=(
            {
                "job_name": "job_a",
                "status": "completed",
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

    rows = viewTime.build_rows(fake_api)

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

    summary = viewTime.summarize_rows(rows)
    assert "rows: 3" in summary
    assert "failure rate: 66.67 %" in summary
    assert "status counts:" in summary


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

    rows = viewTime.build_rows(fake_api, status="completed")

    assert [row["job_name"] for row in rows] == ["job_a"]


def test_build_rows_reports_empty_recorded_data():
    fake_api = FakeRecordedDataApi(())

    with pytest.raises(viewTime.ViewTimeError, match="No recorded timing rows"):
        viewTime.build_rows(fake_api)


def test_view_time_source_does_not_reference_legacy_jsonl_inputs():
    source = Path(viewTime.__file__).read_text(encoding="utf-8")

    assert "indMeta.jsonl" not in source
    assert "para_cost.jsonl" not in source
    assert "optMeta.jsonl" not in source


def test_plot_rows_writes_png_when_matplotlib_is_available(tmp_path):
    if importlib.util.find_spec("matplotlib") is None:
        pytest.skip("matplotlib is not installed")

    rows = viewTime.build_rows(
        FakeRecordedDataApi(
            (
                {
                    "job_name": "job_a",
                    "status": "completed",
                    "recorded_at": "2026-05-14T00:01:00+00:00",
                    "job_metadata": {
                        "started_at": "2026-05-14T08:00:00+08:00",
                        "ended_at": "2026-05-14T08:01:00+08:00",
                    },
                },
                {
                    "job_name": "job_b",
                    "status": "error",
                    "recorded_at": "2026-05-14T00:02:00+00:00",
                    "job_metadata": {
                        "started_at": "2026-05-14T08:02:00+08:00",
                        "ended_at": "2026-05-14T08:02:30+08:00",
                    },
                },
            )
        )
    )

    output = viewTime.plot_rows(rows, tmp_path / "time.png")

    assert output.is_file()
    assert output.stat().st_size > 0
