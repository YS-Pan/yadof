from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import yadof_benchmark as benchmark
from yadof_benchmark import api
from yadof_benchmark import cli
from yadof_benchmark.benchmark_runtime import execution
from yadof_benchmark.benchmark_runtime.baselines import (
    discover_baselines,
    load_baseline,
)
from yadof_benchmark.benchmark_runtime.contracts import (
    BASELINE_FORMAT,
    WORKSPACE_FORMAT,
    CommandResult,
)
from yadof_benchmark.benchmark_runtime.launch import launch_detached
from yadof_benchmark.benchmark_runtime.progress import estimate_run_timing
from yadof_benchmark.benchmark_runtime import results as result_runtime
from yadof_benchmark.benchmark_runtime.results import collect_cell, inspect_run
from yadof_benchmark.benchmark_runtime.storage import (
    create_run,
    load_run,
    prepare_attempt,
    read_json,
    save_state,
)
from yadof_benchmark.benchmark_runtime.terminal import BenchmarkTerminal

pytestmark = pytest.mark.structural


def _baseline(root: Path, baseline_id: str = "provider/task") -> Path:
    baseline = root / "baselines" / Path(*baseline_id.split("/"))
    workspace = baseline / "workspace"
    (workspace / ".yadof").mkdir(parents=True)
    (workspace / ".yadof" / "workspace.json").write_text(
        '{"workspace": "."}\n', encoding="utf-8"
    )
    (workspace / ".yadof" / "logs").mkdir()
    (workspace / ".yadof" / "logs" / "ignored.log").write_text(
        "runtime\n", encoding="utf-8"
    )
    (workspace / "jobs").mkdir()
    (workspace / "jobs" / "ignored.txt").write_text("runtime\n", encoding="utf-8")
    (workspace / "submit").mkdir()
    (workspace / "submit" / "calc_cost.py").write_text(
        "def calculate_cost(*args): return (0.5,)\n", encoding="utf-8"
    )
    (workspace / "submit" / "optimization.py").write_text(
        "def build_optimization(): return 'baseline'\n", encoding="utf-8"
    )
    (workspace / "job_template").mkdir()
    (workspace / "job_template" / "workflow.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    (workspace / "config.py").write_text(
        'EVALUATION_MODE = "fast"\n', encoding="utf-8"
    )
    (workspace / "postprocess.py").write_text(
        "raise SystemExit('the fake command runner owns test artifacts')\n",
        encoding="utf-8",
    )
    (baseline / "baseline.json").write_text(
        json.dumps(
            {
                "format": BASELINE_FORMAT,
                "id": baseline_id,
                "name": "Task",
                "description": "Tiny contract fixture.",
                "workspace": "workspace",
                "execution": {"mode": "fast", "timeout_seconds": 30},
                "contract": {
                    "objective_count": 1,
                    "rawdata_shapes": {"value": [1]},
                },
                "estimates": {
                    "evaluation_seconds": 0.01,
                    "record_mib": 0.001,
                },
                "snapshot_excludes": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return baseline


def _strategy(workspace: Path, name: str) -> Path:
    path = workspace / "resources" / "strategies" / name / "optimization.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"def build_optimization():\n    return {name!r}\n", encoding="utf-8"
    )
    return path


def _workspace(
    root: Path,
    *,
    strategies: tuple[str, ...] = ("alpha", "beta", "gamma"),
    baselines: tuple[str, ...] = ("provider/task",),
    evidence: str = "structural",
    seeds: tuple[int, ...] = (7,),
    population: int = 2,
    generations: int = 3,
    postprocess: str = "",
) -> Path:
    root = Path(api.init_workspace(root)["workspace"])
    for name in strategies:
        _strategy(root, name)
    declarations = "\n".join(
        f'    benchmark.strategy("{name}", "resources/strategies/{name}/optimization.py")'
        for name in strategies
    )
    root.joinpath("benchmark.py").write_text(
        "from yadof_benchmark import Benchmark\n\n"
        + postprocess
        + "\ndef build_benchmark(benchmark: Benchmark) -> None:\n"
        + f"    benchmark.configure(name=\"comparison\", evidence={evidence!r}, fail_fast=False)\n"
        + declarations
        + "\n    benchmark.compare(\n"
        + f"        \"main\", baselines={list(baselines)!r},\n"
        + f"        strategies={list(strategies)!r}, seeds={list(seeds)!r},\n"
        + f"        population={population}, generations={generations}, "
        + "reference=\"alpha\",\n"
        + "    )\n"
        + ("    benchmark.postprocess(\"summary\", make_summary)\n" if postprocess else ""),
        encoding="utf-8",
    )
    return root


def _plan(root: Path):
    markers = list(root.glob("*/.benchmark/workspace.json"))
    assert len(markers) == 1
    return api.plan_workspace(
        markers[0].parents[1], baselines_root=root / "baselines"
    )


def _cell_result(cell: dict, value: float) -> dict:
    planned = cell["planned_evaluations"]
    return {
        "cell": cell["id"],
        "evidence": cell["evidence"],
        "replication_scope": cell["replication_scope"],
        "comparison": cell["comparison"],
        "baseline": cell["baseline"],
        "strategy": cell["strategy"],
        "seed": cell["seed"],
        "budget": {
            "population": cell["population"],
            "generations": cell["generations"],
            "planned_evaluations": planned,
        },
        "counts": {
            "planned": planned,
            "attempted": planned,
            "completed": planned,
            "finite": planned,
        },
        "status_counts": {"completed": planned},
        "attempted_evaluations": planned,
        "completed_evaluations": planned,
        "finite_evaluations": planned,
        "generation_zero_population": {
            "expected": cell["population"],
            "observed": cell["population"],
            "complete": True,
            "fingerprint": f"seed-{cell['seed']}-population-{cell['population']}",
            "issues": [],
        },
        "objective_names": ["score"],
        "hypervolume": {
            "alignment": "attempted_real_evaluations",
            "reference_point": [1.0],
            "trajectory": [
                {
                    "generation": cell["generations"] - 1,
                    "attempted_evaluations": planned,
                    "completed_evaluations": planned,
                    "finite_evaluations": planned,
                    "cumulative_hypervolume": value,
                    "generation_hypervolume": value,
                }
            ],
            "auc": value * planned / 2.0,
            "auc_normalized": value / 2.0,
            "final": value,
        },
        "final_hypervolume": value,
        "hypervolume_auc": value * planned / 2.0,
        "hypervolume_auc_normalized": value / 2.0,
        "surrogate_training": {
            "event_count": 0,
            "completed_events": 0,
            "failed_events": 0,
            "duration_sample_count": 0,
            "total_duration_seconds": None,
            "median_duration_seconds": None,
            "maximum_duration_seconds": None,
            "representative_generation_seconds": cell.get(
                "representative_generation_seconds"
            ),
            "maximum_fraction_of_representative_generation": None,
            "all_completed_within_representative_generation": None,
            "notice": "descriptive only",
        },
        "contract": {
            "objective_count": {"expected": 1, "observed": 1, "matches": True},
            "rawdata_shapes": {
                "expected": {"value": [1]},
                "observed": {"value": [1]},
                "matches": True,
            },
        },
        "rows": [
            {
                "evidence": cell["evidence"],
                "comparison": cell["comparison"],
                "baseline": cell["baseline"],
                "strategy": cell["strategy"],
                "seed": cell["seed"],
                "population": cell["population"],
                "generations": cell["generations"],
                "job": f"{cell['strategy']}-job",
                "generation": 0,
                "objectives": {"score": 1.0 - value},
                "average_objective": 1.0 - value,
                "metadata": {},
            }
        ],
        "extensions": {
            "yadof.optimization": [{"custom": cell["strategy"]}],
            "yadof.surrogate_training": [],
        },
        "issues": [],
    }


def _successful_command(
    command, *, cwd, command_root, label, timeout_seconds, event_sink=None
):
    del cwd, label, timeout_seconds, event_sink
    selected = [str(item) for item in command]
    if selected[1:5] == ["-m", "yadof", "view", "cost"]:
        output = Path(selected[selected.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake png")
    elif len(selected) > 1 and Path(selected[1]).name == "postprocess.py":
        output_dir = Path(selected[selected.index("--output-dir") + 1])
        prefix = selected[selected.index("--output-prefix") + 1]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{prefix}domain.png").write_bytes(b"fake domain png")
    command_root.mkdir(parents=True)
    stdout = command_root / "stdout.log"
    stderr = command_root / "stderr.log"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    return CommandResult(
        tuple(str(item) for item in command), 0, 0.01, False, stdout, stderr
    )


def test_init_creates_code_first_workspace_without_overwrite(tmp_path: Path) -> None:
    requested = tmp_path / "benchmark workspace"
    created = api.init_workspace(requested)
    root = Path(created["workspace"])

    assert created == {"format": WORKSPACE_FORMAT, "workspace": str(root.resolve())}
    assert re.match(r"^\d{8}_\d{6}-benchmark-workspace$", root.name)
    assert json.loads((root / ".benchmark" / "workspace.json").read_text())[
        "format"
    ] == WORKSPACE_FORMAT
    workflow = root / "benchmark.py"
    assert workflow.is_file()
    source = workflow.read_text(encoding="utf-8")
    assert 'name="saw-algorithm-comparison"' in source
    assert 'evidence="structural"' in source
    assert 'benchmark.strategy(\n    #     "nsga3"' in source
    assert 'baselines=["ngspice/saw-ladder"]' in source
    assert 'strategies=["nsga3"]' in source
    assert "seeds=[1]" in source
    assert "population=12" in source
    assert "generations=3" in source
    assert "This intentionally small budget is structural-only" in source
    assert "population >= 100 and generations >= 20" in source
    assert 'benchmark.postprocess("summary", summarize_results)' in source
    for name in ("resources", "runs", "visualizations", "reports", "temp"):
        assert (root / name).is_dir()
        assert not any((root / name).iterdir())
    with pytest.raises(benchmark.BenchmarkError, match="not empty"):
        api.init_workspace(root)


def test_workflow_requires_explicit_valid_evidence_classification(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "workspace", strategies=("alpha",))
    workflow = workspace / "benchmark.py"
    source = workflow.read_text(encoding="utf-8")
    workflow.write_text(source.replace("evidence='structural', ", ""), encoding="utf-8")

    with pytest.raises(benchmark.BenchmarkError, match="explicitly classify"):
        api.plan_workspace(workspace, baselines_root=tmp_path / "baselines")

    workflow.write_text(
        source.replace("evidence='structural'", "evidence='smoke'"),
        encoding="utf-8",
    )
    with pytest.raises(benchmark.BenchmarkError, match="'structural' or 'performance'"):
        api.plan_workspace(workspace, baselines_root=tmp_path / "baselines")


def test_representative_generation_reference_is_explicit_and_validated(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "workspace", strategies=("alpha",))
    workflow = workspace / "benchmark.py"
    source = workflow.read_text(encoding="utf-8")
    workflow.write_text(
        source.replace(
            "evidence='structural', fail_fast=False",
            "evidence='structural', fail_fast=False, "
            "representative_generation_seconds=7200.0",
        ),
        encoding="utf-8",
    )

    spec = api.plan_workspace(workspace, baselines_root=tmp_path / "baselines")

    assert spec.workflow.representative_generation_seconds == 7200.0
    assert {cell.representative_generation_seconds for cell in spec.cells} == {
        7200.0
    }
    assert spec.to_dict()["workflow"]["representative_generation_seconds"] == 7200.0

    workflow.write_text(
        source.replace(
            "evidence='structural', fail_fast=False",
            "evidence='structural', fail_fast=False, "
            "representative_generation_seconds=0",
        ),
        encoding="utf-8",
    )
    with pytest.raises(benchmark.BenchmarkError, match="positive finite"):
        api.plan_workspace(workspace, baselines_root=tmp_path / "baselines")


@pytest.mark.parametrize(
    ("population", "generations"),
    ((99, 20), (100, 19), (12, 3)),
)
def test_performance_rejects_structural_scale_budgets(
    tmp_path: Path,
    population: int,
    generations: int,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(
        tmp_path / "performance workspace",
        strategies=("alpha",),
        evidence="performance",
        population=population,
        generations=generations,
    )

    with pytest.raises(
        benchmark.BenchmarkError,
        match=(
            r"performance comparison 'main'.*population >= 100, "
            r"generations >= 20.*2000 planned real evaluations"
        ),
    ):
        api.plan_workspace(workspace, baselines_root=tmp_path / "baselines")


def test_python_workflow_supports_multiple_comparisons_and_budgets(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "workspace")
    workflow = workspace / "benchmark.py"
    text = workflow.read_text(encoding="utf-8")
    text = text.replace(
        "    benchmark.postprocess",
        "    benchmark.postprocess",
    ).replace(
        "    )\n",
        "    )\n    benchmark.compare(\n"
        "        \"small\", baselines=[\"provider/task\"],\n"
        "        strategies=[\"alpha\", \"beta\"], seeds=[8, 9],\n"
        "        population=1, generations=2, reference=None,\n"
        "    )\n",
        1,
    )
    workflow.write_text(text, encoding="utf-8")

    request = api.load_workflow(workspace)
    spec = api.plan_workspace(request, baselines_root=tmp_path / "baselines")

    assert [item.id for item in request.comparisons] == ["main", "small"]
    assert len(spec.cells) == 7
    assert {cell.comparison_id for cell in spec.cells} == {"main", "small"}
    assert {cell.planned_evaluations for cell in spec.cells} == {2, 6}


def test_performance_classification_is_explicit_and_descriptive(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(
        tmp_path / "performance workspace",
        strategies=("alpha",),
        evidence="performance",
        population=100,
        generations=20,
    )

    assert cli.main(
        [
            "plan",
            "--workspace",
            str(workspace),
            "--baselines-root",
            str(tmp_path / "baselines"),
        ]
    ) == 0
    summary = json.loads(capsys.readouterr().out)

    assert summary["evidence"]["class"] == "performance"
    assert "descriptive only" in summary["evidence"]["notice"]
    assert "acceptance decisions" in summary["evidence"]["notice"]
    assert summary["replication"]["scopes"] == ["exploratory"]
    assert "single-seed" in summary["replication"]["notices"]["exploratory"]

    spec = api.plan_workspace(workspace, baselines_root=tmp_path / "baselines")
    assert {cell.replication_scope for cell in spec.cells} == {"exploratory"}
    run_root = create_run(spec, run_id="exploratory-performance")
    state = execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=lambda _workspace_path, cell: _cell_result(cell, 0.4),
    )
    assert state["status"] == "completed"
    results = read_json(run_root / "results.json")
    assert results["replication"]["scopes"] == ["exploratory"]
    assert all(
        row["replication_scope"] == "exploratory"
        for row in results["comparisons"]
    )
    assert "Exploratory single-seed performance evidence" in (
        run_root / "reports" / "summary.md"
    ).read_text(encoding="utf-8")
    assert inspect_run(run_root)["replication"]["scopes"] == ["exploratory"]


def test_performance_multi_seed_count_is_explicit_and_configurable(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(
        tmp_path / "multi seed performance",
        strategies=("alpha",),
        evidence="performance",
        seeds=(7, 11, 19, 23),
        population=100,
        generations=20,
    )

    spec = api.plan_workspace(workspace, baselines_root=tmp_path / "baselines")
    serialized = spec.to_dict()

    assert len(spec.cells) == 4
    assert {cell.seed for cell in spec.cells} == {7, 11, 19, 23}
    assert {cell.replication_scope for cell in spec.cells} == {"multi-seed"}
    assert serialized["workflow"]["comparisons"][0]["replication_scope"] == (
        "multi-seed"
    )
    assert "significance or robustness" in serialized["workflow"]["comparisons"][0][
        "replication_notice"
    ]


def test_strategy_requires_complete_build_function(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "workspace", strategies=("alpha",))
    _strategy(workspace, "alpha").write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(benchmark.BenchmarkError, match="build_optimization"):
        api.plan_workspace(workspace, baselines_root=tmp_path / "baselines")


def test_recursive_baseline_discovery_and_clean_snapshot(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    discovered = discover_baselines(tmp_path / "baselines")
    assert discovered["provider/task"].root == baseline

    _workspace(tmp_path / "workspace")
    spec = _plan(tmp_path)
    run_root = create_run(spec, run_id="clean-snapshot")
    snapshot = run_root / "inputs" / "baselines" / "provider-task" / "workspace"
    assert (snapshot / ".yadof" / "workspace.json").is_file()
    assert not (snapshot / ".yadof" / "logs").exists()
    assert not (snapshot / "jobs").exists()
    assert (run_root / "inputs" / "workflow" / "benchmark.py").is_file()
    assert (run_root / "driver" / "api.py").is_file()
    assert (run_root / "driver" / "cli.py").is_file()
    assert not (run_root / "driver" / "benchmark.py").exists()
    assert not (run_root / "driver" / "benchmark_core.py").exists()


def test_attempt_workspace_uses_compact_run_local_path(tmp_path: Path) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="compact-workspace")
    saved, state = load_run(run_root)

    attempt_root, materialized, attempt = prepare_attempt(
        run_root, saved["cells"][0], state
    )

    relative = materialized.relative_to(run_root)
    assert relative.parts[0] == "workspaces"
    assert len(relative.parts) == 3
    assert re.fullmatch(r"[0-9a-f]{16}", relative.parts[1])
    assert relative.parts[2] == "0001"
    assert attempt["workspace"] == relative.as_posix()
    assert len(str(materialized)) < len(str(attempt_root / "workspace"))


def test_run_and_workspace_outputs_use_timestamped_human_names(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "human study", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="descriptive-run")

    assert re.match(r"^\d{8}_\d{6}-human-study$", workspace.name)
    assert re.match(r"^\d{8}_\d{6}-descriptive-run$", run_root.name)

    saved, state = load_run(run_root)
    _attempt_root, compact, _attempt = prepare_attempt(
        run_root, saved["cells"][0], state
    )
    assert re.fullmatch(r"[0-9a-f]{16}", compact.parent.name)


def test_manifest_rejects_escape_and_nonsemantic_source_path(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    manifest_path = baseline / "baseline.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["workspace"] = "../../outside"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(benchmark.BenchmarkError, match="escapes"):
        load_baseline(manifest_path)

    data["workspace"] = "workspace"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    misplaced = tmp_path / "baselines" / "provider" / "opaque-source"
    baseline.rename(misplaced)
    with pytest.raises(benchmark.BenchmarkError, match="semantic id"):
        discover_baselines(tmp_path / "baselines")


def test_baseline_requires_uniform_postprocess_script(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    (baseline / "workspace" / "postprocess.py").unlink()

    with pytest.raises(benchmark.BenchmarkError, match="postprocess.py"):
        load_baseline(baseline / "baseline.json")


def test_execution_reports_arbitrary_arms_by_comparison(tmp_path: Path) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace")
    run_root = create_run(_plan(tmp_path), run_id="execute-three")
    values = {"alpha": 0.2, "beta": 0.35, "gamma": 0.1}
    commands: list[tuple[str, ...]] = []

    def command(*args, **kwargs):
        commands.append(tuple(str(item) for item in args[0]))
        return _successful_command(*args, **kwargs)

    state = execution.execute_existing_run(
        run_root,
        command_runner=command,
        collector=lambda _workspace, cell: _cell_result(
            cell, values[cell["strategy"]]
        ),
    )

    assert state["status"] == "completed"
    results = read_json(run_root / "results.json")
    assert results["evidence"]["class"] == "structural"
    assert results["replication"]["scopes"] == ["structural"]
    assert all(row["evidence"] == "structural" for row in results["comparisons"])
    assert all(
        row["replication_scope"] == "structural"
        for row in results["comparisons"]
    )
    by_strategy = {
        row["strategy"]: row["reference_delta"]
        for row in results["comparisons"]
    }
    assert by_strategy == pytest.approx(
        {"alpha": 0.0, "beta": 0.15, "gamma": -0.1}
    )
    assert {row["comparison"] for row in results["comparisons"]} == {"main"}
    assert (run_root / "reports" / "summary.md").is_file()
    assert (run_root / "reports" / "cell-validity.csv").is_file()
    assert (run_root / "reports" / "final-hypervolume.csv").is_file()
    assert (run_root / "reports" / "descriptive-results.json").is_file()
    assert (run_root / "results.csv").read_text(encoding="utf-8").startswith(
        "evidence,replication_scope,"
    )
    assert (run_root / "reports" / "cell-validity.csv").read_text(
        encoding="utf-8"
    ).startswith("evidence,replication_scope,")
    assert (run_root / "reports" / "final-hypervolume.csv").read_text(
        encoding="utf-8"
    ).startswith("evidence,replication_scope,")
    descriptive = read_json(run_root / "reports" / "descriptive-results.json")
    assert descriptive["evidence"]["class"] == "structural"
    summary = (run_root / "reports" / "summary.md").read_text(encoding="utf-8")
    assert "Evidence class: `structural`" in summary
    assert "must not support algorithm performance conclusions" in summary
    inspected = inspect_run(run_root)
    assert inspected["evidence"]["class"] == "structural"
    assert len(list((run_root / "visualizations" / "cost").glob("*.png"))) == 3
    assert len(list((run_root / "visualizations" / "provider-task").glob("*.png"))) == 3
    workspace = Path(_plan(tmp_path).workflow.workspace)
    report_index = workspace / "reports" / run_root.name / "index.json"
    assert read_json(report_index)["evidence"] == "structural"
    assert (workspace / "visualizations" / run_root.name / "index.json").is_file()
    run_commands = [item for item in commands if item[2:4] == ("yadof", "run")]
    assert len(run_commands) == 3
    assert all("--fail-on-all-infinite" in item for item in run_commands)


def test_collect_cell_reports_attempted_aligned_hypervolume_and_training_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof import recorded_data
    from yadof.tools import cost_viewer

    records = [
        {
            "job_name": "g0-0",
            "status": "completed",
            "generation_index": 0,
            "population_index": 0,
        },
        {
            "job_name": "g0-1",
            "status": "completed",
            "generation_index": 0,
            "population_index": 1,
        },
        {
            "job_name": "g1-0",
            "status": "completed",
            "generation_index": 1,
            "population_index": 0,
        },
        {
            "job_name": "g1-1",
            "status": "error",
            "generation_index": 1,
            "population_index": 1,
        },
    ]
    rows = [
        {
            "job_name": "g0-0",
            "generation_index": 0,
            "costs": (0.2,),
            "average_cost": 0.2,
        },
        {
            "job_name": "g0-1",
            "generation_index": 0,
            "costs": (0.3,),
            "average_cost": 0.3,
        },
        {
            "job_name": "g1-0",
            "generation_index": 1,
            "costs": (0.1,),
            "average_cost": 0.1,
        },
    ]

    monkeypatch.setattr(recorded_data, "list_records", lambda _workspace: records)
    monkeypatch.setattr(
        recorded_data, "list_optimization_metadata", lambda _workspace: []
    )
    monkeypatch.setattr(
        recorded_data,
        "list_surrogate_metadata",
        lambda _workspace: [
            {"status": "completed", "duration_sec": 12.0},
            {"status": "completed", "duration_sec": 18.0},
        ],
    )
    monkeypatch.setattr(
        recorded_data,
        "get_normalized_variables",
        lambda _workspace, status=None: [
            ("g0-0", (0.1, 0.2)),
            ("g0-1", (0.8, 0.9)),
            ("g1-0", (0.4, 0.5)),
            ("g1-1", (0.6, 0.7)),
        ],
    )

    def build_rows(_workspace, *, status, issues, objective_names_out):
        assert status == "completed"
        assert isinstance(issues, list)
        objective_names_out.append("score")
        return rows

    monkeypatch.setattr(cost_viewer, "build_rows", build_rows)
    monkeypatch.setattr(
        cost_viewer,
        "hypervolume_series",
        lambda _rows: ([2, 3], [0.2, 0.4], [0.2, 0.3], (1.0,)),
    )
    monkeypatch.setattr(
        result_runtime,
        "_rawdata_shapes",
        lambda _workspace, _records: {"value": [1]},
    )
    cell = {
        "id": "main-provider-task-alpha-s7",
        "evidence": "performance",
        "replication_scope": "exploratory",
        "comparison": "main",
        "baseline": "provider/task",
        "strategy": "alpha",
        "seed": 7,
        "population": 2,
        "generations": 2,
        "planned_evaluations": 4,
        "representative_generation_seconds": 7200.0,
        "contract": {
            "objective_count": 1,
            "rawdata_shapes": {"value": [1]},
        },
    }

    result = collect_cell(tmp_path, cell)

    assert result["counts"] == {
        "planned": 4,
        "attempted": 4,
        "completed": 3,
        "finite": 3,
    }
    assert result["generation_zero_population"]["complete"] is True
    assert result["generation_zero_population"]["fingerprint"]
    trajectory = result["hypervolume"]["trajectory"]
    assert [point["attempted_evaluations"] for point in trajectory] == [2, 4]
    assert [point["finite_evaluations"] for point in trajectory] == [2, 3]
    assert result["final_hypervolume"] == pytest.approx(0.4)
    assert result["hypervolume_auc"] == pytest.approx(0.8)
    assert result["hypervolume_auc_normalized"] == pytest.approx(0.2)
    assert result["surrogate_training"]["median_duration_seconds"] == 15.0
    assert result["surrogate_training"][
        "maximum_fraction_of_representative_generation"
    ] == pytest.approx(18.0 / 7200.0)


def test_invalid_pair_is_retained_but_excluded_from_cross_seed_aggregate(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    _workspace(
        tmp_path / "workspace",
        strategies=("alpha", "beta"),
        seeds=(7, 11),
    )
    run_root = create_run(_plan(tmp_path), run_id="paired-validity")

    def collector(_workspace: Path, cell: dict) -> dict:
        result = _cell_result(
            cell, 0.2 if cell["strategy"] == "alpha" else 0.3
        )
        if cell["seed"] == 7 and cell["strategy"] == "beta":
            result["counts"]["attempted"] -= 1
            result["attempted_evaluations"] -= 1
            result["generation_zero_population"]["fingerprint"] += "-mismatch"
        return result

    state = execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=collector,
    )

    assert state["status"] == "completed"
    results = read_json(run_root / "results.json")
    pairing_by_seed = {row["seed"]: row for row in results["pairings"]}
    assert pairing_by_seed[7]["valid"] is False
    assert pairing_by_seed[7]["checks"]["attempted_budget_matches"] is False
    assert pairing_by_seed[7]["checks"][
        "generation_zero_population_matches"
    ] is False
    assert pairing_by_seed[11]["valid"] is True
    seed_7_rows = [row for row in results["comparisons"] if row["seed"] == 7]
    assert all(row["reference_delta"] is None for row in seed_7_rows)
    assert all(not row["aggregate_eligible"] for row in seed_7_rows)
    assert len(results["cells"]) == 4
    for aggregate in results["cross_seed_aggregates"]:
        assert aggregate["included_seeds"] == [11]
        assert aggregate["excluded_seeds"] == [7]
    for name in (
        "hypervolume-trajectory.csv",
        "pairing-validity.csv",
        "cross-seed-aggregates.csv",
        "surrogate-training.csv",
    ):
        assert (run_root / "reports" / name).is_file()
    final_csv = (run_root / "reports" / "final-hypervolume.csv").read_text(
        encoding="utf-8"
    )
    assert "success_rate" not in final_csv
    assert "runtime_seconds" not in final_csv


def test_fake_three_baseline_pipeline_groups_domain_outputs(tmp_path: Path) -> None:
    baseline_ids = (
        "chrono/trebuchet",
        "ngspice/saw-ladder",
        "test-com/synthetic-antenna",
    )
    for baseline_id in baseline_ids:
        _baseline(tmp_path, baseline_id)
    _workspace(
        tmp_path / "three baselines",
        strategies=("alpha",),
        baselines=baseline_ids,
    )
    run_root = create_run(_plan(tmp_path), run_id="artifact-pipeline")

    state = execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=lambda _workspace, cell: _cell_result(cell, 0.2),
    )

    assert state["status"] == "completed"
    visualizations = run_root / "visualizations"
    assert {path.name for path in visualizations.iterdir() if path.is_dir()} == {
        "cost",
        "chrono-trebuchet",
        "ngspice-saw-ladder",
        "test-com-synthetic-antenna",
    }
    assert len(list((visualizations / "cost").glob("*.png"))) == 3
    for baseline_id in baseline_ids:
        category = baseline_id.replace("/", "-")
        assert len(list((visualizations / category).glob("*domain.png"))) == 1
    summary = (run_root / "reports" / "summary.md").read_text(encoding="utf-8")
    assert "## Cell completion and validity" in summary
    assert "## Final hypervolume" in summary
    report = read_json(run_root / "reports" / "descriptive-results.json")
    assert len(report["cells"]) == 3
    assert all(item["valid"] for item in report["cells"])


def test_missing_or_empty_required_visualization_fails_run(tmp_path: Path) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="missing-visualization")

    def command(command, **kwargs):
        result = _successful_command(command, **kwargs)
        selected = [str(item) for item in command]
        if len(selected) > 1 and Path(selected[1]).name == "postprocess.py":
            output_dir = Path(selected[selected.index("--output-dir") + 1])
            prefix = selected[selected.index("--output-prefix") + 1]
            (output_dir / f"{prefix}domain.png").unlink()
        return result

    state = execution.execute_existing_run(
        run_root,
        command_runner=command,
        collector=lambda _workspace, cell: _cell_result(cell, 0.2),
    )

    assert state["status"] == "failed"
    cell_state = next(iter(state["cells"].values()))
    assert "created no non-empty artifact" in cell_state["error"]
    result = read_json(run_root / cell_state["attempts"][0]["result"])
    assert "required visualization failed" in result["issues"][0]


@pytest.mark.recovery
def test_postprocessor_failure_resumes_without_rerunning_cells(tmp_path: Path) -> None:
    _baseline(tmp_path)
    postprocess = (
        "def make_summary(context):\n"
        "    if context.attempt.name == '0001':\n"
        "        raise RuntimeError('first postprocess failure')\n"
        "    (context.visualizations / 'done.txt').write_text('done', encoding='utf-8')\n"
        "    return {'created': 'done.txt'}\n"
    )
    _workspace(
        tmp_path / "workspace", strategies=("alpha",), postprocess=postprocess
    )
    run_root = create_run(_plan(tmp_path), run_id="postprocess-retry")
    calls: list[str] = []

    def command(*args, **kwargs):
        calls.append(kwargs["label"])
        return _successful_command(*args, **kwargs)

    failed = execution.execute_existing_run(
        run_root,
        command_runner=command,
        collector=lambda _workspace, cell: _cell_result(cell, 0.2),
    )
    resumed = execution.execute_existing_run(
        run_root,
        command_runner=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("successful cell was rerun")
        ),
        collector=lambda *_args: (_ for _ in ()).throw(
            AssertionError("successful cell was recollected")
        ),
    )

    assert failed["status"] == "failed"
    assert resumed["status"] == "completed"
    assert calls == ["check", "run", "view-cost", "baseline-postprocess"]
    assert (run_root / "visualizations" / "done.txt").read_text() == "done"
    attempts = resumed["postprocessors"]["summary"]["attempts"]
    assert [item["status"] for item in attempts] == ["failed", "succeeded"]


@pytest.mark.recovery
def test_postprocessor_import_failure_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _baseline(tmp_path)
    postprocess = (
        "import os\n"
        "if os.environ.get('BENCHMARK_FAIL_SNAPSHOT_IMPORT') == '1':\n"
        "    raise RuntimeError('snapshot import failed')\n\n"
        "def make_summary(context):\n"
        "    return None\n"
    )
    _workspace(
        tmp_path / "workspace", strategies=("alpha",), postprocess=postprocess
    )
    run_root = create_run(_plan(tmp_path), run_id="postprocess-import-failure")
    monkeypatch.setenv("BENCHMARK_FAIL_SNAPSHOT_IMPORT", "1")

    state = execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=lambda _workspace, cell: _cell_result(cell, 0.2),
    )

    item = state["postprocessors"]["summary"]
    assert state["status"] == "failed"
    assert item["status"] == "failed"
    assert "snapshot import failed" in item["error"]
    assert item["attempts"][0]["status"] == "failed"


@pytest.mark.recovery
def test_interrupted_cell_is_sealed_and_retried(tmp_path: Path) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="recover")
    saved, state = load_run(run_root)
    cell = saved["cells"][0]
    _attempt_root, _materialized, attempt = prepare_attempt(run_root, cell, state)
    attempt["status"] = "running"
    state["cells"][cell["id"]]["status"] = "running"
    save_state(run_root, state)

    resumed = execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=lambda _workspace, item: _cell_result(item, 0.2),
    )

    attempts = resumed["cells"][cell["id"]]["attempts"]
    assert [item["status"] for item in attempts] == ["interrupted", "collected"]


@pytest.mark.recovery
def test_resume_uses_run_driver_and_inspect_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="snapshot-resume")
    execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=lambda _workspace, item: _cell_result(item, 0.2),
    )
    state_path = run_root / "state.json"
    before = state_path.stat().st_mtime_ns
    monkeypatch.setattr(
        execution,
        "execute_existing_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("current execution module was used")
        ),
    )

    resumed = api.resume_run(run_root)
    inspected = inspect_run(run_root)

    assert resumed["status"] == "completed"
    assert inspected["workflow"] == "comparison"
    assert state_path.stat().st_mtime_ns == before


