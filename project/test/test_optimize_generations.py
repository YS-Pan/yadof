from __future__ import annotations

import sys
import types


def _module(monkeypatch, name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_run_generations_calls_evaluate_and_writes_lightweight_metadata(monkeypatch, tmp_path):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    evaluate_pkg = _module(monkeypatch, "project.evaluate_manager")
    evaluate_api = _module(monkeypatch, "project.evaluate_manager.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(evaluate_pkg, "api", evaluate_api, raising=False)

    history = []
    evaluate_calls = []
    opt_meta_rows = []

    def get_optimization_history():
        return tuple(history)

    def get_job_names():
        return tuple(job_name for job_name, _x, _costs in history)

    def evaluate_generation(population):
        evaluate_calls.append(population)
        costs = tuple((sum(row),) for row in population)
        for idx, (row, cost) in enumerate(zip(population, costs)):
            history.append((f"job_{len(history):03d}_{idx}", tuple(row), cost))
        return costs

    recorded_api.get_optimization_history = get_optimization_history
    recorded_api.get_job_names = get_job_names
    recorded_api.record_optimization_metadata = lambda metadata: opt_meta_rows.append(dict(metadata)) or dict(metadata)
    evaluate_api.evaluate_generation = evaluate_generation

    from project import config
    from project.optimize.api import run_generations

    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_ALPHA", 1)
    monkeypatch.setattr(config, "OPTIMIZE_SURROGATE_BETA", 0)
    results = run_generations(
        2,
        population_size=2,
        variable_count=2,
        random_seed=17,
        run_id="pytest_run",
    )

    assert len(results) == 2
    assert len(evaluate_calls) == 2
    assert results[0].source == "gpsaf_random"
    assert results[1].source == "gpsaf_offspring"

    assert len(opt_meta_rows) == 2
    first, second = opt_meta_rows

    assert first["record_type"] == "generation"
    assert first["run_id"] == "pytest_run"
    assert first["source"] == "gpsaf_random"
    assert second["source"] == "gpsaf_offspring"
    assert first["population_size"] == 2
    assert len(first["created_job_names"]) == 2
    assert "costs" not in first
    assert "costs" not in second
    assert "population" not in first
