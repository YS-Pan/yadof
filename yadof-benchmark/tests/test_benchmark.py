from __future__ import annotations

import json
import io
import hashlib
import os
import re
import runpy
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import yadof_benchmark as benchmark
from yadof_benchmark import api, cli
from yadof_benchmark.benchmark_runtime import concurrency, execution
from yadof_benchmark.benchmark_runtime.baselines import load_baseline
from yadof_benchmark.benchmark_runtime.contracts import (
    BASELINE_FORMAT,
    BenchmarkError,
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


def _trebuchet_postprocess_path() -> Path:
    installed = (
        Path(benchmark.__file__).resolve().parent
        / "_resources"
        / "baselines"
        / "chrono"
        / "trebuchet"
        / "workspace"
        / "postprocess.py"
    )
    if installed.is_file():
        return installed
    return (
        Path(__file__).resolve().parents[1]
        / "baselines"
        / "chrono"
        / "trebuchet"
        / "workspace"
        / "postprocess.py"
    )


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
        "YADOF_OPTIMIZATION_PROGRAM = {\n"
        "    'api': 'yadof.optimize.program/v1',\n"
        "    'entry': 'optimization_program',\n"
        "    'helpers': (),\n"
        "    'identity': {'program': 'benchmark-baseline-fixture', 'version': 1},\n"
        "    'capabilities': ('real-evaluation',),\n"
        "}\n"
        "def optimization_program(context):\n"
        "    pass\n",
        encoding="utf-8",
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
                        "physical_core_multiplier": 2.0,
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
        "YADOF_OPTIMIZATION_PROGRAM = {\n"
        "    'api': 'yadof.optimize.program/v1',\n"
        "    'entry': 'optimization_program',\n"
        "    'helpers': (),\n"
        f"    'identity': {{'program': {name!r}, 'version': 1}},\n"
        "    'capabilities': ('real-evaluation',),\n"
        "}\n"
        "def optimization_program(context):\n"
        "    pass\n",
        encoding="utf-8",
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

    assert created["format"] == WORKSPACE_FORMAT
    assert created["workspace"] == str(root.resolve())
    assert created["preset"]["id"] == "portable"
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
    assert "test-com/synthetic-antenna" in source
    assert "population=12" in source
    assert "generations=2" in source
    assert (root / ".benchmark" / "preset.json").is_file()


def test_complete_preset_and_mechanical_smoke_profile(tmp_path: Path) -> None:
    root = Path(api.init_workspace(tmp_path / "complete", preset="complete")["workspace"])
    complete = api.plan_workspace(root)
    smoke = api.plan_workspace(root, budget_profile="smoke")

    assert len(complete.cells) == 18
    assert {cell.population for cell in complete.cells} == {200}
    assert {cell.generations for cell in complete.cells} == {25}
    assert {cell.execution["timeout_seconds"] for cell in complete.cells} == {7200}
    assert {cell.seed for cell in complete.cells} == {101, 102, 103}
    assert {cell.baseline_id for cell in complete.cells} == {
        "chrono/trebuchet",
        "ngspice/saw-ladder",
        "test-com/synthetic-antenna",
    }
    assert {cell.strategy_id for cell in complete.cells} == {
        "real-only-nsga3",
        "gpsaf-pca-svd-nsga3",
    }
    assert len(smoke.cells) == 18
    assert {cell.population for cell in smoke.cells} == {200}
    assert {cell.generations for cell in smoke.cells} == {1}
    assert [
        (
            cell.id,
            cell.baseline_id,
            cell.strategy_id,
            cell.seed,
            cell.baseline_digest,
            cell.strategy_digest,
            cell.execution,
        )
        for cell in smoke.cells
    ] == [
        (
            cell.id,
            cell.baseline_id,
            cell.strategy_id,
            cell.seed,
            cell.baseline_digest,
            cell.strategy_digest,
            cell.execution,
        )
        for cell in complete.cells
    ]


def test_blank_is_explicit_and_presets_are_discoverable(tmp_path: Path) -> None:
    presets = api.discover_presets()
    assert list(presets) == ["portable", "complete", "perfect", "blank"]
    assert presets["portable"]["default"] is True
    assert presets["complete"]["long_running"] is True
    assert presets["complete"]["cells"] == 18

    root = Path(api.init_workspace(tmp_path / "blank", preset="blank")["workspace"])
    assert api.load_workspace_preset(root)["id"] == "blank"
    assert "benchmark.configure" in (root / "benchmark.py").read_text(encoding="utf-8")


def test_preset_provenance_uses_relative_sources_and_verified_digests(
    tmp_path: Path,
) -> None:
    root = Path(api.init_workspace(tmp_path / "portable-provenance")["workspace"])
    provenance = api.load_workspace_preset(root)
    assert provenance["id"] == "portable"
    assert provenance["source"] == "packaged"
    assert provenance["files"]
    for item in provenance["files"]:
        assert not Path(item["source"]).is_absolute()
        assert "\\" not in item["source"]
        output = root / Path(*item["workspace_path"].split("/"))
        assert output.is_file()
        assert hashlib.sha256(output.read_bytes()).hexdigest().upper() == item["sha256"]


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


def test_packaged_baselines_use_tuned_physical_core_multipliers() -> None:
    manifests = api.discover_baselines()

    assert {
        baseline_id: manifest.execution["simulation_concurrency"][
            "physical_core_multiplier"
        ]
        for baseline_id, manifest in manifests.items()
    } == {
        "chrono/trebuchet": 2.0,
        "ngspice/saw-ladder": 2.0,
        "test-com/synthetic-antenna": 1.0,
    }


def test_legacy_fixed_simulation_worker_fields_are_rejected(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    manifest_path = baseline / "baseline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["execution"]["simulation_concurrency"] = {
        "max_workers": 4,
        "resource_autodetect": True,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BenchmarkError, match="unknown.*max_workers"):
        load_baseline(manifest_path)


@pytest.mark.parametrize("value", [0, -0.5, True, "2", float("nan"), float("inf")])
def test_physical_core_multiplier_must_be_finite_and_positive(
    tmp_path: Path,
    value: object,
) -> None:
    baseline = _baseline(tmp_path)
    manifest_path = baseline / "baseline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["execution"]["simulation_concurrency"][
        "physical_core_multiplier"
    ] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BenchmarkError, match="finite positive number"):
        load_baseline(manifest_path)