@pytest.mark.recovery
def test_detached_run_does_not_require_originating_workspace(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="detached-evidence")
    detached = tmp_path / "detached" / run_root.name
    shutil.copytree(run_root, detached)
    workspace.rename(tmp_path / "origin-no-longer-available")

    state = execution.execute_existing_run(
        detached,
        command_runner=_successful_command,
        collector=lambda _workspace, item: _cell_result(item, 0.2),
    )

    assert state["status"] == "completed"
    assert (detached / "reports" / "summary.md").is_file()


def test_public_surface_and_cli_have_only_code_first_contract() -> None:
    assert api.__all__ == [
        "BaselineManifest",
        "Benchmark",
        "BenchmarkError",
        "ComparisonSpec",
        "PostprocessContext",
        "RunSpec",
        "WorkflowRequest",
        "discover_baselines",
        "init_workspace",
        "inspect_run",
        "load_workflow",
        "plan_workspace",
        "resume_run",
        "run_workspace",
        "user_doc_root",
    ]
    project = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-m",
        "yadof_benchmark",
        "--help",
    ]
    environment = dict(os.environ)
    if environment.get("YADOF_BENCHMARK_TEST_INSTALLED") != "1":
        environment["PYTHONPATH"] = str(project / "src")
    result = subprocess.run(
        command,
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert "{init,baselines,check,plan,run,resume,inspect,docs}" in result.stdout
    assert "--study" not in result.stdout


def test_distribution_entrypoints_match_code_first_contract() -> None:
    project = Path(__file__).resolve().parents[1]
    package = project / "src" / "yadof_benchmark"
    assert (package / "cli.py").is_file()
    assert (package / "api.py").is_file()
    assert 'name = "yadof-benchmark"' in (project / "pyproject.toml").read_text()
    assert 'dependencies = ["rich>=13", "yadof[plot]>=0.4.2"]' in (
        project / "pyproject.toml"
    ).read_text()
    assert 'yadof-benchmark = "yadof_benchmark.cli:main"' in (
        project / "pyproject.toml"
    ).read_text()


def test_packaged_resources_are_available_from_source_tree() -> None:
    manifests = api.discover_baselines()
    assert {"chrono/trebuchet", "ngspice/saw-ladder", "test-com/synthetic-antenna"} <= set(manifests)
    assert (api.user_doc_root() / "README.md").is_file()


def test_logged_child_progress_reaches_sink_on_foreground_thread(
    tmp_path: Path,
) -> None:
    owner = threading.get_ident()
    observed: list[tuple[int, dict]] = []
    lines = [
        "[yadof] generation 0 (fast) [............................] "
        "0/100 successful=0 errors=0 remaining=100",
        "[yadof] generation 0 (fast) [............................] "
        "1/100 successful=1 errors=0 remaining=99",
        "[yadof] generation 0 (fast) [##############..............] "
        "50/100 successful=50 errors=0 remaining=50",
        "[yadof] generation 1 (fast) [............................] "
        "1/100 successful=1 errors=0 remaining=99",
    ]
    child = (
        "import sys,time; lines="
        + repr(lines)
        + "; [(sys.stderr.write(line+'\\r'),sys.stderr.flush(),time.sleep(0.08)) "
        "for line in lines]; sys.stderr.write('\\n'); sys.stderr.flush()"
    )

    result = execution.run_logged(
        [
            sys.executable,
            "-c",
            child,
            "--generations",
            "20",
            "--population-size",
            "100",
        ],
        cwd=tmp_path,
        command_root=tmp_path / "command",
        label="run",
        timeout_seconds=30,
        event_sink=lambda event: observed.append((threading.get_ident(), dict(event))),
    )

    assert result.returncode == 0
    progress = [
        event for _thread, event in observed if event["event"] == "cell-progress"
    ]
    assert [event["evaluations"] for event in progress] == [1, 50, 101]
    assert all(event["planned_evaluations"] == 2000 for event in progress)
    assert {thread for thread, _event in observed} == {owner}
    persisted = [
        json.loads(line)
        for line in (tmp_path / "command" / "progress.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {item["event"] for item in persisted} >= {
        "command-progress",
        "cell-progress",
    }
    assert all(item["utc"].endswith("Z") for item in persisted)
    assert not any(event["event"] == "child-output" for _thread, event in observed)


def test_raw_child_output_requires_explicit_stream_option(tmp_path: Path) -> None:
    observed: list[dict] = []
    result = execution.run_logged(
        [sys.executable, "-c", "print('bounded child line')"],
        cwd=tmp_path,
        command_root=tmp_path / "streamed-command",
        label="run",
        timeout_seconds=30,
        event_sink=lambda event: observed.append(dict(event)),
        stream_child_output=True,
    )

    assert result.returncode == 0
    assert any(
        item["event"] == "child-output"
        and item["stream"] == "stdout"
        and item["text"] == "bounded child line"
        for item in observed
    )


def test_plan_defaults_to_bounded_summary_and_full_json_is_explicit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "workspace")

    assert cli.main(
        [
            "plan",
            "--workspace",
            str(workspace),
            "--baselines-root",
            str(tmp_path / "baselines"),
        ]
    ) == 0
    summary_text = capsys.readouterr().out
    summary = json.loads(summary_text)
    assert summary["format"] == "yadof.benchmark.plan-summary"
    assert summary["counts"] == {
        "cells": 3,
        "comparisons": 1,
        "planned_evaluations": 18,
    }
    assert summary["evidence"]["class"] == "structural"
    assert "must not support algorithm performance conclusions" in summary["evidence"]["notice"]
    assert "cells" not in summary

    assert cli.main(
        [
            "plan",
            "--workspace",
            str(workspace),
            "--baselines-root",
            str(tmp_path / "baselines"),
            "--json",
        ]
    ) == 0
    full_text = capsys.readouterr().out
    full = json.loads(full_text)
    assert full["workflow"]["evidence"] == "structural"
    assert {cell["evidence"] for cell in full["cells"]} == {"structural"}
    assert len(full["cells"]) == 3
    assert len(summary_text) < len(full_text)


def _complete_timing_run(run_root: Path, durations: dict[str, float]) -> None:
    spec, state = load_run(run_root)
    for cell in spec["cells"]:
        cell_id = str(cell["id"])
        state["cells"][cell_id] = {
            "status": "collected",
            "error": None,
            "attempts": [
                {
                    "number": 1,
                    "runtime_seconds": durations[str(cell["strategy"])],
                    "finished_utc": "2026-08-29T00:00:00Z",
                    "collected_utc": "2026-08-29T00:00:00Z",
                }
            ],
        }
    state["status"] = "completed"
    state["started_utc"] = "2026-08-28T23:50:00Z"
    state["finished_utc"] = "2026-08-29T00:00:00Z"
    save_state(run_root, state)


def _activate_first_cell(
    run_root: Path,
    *,
    started_utc: str,
) -> tuple[dict, dict, Path]:
    spec, state = load_run(run_root)
    cell = spec["cells"][0]
    cell_id = str(cell["id"])
    command_root = (
        run_root / "cells" / cell_id / "attempts" / "0001" / "commands" / "02-run"
    )
    command_root.mkdir(parents=True)
    (command_root / "started.json").write_text(
        json.dumps(
            {
                "label": "run",
                "started_utc": started_utc,
                "command": [],
            }
        ),
        encoding="utf-8",
    )
    (command_root / "stdout.log").write_text("", encoding="utf-8")
    (command_root / "stderr.log").write_text("", encoding="utf-8")
    attempt_root = command_root.parents[1]
    state["cells"][cell_id] = {
        "status": "running",
        "error": None,
        "attempts": [
            {
                "number": 1,
                "path": attempt_root.relative_to(run_root).as_posix(),
                "status": "running",
                "created_utc": started_utc,
                "active_command": command_root.relative_to(run_root).as_posix(),
                "runtime_seconds": 0.0,
            }
        ],
    }
    state["status"] = "running"
    state["started_utc"] = started_utc
    state["finished_utc"] = None
    save_state(run_root, state)
    return spec, state, command_root


def test_eta_prefers_exact_same_arm_history_and_excludes_cross_arm(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha", "beta"))
    plan = _plan(tmp_path)
    prior = create_run(plan, run_id="timing-prior")
    _complete_timing_run(prior, {"alpha": 100.0, "beta": 10.0})
    current = create_run(plan, run_id="timing-current")
    spec, state, _command_root = _activate_first_cell(
        current, started_utc="2026-08-29T00:00:00Z"
    )
    now = dt.datetime(2026, 8, 29, 0, 0, 20, tzinfo=dt.timezone.utc)

    timing = estimate_run_timing(current, spec, state, now=now)

    assert timing["estimated_remaining_seconds"] == pytest.approx(90.0)
    assert timing["matched_history"] == {"exact": 2, "compatible": 0, "none": 0}
    assert {
        (item["cell"], item.get("median_seconds"))
        for item in timing["evidence"]
        if item["kind"] == "matched-cell"
    } == {
        (str(spec["cells"][0]["id"]), 100.0),
        (str(spec["cells"][1]["id"]), 10.0),
    }

    history_path = current / "timing_history.json"
    history = json.loads(history_path.read_text(encoding="utf-8"))
    cross_task_history = json.loads(json.dumps(history))
    for item in cross_task_history["records"]:
        if item["strategy"] == "alpha":
            item["comparison"] = "another-task"
    history_path.write_text(json.dumps(cross_task_history), encoding="utf-8")
    without_same_task = estimate_run_timing(current, spec, state, now=now)
    cross_task_alpha = next(
        item
        for item in without_same_task["evidence"]
        if item["cell"] == str(spec["cells"][0]["id"])
    )
    assert cross_task_alpha["kind"] == "evaluation-lower-bound"

    for item in history["records"]:
        if item["strategy"] == "alpha":
            item["strategy_digest"] = "changed-strategy"
            item["workflow_digest"] = "changed-workflow"
            item["driver_digest"] = "changed-driver"
    history_path.write_text(json.dumps(history), encoding="utf-8")
    compatible = estimate_run_timing(current, spec, state, now=now)
    assert compatible["matched_history"] == {
        "exact": 1,
        "compatible": 1,
        "none": 0,
    }
    compatible_alpha = next(
        item
        for item in compatible["evidence"]
        if item["cell"] == str(spec["cells"][0]["id"])
    )
    assert compatible_alpha["match"] == "compatible"
    assert compatible_alpha["confidence"] == "low"

    history["records"] = [
        item for item in history["records"] if item["strategy"] == "beta"
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")
    without_alpha = estimate_run_timing(current, spec, state, now=now)
    alpha_evidence = next(
        item
        for item in without_alpha["evidence"]
        if item["cell"] == str(spec["cells"][0]["id"])
    )
    assert alpha_evidence["kind"] == "evaluation-lower-bound"
    assert alpha_evidence["seconds"] < 1.0


def test_eta_replay_models_increasing_generation_cost(tmp_path: Path) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="trend-replay")
    spec, state, command_root = _activate_first_cell(
        run_root, started_utc="2026-08-29T00:00:00Z"
    )
    cell = spec["cells"][0]
    cell["generations"] = 6
    cell["planned_evaluations"] = 12
    events = []
    for generation, seconds in ((0, 10), (1, 30), (2, 60)):
        events.append(
            {
                "utc": (
                    dt.datetime(2026, 8, 29, tzinfo=dt.timezone.utc)
                    + dt.timedelta(seconds=seconds)
                ).isoformat().replace("+00:00", "Z"),
                "event": "cell-progress",
                "phase": f"generation {generation}",
                "generation": generation,
                "generation_number": generation + 1,
                "generations": 6,
                "finished": 2,
                "total": 2,
                "remaining": 0,
                "evaluations": (generation + 1) * 2,
                "planned_evaluations": 12,
            }
        )
    (command_root / "progress.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in events),
        encoding="utf-8",
    )
    now = dt.datetime(2026, 8, 29, 0, 1, tzinfo=dt.timezone.utc)

    timing = estimate_run_timing(run_root, spec, state, now=now)

    trend = next(item for item in timing["evidence"] if item["kind"] == "generation-trend")
    assert trend["completed_generations"] == 3
    assert trend["seconds_per_generation_slope"] == pytest.approx(10.0)
    assert timing["estimated_remaining_seconds"] == pytest.approx(150.0)


def test_inspect_bounds_anomalies_and_exposes_progressive_next_steps(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="bounded-inspect")
    _spec, state = load_run(run_root)
    state["status"] = "failed"
    for index in range(30):
        state["cells"][f"synthetic-{index:02d}"] = {
            "status": "failed",
            "attempts": [],
            "error": f"failure-{index:02d}",
        }
    save_state(run_root, state)

    inspected = inspect_run(run_root)

    assert len(inspected["anomalies"]) == 8
    assert inspected["anomalies_truncated"] == 22
    assert inspected["timing"]["confidence"] == "unavailable"
    assert "resume" in inspected["next_commands"]
    assert [item["step"] for item in inspected["progressive_disclosure"]][:3] == [
        "inspect",
        "report_markdown",
        "report_json",
    ]
    assert len(json.dumps(inspected)) < 8000


def test_inspect_adapts_older_results_without_descriptive_report(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="legacy-inspect")
    execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=lambda _workspace, cell: _cell_result(cell, 0.2),
    )
    (run_root / "reports" / "descriptive-results.json").unlink()
    results_path = run_root / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8"))
    results.pop("cell_summaries", None)
    results_path.write_text(json.dumps(results), encoding="utf-8")
    _spec, state = load_run(run_root)
    state.pop("started_utc", None)
    state.pop("finished_utc", None)
    save_state(run_root, state)

    inspected = inspect_run(run_root)

    assert inspected["validity"] == {
        "completed": 1,
        "valid": 1,
        "invalid": 0,
        "incomplete": 0,
    }
    assert inspected["comparison"]["rows"] == 1
    assert inspected["comparison"]["report"] == str(results_path)
    assert [
        item["step"] for item in inspected["progressive_disclosure"]
    ] == ["inspect", "report_markdown", "legacy_results_json"]
    assert all(
        item["path"] is None or Path(item["path"]).exists()
        for item in inspected["progressive_disclosure"]
    )
    assert inspected["timing"]["estimated_completion_utc"] == state["updated_utc"]


def test_rich_progress_survives_dumb_term_and_shows_first_real_update(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class TtyBuffer(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "120")
    terminal = TtyBuffer()
    display = BenchmarkTerminal(stream=terminal)
    assert display.console.is_terminal
    assert not display.console.is_dumb_terminal
    assert display.console.no_color
    display.start()
    display.handle(
        {
            "event": "run-started",
            "run": str(tmp_path),
            "total_cells": 18,
            "finished_cells": 0,
            "completed_cells": 0,
            "failed_cells": 0,
        }
    )
    display.handle(
        {
            "event": "cell-started",
            "cell": "chrono__gpsaf-conditional-inr__seed-130363",
            "population": 100,
            "generations": 20,
            "planned_evaluations": 2000,
            "total_cells": 18,
            "finished_cells": 0,
            "completed_cells": 0,
            "failed_cells": 0,
        }
    )
    before = terminal.getvalue()
    display.handle(
        {
            "event": "cell-progress",
            "phase": "generation 0",
            "generation_number": 1,
            "generations": 20,
            "evaluations": 1,
            "planned_evaluations": 2000,
            "successful": 1,
            "errors": 0,
        }
    )
    intermediate = terminal.getvalue()[len(before):]
    display.finish()

    assert intermediate
    assert "1/2000 eval | 0.1% gen=1/20 ok=1 err=0" in intermediate
    assert intermediate.index("[cell]") < intermediate.index("[benchmark]")
    assert os.environ["TERM"] == "dumb"


def test_progress_rows_keep_critical_fields_in_narrow_terminal() -> None:
    class TtyBuffer(io.StringIO):
        def isatty(self) -> bool:
            return True

    display = BenchmarkTerminal(
        stream=TtyBuffer(),
        environ={"COLUMNS": "42", "LINES": "25", "TERM": "dumb", "NO_COLOR": "1"},
    )
    display.total_cells = 18
    display.finished_cells = 7
    display.completed_cells = 6
    display.failed_cells = 1
    display.cell_total = 2000
    display.cell_completed = 1350
    display.generation_number = 14
    display.generations = 20
    display.cell_errors = 8
    display.phase = "generation 13"

    cell = display._cell_line()
    global_line = display._global_line()
    assert display._bar(0, 0, 5) == "-----"
    assert len(cell) <= 42
    assert "1350/2000" in cell and "g14/20" in cell and "e8" in cell
    assert len(global_line) <= 42
    assert "7/18" in global_line and "ok6" in global_line and "e1" in global_line


def test_terminal_log_retains_final_failure_and_inspection_path(tmp_path: Path) -> None:
    terminal = io.StringIO()
    display = BenchmarkTerminal(tmp_path, stream=terminal)
    display.start()
    display.handle(
        {
            "utc": "2026-08-29T00:00:00Z",
            "event": "run-finished",
            "run": str(tmp_path),
            "status": "failed",
            "total_cells": 1,
            "finished_cells": 1,
            "completed_cells": 0,
            "failed_cells": 1,
        }
    )
    display.finish(result={"status": "failed", "run": str(tmp_path)})

    log = (tmp_path / "benchmark.log").read_text(encoding="utf-8")
    assert "finished; status=failed" in log
    assert str(tmp_path) in log
    assert "benchmark finished: status=failed" in log


@pytest.mark.skipif(os.name != "nt", reason="Windows detached-console contract")
def test_detached_launch_defaults_visible_and_returns_receipt(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    _baseline(tmp_path)
    _workspace(tmp_path / "workspace", strategies=("alpha",))
    run_root = create_run(_plan(tmp_path), run_id="detached-receipt")

    class Process:
        pid = 4242

    def process_factory(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    receipt = launch_detached(run_root, process_factory=process_factory)

    assert receipt["pid"] == 4242
    assert receipt["visible"] is True
    assert receipt["evidence"]["class"] == "structural"
    assert receipt["run"] == str(run_root.resolve())
    assert receipt["log"] == str(run_root.resolve() / "benchmark.log")
    assert "inspect --run" in receipt["inspect"]
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["creationflags"] & subprocess.CREATE_NEW_CONSOLE
    assert kwargs["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert "stdin" not in kwargs
    assert "stdout" not in kwargs and "stderr" not in kwargs


def test_hidden_launch_requires_explicit_detach(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(["resume", "--run", str(tmp_path), "--hidden"])

    assert exit_code == 2
    assert "--hidden is valid only with explicit --detach" in capsys.readouterr().err
