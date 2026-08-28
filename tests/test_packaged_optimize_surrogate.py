from __future__ import annotations

import math
import os
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

import pytest
import yadof

from yadof.config import load_config
from yadof.recorded_data import (
    get_historical_results,
    list_optimization_metadata,
    list_records,
)
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
    (root / "config.py").write_text("\n".join(settings) + "\n", encoding="utf-8")
    component_arguments = (
        'device="cpu", epochs=2, ensemble_size=2, batch_size=2, '
        "x_latent_dim=8, field_embedding_dim=4, coordinate_fourier_features=4, "
        "hidden_dim=16, hidden_layers=1, bootstrap_members=False"
        if surrogate
        else ""
    )
    gpsaf_arguments = (
        "alpha=2, beta=1, exploration_fraction=0.0"
        if surrogate
        else "alpha=1, beta=0"
    )
    (root / "submit/optimization.py").write_text(
        "from yadof.optimize import by_objective_count, gpsaf, pymoo_ga, pymoo_nsga3\n"
        "from yadof.surrogate import conditional_inr\n"
        "def build_optimization():\n"
        "    search = by_objective_count(single=pymoo_ga(), multi=pymoo_nsga3())\n"
        f"    surrogate = conditional_inr({component_arguments})\n"
        f"    return gpsaf(search=search, surrogate=surrogate, {gpsaf_arguments})\n",
        encoding="utf-8",
    )
    return root