def test_simulation_concurrency_resolves_from_physical_cores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        concurrency.psutil,
        "cpu_count",
        lambda *, logical: 12 if logical is False else 24,
    )

    detected = concurrency.resolve_simulation_concurrency(
        {
            "simulation_concurrency": {
                "physical_core_multiplier": 0.875,
            }
        }
    )

    assert detected == {
        "physical_core_detection": "psutil.cpu_count(logical=False)",
        "physical_cores": 12,
        "physical_core_multiplier": 0.875,
        "resolved_max_workers": 10,
        "rounding": "floor",
    }


def test_trebuchet_postprocess_selects_average_and_range_minima() -> None:
    source = _trebuchet_postprocess_path()
    namespace = runpy.run_path(str(source), run_name="trebuchet_postprocess_selection")
    selector = namespace["_select_best"]
    selector_globals = selector.__globals__
    workspace = source.parent
    jobs = ("average-best", "range-best", "error-sentinel", "nonfinite")
    selector_globals["get_raw_variables"] = lambda *_args, **_kwargs: {
        name: (float(index),) for index, name in enumerate(jobs)
    }
    selector_globals["list_records"] = lambda *_args, **_kwargs: [
        {
            "job_name": name,
            "status": "completed",
            "generation_index": 0,
            "population_index": index,
        }
        for index, name in enumerate(jobs)
    ]
    selector_globals["get_historical_results"] = lambda *_args, **_kwargs: [
        ("average-best", (0.1,), (0.20, 0.10, 0.10, 0.10)),
        ("range-best", (0.2,), (0.05, 0.70, 0.70, 0.70)),
        ("error-sentinel", (0.3,), (1.0, 1.0, 1.0, 1.0)),
        ("nonfinite", (0.4,), (0.01, float("nan"), 0.10, 0.10)),
    ]

    selections = selector(workspace)

    assert selections["average_cost"]["source_job_name"] == "average-best"
    assert selections["range_cost"]["source_job_name"] == "range-best"
    assert selections["range_cost"]["range_cost"] == pytest.approx(0.05)
    assert selections["range_cost"]["average_cost"] == pytest.approx(0.5375)


