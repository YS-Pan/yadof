from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import benchmark_core as core


TASK_FINGERPRINT = "1" * 64


def _write_baseline(
    root: Path,
    *,
    case_id: str = "case",
    provider_id: str = "adapter",
    task_id: str = "task",
    baseline_id: str | None = None,
) -> Path:
    identity = baseline_id or f"{task_id}-{TASK_FINGERPRINT[:12]}"
    baseline = root / "baselines" / provider_id / identity
    workspace = baseline / "workspace"
    (workspace / "submit").mkdir(parents=True)
    (workspace / "job_template").mkdir()
    (workspace / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
    (workspace / "postprocess.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )
    (baseline / "baseline.json").write_text(
        json.dumps(
            {
                "baseline_id": identity,
                "case_id": case_id,
                "provider_id": provider_id,
                "task_id": task_id,
                "task_fingerprint": TASK_FINGERPRINT,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return baseline


def test_task_fingerprint_matches_path_tab_hash_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "submit").mkdir(parents=True)
    (workspace / "config.py").write_bytes(b"VALUE = 1\n")
    (workspace / "submit" / "optimization.py").write_bytes(b"STRATEGY = 'real'\n")
    entries = []
    for relative in ("config.py", "submit/optimization.py"):
        digest = hashlib.sha256((workspace / relative).read_bytes()).hexdigest()
        entries.append(f"{relative}\t{digest}")
    expected = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    assert core.task_fingerprint(workspace, ["config.py", "submit"]) == expected


def test_resolve_inside_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(core.BenchmarkError, match="escapes benchmark root"):
        core.resolve_inside(tmp_path, "../outside", label="fixture")


def _write_loadable_config(root: Path) -> Path:
    baseline = _write_baseline(root)
    (root / "strategies").mkdir()
    (root / "strategies" / "real.py").write_text(
        "def build_optimization(): return object()\n", encoding="utf-8"
    )
    (root / "history").mkdir()
    config = root / "benchmark.toml"
    config.write_text(
        """schema_version = 1

[runner]
runs_dir = "runs"
strategy_template_dir = "strategies"
history_snapshot_dir = "history"

[cases.case]
baseline = "{baseline}"
include_paths = ["config.py", "submit", "job_template", "postprocess.py"]
history_policy = "empty"

[arms.real]
strategy_template = "real.py"

[suites.structural]
purpose = "structural"
cases = ["case"]
arms = ["real"]
seeds = [1]

[budgets.structural.case.real]
population = 1
generations = 1
""".format(baseline=baseline.relative_to(root).as_posix()),
        encoding="utf-8",
    )
    return config


def test_runs_dir_override_resolves_from_invocation_directory(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmark source"
    config_path = _write_loadable_config(benchmark_root)
    invocation_cwd = tmp_path / "调用 目录"
    invocation_cwd.mkdir()

    _config, default_paths = core.load_config(config_path)
    assert default_paths.runs == benchmark_root / "runs"

    _config, override_paths = core.load_config(
        config_path,
        runs_dir_override=Path("temp") / "结果",
        invocation_cwd=invocation_cwd,
    )
    assert override_paths.runs == invocation_cwd / "temp" / "结果"

    absolute = tmp_path / "absolute outputs"
    _config, absolute_paths = core.load_config(
        config_path,
        runs_dir_override=absolute,
        invocation_cwd=invocation_cwd,
    )
    assert absolute_paths.runs == absolute


def test_repository_config_defaults_to_checkout_temp() -> None:
    automation_root = Path(__file__).resolve().parents[1]

    _config, paths = core.load_config(automation_root / "benchmark.toml")

    assert paths.runs == automation_root.parent / "temp"


def test_runs_dir_rejects_protected_input_overlap(tmp_path: Path) -> None:
    config_path = _write_loadable_config(tmp_path)
    with pytest.raises(core.BenchmarkError, match="overlaps case 'case' baseline"):
        core.load_config(config_path, runs_dir_override=tmp_path / "baselines")


def test_load_config_requires_declared_postprocess(tmp_path: Path) -> None:
    config_path = _write_loadable_config(tmp_path)
    text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        text.replace(
            ', "postprocess.py"',
            "",
        ),
        encoding="utf-8",
    )
    with pytest.raises(core.BenchmarkError, match="must declare 'postprocess.py'"):
        core.load_config(config_path)


def test_load_config_requires_baseline_postprocess_script(tmp_path: Path) -> None:
    config_path = _write_loadable_config(tmp_path)
    postprocess = next((tmp_path / "baselines").glob("*/*/workspace/postprocess.py"))
    postprocess.unlink()
    with pytest.raises(core.BenchmarkError, match="baseline has no postprocess.py"):
        core.load_config(config_path)


def test_load_config_rejects_legacy_date_baseline_identity(tmp_path: Path) -> None:
    root = tmp_path / "benchmark"
    config_path = _write_loadable_config(root)
    valid_baseline = next((root / "baselines").glob("*/*"))
    baseline = valid_baseline.with_name(f"20260823-{TASK_FINGERPRINT[:12]}")
    valid_baseline.rename(baseline)
    text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        text.replace(
            valid_baseline.relative_to(root).as_posix(),
            baseline.relative_to(root).as_posix(),
        ),
        encoding="utf-8",
    )
    with pytest.raises(core.BenchmarkError, match="must use baselines"):
        core.load_config(config_path)


def test_load_config_rejects_baseline_provider_metadata_mismatch(tmp_path: Path) -> None:
    config_path = _write_loadable_config(tmp_path)
    manifest_path = next((tmp_path / "baselines").glob("*/*/baseline.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provider_id"] = "different-adapter"
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    with pytest.raises(core.BenchmarkError, match="metadata provider_id"):
        core.load_config(config_path)


def test_load_config_rejects_baseline_fingerprint_prefix_mismatch(tmp_path: Path) -> None:
    config_path = _write_loadable_config(tmp_path)
    manifest_path = next((tmp_path / "baselines").glob("*/*/baseline.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["task_fingerprint"] = "2" * 64
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    with pytest.raises(core.BenchmarkError, match="fingerprint prefix"):
        core.load_config(config_path)


def test_plan_has_disposable_smoke_and_independent_measured_cells() -> None:
    config = {
        "cases": {
            "case-a": {
                "baseline": "baselines/provider/task-111111111111",
                "mode": "fast",
                "observed_eval_sec": 2.0,
                "estimated_record_mib": 1.5,
                "max_workers": 2,
            }
        },
        "arms": {"real": {}, "surrogate": {}},
        "suites": {
            "structural": {
                "purpose": "structural",
                "cases": ["case-a"],
                "arms": ["real", "surrogate"],
                "seeds": [17],
                "smoke": True,
                "fail_fast": True,
            }
        },
        "budgets": {
            "structural": {
                "case-a": {
                    "real": {"population": 4, "generations": 1, "max_generations": 1},
                    "surrogate": {"population": 4, "generations": 2, "max_generations": 3},
                }
            }
        },
    }
    paths = core.Paths(Path("."), Path("benchmark.toml"), Path("runs"), Path("strategies"), Path("history"))
    plan = core.build_plan(config, paths, "structural")
    assert plan["cell_count"] == 3
    assert plan["cells"][0]["kind"] == "smoke"
    assert plan["cells"][0]["disposable"] is True
    assert {cell["cell_id"] for cell in plan["cells"]} == {
        "smoke__case-a__seed-17",
        "case-a__real__seed-17",
        "case-a__surrogate__seed-17",
    }
    assert all(cell["planned_commands"][0][3] == "init" for cell in plan["cells"])
    measured = [cell for cell in plan["cells"] if cell["kind"] == "measured"]
    assert all(
        cell["planned_commands"][-2][1].endswith("postprocess.py")
        for cell in measured
    )
    assert all(
        cell["planned_commands"][-1][3:5] == ["view", "cost"]
        for cell in measured
    )
    assert all(
        cell["planned_commands"][-2][-3]
        == "<run-root>/visualizations/task-111111111111"
        for cell in measured
    )
    assert all(
        cell["planned_commands"][-2][-1]
        == f"{cell['cell_id']}__attempt-<attempt>__"
        for cell in measured
    )
    assert all(
        cell["planned_commands"][-1][-1]
        == (
            f"<run-root>/visualizations/viewcost/"
            f"{cell['cell_id']}__attempt-<attempt>__benchmark-cost.png"
        )
        for cell in measured
    )
    assert all("--progress" in cell["planned_commands"][2] for cell in measured)
    filtered = core.build_plan(
        config,
        paths,
        "structural",
        case_ids=["case-a"],
        arm_ids=["real"],
        seeds=[17],
    )
    assert [cell["arm"] for cell in filtered["cells"]] == [None, "real"]


def test_performance_config_requires_equal_planned_attempted_budget(tmp_path: Path) -> None:
    baseline = _write_baseline(tmp_path)
    strategies = tmp_path / "strategies"
    strategies.mkdir()
    for name in ("real.py", "surrogate.py"):
        (strategies / name).write_text("def build_optimization(): return object()\n", encoding="utf-8")
    config = {
        "cases": {
            "case": {
                "baseline": baseline.relative_to(tmp_path).as_posix(),
                "include_paths": [
                    "config.py",
                    "submit",
                    "job_template",
                    "postprocess.py",
                ],
                "history_policy": "empty",
            }
        },
        "arms": {
            "real": {"strategy_template": "real.py"},
            "surrogate": {"strategy_template": "surrogate.py"},
        },
        "suites": {
            "performance": {
                "purpose": "performance",
                "cases": ["case"],
                "arms": ["real", "surrogate"],
                "seeds": [1, 2, 3],
            }
        },
        "budgets": {
            "performance": {
                "case": {
                    "real": {"population": 4, "generations": 2},
                    "surrogate": {"population": 3, "generations": 2},
                }
            }
        },
    }
    paths = core.Paths(tmp_path, tmp_path / "benchmark.toml", tmp_path / "runs", strategies, tmp_path / "history")
    with pytest.raises(core.BenchmarkError, match="unequal planned attempted budgets"):
        core.validate_config(config, paths)


def test_repository_performance_suite_uses_substantial_budget() -> None:
    benchmark_root = Path(__file__).resolve().parents[1]
    config, paths = core.load_config(benchmark_root / "benchmark.toml")
    plan = core.build_plan(config, paths, "performance")
    measured = [cell for cell in plan["cells"] if cell["kind"] == "measured"]
    assert len(measured) == 18
    assert all(cell["population"] >= 100 for cell in measured)
    assert all(cell["generations"] >= 20 for cell in measured)
    assert all(cell["max_generations"] == cell["generations"] for cell in measured)
    assert sum(cell["planned_attempted_evaluations"] for cell in measured) == 36_000
    assert plan["selection"]["arms"] == ["nsga3", "gpsaf-conditional-inr"]
    assert all(config["cases"][case_id]["max_workers"] == 32 for case_id in config["cases"])
    baseline_result_dirs = {
        cell["planned_commands"][-2][-3]
        for cell in measured
    }
    assert baseline_result_dirs == {
        f"<run-root>/visualizations/{Path(config['cases'][case_id]['baseline']).name}"
        for case_id in plan["selection"]["cases"]
    }
    assert len(baseline_result_dirs) == 3
    assert config["runner"]["measured_config_overrides"] == {
        "HISTORY_SEGMENT_MAX_CANDIDATES": 100,
        "HISTORY_UNPUBLISHED_MAX_CANDIDATES": 128,
        "FAST_RESOURCE_AUTODETECT_ENABLED": False,
    }


def _minimal_spec(tmp_path: Path) -> dict:
    spec = {
        "schema_version": 1,
        "created_utc": "2026-08-23T00:00:00.000Z",
        "suite": "fixture",
        "purpose": "structural",
        "label": None,
        "config": {"path": str(tmp_path / "benchmark.toml"), "sha256": "0" * 64},
        "package": {"python": "python", "version": "0", "origin": "fixture"},
        "host": {},
        "runner": {"command_timeout_sec": 1, "audit_sample_percent": 10, "audit_random_seed": 1, "fail_fast": True},
        "cases": {},
        "arms": {},
        "plan": {
            "cells": [
                {
                    "cell_id": "smoke__case__seed-1",
                    "kind": "smoke",
                    "case": "case",
                    "arm": None,
                    "seed": 1,
                }
            ]
        },
    }
    spec["spec_sha256"] = core.object_sha256(spec)
    return spec


def test_default_run_id_starts_with_numeric_utc_date_and_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_datetime = core.dt.datetime

    class FixedDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is core.dt.UTC
            return cls(2026, 8, 24, 12, 34, 56, tzinfo=tz)

    monkeypatch.setattr(core.dt, "datetime", FixedDateTime)
    spec = _minimal_spec(tmp_path)
    suffix = spec["spec_sha256"][:12]
    expected = f"20260824_123456-{suffix}"
    paths = core.Paths(
        tmp_path,
        tmp_path / "benchmark.toml",
        tmp_path / "runs",
        tmp_path / "strategies",
        tmp_path / "history",
    )

    run_id, run_root = core.create_run(paths, spec)
    assert run_id == expected
    assert run_root.name == expected
    assert core.make_run_id(spec, "full benchmark") == (
        f"20260824_123456-full-benchmark-{suffix}"
    )


def test_run_spec_is_immutable_and_state_is_separate(tmp_path: Path) -> None:
    paths = core.Paths(tmp_path, tmp_path / "benchmark.toml", tmp_path / "runs", tmp_path / "strategies", tmp_path / "history")
    spec = _minimal_spec(tmp_path)
    run_id, run_root = core.create_run(paths, spec, run_id="fixture")
    assert run_id == "fixture"
    loaded_root, loaded_spec, state = core.load_run(paths, run_id)
    assert loaded_root == run_root
    assert loaded_spec == spec
    assert state["cells"]["smoke__case__seed-1"]["status"] == "pending"
    tampered = json.loads((run_root / "run_spec.json").read_text(encoding="utf-8"))
    tampered["suite"] = "changed"
    (run_root / "run_spec.json").write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(core.BenchmarkError, match="fingerprint mismatch"):
        core.load_run(paths, run_id)


def test_same_run_id_is_isolated_by_runs_dir(tmp_path: Path) -> None:
    spec = _minimal_spec(tmp_path)
    roots = [tmp_path / "first outputs", tmp_path / "第二 输出"]
    created = []
    for runs in roots:
        paths = core.Paths(
            tmp_path,
            tmp_path / "benchmark.toml",
            runs,
            tmp_path / "strategies",
            tmp_path / "history",
        )
        _run_id, run_root = core.create_run(paths, spec, run_id="same-id")
        created.append(run_root)
    assert created == [roots[0] / "same-id", roots[1] / "same-id"]
    assert all(path.is_dir() for path in created)


def test_load_run_rejects_run_id_escape(tmp_path: Path) -> None:
    paths = core.Paths(
        tmp_path,
        tmp_path / "benchmark.toml",
        tmp_path / "runs",
        tmp_path / "strategies",
        tmp_path / "history",
    )
    with pytest.raises(core.BenchmarkError, match="escapes benchmark root"):
        core.load_run(paths, "../outside")


def test_sequence_directories_are_append_only(tmp_path: Path) -> None:
    first = core._new_sequence_dir(tmp_path, "collect")
    second = core._new_sequence_dir(tmp_path, "collect")
    assert first.name == "collect-0001"
    assert second.name == "collect-0002"
    assert first.is_dir() and second.is_dir()


def test_declared_clone_excludes_runtime_and_replaces_starter_roots(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    (source / "submit").mkdir(parents=True)
    (source / "job_template").mkdir()
    (source / "recorded_data").mkdir()
    (source / "config.py").write_text("SOURCE = True\n", encoding="utf-8")
    (source / "submit" / "optimization.py").write_text("ARM = 'source'\n", encoding="utf-8")
    (source / "job_template" / "workflow.py").write_text("pass\n", encoding="utf-8")
    (source / "recorded_data" / "row.json").write_text("{}", encoding="utf-8")
    (destination / "submit").mkdir(parents=True)
    (destination / "job_template").mkdir()
    (destination / "submit" / "starter.py").write_text("pass\n", encoding="utf-8")
    core._copy_declared_inputs(source, destination, ["config.py", "submit", "job_template"])
    assert (destination / "config.py").read_text(encoding="utf-8") == "SOURCE = True\n"
    assert not (destination / "submit" / "starter.py").exists()
    assert not (destination / "recorded_data").exists()


def test_managed_config_override_is_single_use(tmp_path: Path) -> None:
    config = tmp_path / "config.py"
    config.write_text("VALUE = 1\n", encoding="utf-8")
    core._apply_config_overrides(config, {"OPTIMIZE_SMOKE_TEST_ENABLED": False})
    text = config.read_text(encoding="utf-8")
    assert text.count(core.CONFIG_BLOCK_START) == 1
    with pytest.raises(core.BenchmarkError, match="already exists"):
        core._apply_config_overrides(config, {"OPTIMIZE_SMOKE_TEST_ENABLED": False})


def test_attempt_replacement_links_to_sealed_predecessor(tmp_path: Path) -> None:
    paths = core.Paths(tmp_path, tmp_path / "benchmark.toml", tmp_path / "runs", tmp_path / "strategies", tmp_path / "history")
    run_root = tmp_path / "runs" / "run"
    cell_plan = {"cell_id": "case__real__seed-1", "case": "case", "arm": "real", "seed": 1}
    cell_state = {"status": "pending", "attempts": []}
    spec = {
        "cases": {"case": {"baseline": {"baseline_id": "task-111111111111"}}}
    }
    _root1, attempt1 = core._prepare_attempt({}, paths, run_root, spec, cell_plan, cell_state)
    attempt1["status"] = "failed"
    cell_state["status"] = "failed"
    _root2, attempt2 = core._prepare_attempt({}, paths, run_root, spec, cell_plan, cell_state)
    assert attempt1["attempt"] == 1
    assert attempt2["attempt"] == 2
    assert attempt2["replacement_for"] == 1
    assert Path(attempt1["workspace"]).parent != Path(attempt2["workspace"]).parent
    assert attempt1["visualization_output_dir"] == attempt2["visualization_output_dir"]
    assert attempt1["visualization_file_prefix"] != attempt2["visualization_file_prefix"]


def test_candidate_budget_uses_public_generation_population_sizes() -> None:
    metadata = [
        {"record_type": "generation", "generation_index": 0, "population_size": 4},
        {"record_type": "generation", "generation_index": 1, "population_size": 4},
    ]
    assert core._attempted_count(metadata) == 8


@pytest.mark.parametrize(
    ("fail_fast", "expected"),
    [
        (True, ["failed", "skipped"]),
        (False, ["failed", "completed"]),
    ],
)
def test_suite_failure_policy_controls_independent_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_fast: bool, expected: list[str]
) -> None:
    paths = core.Paths(tmp_path, tmp_path / "benchmark.toml", tmp_path / "runs", tmp_path / "strategies", tmp_path / "history")
    cells = [
        {"cell_id": "first", "kind": "measured", "case": "case", "arm": "real", "seed": 1},
        {"cell_id": "second", "kind": "measured", "case": "case", "arm": "real", "seed": 2},
    ]
    spec = _minimal_spec(tmp_path)
    spec["plan"]["cells"] = cells
    spec["runner"]["fail_fast"] = fail_fast
    spec["spec_sha256"] = core.object_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})
    run_id, _run_root = core.create_run(paths, spec, run_id=f"policy-{fail_fast}")

    def fake_run_one(
        _config,
        _paths,
        run_root,
        _spec,
        state,
        cell_plan,
        *,
        stream_subprocess_output=False,
        progress=None,
    ):
        assert stream_subprocess_output is False
        assert isinstance(progress, core.CellProgress)
        cell_state = state["cells"][cell_plan["cell_id"]]
        if cell_plan["cell_id"] == "first":
            cell_state["status"] = "failed"
            core._save_state(run_root, state)
            return False
        cell_state["status"] = "completed"
        core._save_state(run_root, state)
        return True

    monkeypatch.setattr(core, "_run_one_cell", fake_run_one)
    state = core.execute_run({}, paths, run_id)
    assert [state["cells"][cell["cell_id"]]["status"] for cell in cells] == expected


def test_measured_cell_groups_postprocess_results_by_baseline_and_shares_viewcost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    visualization_dir = run_root / "visualizations"
    visualization_dir.mkdir()
    result_dir = visualization_dir / "task-111111111111"
    result_dir.mkdir()
    (result_dir / "prior-cell.png").write_bytes(b"prior")
    paths = core.Paths(
        tmp_path,
        tmp_path / "benchmark.toml",
        tmp_path / "runs",
        tmp_path / "strategies",
        tmp_path / "history",
    )
    cell = {
        "cell_id": "case__nsga3__seed-1",
        "kind": "measured",
        "case": "case",
        "arm": "nsga3",
        "seed": 1,
        "population": 4,
        "generations": 1,
        "max_generations": 1,
    }
    spec = {
        "package": {"python": "python"},
        "runner": {"command_timeout_sec": 30},
        "cases": {
            "case": {
                "baseline": {
                    "baseline_id": "task-111111111111",
                    "include_paths": ["config.py"],
                },
                "mode": "fast",
            }
        },
        "arms": {"nsga3": {"surrogate": False}},
    }
    state = {
        "schema_version": 1,
        "updated_utc": "",
        "events": [],
        "cells": {cell["cell_id"]: {"status": "pending", "attempts": []}},
    }
    commands: list[tuple[str, list[str]]] = []

    def fake_execute(command, **kwargs):
        commands.append((kwargs["label"], list(command)))
        return {"returncode": 0, "timed_out": False}

    def fake_materialize(_paths, _spec, _cell, _attempt_root, attempt):
        Path(attempt["workspace"]).mkdir(parents=True)
        (Path(attempt["workspace"]) / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
        attempt["input_fingerprint"] = core.task_fingerprint(
            Path(attempt["workspace"]), ["config.py"]
        )

    monkeypatch.setattr(core, "_execute_logged", fake_execute)
    monkeypatch.setattr(core, "_materialize_attempt_inputs", fake_materialize)
    monkeypatch.setattr(core, "_has_completed_generation_prefix", lambda *_args: (True, [0]))
    assert core._run_one_cell({}, paths, run_root, spec, state, cell)
    assert [label for label, _command in commands] == [
        "init",
        "check",
        "optimize",
        "postprocess",
        "view-cost",
    ]
    attempt = state["cells"][cell["cell_id"]]["attempts"][0]
    visualization_prefix = f"{cell['cell_id']}__attempt-0001__"
    viewcost_dir = visualization_dir / "viewcost"
    assert Path(attempt["visualization_output_dir"]) == result_dir
    assert attempt["visualization_file_prefix"] == visualization_prefix
    assert Path(attempt["cost_visualization_output"]) == (
        viewcost_dir / f"{visualization_prefix}benchmark-cost.png"
    )
    assert visualization_dir.is_dir()
    assert result_dir.is_dir()
    assert viewcost_dir.is_dir()
    assert (result_dir / "prior-cell.png").read_bytes() == b"prior"
    assert commands[-2][1][-3] == str(result_dir)
    assert commands[-2][1][-1] == visualization_prefix
    assert commands[-1][1][-1] == str(
        viewcost_dir / f"{visualization_prefix}benchmark-cost.png"
    )
    assert state["cells"][cell["cell_id"]]["status"] == "completed"


def _cell(
    case: str,
    arm: str,
    seed: int,
    *,
    complete: bool,
    fingerprint: str | None,
    attempted: int,
    hv: float,
) -> dict:
    return {
        "cell_id": f"{case}-{arm}-{seed}",
        "kind": "measured",
        "case": case,
        "arm": arm,
        "seed": seed,
        "execution_status": "completed" if complete else "failed",
        "eligible_for_primary_performance_aggregate": complete,
        "metrics": {
            "initial_population_fingerprint": fingerprint,
            "attempted_real_evaluations": attempted,
            "hypervolume": {"final_cumulative": hv},
            "evaluator_elapsed_sec_sum": 4.0 if arm == "real" else 3.0,
            "cell_command_wall_sec": 5.0 if arm == "real" else 4.0,
            "finite_objective_rows": attempted,
            "invalid_objective_rows": 0,
            "evaluation_normalized_hv_auc": {"value": None},
            "surrogate": {"training_duration_sec": 1.25} if arm == "surrogate" else None,
        },
    }


def test_performance_report_pairs_only_complete_equal_population_cells() -> None:
    spec = {"arms": {"real": {"surrogate": False}, "surrogate": {"surrogate": True}}}
    cells = [
        _cell("case", "real", 1, complete=True, fingerprint="same", attempted=8, hv=0.2),
        _cell("case", "surrogate", 1, complete=True, fingerprint="same", attempted=8, hv=0.3),
        _cell("case", "real", 2, complete=True, fingerprint="other", attempted=8, hv=0.4),
        _cell("case", "surrogate", 2, complete=False, fingerprint=None, attempted=4, hv=0.1),
    ]
    collection = {"cells": {cell["cell_id"]: cell for cell in cells}, "tool_gaps": {}}
    report = core._performance_report(spec, collection)
    assert len(report["included_pairs"]) == 1
    assert len(report["excluded_pairs_retained"]) == 1
    difference = report["included_pairs"][0]["differences"]["surrogate_minus_real"]
    assert difference["final_cumulative_hypervolume"] == pytest.approx(0.1)
    assert report["descriptive_aggregate_by_case"]["case"][
        "surrogate_minus_real.final_cumulative_hypervolume"
    ]["count"] == 1


def test_json_safe_replaces_nonfinite_values() -> None:
    assert core._json_safe({"finite": 1.0, "nan": float("nan"), "inf": float("inf")}) == {
        "finite": 1.0,
        "nan": None,
        "inf": None,
    }


def test_initial_population_is_fingerprinted_in_population_index_order() -> None:
    generations = [
        {
            "record_type": "generation",
            "generation_index": 0,
            "created_job_names": ["finished-second", "finished-first"],
        }
    ]
    records = [
        {"job_name": "finished-second", "population_index": 1},
        {"job_name": "finished-first", "population_index": 0},
    ]
    normalized = {"finished-first": (0.1, 0.2), "finished-second": (0.3, 0.4)}
    fingerprint, count, gap = core._initial_population_fingerprint(
        generations, normalized, records
    )
    assert fingerprint == core.object_sha256([[0.1, 0.2], [0.3, 0.4]])
    assert count == 2
    assert gap is None


def test_utf8_io_and_space_non_ascii_path(tmp_path: Path) -> None:
    root = tmp_path / "含 空格"
    path = root / "状态.json"
    core.atomic_write_json(path, {"message": "结构验证 ✓"})
    assert core.read_json(path) == {"message": "结构验证 ✓"}
    text_path = root / "日志.log"
    core._write_new_text(text_path, "第一行\n第二行 ✓\n")
    assert text_path.read_text(encoding="utf-8") == "第一行\n第二行 ✓\n"


def test_materialization_selects_strategy_and_records_starting_evidence(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    workspace = tmp_path / "attempt" / "workspace"
    attempt_root = workspace.parent
    for root in (baseline, workspace):
        (root / "submit").mkdir(parents=True)
        (root / "job_template").mkdir()
        (root / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "submit" / "optimization.py").write_text("ARM = 'starter'\n", encoding="utf-8")
        (root / "job_template" / "workflow.py").write_text("pass\n", encoding="utf-8")
    strategy = tmp_path / "surrogate.py"
    strategy.write_text("ARM = 'surrogate'\n", encoding="utf-8")
    include = ["config.py", "submit", "job_template"]
    spec = {
        "runner": {
            "measured_config_overrides": {
                "HISTORY_SEGMENT_MAX_CANDIDATES": 100,
                "HISTORY_UNPUBLISHED_MAX_CANDIDATES": 128,
            }
        },
        "cases": {
            "case": {
                "baseline": {
                    "workspace": str(baseline),
                    "include_paths": include,
                    "actual_task_fingerprint": core.task_fingerprint(baseline, include),
                },
                "history_policy": "empty",
                "starting_evidence": {"policy": "empty", "fingerprint": "empty"},
                "max_workers": 2,
            }
        },
        "arms": {
            "surrogate": {
                "template": str(strategy),
                "sha256": core.file_sha256(strategy),
                "config_overrides": {"OPTIMIZE_SURROGATE_ALPHA": 3},
            }
        },
    }
    cell = {"kind": "measured", "case": "case", "arm": "surrogate", "seed": 1}
    attempt = {
        "workspace": str(workspace),
        "input_fingerprint": None,
    }
    paths = core.Paths(tmp_path, tmp_path / "benchmark.toml", tmp_path / "runs", tmp_path, tmp_path / "history")
    core._materialize_attempt_inputs(paths, spec, cell, attempt_root, attempt)
    assert (workspace / "submit" / "optimization.py").read_text(encoding="utf-8") == "ARM = 'surrogate'\n"
    config_text = (workspace / "config.py").read_text(encoding="utf-8")
    assert "HISTORY_SEGMENT_MAX_CANDIDATES = 100" in config_text
    assert "HISTORY_UNPUBLISHED_MAX_CANDIDATES = 128" in config_text
    assert "OPTIMIZE_SURROGATE_ALPHA = 3" in config_text
    manifest = core.read_json(attempt_root / "input_manifest.json")
    assert manifest["starting_evidence_fingerprint"] == "empty"


def test_seal_marks_mutated_declared_inputs_failed(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    workspace.mkdir(parents=True)
    config = workspace / "config.py"
    config.write_text("VALUE = 1\n", encoding="utf-8")
    before = core.task_fingerprint(workspace, ["config.py"])
    attempt = {
        "attempt": 1,
        "workspace": str(workspace),
        "input_fingerprint": before,
        "post_input_fingerprint": None,
        "status": "running",
        "error": None,
        "sealed_utc": None,
    }
    state = {
        "updated_utc": "",
        "events": [],
        "cells": {"cell": {"status": "running"}},
    }
    config.write_text("VALUE = 2\n", encoding="utf-8")
    core._seal_attempt(
        run_root,
        state,
        {"cell_id": "cell"},
        attempt,
        status="completed",
        include_paths=["config.py"],
    )
    assert attempt["status"] == "failed"
    assert "changed during execution" in attempt["error"]
    assert state["cells"]["cell"]["status"] == "failed"