def _viewer_json(workspace: Path, *arguments: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "yadof",
            "view",
            "surrogate",
            *arguments,
            "--workspace",
            str(workspace),
            "--format",
            "json",
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    json.dumps(payload, allow_nan=False)
    return payload


def _assert_finite_audit_matrices(payload: dict[str, object]) -> None:
    matrices = payload["matrices"]
    assert isinstance(matrices, list)
    assert matrices
    for matrix in matrices:
        assert isinstance(matrix, dict)
        values = matrix["values"]
        assert isinstance(values, list)
        assert values
        for row in values:
            assert isinstance(row, list)
            assert row
            assert all(
                value is not None and math.isfinite(float(value))
                for value in row
            )


def test_surrogate_viewer_orders_mapped_history_by_parameter_declaration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.tools.surrogate_viewer.backend import SurrogateWorkspace
    from yadof.tools.surrogate_viewer.backend import workspace as viewer_workspace

    viewer = object.__new__(SurrogateWorkspace)
    viewer.root = tmp_path
    viewer.parameters = tuple(
        SimpleNamespace(name=name) for name in ("x0", "x1", "x2")
    )
    monkeypatch.setattr(
        viewer_workspace,
        "list_records",
        lambda _workspace: (
            {
                "status": "completed",
                "generation_index": 3,
                "population_index": 4,
                "job_name": "mapped-order",
                "raw_variables": {"x2": 30.0, "x0": 10.0, "x1": 20.0},
            },
            {
                "status": "completed",
                "generation_index": 3,
                "population_index": 5,
                "job_name": "undocumented-sequence",
                "raw_variables": (10.0, 20.0, 30.0),
            },
        ),
    )
    normalized_inputs: list[tuple[float, ...]] = []

    def normalize_variables(
        _workspace: Path,
        raw_values: tuple[float, ...],
    ) -> tuple[float, ...]:
        normalized_inputs.append(raw_values)
        return tuple(value / 100.0 for value in raw_values)

    monkeypatch.setattr(
        viewer_workspace.job_template_api,
        "normalize_variables",
        normalize_variables,
    )

    results = viewer._load_real_results()

    assert normalized_inputs == [(10.0, 20.0, 30.0)]
    assert len(results) == 1
    assert results[0].job_name == "mapped-order"
    assert results[0].raw_values == (10.0, 20.0, 30.0)
    assert results[0].normalized_values == (0.1, 0.2, 0.3)


def test_surrogate_viewer_cli_reports_mapped_history_as_finite_json(
    tmp_path: Path,
) -> None:
    from yadof.optimize import run_one_generation
    from yadof.surrogate import wait_for_pending_training

    workspace = _workspace(tmp_path, "viewer_mapped_history", surrogate=True)
    run_one_generation(
        workspace,
        generation_index=0,
        population_size=2,
        random_seed=47,
    )
    wait_for_pending_training(workspace)
    records = list_records(workspace)
    assert records
    assert all(isinstance(record.get("raw_variables"), dict) for record in records)

    summary = _viewer_json(workspace, "summary")
    cost_audit = _viewer_json(
        workspace,
        "audit",
        "--sample-percent",
        "100",
        "--random-seed",
        "47",
        "--metric",
        "both",
        "--quantity",
        "all-costs",
    )
    rawdata_audit = _viewer_json(
        workspace,
        "audit",
        "--sample-percent",
        "100",
        "--random-seed",
        "47",
        "--metric",
        "both",
        "--quantity",
        "all-rawdata",
    )

    assert summary["schema_version"] == 2
    assert summary["analysis"] == "surrogate_workspace_summary"
    assert summary["optimization_generations"] == [
        {"generation": 0, "completed_results": 2}
    ]
    assert summary["checkpoints"]
    assert cost_audit["schema_version"] == 2
    assert cost_audit["quantity"]["selector"] == "all-costs"
    assert rawdata_audit["schema_version"] == 2
    assert rawdata_audit["quantity"]["selector"] == "all-rawdata"
    _assert_finite_audit_matrices(cost_audit)
    _assert_finite_audit_matrices(rawdata_audit)


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
    from yadof.surrogate import conditional_inr
    from yadof.surrogate.conditional_inr import runtime

    workspace_a = _workspace(tmp_path, "surrogate_a", surrogate=True)
    workspace_b = _workspace(tmp_path, "surrogate_b", surrogate=True)
    component_settings = conditional_inr(
        device="cpu",
        epochs=2,
        ensemble_size=2,
        batch_size=2,
        x_latent_dim=8,
        field_embedding_dim=4,
        coordinate_fourier_features=4,
        hidden_dim=16,
        hidden_layers=1,
        bootstrap_members=False,
    ).settings

    # Warm-up uses real evaluation only because no history/model exists yet.
    run_one_generation(
        workspace_a, generation_index=0, population_size=2, random_seed=37
    )
    from yadof.surrogate import wait_for_pending_training

    wait_for_pending_training(workspace_a)
    assert runtime.has_trained_state(workspace_a, _settings=component_settings)
    assert not runtime.has_trained_state(workspace_b, _settings=component_settings)
    state = runtime._require_state(load_config(workspace_a), component_settings)
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

    before = runtime.predict_population(
        workspace_a, ((0.25,),), _settings=component_settings
    )[0][0][0]
    calc_cost = workspace_a / "submit" / "calc_cost.py"
    calc_cost.write_text(
        calc_cost.read_text(encoding="utf-8").replace(
            "RESPONSE_WORST = 1.0",
            "RESPONSE_WORST = 2.0",
        ),
        encoding="utf-8",
    )
    after = runtime.predict_population(
        workspace_a, ((0.25,),), _settings=component_settings
    )[0][0][0]
    assert after != pytest.approx(before)
    assert 0.0 <= before <= 1.0
    assert 0.0 <= after <= 1.0

    # Drop memory state and prove recovery is from A's checkpoint and current task.
    runtime.reset_workspace_state(workspace_a)
    assert runtime.has_trained_state(workspace_a, _settings=component_settings)
    recovered = runtime.predict_population(
        workspace_a, ((0.25,),), _settings=component_settings
    )[0][0][0]
    assert recovered == pytest.approx(after)
    assert not runtime.has_trained_state(workspace_b, _settings=component_settings)

    # Parameter normalization is semantic state: range edits reject the old model.
    parameter_path = workspace_a / "job_template" / "parameters_constraints.py"
    original_parameters = parameter_path.read_text(encoding="utf-8")
    parameter_path.write_text(
        original_parameters.replace("((-1.0, 1.0),)", "((-2.0, 2.0),)"),
        encoding="utf-8",
    )
    runtime.reset_workspace_state(workspace_a)
    assert not runtime.has_trained_state(workspace_a, _settings=component_settings)
    assert artifact_dir.is_dir()
    parameter_path.write_text(original_parameters, encoding="utf-8")
    runtime.reset_workspace_state(workspace_a)
    assert runtime.has_trained_state(workspace_a, _settings=component_settings)
    assert runtime._require_state(
        load_config(workspace_a), component_settings
    ).artifact_dir == artifact_dir

    # A different train config may publish at the same generation without deleting A.
    changed_settings = conditional_inr(
        device="cpu",
        epochs=2,
        ensemble_size=2,
        batch_size=2,
        x_latent_dim=8,
        field_embedding_dim=4,
        coordinate_fourier_features=4,
        hidden_dim=20,
        hidden_layers=1,
        bootstrap_members=False,
    ).settings
    runtime.reset_workspace_state(workspace_a)
    assert not runtime.has_trained_state(workspace_a, _settings=changed_settings)
    state_b = runtime.train(
        workspace_a, generation_index=0, _settings=changed_settings
    )
    assert state_b.state_signature != manifest["state_signature"]
    assert state_b.artifact_dir != artifact_dir
    assert artifact_dir.is_dir()
    assert state_b.artifact_dir.is_dir()

    # Returning to A recovers A's retained namespaced publication, not B's root pointer.
    runtime.reset_workspace_state(workspace_a)
    assert runtime.has_trained_state(workspace_a, _settings=component_settings)
    returned = runtime._require_state(load_config(workspace_a), component_settings)
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
    from yadof.surrogate import conditional_inr, wait_for_pending_training
    from yadof.surrogate.conditional_inr import runtime
    from yadof.tools.surrogate_viewer.backend.workspace import SurrogateWorkspace

    workspace = _workspace(tmp_path, "strategy_state", surrogate=True)
    optimization_path = workspace / "submit/optimization.py"
    default_source = optimization_path.read_text(encoding="utf-8")
    component_settings = conditional_inr(
        device="cpu",
        epochs=2,
        ensemble_size=2,
        batch_size=2,
        x_latent_dim=8,
        field_embedding_dim=4,
        coordinate_fourier_features=4,
        hidden_dim=16,
        hidden_layers=1,
        bootstrap_members=False,
    ).settings

    run_one_generation(workspace, generation_index=0, random_seed=43)
    wait_for_pending_training(workspace)
    first_active = read_active_strategy_state(workspace)
    assert first_active is not None
    first_model = runtime._require_state(
        load_config(workspace), component_settings
    ).artifact_dir
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
    assert not runtime.has_trained_state(
        workspace, _settings=component_settings
    )
    assert first_model.is_dir()
    with pytest.raises(FileNotFoundError, match="selected strategy may not use"):
        SurrogateWorkspace(workspace)

    optimization_path.write_text(default_source, encoding="utf-8")
    returned = run_one_generation(workspace, generation_index=2, random_seed=43)
    third_active = read_active_strategy_state(workspace)
    assert third_active is not None
    assert third_active.strategy_signature == first_active.strategy_signature
    assert returned.surrogate_used is True
    assert runtime.has_trained_state(workspace, _settings=component_settings)
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
    from yadof.optimize.gpsaf.phases import surrogate_state_ready
    from yadof.surrogate import conditional_inr
    from yadof.surrogate.conditional_inr import runtime
    from yadof.surrogate.conditional_inr.types import TrainingData

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