def test_trebuchet_postprocess_exports_both_visualization_sets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _trebuchet_postprocess_path()
    namespace = runpy.run_path(str(source), run_name="trebuchet_postprocess_exports")
    main = namespace["main"]
    main_globals = main.__globals__
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "visualizations"
    workspace.mkdir()
    selections = {
        "average_cost": {
            "source_job_name": "average-best",
            "average_cost": 0.125,
            "range_cost": 0.20,
        },
        "range_cost": {
            "source_job_name": "range-best",
            "average_cost": 0.5375,
            "range_cost": 0.05,
        },
    }
    staged_jobs: list[str] = []

    def fake_stage_snapshot(_workspace, scratch_root, selection):
        staged_jobs.append(str(selection["source_job_name"]))
        snapshot = scratch_root / "selected_job"
        snapshot.mkdir()
        (snapshot / "selection.txt").write_text(
            str(selection["source_job_name"]), encoding="utf-8"
        )
        return snapshot

    def fake_renderer(command, *, cwd, check):
        assert Path(cwd) == workspace.resolve()
        assert check is True
        selected = [str(item) for item in command]
        video = Path(selected[selected.index("--output") + 1])
        poster = Path(selected[selected.index("--poster") + 1])
        work_dir = Path(selected[selected.index("--work-dir") + 1])
        video.parent.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"video")
        poster.write_bytes(b"poster")
        (work_dir / "continuation_diagnostics.json").write_text(
            "{}\n", encoding="utf-8"
        )
        (work_dir / "trebuchet_animation_trajectory.npz").write_bytes(b"trajectory")
        return subprocess.CompletedProcess(selected, 0)

    monkeypatch.setitem(
        main_globals,
        "_parse_args",
        lambda: SimpleNamespace(
            workspace=workspace,
            output_dir=output_dir,
            output_prefix="cell__",
            fps=30,
            dpi=120,
            continuation_timeout=180.0,
        ),
    )
    monkeypatch.setitem(main_globals, "_select_best", lambda _workspace: selections)
    monkeypatch.setitem(main_globals, "_stage_snapshot", fake_stage_snapshot)
    monkeypatch.setattr(main_globals["subprocess"], "run", fake_renderer)

    assert main() == 0
    assert staged_jobs == ["average-best", "range-best"]
    expected = {
        "cell__trebuchet_best.mp4",
        "cell__trebuchet_best_poster.png",
        "cell__trebuchet_selected_job.zip",
        "cell__trebuchet_continuation_diagnostics.json",
        "cell__trebuchet_animation_trajectory.npz",
        "cell__trebuchet_range_best.mp4",
        "cell__trebuchet_range_best_poster.png",
        "cell__trebuchet_range_selected_job.zip",
        "cell__trebuchet_range_continuation_diagnostics.json",
        "cell__trebuchet_range_animation_trajectory.npz",
        "cell__postprocess_manifest.json",
    }
    assert {path.name for path in output_dir.iterdir()} == expected
    manifest = json.loads(
        (output_dir / "cell__postprocess_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 2
    assert manifest["selection"]["source_job_name"] == "average-best"
    assert manifest["range_selection"]["source_job_name"] == "range-best"
    assert Path(manifest["range_video"]).name == "cell__trebuchet_range_best.mp4"


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
    assert all("display_label" in cell for cell in expanded["cells"])
    assert all("provider/a-very-long-semantic-baseline-name" in cell["display_label"] for cell in expanded["cells"])
    assert all("seed=123456789" in cell["display_label"] for cell in expanded["cells"])
    assert not any("snapshot" in key for cell in expanded["cells"] for key in cell)


def test_display_labels_handle_special_names_without_becoming_paths(
    tmp_path: Path,
) -> None:
    baseline = _baseline(tmp_path, "provider/task-with-a-very-long-safe-id")
    manifest_path = baseline / "baseline.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["name"] = "Task | 特殊 名称"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    workspace = _workspace(
        tmp_path / "labels",
        baselines=("provider/task-with-a-very-long-safe-id",),
        strategies=("alpha",),
    )
    workflow = workspace / "benchmark.py"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            '"resources/strategies/alpha/optimization.py", slow_surrogate=False)',
            '"resources/strategies/alpha/optimization.py", name="算法 | alpha", slow_surrogate=False)',
        ),
        encoding="utf-8",
    )
    plan = _plan(tmp_path, workspace)

    assert "Task | 特殊 名称" in plan.cells[0].display_label
    assert "算法 | alpha" in plan.cells[0].display_label
    initialized = initialize_workspace(plan)
    assert [path.name for path in (initialized / "cells").iterdir()] == []
    assert plan.cells[0].id == "c0001"


