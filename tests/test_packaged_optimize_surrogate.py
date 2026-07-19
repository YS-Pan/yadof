from __future__ import annotations

import math
import os
from pathlib import Path

import pytest
import yadof

from yadof.recorded_data import get_historical_results, list_optimization_metadata
from yadof.workspace.init import init_workspace


@pytest.fixture(autouse=True)
def _source_package_for_worker_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    package_parent = Path(yadof.__file__).resolve().parents[1]
    inherited = os.environ.get("PYTHONPATH", "")
    value = str(package_parent)
    if inherited:
        value += os.pathsep + inherited
    monkeypatch.setenv("PYTHONPATH", value)


def _workspace(tmp_path: Path, name: str, *, surrogate: bool = False) -> Path:
    root = tmp_path / name
    init_workspace(root)
    settings = [
        'EVALUATION_MODE = "local"',
        "OPTIMIZE_POPULATION_SIZE = 2",
        "OPTIMIZE_SMOKE_TEST_ENABLED = False",
    ]
    if surrogate:
        settings.extend(
            [
                "OPTIMIZE_SURROGATE_ALPHA = 2",
                "OPTIMIZE_SURROGATE_BETA = 1",
                "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION = 0.0",
                'SURROGATE_TORCH_DEVICE = "cpu"',
                "SURROGATE_INR_EPOCHS = 2",
                "SURROGATE_INR_ENSEMBLE_SIZE = 2",
                "SURROGATE_INR_BATCH_SIZE = 2",
                "SURROGATE_INR_X_LATENT_DIM = 8",
                "SURROGATE_INR_FIELD_EMB_DIM = 4",
                "SURROGATE_INR_COORD_FOURIER_FEATURES = 4",
                "SURROGATE_INR_HIDDEN_DIM = 16",
                "SURROGATE_INR_HIDDEN_LAYERS = 1",
                "SURROGATE_INR_BOOTSTRAP_MEMBERS = False",
            ]
        )
    else:
        settings.extend(
            [
                "OPTIMIZE_SURROGATE_ALPHA = 1",
                "OPTIMIZE_SURROGATE_BETA = 0",
            ]
        )
    (root / "config.py").write_text("\n".join(settings) + "\n", encoding="utf-8")
    return root


def test_packaged_optimizer_recovers_history_without_crossing_workspaces(tmp_path):
    from yadof.optimize import run_one_generation

    workspace_a = _workspace(tmp_path, "optimize_a")
    workspace_b = _workspace(tmp_path, "optimize_b")

    first_a = run_one_generation(
        workspace_a, generation_index=0, population_size=2, random_seed=19
    )
    second_a = run_one_generation(
        workspace_a, generation_index=1, population_size=2, random_seed=19
    )
    first_b = run_one_generation(
        workspace_b, generation_index=0, population_size=2, random_seed=23
    )

    assert first_a.history_count == 0
    assert second_a.history_count == 2
    assert first_b.history_count == 0
    assert len(get_historical_results(workspace_a)) == 4
    assert len(get_historical_results(workspace_b)) == 2
    assert len(list_optimization_metadata(workspace_a)) == 0
    assert len(list_optimization_metadata(workspace_b)) == 0
    assert not (workspace_a / ".yadof" / "surrogate" / "checkpoints").exists()
    assert not (workspace_b / ".yadof" / "surrogate" / "checkpoints").exists()


def test_packaged_run_generations_records_workspace_local_metadata(tmp_path):
    from yadof.optimize import run_generations

    workspace = _workspace(tmp_path, "generation_metadata")
    results = run_generations(
        workspace,
        2,
        population_size=2,
        random_seed=31,
        run_id="workspace_run",
    )

    rows = list_optimization_metadata(workspace)
    assert len(results) == 2
    assert [row["generation_index"] for row in rows] == [0, 1]
    assert all(row["run_id"] == "workspace_run" for row in rows)
    assert all("costs" not in row and "population" not in row for row in rows)


def test_packaged_optimizer_keeps_individual_failures_as_infinite_costs(tmp_path):
    from yadof.optimize import run_one_generation

    workspace = _workspace(tmp_path, "failing_generation")
    workflow = workspace / "job_template" / "workflow.py"
    workflow.write_text(
        "raise RuntimeError('synthetic workflow failure')\n", encoding="utf-8"
    )

    result = run_one_generation(
        workspace, generation_index=0, population_size=2, random_seed=7
    )

    assert len(result.costs) == 2
    assert all(len(row) == 1 and math.isinf(row[0]) for row in result.costs)


def test_surrogate_state_checkpoint_and_cost_policy_are_workspace_scoped(tmp_path):
    pytest.importorskip("torch")

    from yadof.optimize import run_one_generation
    from yadof.surrogate import runtime

    workspace_a = _workspace(tmp_path, "surrogate_a", surrogate=True)
    workspace_b = _workspace(tmp_path, "surrogate_b", surrogate=True)

    # Warm-up uses real evaluation only because no history/model exists yet.
    run_one_generation(
        workspace_a, generation_index=0, population_size=2, random_seed=37
    )
    from yadof.surrogate import wait_for_pending_training

    wait_for_pending_training(workspace_a)
    assert runtime.has_trained_state(workspace_a)
    assert not runtime.has_trained_state(workspace_b)

    checkpoint_dir_a = workspace_a / ".yadof" / "surrogate" / "checkpoints"
    checkpoint_dir_b = workspace_b / ".yadof" / "surrogate" / "checkpoints"
    assert checkpoint_dir_a.joinpath("generation_0000.json").is_file()
    assert not checkpoint_dir_b.exists()

    before = runtime.predict_population(workspace_a, ((0.25,),))[0][0][0]
    calc_cost = workspace_a / "job_template" / "calc_cost.py"
    calc_cost.write_text(
        calc_cost.read_text(encoding="utf-8").replace(
            "return (float(value.item()),)",
            "return (10.0 * float(value.item()),)",
        ),
        encoding="utf-8",
    )
    after = runtime.predict_population(workspace_a, ((0.25,),))[0][0][0]
    assert after == pytest.approx(before * 10.0)

    # Drop memory state and prove recovery is from A's checkpoint and current task.
    runtime.reset_workspace_state(workspace_a)
    assert runtime.has_trained_state(workspace_a)
    recovered = runtime.predict_population(workspace_a, ((0.25,),))[0][0][0]
    assert recovered == pytest.approx(after)
    assert not runtime.has_trained_state(workspace_b)


def test_packaged_optimize_and_surrogate_have_no_project_namespace_imports():
    package_root = Path(__file__).resolve().parents[1] / "src" / "yadof"
    for module_dir in (package_root / "optimize", package_root / "surrogate"):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in module_dir.glob("*.py")
        )
        assert "project." not in source
