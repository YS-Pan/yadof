from contextlib import contextmanager
from dataclasses import replace
import math
from types import SimpleNamespace

import pytest

from yadof.config import load_config
from yadof.job_template import get_parameter_names, get_objective_count
from yadof.recorded_data import list_records
from yadof.surrogate import SurrogateContractError, SurrogateTrainingData
from yadof.task_snapshot import create_generation_snapshot
from yadof_benchmark import discover_baselines, init_workspace, plan_workspace
from yadof_benchmark.benchmark_runtime.baselines import materialize_baseline
from yadof_benchmark import perfect_oracle as oracle_module
from yadof_benchmark.perfect_oracle import PerfectSimulationOracle
from yadof_benchmark.perfect_protocol import top10, record_generation, collect_top10
from yadof_benchmark.benchmark_runtime.storage import atomic_write_json, read_json


@pytest.fixture
def oracle_context(tmp_path):
    materialize_baseline(discover_baselines()["test-com/synthetic-antenna"], tmp_path / "cell")
    workspace = tmp_path / "cell/workspace"
    with (workspace / "config.py").open("a", encoding="utf-8") as stream:
        stream.write("\nFAST_EVALUATION_MAX_WORKERS = 2\n")
    snapshot = create_generation_snapshot(load_config(workspace))
    context = SimpleNamespace(config=snapshot.config, snapshot=snapshot,
        problem=SimpleNamespace(objective_count=get_objective_count(snapshot.config.workspace)),
        generation_index=1, optimization_index=0, run_id="oracle-test")
    try:
        yield context
    finally:
        snapshot.close()


def _inputs(context):
    names = get_parameter_names(context.config.workspace)
    return SurrogateTrainingData(names, (), ()), ((0.5,) * len(names), (0.25,) * len(names))


def test_oracle_cost_items_payloads_and_no_official_recording(oracle_context, monkeypatch):
    context = oracle_context
    training, rows = _inputs(context)
    seen = []
    original = oracle_module.calculate_costs_from_raw_data
    def checked(workspace, samples, variables):
        assert all(isinstance(item, dict) or hasattr(item, "keys") for sample in samples for item in sample)
        seen.append(samples)
        return original(workspace, samples, variables)
    monkeypatch.setattr(oracle_module, "calculate_costs_from_raw_data", checked)
    oracle = PerfectSimulationOracle()
    prediction = oracle.predict_for_selection(context, rows, training)
    assert len(seen) == 1
    assert prediction.valid_mask == (True, True)
    assert len(list_records(context.config.workspace)) == 0
    assert oracle.diagnostics()["oracle_simulation_evaluations"] == 2
    oracle.verify_selected(context, SimpleNamespace(predicted_costs=prediction.costs), prediction.costs)
    assert oracle.diagnostics()["oracle_selected_bitwise_matches"] == 2


def test_training_free_oracle_is_fresh_with_empty_data_and_zero_lag(oracle_context):
    from yadof.surrogate.training import assess_surrogate_selection_freshness
    training, _ = _inputs(oracle_context)
    context = SimpleNamespace(config=SimpleNamespace(OPTIMIZE_SURROGATE_MAX_TRAINING_LAG=0), generation_index=1)
    result = assess_surrogate_selection_freshness(PerfectSimulationOracle(), context, training)
    assert result.ready and result.lag == 0


def test_installed_perfect_program_really_uses_alpha_beta_and_matches_formal_rows(tmp_path):
    import shutil
    from pathlib import Path
    from yadof.optimize import run_generations
    receipt = init_workspace(tmp_path / "preset", preset="perfect")
    source = Path(receipt["workspace"]) / "resources/strategies/top10-perfect-gpsaf/optimization.py"
    materialize_baseline(discover_baselines()["test-com/synthetic-antenna"], tmp_path / "cell")
    workspace = tmp_path / "cell/workspace"
    shutil.copyfile(source, workspace / "submit/optimization.py")
    with (workspace / "config.py").open("a", encoding="utf-8") as stream:
        stream.write("\nOPTIMIZE_POPULATION_SIZE = 12\nOPTIMIZE_SMOKE_TEST_ENABLED = False\nFAST_EVALUATION_MAX_WORKERS = 2\n")
    from yadof_benchmark.runtime_freeze import task_fingerprint
    atomic_write_json(workspace / "benchmark_control.json", {"root": str(tmp_path),
        "reference": False, "threshold": 0.0, "task_files": task_fingerprint(workspace)})
    results = run_generations(workspace, 2, start_generation=0)
    assert len(results) == 2 and results[1].surrogate_used
    diagnostics = results[1].diagnostics
    assert diagnostics["alpha_candidate_count"] == 33
    assert diagnostics["beta_iterations"] == 3 and diagnostics["beta_candidate_count"] == 33
    assert diagnostics["oracle_simulation_evaluations"] == 66
    assert diagnostics["oracle_selected_bitwise_matches"] == 11
    assert diagnostics["oracle_contract_errors"] == 0
    assert len(list_records(workspace)) == 24