def test_duplicate_semantic_cell_identity_is_rejected(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "duplicate", strategies=("alpha",))
    with (workspace / "benchmark.py").open("a", encoding="utf-8") as stream:
        stream.write(
            "    benchmark.compare('duplicate', baselines=['provider/task'], "
            "strategies=['alpha'], reference='alpha', seeds=[7], "
            "population=2, generations=3)\n"
        )
    with pytest.raises(BenchmarkError, match="duplicate benchmark cell identity"):
        _plan(tmp_path, workspace)


def test_program_protocol_v1_is_accepted_but_lookalike_release_marker_is_not(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "protocol", strategies=("alpha",))
    assert _plan(tmp_path, workspace).cells

    strategy = workspace / "resources/strategies/alpha/optimization.py"
    strategy.write_text(
        strategy.read_text(encoding="utf-8").replace(
            "yadof.optimize.program/v1", "yadof.optimize.program/v2"
        ),
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkError, match="program api must be"):
        _plan(tmp_path, workspace)


def test_explicit_program_helpers_are_hashed_and_materialized(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "explicit", strategies=("alpha",))
    strategy = workspace / "resources/strategies/alpha/optimization.py"
    helper = strategy.with_name("optimization_helpers.py")
    sentinel = workspace / "strategy-ran.txt"
    strategy.write_text(
        "from pathlib import Path\n"
        "from optimization_helpers import VALUE\n\n"
        "YADOF_OPTIMIZATION_PROGRAM = {\n"
        "    'api': 'yadof.optimize.program/v1',\n"
        "    'entry': 'optimization_program',\n"
        "    'helpers': ('optimization_helpers.py',),\n"
        "    'identity': {'name': 'explicit-test'},\n"
        "    'capabilities': ('test',),\n"
        "}\n\n"
        "def optimization_program(context):\n"
        f"    Path({str(sentinel)!r}).write_text(str(VALUE), encoding='utf-8')\n",
        encoding="utf-8",
    )
    helper.write_text("VALUE = 'first'\n", encoding="utf-8")

    first = _plan(tmp_path, workspace).to_dict()["cells"][0]
    assert set(first["strategy_files"]) == {
        "optimization.py",
        "optimization_helpers.py",
    }
    first_digest = first["strategy_digest"]
    assert not sentinel.exists()

    helper.write_text("VALUE = 'second'\n", encoding="utf-8")
    second = _plan(tmp_path, workspace).to_dict()["cells"][0]
    assert second["strategy_digest"] != first_digest
    assert not sentinel.exists()

    _execute(tmp_path, workspace)
    copied = workspace / "cells/c0001/workspace/submit/optimization_helpers.py"
    assert copied.read_text(encoding="utf-8") == "VALUE = 'second'\n"
    assert not sentinel.exists()


def test_explicit_program_helper_path_is_statically_rejected(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "invalid-helper", strategies=("alpha",))
    strategy = workspace / "resources/strategies/alpha/optimization.py"
    strategy.write_text(
        "YADOF_OPTIMIZATION_PROGRAM = {\n"
        "    'api': 'yadof.optimize.program/v1',\n"
        "    'entry': 'optimization_program',\n"
        "    'helpers': ('../escape.py',),\n"
        "    'identity': {'name': 'invalid'},\n"
        "    'capabilities': (),\n"
        "}\n\n"
        "def optimization_program(context):\n"
        "    raise AssertionError('must not run')\n",
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkError, match="canonical relative .py path"):
        _plan(tmp_path, workspace)


def test_removed_legacy_strategy_source_is_rejected(tmp_path: Path) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "removed-factory", strategies=("alpha",))
    strategy = workspace / "resources/strategies/alpha/optimization.py"
    strategy.write_text(
        "def build_optimization():\n"
        "    raise AssertionError('must not run')\n",
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkError, match="not supported"):
        _plan(tmp_path, workspace)


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


