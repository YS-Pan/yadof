from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import yadof.tools.view_error as view_error


class FakeRecordedDataApi:
    def __init__(self, records):
        self.records = tuple(records)
        self.list_calls = 0

    def list_records(self, _workspace):
        self.list_calls += 1
        return self.records


def _records():
    return (
        {
            "job_name": "completed_job",
            "status": "completed",
            "ended_at": "2026-07-24T08:00:00",
        },
        {
            "job_name": "workflow_job",
            "status": "error",
            "recorded_at": "2026-07-24T08:02:30",
            "job_metadata": {
                "failed_at": "2026-07-24T08:02:00",
                "error_type": "RuntimeError",
                "error_message": "solver failed",
            },
        },
        {
            "job_name": "timeout_job",
            "status": "timeout",
            "failed_at": "2026-07-24T08:03:00",
            "job_metadata": {
                "timed_out": True,
                "error": "workflow exceeded its limit",
            },
        },
        {
            "job_name": "collect_job",
            "status": "error",
            "recorded_at": "2026-07-24T08:04:00",
            "job_metadata": {
                "failure_stage": "collect",
                "error": "missing rawData.zip",
            },
        },
    )


def test_build_rows_classifies_error_types_and_uses_occurrence_times():
    fake_api = FakeRecordedDataApi(_records())

    rows = view_error.build_rows(object(), recorded_api=fake_api)

    assert fake_api.list_calls == 1
    assert [row["job_name"] for row in rows] == [
        "completed_job",
        "workflow_job",
        "timeout_job",
        "collect_job",
    ]
    assert [row["error_type"] for row in rows] == [
        None,
        "RuntimeError",
        "timeout",
        "collect error",
    ]
    assert str(rows[1]["event_time"]) == "2026-07-24 08:02:00"
    assert rows[1]["error_message"] == "solver failed"
    assert [row["failed"] for row in rows] == [False, True, True, True]


def test_summary_owns_failure_rate_and_lists_every_error_occurrence():
    rows = view_error.build_rows(
        object(), recorded_api=FakeRecordedDataApi(_records())
    )

    summary = view_error.summarize_rows(rows)

    assert "rows: 4" in summary
    assert "errors: 3" in summary
    assert "failure rate: 75.00 %" in summary
    assert "RuntimeError" in summary
    assert "collect error" in summary
    assert "2026-07-24 08:02:00" in summary
    assert "2026-07-24 08:03:00" in summary
    assert "2026-07-24 08:04:00" in summary


def test_error_type_colors_are_distinct_and_stable():
    first = view_error._error_type_colors(
        ("RuntimeError", "timeout", "collect error")
    )
    second = view_error._error_type_colors(
        ("RuntimeError", "timeout", "collect error")
    )

    assert first == second
    assert len(set(first.values())) == 3


def test_build_rows_reports_empty_recorded_data():
    with pytest.raises(
        view_error.ViewErrorError, match="No recorded evaluation rows"
    ):
        view_error.build_rows(
            object(), recorded_api=FakeRecordedDataApi(())
        )


def test_plot_rows_writes_png_with_error_types_and_failure_rate(tmp_path):
    if importlib.util.find_spec("matplotlib") is None:
        pytest.skip("matplotlib is not installed")

    rows = view_error.build_rows(
        object(), recorded_api=FakeRecordedDataApi(_records())
    )
    output = view_error.plot_rows(object(), rows, tmp_path / "error.png")

    assert output.is_file()
    assert output.stat().st_size > 0
    from matplotlib import image as matplotlib_image

    assert matplotlib_image.imread(output).shape[:2] == (2100, 3300)


def test_plot_rows_supports_history_without_errors(tmp_path):
    if importlib.util.find_spec("matplotlib") is None:
        pytest.skip("matplotlib is not installed")

    rows = view_error.build_rows(
        object(),
        recorded_api=FakeRecordedDataApi(
            (
                {
                    "job_name": "completed_job",
                    "status": "completed",
                    "recorded_at": "2026-07-24T08:00:00",
                },
            )
        ),
    )

    output = view_error.plot_rows(
        object(), rows, tmp_path / "no_errors.png"
    )

    assert output.is_file()
    assert "failure rate: 0.00 %" in view_error.summarize_rows(rows)


def test_view_error_has_a_package_entrypoint():
    assert Path(view_error.__file__).name == "view_error.py"