def test_all_one_is_valid_but_cost_interface_exception_is_fatal(oracle_context, monkeypatch):
    training, rows = _inputs(oracle_context)
    oracle = PerfectSimulationOracle()
    width = oracle_context.problem.objective_count
    monkeypatch.setattr(oracle_module, "calculate_costs_from_raw_data", lambda w, s, v: ((1.0,) * width,) * len(s))
    assert oracle.predict_for_selection(oracle_context, rows, training).costs == ((1.0,) * width,) * 2
    def broken(*args):
        raise TypeError("wrong payload programming error")
    monkeypatch.setattr(oracle_module, "calculate_costs_from_raw_data", broken)
    with pytest.raises(SurrogateContractError, match="wrong payload"):
        oracle.predict_for_selection(oracle_context, rows, training)
    assert oracle.diagnostics()["oracle_contract_errors"] == 1
    assert oracle.diagnostics()["oracle_simulation_failures"] == 0


def test_declared_physical_failure_is_inf_without_fabricated_rawdata(oracle_context, monkeypatch):
    class PhysicsFailure(RuntimeError):
        pass
    def failed(*args):
        raise PhysicsFailure("impossible geometry")
    @contextmanager
    def fake_module(*args):
        yield SimpleNamespace(PHYSICAL_FAILURE_TYPES=(PhysicsFailure,), evaluate_rawdata=failed)
    monkeypatch.setattr(oracle_module, "task_module", fake_module)
    training, rows = _inputs(oracle_context)
    oracle = PerfectSimulationOracle()
    prediction = oracle.predict_for_selection(oracle_context, rows, training)
    assert prediction.valid_mask == (False, False)
    assert prediction.raw_data == (None, None)
    assert all(v == math.inf for row in prediction.costs for v in row)
    assert oracle.diagnostics()["oracle_simulation_failures"] == 2
    assert len(list_records(oracle_context.config.workspace)) == 0
    import json
    audit = oracle_context.config.workspace.root / "oracle_audit/events.jsonl"
    event = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
    assert [c["normalized_variables"] for c in event["failed_candidates"]] == [list(row) for row in rows]
    assert all("impossible geometry" in c["error"] for c in event["failed_candidates"])


def test_physical_failures_continue_through_later_gpsaf_generations(tmp_path):
    import shutil
    from pathlib import Path
    from yadof.job_template import assign_parameters
    from yadof.optimize import run_generations
    from yadof_benchmark.runtime_freeze import task_fingerprint

    preset = Path(init_workspace(tmp_path / "preset", preset="perfect")["workspace"])
    materialize_baseline(discover_baselines()["test-com/synthetic-antenna"], tmp_path / "cell")
    workspace = tmp_path / "cell/workspace"
    shutil.copyfile(preset / "resources/strategies/top10-perfect-gpsaf/optimization.py",
                    workspace / "submit/optimization.py")
    names = get_parameter_names(workspace)
    midpoint = assign_parameters(workspace, (0.5,) * len(names))[0]
    # The same deterministic task failure is seen by oracle and real workers.
    # It exercises failed candidate isolation, not a permissive oracle-only mock.
    with (workspace / "job_template/evaluation.py").open("a", encoding="utf-8") as stream:
        stream.write(
            "\nclass NumericalFailure(RuntimeError):\n    pass\n"
            "PHYSICAL_FAILURE_TYPES = (NumericalFailure,)\n"
            "_finite_evaluation = evaluate_rawdata\n"
            "def evaluate_rawdata(parameters, context):\n"
            f"    if parameters[{midpoint.name!r}] > {float(midpoint.value)!r}:\n"
            "        raise NumericalFailure('numerical divergence')\n"
            "    return _finite_evaluation(parameters, context)\n"
        )
    with (workspace / "config.py").open("a", encoding="utf-8") as stream:
        stream.write("\nOPTIMIZE_POPULATION_SIZE = 12\nOPTIMIZE_SMOKE_TEST_ENABLED = False\nFAST_EVALUATION_MAX_WORKERS = 2\n")
    atomic_write_json(workspace / "benchmark_control.json", {"root": str(tmp_path),
        "reference": False, "threshold": 0.0, "task_files": task_fingerprint(workspace)})
    results = run_generations(workspace, 3, start_generation=0)
    assert len(results) == 3 and all(r.surrogate_used for r in results[1:])
    records = list_records(workspace)
    assert len(records) == 36
    assert any(r["status"] == "error" for r in records)
    final = results[-1].diagnostics
    assert final["oracle_simulation_failures"] > 0
    assert final["oracle_contract_errors"] == 0
    assert final["oracle_simulation_evaluations"] == 132
    assert final["oracle_selected_bitwise_matches"] == 22
    assert final["oracle_recorded_in_history"] is False