def test_cell_started_event_carries_active_identity_and_execution_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        concurrency.psutil,
        "cpu_count",
        lambda *, logical: 6 if logical is False else 12,
    )
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "event-capacity", strategies=("alpha",))
    plan = _plan(tmp_path, workspace)
    initialize_workspace(plan)
    events: list[dict] = []
    state = execution.execute_workspace(
        workspace,
        command_runner=_successful_command,
        collector=lambda _workspace, cell: _cell_result(cell, 0.2),
        event_sink=lambda event: events.append(dict(event)),
    )

    started = next(event for event in events if event.get("event") == "cell-started")
    expected = plan.cells[0]
    assert started["cell"] == expected.id
    assert started["display_label"] == expected.display_label
    assert started["baseline"] == expected.baseline_id
    assert started["strategy"] == expected.strategy_id
    assert started["seed"] == expected.seed
    assert started["timeout_seconds"] == expected.execution["timeout_seconds"]
    assert started["simulator_mode"] == expected.execution["mode"]
    assert started["simulator_physical_core_multiplier"] == expected.execution[
        "simulation_concurrency"
    ]["physical_core_multiplier"]
    resolved = next(
        event
        for event in events
        if event.get("event") == "simulation-concurrency-resolved"
    )
    assert resolved["simulator_physical_cores"] == 6
    assert resolved["simulator_physical_core_multiplier"] == 2.0
    assert resolved["simulator_workers"] == 12
    recorded = state["cells"]["c0001"]["simulation_concurrency"]
    assert recorded["physical_cores"] == 6
    assert recorded["resolved_max_workers"] == 12
    config = (workspace / "cells" / "c0001" / "workspace" / "config.py").read_text(
        encoding="utf-8"
    )
    assert "FAST_EVALUATION_MAX_WORKERS = 12" in config
    assert "FAST_RESOURCE_AUTODETECT_ENABLED" not in config


