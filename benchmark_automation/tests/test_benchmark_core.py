from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

import pytest

import benchmark_core as core
from benchmark_runtime import execution, results as result_runtime
from benchmark_runtime.baselines import discover_baselines, load_baseline
from benchmark_runtime.contracts import (
    BASELINE_FORMAT,
    STUDY_FORMAT,
    CommandResult,
)
from benchmark_runtime.planning import load_study, plan_study
from benchmark_runtime.results import inspect_run
from benchmark_runtime.storage import (
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


def _strategy(root: Path, name: str) -> Path:
    path = root / "strategies" / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"def build_optimization():\n    return {name!r}\n",
        encoding="utf-8",
    )
    return path


def _study(
    root: Path,
    strategies: tuple[str, ...] = ("alpha", "beta", "gamma"),
) -> Path:
    paths = {name: _strategy(root, name) for name in strategies}
    lines = [
        f'format = "{STUDY_FORMAT}"',
        'name = "comparison"',
        'baselines = ["provider/task"]',
        "seeds = [7]",
        "population = 2",
        "generations = 3",
        'reference = "alpha"',
        "fail_fast = false",
        f'runs_dir = "{(root / "runs").as_posix()}"',
        f'python = "{Path(sys.executable).as_posix()}"',
    ]
    for name in strategies:
        lines.extend(
            [
                "",
                "[[strategies]]",
                f'id = "{name}"',
                f'name = "{name.title()}"',
                f'source = "{paths[name].as_posix()}"',
            ]
        )
    path = root / "study.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _plan(root: Path):
    baseline_root = root / "baselines"
    request = load_study(_study(root), default_runs_dir=root / "runs")
    return plan_study(request, discover_baselines(baseline_root))


