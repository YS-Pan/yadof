from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from types import SimpleNamespace

import pytest

import yadof.tools.view_cost as view_cost
from yadof.tools.cost_viewer import plotting
from yadof.tools.cost_viewer.types import ProgressMessage


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
    assert all(isinstance(call[2], ProgressMessage) for call in progress_calls)
    assert [
        (call[2].bar_completed, call[2].bar_total) for call in progress_calls
    ] == [(0, 1), (1, 1), (1, 1)]


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