@pytest.fixture
def chrono_worker(monkeypatch):
    import runpy
    import sys
    directory = discover_baselines()["chrono/trebuchet"].workspace / "job_template"
    monkeypatch.syspath_prepend(str(directory))
    for name in ("chrono_com", "task_spec"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    return SimpleNamespace(**runpy.run_path(str(directory / "chrono_worker.py")))


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_chrono_divergent_state_is_a_typed_candidate_failure(chrono_worker, invalid):
    import numpy as np
    failure = chrono_worker.PyChronoSimulationError
    with pytest.raises(failure, match="numerical divergence: ball state"):
        chrono_worker._require_finite_state("ball state", (1.0, invalid, 0.0))
    with pytest.raises(failure, match="history values"):
        chrono_worker._resample_phase_history(
            np.array([0.0, 1.0]), np.array([[0.0], [invalid]]), total_time_s=1.0)
    link = SimpleNamespace(GetReaction2=lambda: SimpleNamespace(force=SimpleNamespace(Length=lambda: invalid)))
    with pytest.raises(failure, match="constraint reaction"):
        chrono_worker._reaction_magnitude(link)


def test_chrono_state_checks_do_not_hide_interface_or_shape_errors(chrono_worker):
    import numpy as np
    with pytest.raises(AttributeError):
        chrono_worker._reaction_magnitude(object())
    with pytest.raises(TypeError):
        chrono_worker._require_finite_state("ball state", (object(),))
    with pytest.raises(RuntimeError, match="incompatible shapes") as error:
        chrono_worker._resample_phase_history(
            np.array([0.0, 1.0]), np.array([[0.0]]), total_time_s=1.0)
    assert not isinstance(error.value, chrono_worker.PyChronoSimulationError)
    finite = chrono_worker._resample_phase_history(
        np.array([0.0, 1.0]), np.array([[2.0], [2.0]]), total_time_s=1.0)
    assert np.all(finite == 2.0)


def test_metric_uses_cumulative_formal_top_ten_and_strict_crossing(tmp_path):
    atomic_write_json(tmp_path / "benchmark_control.json", {"reference": False, "threshold": 0.5})
    context = SimpleNamespace(config=SimpleNamespace(workspace=SimpleNamespace(root=tmp_path)),
                              generation_index=0, population_size=10, history=())
    assert not record_generation(context, ((0.5, 0.5),) * 10)
    context.generation_index = 1
    context.history = tuple(SimpleNamespace(costs=(0.5, 0.5)) for _ in range(10))
    assert record_generation(context, ((0.25, 0.25),) * 10)
    records = [{"generation_index": g} for g in range(2) for _ in range(10)]
    rows = [{"generation_index": g, "costs": costs} for g, costs in ((0, (0.5, 0.5)), (1, (0.25, 0.25))) for _ in range(10)]
    result = collect_top10(tmp_path, {"generations": 50, "population": 10}, records, rows)
    assert result["budget_satisfied"]
    assert result["first_strictly_better_generation"] == 2
    assert result["formal_evaluations"] == 20
    assert top10([(1, 3)] * 10 + [(9, 9)] * 20) == 2.0
    assert top10([(1, 1)] * 9 + [(math.inf, math.inf)]) is None


def test_installed_perfect_preset_has_complete_paired_matrix(tmp_path):
    initialized = init_workspace(tmp_path / "experiment", preset="perfect")
    spec = plan_workspace(initialized["workspace"]).to_dict()
    assert len(spec["cells"]) == 6
    assert all(c["population"] == 200 and c["generations"] == 50 and c["seed"] == 101 for c in spec["cells"])
    assert all(c["top10_reference"] == "real-nsga3" for c in spec["cells"])
    assert spec["workflow"]["postprocessors"][0]["run_on_failure"] is True
