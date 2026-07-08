from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import types


def _module(monkeypatch, name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _configure_fast_inr(monkeypatch, config) -> None:
    monkeypatch.setattr(config, "SURROGATE_TORCH_DEVICE", "cpu")
    monkeypatch.setattr(config, "SURROGATE_INR_EPOCHS", 8)
    monkeypatch.setattr(config, "SURROGATE_INR_ENSEMBLE_SIZE", 2)
    monkeypatch.setattr(config, "SURROGATE_INR_BATCH_SIZE", 4)
    monkeypatch.setattr(config, "SURROGATE_INR_X_LATENT_DIM", 8)
    monkeypatch.setattr(config, "SURROGATE_INR_FIELD_EMB_DIM", 4)
    monkeypatch.setattr(config, "SURROGATE_INR_COORD_FOURIER_FEATURES", 4)
    monkeypatch.setattr(config, "SURROGATE_INR_HIDDEN_DIM", 16)
    monkeypatch.setattr(config, "SURROGATE_INR_HIDDEN_LAYERS", 1)
    monkeypatch.setattr(config, "SURROGATE_INR_BOOTSTRAP_MEMBERS", False)


def test_surrogate_predicts_rawdata_then_costs_and_writes_conditional_inr_checkpoint(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    job_template_pkg = _module(monkeypatch, "project.job_template")
    job_template_api = _module(monkeypatch, "project.job_template.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(job_template_pkg, "api", job_template_api, raising=False)

    raw_samples = (
        ({"rawData": (0.0, 0.0), "metadata": {"source": "low"}},),
        ({"rawData": (10.0, 10.0), "metadata": {"source": "high"}},),
    )
    recorded_api.get_surrogate_training_data = lambda: {
        "parameter_names": ("x", "y"),
        "normalized_variables": ((0.1, 0.1), (0.9, 0.9)),
        "raw_data": raw_samples,
    }
    cost_calls = []

    def calculate_costs_from_raw_data(samples):
        cost_calls.append(samples)
        return tuple((100.0 + float(sum(sample[0]["rawData"])),) for sample in samples)

    job_template_api.calculate_costs_from_raw_data = calculate_costs_from_raw_data

    from project import config
    from project.surrogate import runtime

    checkpoint_dir = Path.cwd() / "project" / "test" / "_pytest_tmp" / "surrogate_interpolation"
    if checkpoint_dir.is_dir():
        shutil.rmtree(checkpoint_dir)
    monkeypatch.setattr(config, "SURROGATE_CHECKPOINT_DIR", checkpoint_dir)
    _configure_fast_inr(monkeypatch, config)
    runtime._STATE = None

    state = runtime.train(generation_index=2)
    prediction = runtime.predict_population(((0.5, 0.5),))[0]
    checkpoint = json.loads(state.checkpoint_path.read_text(encoding="utf-8"))

    assert state.model_path.is_file()
    assert state.artifact_dir.is_dir()
    assert checkpoint["model"] == "conditional_inr_rawdata_deep_ensemble"
    assert checkpoint["model"] == state.model_name
    assert checkpoint["model_path"] == state.model_path.name
    assert any(len(call) == 1 for call in cost_calls)
    assert 100.0 <= prediction[0][0] <= 120.0
    assert prediction[1][0][0] <= prediction[1][0][1]


def test_surrogate_parameters_use_gpsaf_surrogate(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    evaluate_pkg = _module(monkeypatch, "project.evaluate_manager")
    evaluate_api = _module(monkeypatch, "project.evaluate_manager.api")
    job_template_pkg = _module(monkeypatch, "project.job_template")
    job_template_api = _module(monkeypatch, "project.job_template.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(evaluate_pkg, "api", evaluate_api, raising=False)
    monkeypatch.setattr(job_template_pkg, "api", job_template_api, raising=False)

    history = (
        ("job_a", (0.10, 0.10), (1.0,)),
        ("job_b", (0.35, 0.30), (0.2,)),
        ("job_c", (0.70, 0.65), (0.8,)),
        ("job_d", (0.90, 0.90), (1.4,)),
    )
    raw_samples = tuple(
        ({"rawData": (costs[0],), "metadata": {"source": job_name}},)
        for job_name, _x, costs in history
    )
    recorded_api.get_optimization_history = lambda: history
    recorded_api.get_surrogate_training_data = lambda: {
        "parameter_names": ("x", "y"),
        "normalized_variables": tuple(x for _job_name, x, _costs in history),
        "raw_data": raw_samples,
    }
    job_template_api.calculate_costs_from_raw_data = lambda samples: tuple(
        (float(sample[0]["rawData"][0]),) for sample in samples
    )

    seen = {}

    def evaluate_generation(population):
        seen["population"] = population
        return tuple((sum(individual),) for individual in population)

    evaluate_api.evaluate_generation = evaluate_generation

    from project import config
    from project.surrogate import runtime

    checkpoint_dir = Path.cwd() / "project" / "test" / "_pytest_tmp" / "optimize_gpsaf_surrogate"
    if checkpoint_dir.is_dir():
        shutil.rmtree(checkpoint_dir)
    monkeypatch.setattr(config, "SURROGATE_CHECKPOINT_DIR", checkpoint_dir)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_ALPHA", 2)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_BETA", 1)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_GAMMA", 0.5)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION", 0.0)
    _configure_fast_inr(monkeypatch, config)
    runtime._STATE = None
    runtime.train(generation_index=2)

    from project.optimize.api import run_one_generation
    from project.surrogate.api import wait_for_pending_training

    result = run_one_generation(generation_index=3, population_size=2, random_seed=42)
    wait_for_pending_training()

    assert result.source == "gpsaf_surrogate"
    assert result.surrogate_used is True
    assert result.history_count == 4
    assert result.population == seen["population"]
    assert result.population != ((0.35, 0.30), (0.70, 0.65))
    assert result.diagnostics["alpha_batches"] == 2
    assert result.diagnostics["alpha_selection"] == "nsga3_pooled_survival"
    assert result.diagnostics["beta_iterations"] == 1
    assert result.diagnostics["beta_selection"] == "nsga3_pooled_survival"
    assert result.diagnostics["beta_cluster_size_max"] >= 1
    assert len(result.diagnostics["beta_cluster_sizes"]) == 2
    assert checkpoint_dir.joinpath("generation_0003.json").is_file()


def test_gpsaf_parameters_call_surrogate(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    evaluate_pkg = _module(monkeypatch, "project.evaluate_manager")
    evaluate_api = _module(monkeypatch, "project.evaluate_manager.api")
    surrogate_pkg = _module(monkeypatch, "project.surrogate")
    surrogate_api = _module(monkeypatch, "project.surrogate.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(evaluate_pkg, "api", evaluate_api, raising=False)
    monkeypatch.setattr(surrogate_pkg, "api", surrogate_api, raising=False)

    history = (
        ("job_a", (0.10, 0.10), (1.0,)),
        ("job_b", (0.35, 0.30), (0.2,)),
        ("job_c", (0.70, 0.65), (0.8,)),
    )
    calls = {"train": 0}
    recorded_api.get_optimization_history = lambda: history
    evaluate_api.evaluate_generation = lambda population: tuple((sum(individual),) for individual in population)
    surrogate_api.predict_population = lambda population: tuple(
        ((sum(individual),), ((sum(individual) - 0.1, sum(individual) + 0.1),))
        for individual in population
    )
    surrogate_api.evaluate_historical_errors = lambda: ((0.05,),)

    def train(**_kwargs):
        calls["train"] += 1
        return object()

    surrogate_api.train = train

    from project import config
    from project.optimize.api import run_one_generation

    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_ALPHA", 2)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_BETA", 1)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_EXPLORATION_FRACTION", 0.0)
    result = run_one_generation(generation_index=2, population_size=2, random_seed=11)

    assert calls["train"] == 1
    assert result.source == "gpsaf_surrogate"
    assert result.surrogate_used is True
    assert result.diagnostics["alpha_batches"] == 2
    assert result.diagnostics["beta_iterations"] == 1


def test_gpsaf_falls_back_when_surrogate_is_unavailable(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    evaluate_pkg = _module(monkeypatch, "project.evaluate_manager")
    evaluate_api = _module(monkeypatch, "project.evaluate_manager.api")
    surrogate_pkg = _module(monkeypatch, "project.surrogate")
    surrogate_api = _module(monkeypatch, "project.surrogate.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(evaluate_pkg, "api", evaluate_api, raising=False)
    monkeypatch.setattr(surrogate_pkg, "api", surrogate_api, raising=False)

    recorded_api.get_optimization_history = lambda: (
        ("job_bad", (0.9, 0.9), (10.0,)),
        ("job_good", (0.2, 0.3), (1.0,)),
    )
    surrogate_api.has_trained_state = lambda: False
    surrogate_api.train = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("model offline"))
    evaluate_api.evaluate_generation = lambda population: tuple((sum(individual),) for individual in population)

    from project import config
    from project.optimize.api import run_one_generation

    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_ALPHA", 2)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_BETA", 0)
    result = run_one_generation(population_size=2, random_seed=7)

    assert result.source == "gpsaf_warm_start"
    assert result.surrogate_used is False
    assert result.population[0] == (0.2, 0.3)
    assert result.diagnostics["surrogate_error"] == "no_trained_surrogate"
    assert result.diagnostics["surrogate_mode"] == "waiting_for_first_staggered_training"


def test_gpsaf_entrypoint_stays_small():
    from project.optimize import gpsaf

    path = Path(gpsaf.__file__)
    assert len(path.read_text(encoding="utf-8").splitlines()) < 160
    assert path.stat().st_size < 7000