def test_legacy_execution_without_display_labels_remains_inspectable(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "legacy-labels", strategies=("alpha",))
    _execute(tmp_path, workspace)
    spec = read_json(workspace / "spec.json")
    state = read_json(workspace / "state.json")
    for cell in spec["cells"]:
        cell.pop("display_label", None)
    for cell in state["cells"].values():
        cell.pop("display_label", None)
    (workspace / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (workspace / "state.json").write_text(json.dumps(state), encoding="utf-8")

    inspected = inspect_workspace(workspace)
    assert "baseline=provider/task" in inspected["cell_labels"]["c0001"]
    assert "strategy=alpha" in inspected["cell_labels"]["c0001"]


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


@pytest.mark.parametrize("active_status", ["running", "succeeded"])
def test_inspect_active_cell_includes_identity_timeout_and_worker_state(
    tmp_path: Path,
    active_status: str,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "inspect-active", strategies=("alpha",))
    plan = _plan(tmp_path, workspace)
    initialize_workspace(plan)
    _, state = load_execution(workspace)
    state["status"] = "running"
    state["cells"]["c0001"]["status"] = active_status
    (workspace / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    observed = api.inspect_workspace(workspace)
    expected = plan.to_dict()["cells"][0]
    active = observed["active"]
    assert active["cell"] == "c0001"
    assert active["display_label"] == expected["display_label"]
    assert active["baseline"] == expected["baseline"]
    assert active["strategy"] == expected["strategy"]
    assert active["seed"] == expected["seed"]
    assert active["timeout_seconds"] == expected["execution"]["timeout_seconds"]
    assert active["simulator"]["workers"] == expected["execution"][
        "simulation_concurrency"
    ]
    assert observed["anomalies"] == []


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
    assert receipt["window_remains_open_after_run"] is True
    assert receipt["workspace"] == str(Path(workspace).resolve())
    assert "inspect --workspace" in receipt["inspect"]
    assert "resume" not in command
    assert command[0].lower().endswith("powershell.exe")
    assert "-NoExit" in command
    persistent_script = command[-1]
    assert sys.executable.replace("'", "''") in persistent_script
    assert "yadof_benchmark" in persistent_script
    assert "'run'" in persistent_script
    assert str(Path(workspace).resolve()).replace("'", "''") in persistent_script
    assert "This window will remain open" in persistent_script
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["creationflags"] & subprocess.CREATE_NEW_CONSOLE
    assert kwargs["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert "stdout" not in kwargs and "stderr" not in kwargs


@pytest.mark.skipif(os.name != "nt", reason="Windows detached-console contract")
def test_hidden_detached_launch_remains_direct_and_automatic(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    workspace = api.init_workspace(tmp_path / "hidden-detached")["workspace"]

    class Process:
        pid = 4343

    def process_factory(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    receipt = launch_detached(
        workspace,
        hidden=True,
        process_factory=process_factory,
    )

    command = [str(item) for item in captured["command"]]
    assert command[:4] == [sys.executable, "-m", "yadof_benchmark", "run"]
    assert "-NoExit" not in command
    assert receipt["visible"] is False
    assert receipt["window_remains_open_after_run"] is False
    assert Path(receipt["stdout"]).is_file()
    assert Path(receipt["stderr"]).is_file()
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
    assert "stdout" in kwargs and "stderr" in kwargs


def test_cli_surface_has_no_resume_or_run_id() -> None:
    parser = cli._parser()
    subparsers = next(
        action for action in parser._actions if action.dest == "command"
    )
    assert set(subparsers.choices) == {
        "init",
        "presets",
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
    init_options = {
        option
        for action in subparsers.choices["init"]._actions
        for option in action.option_strings
    }
    inspect_options = {
        option
        for action in subparsers.choices["inspect"]._actions
        for option in action.option_strings
    }
    assert "--run-id" not in run_options
    assert {"--preset", "--blank"} <= init_options
    init_help = " ".join(subparsers.choices["init"].format_help().split())
    assert "long-running complete preset" in init_help
    assert "--budget-profile" in run_options
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


def test_actual_yadof_evaluation_output_emits_truthful_generation_progress(
    tmp_path: Path,
) -> None:
    events: list[dict] = []
    script = (
        "import sys\n"
        "for _batch in range(2):\n"
        "    for finished in range(5):\n"
        "        successful = finished\n"
        "        remaining = 4 - finished\n"
        "        print(f'[yadof] evaluation (fast) [####] {finished}/4 '"
        "              f'successful={successful} errors=0 remaining={remaining}', "
        "              file=sys.stderr, flush=True)\n"
    )
    result = execution.run_logged(
        [
            sys.executable,
            "-c",
            script,
            "--generations",
            "2",
            "--population-size",
            "4",
        ],
        cwd=tmp_path,
        command_root=tmp_path / "progress-command",
        label="run",
        timeout_seconds=10,
        event_sink=lambda event: events.append(dict(event)),
    )

    progress = [event for event in events if event.get("event") == "cell-progress"]
    assert result.returncode == 0
    assert progress
    assert [event["generation_number"] for event in progress if event["remaining"] == 0] == [1, 2]
    assert progress[-1]["evaluations"] == 8
    assert progress[-1]["planned_evaluations"] == 8


class _TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    ("stream", "non_tty"),
    [(io.StringIO(), True), (_TTYBuffer(), False)],
)
def test_terminal_surfaces_semantic_cell_label_without_ansi(
    tmp_path: Path,
    stream: io.StringIO,
    non_tty: bool,
) -> None:
    label = (
        "baseline=provider/a-long-task (Task | 特殊) | "
        "strategy=gpsaf-pca-svd (GPSAF + PCA/SVD) | seed=101"
    )
    terminal = BenchmarkTerminal(
        tmp_path,
        stream=stream,
        environ={"NO_COLOR": "1", "COLUMNS": "240"},
    )
    terminal.start()
    terminal.handle(
        {
            "event": "cell-started",
            "cell": "c0001",
            "display_label": label,
            "baseline": "provider/a-long-task",
            "strategy": "gpsaf-pca-svd",
            "seed": 101,
            "population": 4,
            "generations": 2,
            "planned_evaluations": 8,
            "timeout_seconds": 7200,
            "simulator_mode": "fast",
            "simulator_physical_core_multiplier": 2.0,
            "simulator_resource": "YADOF_SIMULATOR",
            "total_cells": 1,
            "finished_cells": 0,
            "completed_cells": 0,
            "failed_cells": 0,
        }
    )
    terminal.handle(
        {
            "event": "simulation-concurrency-resolved",
            "cell": "c0001",
            "display_label": label,
            "simulator_physical_cores": 8,
            "simulator_physical_core_multiplier": 2.0,
            "simulator_workers": 16,
        }
    )
    terminal.finish(error="short test stop")
    rendered = stream.getvalue()
    assert label in rendered
    assert "timeout=7200s" in rendered
    assert "workers=physical_cores*2" in rendered
    assert "physical_cores=8 multiplier=2 workers=16" in rendered
    if non_tty:
        assert "\x1b" not in rendered


def test_live_terminal_tracks_semantics_capacity_and_concurrent_counts(
    tmp_path: Path,
) -> None:
    stream = _TTYBuffer()
    terminal = BenchmarkTerminal(
        tmp_path,
        stream=stream,
        environ={"NO_COLOR": "1", "COLUMNS": "240"},
    )
    terminal.start()
    first = {
        "event": "cell-started",
        "cell": "c0001",
        "display_label": "baseline=chrono/trebuchet (Trebuchet) | strategy=real-only-nsga3 (Real-only NSGA-III) | seed=101",
        "baseline": "chrono/trebuchet",
        "strategy": "real-only-nsga3",
        "seed": 101,
        "population": 200,
        "generations": 25,
        "planned_evaluations": 5000,
        "timeout_seconds": 7200,
        "simulator_mode": "fast",
        "simulator_workers": 16,
        "simulator_physical_cores": 8,
        "simulator_physical_core_multiplier": 2.0,
        "simulator_resource": "YADOF_PYCHRONO_PYTHON",
        "total_cells": 3,
        "finished_cells": 0,
        "completed_cells": 0,
        "failed_cells": 0,
    }
    second = {
        **first,
        "cell": "c0002",
        "display_label": "baseline=ngspice/saw-ladder (SAW ladder) | strategy=gpsaf-pca-svd-nsga3 (GPSAF) | seed=102",
        "baseline": "ngspice/saw-ladder",
        "strategy": "gpsaf-pca-svd-nsga3",
        "seed": 102,
        "simulator_workers": 16,
        "simulator_resource": "YADOF_NGSPICE_EXE",
    }
    terminal.handle(first)
    terminal.handle(second)

    assert second["display_label"] in terminal._cell_detail()
    assert "timeout=7200s" in terminal._cell_detail()
    assert "workers=16(8*2)" in terminal._cell_detail()
    assert "run=2 queued=1" in terminal._global_detail()

    terminal.handle(
        {
            "event": "cell-progress",
            "cell": "c0001",
            "display_label": first["display_label"],
            "evaluations": 100,
            "planned_evaluations": 5000,
            "generation_number": 1,
            "generations": 25,
            "successful": 90,
            "errors": 10,
            "phase": "evaluation",
        }
    )
    terminal.handle(
        {
            "event": "cell-progress",
            "cell": "c0002",
            "display_label": second["display_label"],
            "evaluations": 50,
            "planned_evaluations": 5000,
            "generation_number": 1,
            "generations": 25,
            "successful": 50,
            "errors": 0,
            "phase": "evaluation",
        }
    )
    terminal.handle(
        {
            "event": "cell-progress",
            "cell": "c0001",
            "display_label": first["display_label"],
            "evaluations": 200,
            "planned_evaluations": 5000,
            "generation_number": 1,
            "generations": 25,
            "successful": 180,
            "errors": 20,
            "phase": "evaluation",
        }
    )
    assert terminal.current_cell == "c0001"
    assert terminal.cell_completed == 200
    assert terminal.cell_errors == 20

    terminal._select_cell({"cell": "c0002"})
    assert terminal.cell_completed == 50
    assert terminal.cell_errors == 0

    terminal.handle(
        {
            "event": "command-finished",
            "cell": "c0002",
            "display_label": second["display_label"],
            "label": "run",
            "returncode": 1,
            "timed_out": True,
            "process_tree_cleanup": "requested-and-parent-exited",
            "duration_seconds": 7200.0,
        }
    )
    assert terminal.phase == "timeout"
    terminal.handle(
        {
            "event": "cell-failed",
            "cell": "c0002",
            "display_label": second["display_label"],
            "error": "run failed after timeout",
            "total_cells": 3,
            "finished_cells": 1,
            "completed_cells": 0,
            "failed_cells": 1,
        }
    )
    assert "err=1 run=1 queued=1" in terminal._global_detail()
    terminal.finish(error="cancelled by user")
    rendered = stream.getvalue()
    assert "timed_out=True" in rendered
    assert "cleanup=requested-and-parent-exited" in rendered
    assert "benchmark failed: cancelled by user" in rendered


def test_narrow_terminal_uses_deterministic_semantic_compression(
    tmp_path: Path,
) -> None:
    terminal = BenchmarkTerminal(
        tmp_path,
        stream=_TTYBuffer(),
        environ={"NO_COLOR": "1", "COLUMNS": "48"},
    )
    terminal.handle(
        {
            "event": "cell-started",
            "cell": "c0001",
            "display_label": "baseline=provider/a-very-long-task | strategy=gpsaf-pca-svd-nsga3 | seed=101",
            "baseline": "provider/a-very-long-task",
            "strategy": "gpsaf-pca-svd-nsga3",
            "seed": 101,
            "planned_evaluations": 5000,
            "generations": 25,
            "timeout_seconds": 7200,
            "simulator_workers": 8,
            "simulator_physical_cores": 8,
            "simulator_physical_core_multiplier": 1.0,
            "total_cells": 18,
            "finished_cells": 0,
            "completed_cells": 0,
            "failed_cells": 0,
        }
    )
    detail = terminal._cell_detail()
    assert "c0001" in detail
    assert "b=" in detail and "s=" in detail and "z=101" in detail
    assert "to=7200s" in detail and "w=8(8*1)" in detail


def test_non_tty_terminal_appends_real_elapsed_heartbeat(tmp_path: Path) -> None:
    stream = io.StringIO()
    terminal = BenchmarkTerminal(tmp_path, stream=stream)
    terminal.start()
    terminal.handle(
        {
            "event": "cell-started",
            "cell": "c0001",
            "display_label": "baseline=task | strategy=algo | seed=101",
            "population": 200,
            "generations": 25,
            "planned_evaluations": 5000,
            "total_cells": 18,
            "finished_cells": 0,
            "completed_cells": 0,
            "failed_cells": 0,
        }
    )
    terminal.handle({"event": "command-started", "label": "run"})
    terminal.handle(
        {
            "event": "command-progress",
            "label": "run",
            "elapsed_seconds": 65.0,
            "inactivity_seconds": 2.0,
        }
    )
    terminal.finish(error="short test stop")
    rendered = stream.getvalue()
    assert "t=65s" in rendered
    assert "\x1b" not in rendered


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree contract")
def test_timeout_stops_descendant_process_tree(tmp_path: Path) -> None:
    sentinel = tmp_path / "descendant-survived.txt"
    child = tmp_path / "child.py"
    parent = tmp_path / "parent.py"
    child.write_text(
        "import pathlib, sys, time\n"
        "time.sleep(2.5)\n"
        "pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')\n",
        encoding="utf-8",
    )
    parent.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    result = execution.run_logged(
        [sys.executable, str(parent), str(child), str(sentinel)],
        cwd=tmp_path,
        command_root=tmp_path / "timeout-command",
        label="run",
        timeout_seconds=1,
    )
    time.sleep(2.0)
    assert result.timed_out is True
    assert result.returncode != 0
    assert not sentinel.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows taskkill fallback contract")
def test_timeout_cleanup_falls_back_when_psutil_denies_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PsutilError(Exception):
        pass

    def deny_process(_pid: int):
        raise PsutilError("access denied")

    fake_psutil = SimpleNamespace(
        Error=PsutilError,
        NoSuchProcess=PsutilError,
        Process=deny_process,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    taskkill_calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        taskkill_calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(execution.subprocess, "run", fake_run)

    class Process:
        pid = 4321

        @staticmethod
        def poll():
            return None

        @staticmethod
        def wait(timeout):
            del timeout
            return 0

        @staticmethod
        def kill():
            raise AssertionError("parent-only fallback should not be needed")

    execution._stop_process_tree(Process())

    assert taskkill_calls == [["taskkill", "/PID", "4321", "/T", "/F"]]


def test_timeout_fails_one_cell_continues_independent_cell_and_fails_workspace(
    tmp_path: Path,
) -> None:
    _baseline(tmp_path)
    workspace = _workspace(tmp_path / "continue", strategies=("alpha", "beta"))
    spec = _plan(tmp_path, workspace)
    initialize_workspace(spec)
    timed_out = False

    def runner(command, **kwargs):
        nonlocal timed_out
        result = _successful_command(command, **kwargs)
        if kwargs["label"] == "run" and not timed_out:
            timed_out = True
            return CommandResult(
                result.command,
                1,
                result.duration_seconds,
                True,
                result.stdout,
                result.stderr,
            )
        return result

    state = execution.execute_workspace(
        workspace,
        command_runner=runner,
        collector=lambda _workspace, cell: _cell_result(cell, 0.2),
    )
    assert state["status"] == "failed"
    assert [state["cells"][cell]["status"] for cell in ("c0001", "c0002")] == [
        "failed",
        "collected",
    ]
    assert "timeout" in state["cells"]["c0001"]["error"]
    inspected = api.inspect_workspace(workspace)
    assert any(
        item["scope"] == "c0001" and "timeout" in item["message"]
        for item in inspected["anomalies"]
    )
    assert any(
        item["scope"] == "c0001"
        and item["message"] == "cell collection incomplete"
        for item in inspected["anomalies"]
    )


def test_distribution_version() -> None:
    assert benchmark.__version__ == "0.5.0"
