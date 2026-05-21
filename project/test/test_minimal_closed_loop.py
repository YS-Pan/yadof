from __future__ import annotations

from pathlib import Path
import shutil
import sys
import types

import numpy as np


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


def test_optimize_uses_history_then_calls_evaluate_manager(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    evaluate_pkg = _module(monkeypatch, "project.evaluate_manager")
    evaluate_api = _module(monkeypatch, "project.evaluate_manager.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(evaluate_pkg, "api", evaluate_api, raising=False)

    recorded_api.get_optimization_history = lambda: (
        ("job_bad", (0.9, 0.9), (10.0,)),
        ("job_good", (0.2, 0.3), (1.0,)),
    )
    seen = {}

    def evaluate_generation(population):
        seen["population"] = population
        return tuple((sum(individual),) for individual in population)

    evaluate_api.evaluate_generation = evaluate_generation

    from project.optimize.api import run_one_generation

    result = run_one_generation(population_size=2, variable_count=2, random_seed=7)

    assert result.source == "gpsaf_warm_start"
    assert result.surrogate_used is False
    assert result.history_count == 2
    assert seen["population"][0] == (0.2, 0.3)
    assert result.costs == ((0.5,), (1.8,))


def test_optimize_random_generation_when_history_empty(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    evaluate_pkg = _module(monkeypatch, "project.evaluate_manager")
    evaluate_api = _module(monkeypatch, "project.evaluate_manager.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(evaluate_pkg, "api", evaluate_api, raising=False)

    recorded_api.get_optimization_history = lambda: ()
    evaluate_api.evaluate_generation = lambda population: tuple((1.0,) for _ in population)

    from project.optimize.api import run_one_generation

    result = run_one_generation(population_size=3, variable_count=2, random_seed=3)

    assert result.source == "gpsaf_random"
    assert result.surrogate_used is False
    assert len(result.population) == 3
    assert all(len(individual) == 2 for individual in result.population)
    assert result.costs == ((1.0,), (1.0,), (1.0,))


def test_default_optimize_does_not_call_surrogate(monkeypatch):
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
        ("job_a", (0.1, 0.2), (0.5,)),
        ("job_b", (0.7, 0.8), (1.5,)),
    )
    evaluate_api.evaluate_generation = lambda population: tuple((sum(row),) for row in population)

    def fail_train(*_args, **_kwargs):
        raise AssertionError("surrogate should be disabled by default")

    surrogate_api.train = fail_train

    from project import config
    from project.optimize.api import run_one_generation

    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_ALPHA", 1)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_BETA", 0)
    result = run_one_generation(population_size=2, random_seed=5)

    assert result.surrogate_used is False
    assert result.source == "gpsaf_warm_start"


def test_surrogate_raw_data_to_cost_shape_and_checkpoint(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    job_template_pkg = _module(monkeypatch, "project.job_template")
    job_template_api = _module(monkeypatch, "project.job_template.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(job_template_pkg, "api", job_template_api, raising=False)

    raw_samples = (
        ({"rawData": (1.0, 2.0), "metadata": {"source": "test_com"}},),
        ({"rawData": (3.0, 4.0), "metadata": {"source": "test_com"}},),
    )
    recorded_api.get_surrogate_training_data = lambda: {
        "parameter_names": ("x", "y"),
        "normalized_variables": ((0.1, 0.2), (0.8, 0.9)),
        "raw_data": raw_samples,
    }

    def calculate_costs_from_raw_data(samples):
        costs = []
        for sample in samples:
            item = sample[0]
            values = item["rawData"]
            costs.append((sum(values),))
        return tuple(costs)

    job_template_api.calculate_costs_from_raw_data = calculate_costs_from_raw_data

    from project import config
    from project.surrogate import runtime

    checkpoint_dir = Path.cwd() / "project" / "test" / "_pytest_tmp" / "surrogate_checkpoints"
    if checkpoint_dir.is_dir():
        shutil.rmtree(checkpoint_dir)
    monkeypatch.setattr(config, "SURROGATE_CHECKPOINT_DIR", checkpoint_dir)
    _configure_fast_inr(monkeypatch, config)
    runtime._STATE = None
    monkeypatch.setattr(
        runtime,
        "_predict_costs_for_error_audit",
        lambda _state, _x: ((4.0,), (9.0,)),
    )

    state = runtime.train(generation_index=5)
    monkeypatch.setattr(
        runtime,
        "_predict_member_flats",
        lambda _state, _x: np.asarray(
            [
                [[1.0, 2.0], [3.0, 4.0]],
                [[1.0, 2.0], [3.0, 4.0]],
            ],
            dtype=float,
        ),
    )
    predictions = runtime.predict_population(((0.12, 0.18), (0.75, 0.85)))
    errors = runtime.evaluate_historical_errors()

    assert state.checkpoint_path.is_file()
    assert predictions[0][0] == (3.0,)
    assert predictions[1][0] == (7.0,)
    assert predictions[0][1] == ((3.0, 3.0),)
    assert errors == ((1.0 / 3.0,), (2.0 / 7.0,))
    assert state.mean_relative_error > 0.0
    assert state.historical_relative_error_p90


def test_surrogate_interval_is_member_cost_min_max(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    job_template_pkg = _module(monkeypatch, "project.job_template")
    job_template_api = _module(monkeypatch, "project.job_template.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(job_template_pkg, "api", job_template_api, raising=False)

    raw_samples = (
        ({"rawData": (1.0, 2.0), "metadata": {"source": "low"}},),
        ({"rawData": (5.0, 8.0), "metadata": {"source": "high"}},),
    )
    recorded_api.get_surrogate_training_data = lambda: {
        "parameter_names": ("x", "y"),
        "normalized_variables": ((0.0, 0.0), (1.0, 1.0)),
        "raw_data": raw_samples,
    }
    job_template_api.calculate_costs_from_raw_data = lambda samples: tuple(
        (float(sum(sample[0]["rawData"])),) for sample in samples
    )

    from project import config
    from project.surrogate import runtime

    checkpoint_dir = Path.cwd() / "project" / "test" / "_pytest_tmp" / "surrogate_member_interval"
    if checkpoint_dir.is_dir():
        shutil.rmtree(checkpoint_dir)
    monkeypatch.setattr(config, "SURROGATE_CHECKPOINT_DIR", checkpoint_dir)
    _configure_fast_inr(monkeypatch, config)
    runtime._STATE = None
    runtime.train(generation_index=6)
    monkeypatch.setattr(
        runtime,
        "_predict_member_flats",
        lambda _state, _x: np.asarray([[[1.0, 2.0]], [[2.0, 4.0]]], dtype=float),
    )

    prediction = runtime.predict_population(((0.5, 0.5),))[0]

    assert prediction[0] == (4.5,)
    assert prediction[1] == ((3.0, 6.0),)
