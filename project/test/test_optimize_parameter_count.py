from __future__ import annotations

import sys
import types


def _module(monkeypatch, name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _install_empty_history_and_capture_evaluate(monkeypatch):
    recorded_pkg = _module(monkeypatch, "project.recorded_data")
    recorded_api = _module(monkeypatch, "project.recorded_data.api")
    evaluate_pkg = _module(monkeypatch, "project.evaluate_manager")
    evaluate_api = _module(monkeypatch, "project.evaluate_manager.api")
    monkeypatch.setattr(recorded_pkg, "api", recorded_api, raising=False)
    monkeypatch.setattr(evaluate_pkg, "api", evaluate_api, raising=False)

    recorded_api.get_optimization_history = lambda: ()
    seen = {}

    def evaluate_generation(population):
        seen["population"] = population
        return tuple((1.0,) for _ in population)

    evaluate_api.evaluate_generation = evaluate_generation
    return seen


def _install_job_template_info(monkeypatch, names: tuple[str, ...], objective_names: tuple[str, ...] = ("cost",)):
    job_template_pkg = _module(monkeypatch, "project.job_template")
    job_template_api = _module(monkeypatch, "project.job_template.api")
    monkeypatch.setattr(job_template_pkg, "api", job_template_api, raising=False)
    calls = {"get_variable_count": 0, "get_objective_count": 0, "get_objective_names": 0}

    def get_variable_count():
        calls["get_variable_count"] += 1
        return len(names)

    def get_objective_count():
        calls["get_objective_count"] += 1
        return len(objective_names)

    def get_objective_names():
        calls["get_objective_names"] += 1
        return objective_names

    job_template_api.get_parameter_names = lambda: names
    job_template_api.get_variable_count = get_variable_count
    job_template_api.get_objective_count = get_objective_count
    job_template_api.get_objective_names = get_objective_names
    return calls


def test_random_generation_width_uses_job_template_parameter_count(monkeypatch):
    seen = _install_empty_history_and_capture_evaluate(monkeypatch)
    calls = _install_job_template_info(monkeypatch, ("p0", "p1", "p2", "p3", "p4"))

    from project.optimize.api import run_one_generation

    result = run_one_generation(population_size=3, random_seed=11)

    assert result.source == "gpsaf_random"
    assert result.population == seen["population"]
    assert len(result.population) == 3
    assert all(len(individual) == 5 for individual in result.population)
    assert calls == {"get_variable_count": 1, "get_objective_count": 1, "get_objective_names": 1}


def test_explicit_variable_count_overrides_job_template_parameter_count(monkeypatch):
    seen = _install_empty_history_and_capture_evaluate(monkeypatch)
    calls = _install_job_template_info(monkeypatch, ("p0", "p1", "p2", "p3", "p4"))

    from project.optimize.api import run_one_generation

    result = run_one_generation(population_size=2, variable_count=2, random_seed=13)

    assert result.source == "gpsaf_random"
    assert result.population == seen["population"]
    assert len(result.population) == 2
    assert all(len(individual) == 2 for individual in result.population)
    assert calls == {"get_variable_count": 1, "get_objective_count": 1, "get_objective_names": 1}


def test_default_job_template_width_matches_current_antenna_task():
    from project.job_template import api as job_template_api

    assert job_template_api.get_variable_count() == 19
    assert job_template_api.get_parameter_names() == (
        "dipole_gap",
        "dipole_l",
        "dipole_post_xposi",
        "dipole_w",
        "feedline1_l",
        "feedline1_w",
        "feedline2_xposi",
        "feedline2_yposi",
        "slot_l",
        "slot_w",
        "strip_l",
        "strip_w",
        "top_sub_zposi",
        "yagi_l1",
        "yagi_l2",
        "yagi_w",
        "yagi_w2",
        "yagi_xmove",
        "yagi_yposi",
    )
    assert job_template_api.get_objective_count() == 3
    assert job_template_api.get_objective_names() == (
        "cost_s11_band",
        "cost_gain_lhcp_targets",
        "cost_axial_ratio_targets",
    )


def test_config_no_longer_owns_problem_shape():
    from project import config_all as config

    assert not hasattr(config, "OPTIMIZE_VARIABLE_COUNT")
    assert not hasattr(config, "OPTIMIZE_OBJECTIVE_COUNT")
    assert not hasattr(config, "OPTIMIZE_NSGA3_P_CAP")
    assert not hasattr(config, "OPTIMIZE_NSGA3_DIM_MUT_PER_INDIVIDUAL")
    assert not hasattr(config, "OPTIMIZE_SURROGATE_ENABLED")


def test_standalone_nsga3_entrypoint_is_removed():
    from pathlib import Path

    optimize_dir = Path(__file__).resolve().parents[1] / "optimize"
    assert not optimize_dir.joinpath("nsga3.py").exists()
    assert not optimize_dir.joinpath("nsga3_misc.py").exists()
