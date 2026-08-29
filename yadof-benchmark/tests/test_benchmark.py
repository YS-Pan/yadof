from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

import yadof_benchmark as benchmark
from yadof_benchmark import api, cli
from yadof_benchmark.benchmark_runtime import execution
from yadof_benchmark.benchmark_runtime.baselines import load_baseline
from yadof_benchmark.benchmark_runtime.contracts import (
    BASELINE_FORMAT,
    DEFAULT_GENERATIONS,
    DEFAULT_POPULATION,
    DEFAULT_SEED,
    SLOW_SURROGATE_GENERATIONS,
    WORKSPACE_FORMAT,
    CommandResult,
)
from yadof_benchmark.benchmark_runtime.launch import launch_detached
from yadof_benchmark.benchmark_runtime.results import inspect_workspace
from yadof_benchmark.benchmark_runtime.storage import (
    initialize_workspace,
    load_execution,
    read_json,
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
                "execution": {
                    "mode": "fast",
                    "timeout_seconds": 30,
                    "simulation_concurrency": {
                        "max_workers": 4,
                        "resource_autodetect": True,
                    },
                },
                "contract": {
                    "objective_count": 1,
                    "rawdata_shapes": {"value": [1]},
                },
                "estimates": {
                    "evaluation_seconds": 0.01,
                    "record_mib": 0.001,
                },
                "materialize_excludes": [],
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
    requested: Path,
    *,
    strategies: tuple[str, ...] = ("alpha", "beta"),
    baselines: tuple[str, ...] = ("provider/task",),
    evidence: str = "structural",
    seeds: tuple[int, ...] | None = (7,),
    population: int | None = 2,
    generations: int | None = 3,
    slow: tuple[str, ...] = (),
    postprocess_source: str = "",
    fail_fast: bool = False,
    cell_concurrency: int = 1,
) -> Path:
    root = Path(api.init_workspace(requested)["workspace"])
    for name in strategies:
        _strategy(root, name)
    declarations = "\n".join(
        (
            f'    benchmark.strategy("{name}", '
            f'"resources/strategies/{name}/optimization.py", '
            f"slow_surrogate={name in slow!r})"
        )
        for name in strategies
    )
    compare_arguments = [
        f"baselines={list(baselines)!r}",
        f"strategies={list(strategies)!r}",
        'reference="alpha"',
    ]
    if seeds is not None:
        compare_arguments.append(f"seeds={list(seeds)!r}")
    if population is not None:
        compare_arguments.append(f"population={population}")
    if generations is not None:
        compare_arguments.append(f"generations={generations}")
    postprocess_registration = (
        '    benchmark.postprocess("summary", make_summary)\n'
        if postprocess_source
        else ""
    )
    (root / "benchmark.py").write_text(
        "from yadof_benchmark import Benchmark, PostprocessContext\n\n"
        + postprocess_source
        + "\ndef build_benchmark(benchmark: Benchmark) -> None:\n"
        + f"    benchmark.configure(name='comparison', evidence={evidence!r}, "
        + f"fail_fast={fail_fast!r}, cell_concurrency={cell_concurrency})\n"
        + declarations
        + "\n    benchmark.compare('main', "
        + ", ".join(compare_arguments)
        + ")\n"
        + postprocess_registration,
        encoding="utf-8",
    )
    return root


def _plan(root: Path, workspace: Path):
    return api.plan_workspace(workspace, baselines_root=root / "baselines")


def _cell_result(
    cell: dict,
    value: float,
    *,
    failed: int = 0,
    nonfinite: int = 0,
    issues: list[str] | None = None,
) -> dict:
    planned = int(cell["planned_evaluations"])
    completed = max(0, planned - failed)
    finite = max(0, completed - nonfinite)
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
            "completed": completed,
            "finite": finite,
        },
        "status_counts": {
            "completed": completed,
            **({"error": failed} if failed else {}),
        },
        "attempted_evaluations": planned,
        "completed_evaluations": completed,
        "finite_evaluations": finite,
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
                    "completed_evaluations": completed,
                    "finite_evaluations": finite,
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
                "replication_scope": cell["replication_scope"],
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
        "issues": list(issues or []),
    }