def _cell_result(cell: dict, value: float) -> dict:
    return {
        "cell": cell["id"],
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


def test_recursive_baseline_discovery_and_clean_snapshot(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    discovered = discover_baselines(tmp_path / "baselines")

    assert list(discovered) == ["provider/task"]
    assert discovered["provider/task"].root == baseline

    spec = _plan(tmp_path)
    run_root = create_run(spec, run_id="clean-snapshot")
    snapshot = run_root / "inputs" / "baselines" / "provider-task" / "workspace"
    assert (snapshot / ".yadof" / "workspace.json").is_file()
    assert not (snapshot / ".yadof" / "logs").exists()
    assert not (snapshot / "jobs").exists()


def test_manifest_rejects_workspace_escape_and_duplicate_id(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    manifest_path = baseline / "baseline.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["workspace"] = "../../outside"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(core.BenchmarkError, match="escapes"):
        load_baseline(manifest_path)

    data["workspace"] = "workspace"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    _baseline(tmp_path / "second")
    with pytest.raises(core.BenchmarkError, match="duplicate baseline id"):
        discover_baselines(tmp_path)


def test_manifest_missing_contract_field_has_context(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    manifest_path = baseline / "baseline.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    del data["contract"]["objective_count"]
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(core.BenchmarkError, match="objective_count"):
        load_baseline(manifest_path)


def test_manifest_cannot_exclude_behavioral_workspace_input(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    manifest_path = baseline / "baseline.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["snapshot_excludes"] = ["submit"]
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(core.BenchmarkError, match="behavioral input"):
        load_baseline(manifest_path)


def test_study_accepts_unknown_complete_strategies_and_arbitrary_arms(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    spec = _plan(tmp_path)

    assert [item.id for item in spec.study.strategies] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert len(spec.cells) == 3
    assert {cell.planned_evaluations for cell in spec.cells} == {6}
    assert all(cell.strategy_source.is_file() for cell in spec.cells)


def test_strategy_requires_complete_build_function(tmp_path: Path) -> None:
    _baseline(tmp_path)
    study = _study(tmp_path, ("alpha",))
    source = _strategy(tmp_path, "alpha")
    source.write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(core.BenchmarkError, match="build_optimization"):
        load_study(
            study,
            default_runs_dir=tmp_path / "runs",
        )


def test_saved_spec_is_the_plan_and_inputs_are_immutable(tmp_path: Path) -> None:
    _baseline(tmp_path)
    spec = _plan(tmp_path)
    run_root = create_run(spec, run_id="same-plan")
    saved, _state = load_run(run_root)

    assert saved["digest"] == spec.digest
    assert saved["cells"] == [cell.to_dict() for cell in spec.cells]
    external = spec.cells[0].strategy_source
    snapshot = run_root / spec.cells[0].strategy_snapshot
    before = snapshot.read_text(encoding="utf-8")
    external.write_text("def build_optimization(): return 'changed'\n", encoding="utf-8")
    assert snapshot.read_text(encoding="utf-8") == before


def test_execution_checks_the_materialized_strategy_and_reports_three_arms(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    spec = _plan(tmp_path)
    run_root = create_run(spec, run_id="execute-three")
    checked: list[str] = []

    def fake_command(
        command,
        *,
        cwd,
        command_root,
        label,
        timeout_seconds,
        event_sink=None,
    ):
        del timeout_seconds, event_sink
        selected = (cwd / "submit" / "optimization.py").read_text(encoding="utf-8")
        if label == "check":
            checked.append(selected)
            assert "baseline" not in selected
        command_root.mkdir(parents=True)
        stdout = command_root / "stdout.log"
        stderr = command_root / "stderr.log"
        stdout.write_text("", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        return CommandResult(
            tuple(str(item) for item in command),
            0,
            0.01,
            False,
            stdout,
            stderr,
        )

    values = {"alpha": 0.2, "beta": 0.35, "gamma": 0.1}

    def fake_collect(_workspace: Path, cell: dict) -> dict:
        return _cell_result(cell, values[cell["strategy"]])

    state = execution.execute_existing_run(
        run_root,
        command_runner=fake_command,
        collector=fake_collect,
    )

    assert state["status"] == "completed"
    assert len(checked) == 3
    results = read_json(run_root / "results.json")
    assert len(results["rows"]) == 3
    by_strategy = {
        row["strategy"]: row["reference_delta"]
        for row in results["comparisons"]
    }
    assert by_strategy == pytest.approx(
        {"alpha": 0.0, "beta": 0.15, "gamma": -0.1}
    )
    assert results["cells"][next(iter(results["cells"]))]["extensions"][
        "yadof.optimization"
    ]
    assert "Evaluations" in (run_root / "report.md").read_text(encoding="utf-8")


def test_three_arm_report_is_complete_without_reference(tmp_path: Path) -> None:
    _baseline(tmp_path)
    study = _study(tmp_path)
    study.write_text(
        study.read_text(encoding="utf-8").replace('reference = "alpha"\n', ""),
        encoding="utf-8",
    )
    request = load_study(study, default_runs_dir=tmp_path / "runs")
    spec = plan_study(request, discover_baselines(tmp_path / "baselines"))
    run_root = create_run(spec, run_id="no-reference")
    execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=lambda _workspace, cell: _cell_result(cell, 0.2),
    )

    comparisons = read_json(run_root / "results.json")["comparisons"]
    assert len(comparisons) == 3
    assert all(row["reference"] is None for row in comparisons)
    assert all(row["reference_delta"] is None for row in comparisons)


def test_failed_cell_retries_and_interrupted_attempt_is_sealed(tmp_path: Path) -> None:
    _baseline(tmp_path)
    request = load_study(
        _study(tmp_path, ("alpha",)), default_runs_dir=tmp_path / "runs"
    )
    spec = plan_study(request, discover_baselines(tmp_path / "baselines"))
    run_root = create_run(spec, run_id="recover")
    saved, state = load_run(run_root)
    cell = saved["cells"][0]
    _attempt_root, _workspace, attempt = prepare_attempt(run_root, cell, state)
    attempt["status"] = "running"
    state["cells"][cell["id"]]["status"] = "running"
    save_state(run_root, state)

    resumed = execution.execute_existing_run(
        run_root,
        command_runner=_successful_command,
        collector=lambda _workspace, item: _cell_result(item, 0.2),
    )

    attempts = resumed["cells"][cell["id"]]["attempts"]
    assert resumed["status"] == "completed"
    assert [item["status"] for item in attempts] == ["interrupted", "collected"]


def test_failed_cell_gets_a_new_attempt_on_resume(tmp_path: Path) -> None:
    _baseline(tmp_path)
    request = load_study(
        _study(tmp_path, ("alpha",)), default_runs_dir=tmp_path / "runs"
    )
    spec = plan_study(request, discover_baselines(tmp_path / "baselines"))
    run_root = create_run(spec, run_id="retry-failure")
    fail_once = [True]

    def command(*args, **kwargs):
        result = _successful_command(*args, **kwargs)
        if kwargs["label"] == "check" and fail_once.pop():
            return CommandResult(
                result.command, 9, result.duration_seconds, False,
                result.stdout, result.stderr,
            )
        return result

    failed = execution.execute_existing_run(
        run_root, command_runner=command,
        collector=lambda _workspace, item: _cell_result(item, 0.2),
    )
    resumed = execution.execute_existing_run(
        run_root, command_runner=_successful_command,
        collector=lambda _workspace, item: _cell_result(item, 0.2),
    )

    attempts = next(iter(resumed["cells"].values()))["attempts"]
    assert failed["status"] == "failed"
    assert resumed["status"] == "completed"
    assert [item["status"] for item in attempts] == ["failed", "collected"]


def test_truncated_state_fails_closed_with_path_context(tmp_path: Path) -> None:
    _baseline(tmp_path)
    run_root = create_run(_plan(tmp_path), run_id="truncated-state")
    (run_root / "state.json").write_text("{", encoding="utf-8")

    with pytest.raises(core.BenchmarkError, match=r"state\.json"):
        result_runtime.inspect_run(run_root)


def test_resume_uses_run_driver_and_inspect_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _baseline(tmp_path)
    spec = _plan(tmp_path)
    run_root = create_run(spec, run_id="snapshot-resume")
    saved, state = load_run(run_root)
    for cell_id, cell in state["cells"].items():
        cell["status"] = "collected"
        attempt_root = run_root / "cells" / cell_id / "attempts" / "0001"
        attempt_root.mkdir(parents=True)
        workspace = attempt_root / "workspace"
        workspace.mkdir()
        result_path = attempt_root / "result.json"
        cell_plan = next(item for item in saved["cells"] if item["id"] == cell_id)
        result_path.write_text(
            json.dumps(_cell_result(cell_plan, 0.2)) + "\n",
            encoding="utf-8",
        )
        cell["attempts"] = [
            {
                "number": 1,
                "path": attempt_root.relative_to(run_root).as_posix(),
                "workspace": workspace.relative_to(run_root).as_posix(),
                "status": "collected",
                "result": result_path.relative_to(run_root).as_posix(),
            }
        ]
    state["status"] = "completed"
    from benchmark_runtime.storage import atomic_write_json

    atomic_write_json(run_root / "state.json", state)
    state_path = run_root / "state.json"
    before = state_path.stat().st_mtime_ns
    monkeypatch.setattr(
        execution,
        "execute_existing_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("current execution module was used")
        ),
    )

    result = core.resume_run(run_root)
    inspected = inspect_run(run_root)

    assert result["status"] == "completed"
    assert inspected["status"] == "completed"
    assert state_path.stat().st_mtime_ns == before


def test_missing_run_driver_fails_closed(tmp_path: Path) -> None:
    _baseline(tmp_path)
    run_root = create_run(_plan(tmp_path), run_id="missing-driver")
    (run_root / "driver" / "benchmark_runtime" / "__init__.py").unlink()

    with pytest.raises(core.BenchmarkError, match="driver snapshot is incomplete"):
        core.resume_run(run_root)


def test_core_exports_only_explicit_public_surface() -> None:
    assert core.__all__ == [
        "BaselineManifest",
        "BenchmarkError",
        "RunSpec",
        "StudyRequest",
        "discover_baselines",
        "inspect_run",
        "load_study",
        "plan_study",
        "resume_run",
        "run_study",
    ]
    assert not any(name.startswith("_") for name in core.__all__)


def test_cli_has_only_the_current_command_surface(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / "benchmark.py"), "--help"]
    result = subprocess.run(command, cwd=root.parent, text=True, capture_output=True)

    assert result.returncode == 0
    assert "{baselines,plan,run,resume,inspect}" in result.stdout
    for removed in ("preflight", "collect", "report", "--suite"):
        assert removed not in result.stdout


def test_product_tree_and_runtime_complexity_guards() -> None:
    root = Path(__file__).resolve().parents[1]
    ignored = {"__pycache__", ".pytest_cache"}
    assert {item.name for item in root.iterdir()} - ignored == {
        "benchmark.py", "benchmark_core.py", "baselines", "benchmark_runtime",
        "dev_doc", "tests",
    }
    runtime = sorted((root / "benchmark_runtime").glob("*.py"))
    sources = [root / "benchmark.py", root / "benchmark_core.py", *runtime]
    assert sum(len(path.read_text(encoding="utf-8").splitlines()) for path in sources) <= 2000
    assert all(len(path.read_text(encoding="utf-8").splitlines()) <= 450 for path in runtime)
    forbidden_algorithms = re.compile(
        r"qnehvi|gpsaf|pca|svd|hierarchical|conditional|pymoo", re.IGNORECASE
    )
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert not forbidden_algorithms.search(text), path
        tree = ast.parse(text)
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        assert all(node.end_lineno - node.lineno + 1 <= 80 for node in functions)
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.level
            and any(alias.name.startswith("_") for alias in node.names)
            for node in ast.walk(tree)
        )
        assert not any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(tree)
        )


def test_current_surface_has_no_incidental_generation_markers() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "benchmark.py", root / "benchmark_core.py"]
    paths += list((root / "benchmark_runtime").glob("*.py"))
    paths += list((root / "dev_doc").glob("*.md"))
    marker = re.compile(r"(?<![A-Za-z0-9])v\d+", re.IGNORECASE)
    assert not [path for path in paths if marker.search(path.read_text(encoding="utf-8"))]
