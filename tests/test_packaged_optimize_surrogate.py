from __future__ import annotations

import math
import os
import json
from pathlib import Path

import numpy as np

import pytest
import yadof

from yadof.config import load_config
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
    assert len(list_optimization_metadata(workspace_a)) == 2
    assert len(list_optimization_metadata(workspace_b)) == 1
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
    state = runtime._require_state(load_config(workspace_a))
    assert state.train_history["training_policy"] == "real_field_balanced"
    assert "mixup" not in state.train_history
    assert "relative" not in state.train_history

    checkpoint_dir_a = workspace_a / ".yadof" / "surrogate" / "checkpoints"
    checkpoint_dir_b = workspace_b / ".yadof" / "surrogate" / "checkpoints"
    assert checkpoint_dir_a.joinpath("generation_0000.json").is_file()
    assert not checkpoint_dir_b.exists()
    manifest = json.loads(
        checkpoint_dir_a.joinpath("generation_0000.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["format_version"] == 2
    assert manifest["surrogate_method"] == "conditional_inr"
    assert manifest["training_policy"] == "real_field_balanced"
    assert len(manifest["state_signature"]) == 64
    assert len(manifest["strategy_signature"]) == 64
    assert manifest["run_namespace"].startswith("strategy-")
    assert manifest["component_namespace"] == "conditional-inr"
    namespace_manifest = checkpoint_dir_a / manifest["namespace_manifest"]
    artifact_dir = checkpoint_dir_a / manifest["artifact_dir"]
    assert json.loads(namespace_manifest.read_text(encoding="utf-8")) == manifest
    with np.load(artifact_dir / manifest["model_path"], allow_pickle=False) as auxiliary:
        assert "query_weights" not in auxiliary.files
        assert "training_flat_values" not in auxiliary.files

    before = runtime.predict_population(workspace_a, ((0.25,),))[0][0][0]
    calc_cost = workspace_a / "submit" / "calc_cost.py"
    calc_cost.write_text(
        calc_cost.read_text(encoding="utf-8").replace(
            "RESPONSE_WORST = 1.0",
            "RESPONSE_WORST = 2.0",
        ),
        encoding="utf-8",
    )
    after = runtime.predict_population(workspace_a, ((0.25,),))[0][0][0]
    assert after != pytest.approx(before)
    assert 0.0 <= before <= 1.0
    assert 0.0 <= after <= 1.0

    # Drop memory state and prove recovery is from A's checkpoint and current task.
    runtime.reset_workspace_state(workspace_a)
    assert runtime.has_trained_state(workspace_a)
    recovered = runtime.predict_population(workspace_a, ((0.25,),))[0][0][0]
    assert recovered == pytest.approx(after)
    assert not runtime.has_trained_state(workspace_b)

    # Parameter normalization is semantic state: range edits reject the old model.
    parameter_path = workspace_a / "job_template" / "parameters_constraints.py"
    original_parameters = parameter_path.read_text(encoding="utf-8")
    parameter_path.write_text(
        original_parameters.replace("((-1.0, 1.0),)", "((-2.0, 2.0),)"),
        encoding="utf-8",
    )
    runtime.reset_workspace_state(workspace_a)
    assert not runtime.has_trained_state(workspace_a)
    assert artifact_dir.is_dir()
    parameter_path.write_text(original_parameters, encoding="utf-8")
    runtime.reset_workspace_state(workspace_a)
    assert runtime.has_trained_state(workspace_a)
    assert runtime._require_state(load_config(workspace_a)).artifact_dir == artifact_dir

    # A different train config may publish at the same generation without deleting A.
    config_path = workspace_a / "config.py"
    original_config = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        original_config.replace(
            "SURROGATE_INR_HIDDEN_DIM = 16",
            "SURROGATE_INR_HIDDEN_DIM = 20",
        ),
        encoding="utf-8",
    )
    runtime.reset_workspace_state(workspace_a)
    assert not runtime.has_trained_state(workspace_a)
    state_b = runtime.train(workspace_a, generation_index=0)
    assert state_b.state_signature != manifest["state_signature"]
    assert state_b.artifact_dir != artifact_dir
    assert artifact_dir.is_dir()
    assert state_b.artifact_dir.is_dir()

    # Returning to A recovers A's retained namespaced publication, not B's root pointer.
    config_path.write_text(original_config, encoding="utf-8")
    runtime.reset_workspace_state(workspace_a)
    assert runtime.has_trained_state(workspace_a)
    returned = runtime._require_state(load_config(workspace_a))
    assert returned.state_signature == manifest["state_signature"]
    assert returned.artifact_dir == artifact_dir

    # Viewer validates B against B's persisted config even while current training config is A.
    from yadof.tools.surrogate_viewer.backend.checkpoints import (
        CheckpointPredictor,
        discover_checkpoints,
    )

    visible = discover_checkpoints(checkpoint_dir_a)
    assert len(visible) == 1
    assert visible[0].payload["state_signature"] == state_b.state_signature
    template_sample = runtime._load_training_data(
        load_config(workspace_a).workspace
    ).raw_data[0]
    viewer_predictor = CheckpointPredictor(
        workspace_a,
        visible[0],
        template_sample,
    )
    assert viewer_predictor.train_cfg.hidden_dim == 20
    _samples, viewer_costs, _members = viewer_predictor.predict(((0.25,),))
    assert len(viewer_costs) == 1


def test_strategy_switch_isolates_and_recovers_conditional_inr_weights(
    tmp_path: Path,
) -> None:
    from yadof.optimize import run_one_generation
    from yadof.optimize.state import read_active_strategy_state
    from yadof.surrogate import runtime, wait_for_pending_training
    from yadof.tools.surrogate_viewer.backend.workspace import SurrogateWorkspace

    workspace = _workspace(tmp_path, "strategy_state", surrogate=True)
    optimization_path = workspace / "submit/optimization.py"
    default_source = optimization_path.read_text(encoding="utf-8")

    run_one_generation(workspace, generation_index=0, random_seed=43)
    wait_for_pending_training(workspace)
    first_active = read_active_strategy_state(workspace)
    assert first_active is not None
    first_model = runtime._require_state(load_config(workspace)).artifact_dir
    assert first_model.is_dir()

    optimization_path.write_text(
        "from yadof.optimize import pymoo_ga, real_search\n"
        "def build_optimization():\n"
        "    return real_search(search=pymoo_ga())\n",
        encoding="utf-8",
    )
    run_one_generation(workspace, generation_index=1, random_seed=43)
    second_active = read_active_strategy_state(workspace)
    assert second_active is not None
    assert second_active.strategy_signature != first_active.strategy_signature
    assert not runtime.has_trained_state(workspace)
    assert first_model.is_dir()
    with pytest.raises(FileNotFoundError, match="selected strategy may not use"):
        SurrogateWorkspace(workspace)

    optimization_path.write_text(default_source, encoding="utf-8")
    returned = run_one_generation(workspace, generation_index=2, random_seed=43)
    third_active = read_active_strategy_state(workspace)
    assert third_active is not None
    assert third_active.strategy_signature == first_active.strategy_signature
    assert returned.surrogate_used is True
    assert runtime.has_trained_state(workspace)
    assert first_model.is_dir()
    wait_for_pending_training(workspace)


@pytest.mark.parametrize(
    "raw_rows",
    [
        ((0.0, np.asarray([1.0])),),
        (
            (0.0, np.asarray([1.0])),
            (1.0, np.asarray([1.0])),
        ),
    ],
    ids=("one-sample", "constant-rawdata"),
)
def test_nontrainable_surrogate_attempt_never_becomes_optimizer_ready(
    tmp_path: Path,
    raw_rows,
) -> None:
    from yadof.optimize.gpsaf_phases import surrogate_state_ready
    from yadof.surrogate import conditional_inr
    from yadof.surrogate import runtime
    from yadof.surrogate.types import TrainingData

    workspace = _workspace(tmp_path, "not_trainable", surrogate=True)
    data = TrainingData(
        parameter_names=("input_value",),
        normalized_variables=tuple((float(x),) for x, _values in raw_rows),
        raw_data=tuple(
            ({"data": values.copy()},)
            for _x, values in raw_rows
        ),
    )
    state = runtime.train_with_config(
        load_config(workspace),
        generation_index=0,
        training_data=data,
    )

    assert state.train_history["skipped"] is True
    assert state.model is None
    assert not runtime.has_trained_state(workspace)
    component_context = type(
        "ComponentContext",
        (),
        {"config": load_config(workspace)},
    )()
    assert not surrogate_state_ready(conditional_inr(), component_context)
    with pytest.raises(RuntimeError, match="not trained"):
        runtime.predict_population(workspace, ((0.5,),))


def test_packaged_optimize_and_surrogate_have_no_project_namespace_imports():
    package_root = Path(__file__).resolve().parents[1] / "src" / "yadof"
    for module_dir in (package_root / "optimize", package_root / "surrogate"):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in module_dir.glob("*.py")
        )
        assert "project." not in source