def _successful_command(
    command,
    *,
    cwd,
    command_root,
    label,
    timeout_seconds,
    event_sink=None,
    **_kwargs,
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


def _execute(
    root: Path,
    workspace: Path,
    *,
    collector=None,
):
    plan = _plan(root, workspace)
    initialize_workspace(plan)
    selected_collector = collector or (
        lambda _workspace, cell: _cell_result(
            cell, {"alpha": 0.2, "beta": 0.35}.get(cell["strategy"], 0.1)
        )
    )
    return execution.execute_workspace(
        workspace,
        command_runner=_successful_command,
        collector=selected_collector,
    )


def test_init_creates_single_execution_workspace(tmp_path: Path) -> None:
    created = api.init_workspace(tmp_path / "benchmark workspace")
    root = Path(created["workspace"])

    assert created == {"format": WORKSPACE_FORMAT, "workspace": str(root.resolve())}
    assert re.match(r"^\d{8}_\d{6}-benchmark-workspace$", root.name)
    assert (root / "benchmark.py").is_file()
    assert {
        "resources",
        "cells",
        "postprocessing",
        "visualizations",
        "reports",
        "temp",
    } <= {item.name for item in root.iterdir()}
    assert not (root / "runs").exists()
    source = (root / "benchmark.py").read_text(encoding="utf-8")
    assert "default to one seed" in source
    assert "slow_surrogate=True" in source
    assert "default is 15 generations" in source


def test_default_budget_depends_on_slow_surrogate_and_defaults_to_one_seed(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    standard = _workspace(
        tmp_path / "standard",
        strategies=("alpha",),
        seeds=None,
        population=None,
        generations=None,
    )
    standard_plan = _plan(tmp_path, standard)
    comparison = standard_plan.workflow.comparisons[0]
    assert comparison.seeds == (DEFAULT_SEED,)
    assert comparison.population == DEFAULT_POPULATION
    assert comparison.generations == DEFAULT_GENERATIONS
    assert comparison.contains_slow_surrogate is False

    slow = _workspace(
        tmp_path / "slow",
        strategies=("alpha", "beta"),
        slow=("beta",),
        seeds=None,
        population=None,
        generations=None,
    )
    slow_plan = _plan(tmp_path, slow)
    slow_comparison = slow_plan.workflow.comparisons[0]
    assert slow_comparison.seeds == (DEFAULT_SEED,)
    assert slow_comparison.population == DEFAULT_POPULATION
    assert slow_comparison.generations == SLOW_SURROGATE_GENERATIONS
    assert slow_comparison.contains_slow_surrogate is True
    assert {cell.generations for cell in slow_plan.cells} == {
        SLOW_SURROGATE_GENERATIONS
    }


def test_explicit_budget_and_seed_list_are_respected_without_scale_floor(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(
        tmp_path / "explicit",
        strategies=("alpha",),
        evidence="performance",
        seeds=(1, 2, 3),
        population=3,
        generations=2,
        slow=("alpha",),
    )
    plan = _plan(tmp_path, workspace)
    comparison = plan.workflow.comparisons[0]

    assert comparison.seeds == (1, 2, 3)
    assert comparison.population == 3
    assert comparison.generations == 2
    assert {cell.replication_scope for cell in plan.cells} == {"multi-seed"}


def test_baseline_contract_uses_materialization_language(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    manifest = load_baseline(baseline / "baseline.json")
    assert manifest.materialize_excludes == ()


def test_plan_uses_short_cell_ids_and_keeps_semantics_in_spec(tmp_path: Path) -> None:
    _baseline(tmp_path, "provider/a-very-long-semantic-baseline-name")
    workspace = _workspace(
        tmp_path / "short",
        baselines=("provider/a-very-long-semantic-baseline-name",),
        strategies=("alpha", "beta"),
        seeds=(123456789,),
    )
    plan = _plan(tmp_path, workspace)
    expanded = plan.to_dict()

    assert [cell.id for cell in plan.cells] == ["c0001", "c0002"]
    assert {
        (cell["id"], cell["baseline"], cell["strategy"], cell["seed"])
        for cell in expanded["cells"]
    } == {
        (
            "c0001",
            "provider/a-very-long-semantic-baseline-name",
            "alpha",
            123456789,
        ),
        (
            "c0002",
            "provider/a-very-long-semantic-baseline-name",
            "beta",
            123456789,
        ),
    }
    assert all(len(cell["id"]) == 5 for cell in expanded["cells"])
    assert not any("snapshot" in key for cell in expanded["cells"] for key in cell)


def test_workspace_initialization_records_runtime_once_without_snapshots(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "direct", strategies=("alpha",))
    root = initialize_workspace(_plan(tmp_path, workspace))

    runtime = read_json(root / "runtime.json")
    spec, state = load_execution(root)
    assert runtime["format"] == "yadof.benchmark.runtime"
    assert runtime["packages"]["yadof-benchmark"] == benchmark.__version__
    assert runtime["packages"]["yadof"]
    assert runtime["python"]["executable"]
    assert runtime["host"]["user"]
    assert spec["workflow"]["workspace"] == str(root)
    assert state["status"] == "planned"
    for forbidden in ("runs", "driver", "inputs", "workspaces", "timing_history.json"):
        assert not (root / forbidden).exists()


def test_fake_pipeline_writes_direct_short_paths_and_reports(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "pipeline")
    state = _execute(tmp_path, workspace)

    assert state["status"] == "completed"
    assert sorted(path.name for path in (workspace / "cells").iterdir()) == [
        "c0001",
        "c0002",
    ]
    for cell_id, cell_state in state["cells"].items():
        cell_root = workspace / "cells" / cell_id
        assert (cell_root / "workspace").is_dir()
        assert (cell_root / "commands" / "01-check").is_dir()
        assert (cell_root / "commands" / "02-run").is_dir()
        assert (cell_root / "result.json").is_file()
        assert "attempts" not in cell_state
        assert "/attempts/" not in json.dumps(cell_state)
    assert sorted(
        path.name for path in (workspace / "visualizations" / "cost").glob("*.png")
    ) == ["c0001.png", "c0002.png"]
    assert sorted(
        path.name
        for path in (workspace / "visualizations" / "domain").glob("*.png")
    ) == ["c0001--domain.png", "c0002--domain.png"]
    assert all(
        len(path.name) < 80
        for path in (workspace / "visualizations").rglob("*")
        if path.is_file()
    )
    assert max(
        len(path.relative_to(workspace).as_posix())
        for path in workspace.rglob("*")
    ) < 120
    results = read_json(workspace / "results.json")
    assert results["workspace"] == str(workspace.resolve())
    assert "run_id" not in results
    assert (workspace / "reports" / "summary.md").is_file()
    inspected = inspect_workspace(workspace)
    assert inspected["workspace"] == str(workspace.resolve())
    assert inspected["status"] == "completed"
    assert "run_id" not in inspected
    assert "resume" not in inspected["next_commands"]


def test_individual_simulation_errors_do_not_invalidate_cell(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "errors", strategies=("alpha",))

    def collector(_workspace: Path, cell: dict) -> dict:
        return _cell_result(
            cell,
            0.25,
            failed=1,
            issues=["one simulation recorded status=error"],
        )

    state = _execute(tmp_path, workspace, collector=collector)
    report = read_json(workspace / "reports" / "descriptive-results.json")
    cell = report["cells"][0]

    assert state["status"] == "completed"
    assert cell["valid"] is True
    assert cell["attempt_count_complete"] is True
    assert cell["failed_evaluations"] == 1
    assert cell["simulation_errors_tolerated"] is True
    assert cell["issues"] == ["one simulation recorded status=error"]
    assert inspect_workspace(workspace)["validity"]["simulation_errors_tolerated"] == 1


def test_missing_attempted_evaluations_still_invalidates_cell(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "incomplete", strategies=("alpha",))

    def collector(_workspace: Path, cell: dict) -> dict:
        result = _cell_result(cell, 0.25)
        result["counts"]["attempted"] -= 1
        result["attempted_evaluations"] -= 1
        return result

    state = _execute(tmp_path, workspace, collector=collector)
    report = read_json(workspace / "reports" / "descriptive-results.json")
    cell = report["cells"][0]

    assert state["status"] == "failed"
    assert cell["valid"] is False
    assert cell["attempt_count_complete"] is False
    assert "attempted evaluation count differs from plan" in cell["validity_issues"]


def test_postprocessor_has_one_direct_output_directory(tmp_path: Path) -> None:
    _baseline(tmp_path)
    postprocess = (
        "def make_summary(context: PostprocessContext):\n"
        "    (context.output / 'note.txt').write_text('ok', encoding='utf-8')\n"
        "    return {'status': 'ok'}\n"
    )
    workspace = _workspace(
        tmp_path / "postprocess",
        strategies=("alpha",),
        postprocess_source=postprocess,
    )
    state = _execute(tmp_path, workspace)

    output = workspace / "postprocessing" / "summary"
    assert state["status"] == "completed"
    assert (output / "note.txt").read_text(encoding="utf-8") == "ok"
    assert read_json(output / "result.json")["return"] == {"status": "ok"}
    assert not (output / "attempts").exists()
    assert state["postprocessors"]["summary"]["result"] == (
        "postprocessing/summary/result.json"
    )


def test_inspect_is_read_only(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "inspect", strategies=("alpha",))
    _execute(tmp_path, workspace)
    before = {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }

    first = api.inspect_workspace(workspace)
    second = api.inspect_workspace(workspace)
    after = {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }

    assert first["status"] == second["status"] == "completed"
    assert first["artifacts"] == second["artifacts"]
    assert before == after


@pytest.mark.skipif(os.name != "nt", reason="Windows detached-console contract")
def test_detached_launch_runs_workspace_directly_and_defaults_visible(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    workspace = api.init_workspace(tmp_path / "detached")["workspace"]

    class Process:
        pid = 4242

    def process_factory(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    receipt = launch_detached(
        workspace,
        evidence="structural",
        process_factory=process_factory,
    )

    command = [str(item) for item in captured["command"]]
    assert receipt["pid"] == 4242
    assert receipt["visible"] is True
    assert receipt["workspace"] == str(Path(workspace).resolve())
    assert "inspect --workspace" in receipt["inspect"]
    assert "resume" not in command
    assert command[3:6] == ["run", "--workspace", str(Path(workspace).resolve())]
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["creationflags"] & subprocess.CREATE_NEW_CONSOLE
    assert kwargs["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert "stdout" not in kwargs and "stderr" not in kwargs


def test_cli_surface_has_no_resume_or_run_id() -> None:
    parser = cli._parser()
    subparsers = next(
        action for action in parser._actions if action.dest == "command"
    )
    assert set(subparsers.choices) == {
        "init",
        "baselines",
        "check",
        "plan",
        "run",
        "inspect",
        "docs",
    }
    run_options = {
        option
        for action in subparsers.choices["run"]._actions
        for option in action.option_strings
    }
    inspect_options = {
        option
        for action in subparsers.choices["inspect"]._actions
        for option in action.option_strings
    }
    assert "--run-id" not in run_options
    assert inspect_options == {"-h", "--help", "--workspace"}
    assert "resume_run" not in benchmark.__all__
    assert "inspect_run" not in benchmark.__all__
    assert "inspect_workspace" in benchmark.__all__


def test_hidden_console_requires_explicit_detach(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        ["run", "--workspace", str(tmp_path), "--hidden"]
    )
    assert exit_code == 2
    assert "--hidden is valid only with explicit --detach" in capsys.readouterr().err


def test_terminal_logs_workspace_lifecycle(tmp_path: Path) -> None:
    display = BenchmarkTerminal(tmp_path, stream=open(os.devnull, "w"))
    try:
        display.start()
        display.handle(
            {
                "event": "workspace-started",
                "workspace": str(tmp_path),
                "total_cells": 1,
                "finished_cells": 0,
                "completed_cells": 0,
                "failed_cells": 0,
            }
        )
        display.handle(
            {
                "event": "workspace-finished",
                "workspace": str(tmp_path),
                "status": "completed",
                "total_cells": 1,
                "finished_cells": 1,
                "completed_cells": 1,
                "failed_cells": 0,
            }
        )
        display.finish(result={"status": "completed", "workspace": str(tmp_path)})
    finally:
        display.stream.close()

    log = (tmp_path / "benchmark.log").read_text(encoding="utf-8")
    assert "workspace=" in log
    assert "finished; status=completed" in log


def test_distribution_version_is_breaking_release() -> None:
    assert benchmark.__version__ == "0.2.0"
