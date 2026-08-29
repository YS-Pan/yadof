from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import yadof_benchmark as benchmark
from yadof_benchmark import api
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
from yadof_benchmark.benchmark_runtime.results import inspect_run
from yadof_benchmark.benchmark_runtime.storage import (
    create_run,
    load_run,
    prepare_attempt,
    read_json,
    save_state,
)


def _baseline(root: Path, baseline_id: str = "provider/task") -> Path:
    baseline = root / "baselines" / "provider" / "task"
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
    postprocess: str = "",
) -> Path:
    api.init_workspace(root)
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
        + "    benchmark.configure(name=\"comparison\", fail_fast=False)\n"
        + declarations
        + "\n    benchmark.compare(\n"
        + "        \"main\", baselines=[\"provider/task\"],\n"
        + f"        strategies={list(strategies)!r}, seeds=[7],\n"
        + "        population=2, generations=3, reference=\"alpha\",\n"
        + "    )\n"
        + ("    benchmark.postprocess(\"summary\", make_summary)\n" if postprocess else ""),
        encoding="utf-8",
    )
    return root


def _plan(root: Path):
    return api.plan_workspace(root / "workspace", baselines_root=root / "baselines")


def _cell_result(cell: dict, value: float) -> dict:
    return {
        "cell": cell["id"],
        "comparison": cell["comparison"],
        "baseline": cell["baseline"],
        "strategy": cell["strategy"],
        "seed": cell["seed"],
        "budget": {
            "population": cell["population"],
            "generations": cell["generations"],
            "planned_evaluations": cell["planned_evaluations"],
        },
        "status_counts": {"completed": cell["planned_evaluations"]},
        "completed_evaluations": cell["planned_evaluations"],
        "success_rate": 1.0,
        "objective_names": ["score"],
        "final_hypervolume": value,
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
        "extensions": {"yadof.optimization": [{"custom": cell["strategy"]}]},
        "issues": [],
    }


def _successful_command(
    command, *, cwd, command_root, label, timeout_seconds, event_sink=None
):
    del cwd, label, timeout_seconds, event_sink
    command_root.mkdir(parents=True)
    stdout = command_root / "stdout.log"
    stderr = command_root / "stderr.log"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    return CommandResult(
        tuple(str(item) for item in command), 0, 0.01, False, stdout, stderr
    )


def test_init_creates_code_first_workspace_without_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "benchmark workspace"
    created = api.init_workspace(root)

    assert created == {"format": WORKSPACE_FORMAT, "workspace": str(root.resolve())}
    assert json.loads((root / ".benchmark" / "workspace.json").read_text())[
        "format"
    ] == WORKSPACE_FORMAT
    workflow = root / "benchmark.py"
    assert workflow.is_file()
    source = workflow.read_text(encoding="utf-8")
    assert 'benchmark.configure(name="saw-algorithm-comparison"' in source
    assert 'benchmark.strategy(\n    #     "nsga3"' in source
    assert 'baselines=["ngspice/saw-ladder"]' in source
    assert 'strategies=["nsga3"]' in source
    assert "seeds=[1]" in source
    assert "population=12" in source
    assert "generations=20" in source
    assert 'benchmark.postprocess("summary", summarize_results)' in source
    for name in ("resources", "runs", "visualizations", "reports", "temp"):
        assert (root / name).is_dir()
        assert not any((root / name).iterdir())
    with pytest.raises(benchmark.BenchmarkError, match="not empty"):
        api.init_workspace(root)


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
    by_strategy = {
        row["strategy"]: row["reference_delta"]
        for row in results["comparisons"]
    }
    assert by_strategy == pytest.approx(
        {"alpha": 0.0, "beta": 0.15, "gamma": -0.1}
    )
    assert {row["comparison"] for row in results["comparisons"]} == {"main"}
    assert (run_root / "reports" / "summary.md").is_file()
    run_commands = [item for item in commands if item[2:4] == ("yadof", "run")]
    assert len(run_commands) == 3
    assert all("--fail-on-all-infinite" in item for item in run_commands)


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
    assert calls == ["check", "run"]
    assert (run_root / "visualizations" / "done.txt").read_text() == "done"
    attempts = resumed["postprocessors"]["summary"]["attempts"]
    assert [item["status"] for item in attempts] == ["failed", "succeeded"]


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
    assert 'yadof-benchmark = "yadof_benchmark.cli:main"' in (
        project / "pyproject.toml"
    ).read_text()


def test_packaged_resources_are_available_from_source_tree() -> None:
    manifests = api.discover_baselines()
    assert {"chrono/trebuchet", "ngspice/saw-ladder", "test-com/synthetic-antenna"} <= set(manifests)
    assert (api.user_doc_root() / "README.md").is_file()
