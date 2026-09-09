"""Independent survivor, infill and paired initial-design budgets."""
from dataclasses import replace

import pytest

from yadof.optimize import (GPSAFErrorState, full_real_search, gpsaf_settings,
                            prepare_search, pymoo_nsga3, select_gpsaf_generation)
from yadof.optimize.problem_info import ProblemInfo
from yadof.optimize.strategy import GenerationContext, HistoryRecord
from yadof.surrogate import SurrogateTrainingData
from test_explicit_search_primitives import _context, _GoldenDeterministicSurrogate


class _FreshSurrogate(_GoldenDeterministicSurrogate):
    def latest_trained_generation(self, context, training_data):
        return context.generation_index - 1


def make_context(p, b, *, history=(), generation=0):
    base = _context(ProblemInfo(2, 2, ("a", "b")), population_size=p,
                    history=history, generation=generation, seed=733)
    base.config.OPTIMIZE_BATCH_SIZE = b
    base.config.OPTIMIZE_INITIAL_POPULATION_SIZE = 12
    return GenerationContext(config=base.config, generation_index=generation,
        population_size=p, random_seed=733, run_id="budget-test", optimization_index=0,
        session=None, snapshot=base.snapshot, history=tuple(history), problem=base.problem,
        strategy_signature=base.strategy_signature, strategy_identity={})


@pytest.mark.parametrize("p", [2, 4, 8])
@pytest.mark.parametrize("b", [1, 3, 9])
def test_initial_pairing_survival_offspring_and_gpsaf(p, b):
    search = pymoo_nsga3()
    context = make_context(p, b)
    initial = full_real_search(context, search)
    reference = full_real_search(make_context(12, 12), search)
    assert initial.population == reference.population
    assert len(initial.population) == 12
    history = tuple(HistoryRecord(str(i), x, (x[0], 1 - x[0]),
                    generation_index=0, population_index=i)
                    for i, x in enumerate(initial.population))
    later = replace(context, generation_index=1, history=history)
    state = prepare_search(later, search)
    assert state._runtime.algorithm.pop_size == p
    assert state._runtime.algorithm.n_offsprings == b
    assert len(state._runtime.algorithm.pop) == p
    ordinary = full_real_search(later, search)
    assert len(ordinary.population) == b
    assert not set(ordinary.population).intersection(initial.population)
    assisted = select_gpsaf_generation(later, search=search,
        surrogate=_FreshSurrogate(), settings=gpsaf_settings(),
        training_data=SurrogateTrainingData(("left", "right"), (), ()),
        error_state=GPSAFErrorState(initial_error=(0., 0.)))
    assert assisted.surrogate_used, dict(assisted.diagnostics)
    assert len(assisted.population) == len(set(assisted.population)) == b
    assert not set(assisted.population).intersection(initial.population)
    assert len(assisted.predicted_costs) == b


def test_distinct_budgets_have_distinct_semantic_identity():
    search = pymoo_nsga3()
    original = make_context(4, 4)
    original.config.OPTIMIZE_INITIAL_POPULATION_SIZE = None
    implicit = make_context(4, 4)
    implicit.config.OPTIMIZE_BATCH_SIZE = None
    implicit.config.OPTIMIZE_INITIAL_POPULATION_SIZE = None
    assert search.semantic_identity(original.config, original.problem) == search.semantic_identity(implicit.config, implicit.problem)
    assert search.semantic_identity(make_context(4, 2).config, original.problem) != search.semantic_identity(original.config, original.problem)


@pytest.mark.parametrize("p,b,initial", [(8, 3, 12), (3, 8, 12), (8, 3, 2)])
def test_public_api_records_actual_generation_budgets(tmp_path, p, b, initial):
    from collections import Counter
    from yadof.optimize import run_generations
    from yadof.recorded_data import list_records
    from yadof.tools.cost_viewer import build_rows, hypervolume_series
    from test_optimization_program import _workspace, _real_program
    program = _real_program().replace(
        "diagnostics.update(dict(selected.diagnostics))",
        "diagnostics.update(dict(selected.diagnostics))\n"
        "                diagnostics['retained_designs'] = (selected.state._runtime.algorithm.pop.get('X').tolist()\n"
        "                    if step.context.history else [])")
    workspace = _workspace(tmp_path / "real", program=program)
    results = run_generations(workspace, 3, population_size=p, batch_size=b,
                              initial_population_size=initial)
    assert [len(r.population) for r in results] == [initial, b, b]
    records = list_records(workspace)
    assert len(records) == initial + 2 * b
    assert len({record["job_name"] for record in records}) == len(records)
    assert len({x for result in results for x in result.population}) == len(records)
    # The viewer reads each real result once, regardless of retained membership.
    rows = build_rows(workspace)
    assert len(rows) == len(records)
    assert {row["job_name"] for row in rows} == {record["job_name"] for record in records}
    assert Counter(row["generation_index"] for row in rows) == Counter({0: initial, 1: b, 2: b})
    assert hypervolume_series(rows)[0].tolist() == [initial, initial + b, initial + 2 * b]
    if p > b:
        retained = [{tuple(x) for x in result.diagnostics["retained_designs"]} for result in results[1:]]
        assert retained[0].intersection(retained[1])  # Actual individuals survive multiple generations.
    for g, result in enumerate(results):
        assert result.diagnostics["retained_population_size"] == p
        assert result.diagnostics["batch_size"] == b
        assert result.diagnostics["initial_population_size"] == initial
        assert result.diagnostics["evaluation_size"] == (initial if g == 0 else b)
        assert sum(r["generation_index"] == g for r in records) == len(result.population)


def test_replaying_longer_history_preserves_initial_survival_boundary():
    import numpy as np
    from pymoo.core.population import Population
    search = pymoo_nsga3()
    initial = full_real_search(make_context(4, 3), search).population
    history = tuple(HistoryRecord(str(i), x, (x[0], 1 - x[0]),
                    generation_index=0, population_index=i)
                    for i, x in enumerate(initial))
    context = make_context(4, 3, history=history, generation=1)
    prefix = prepare_search(context, search)._runtime.algorithm
    next_x = np.asarray([[0.01, 0.3], [0.7, 0.2], [0.9, 0.8]])
    next_f = np.asarray([[0.01, 0.99], [0.7, 0.3], [0.9, 0.1]])
    prefix.random_state = np.random.default_rng(context.random_seed + 1009 + 701)
    prefix.tell(infills=Population.new(X=next_x, F=next_f))
    complete = history + tuple(HistoryRecord(f"next{i}", tuple(x), tuple(f),
        generation_index=1, population_index=i) for i, (x, f) in enumerate(zip(next_x, next_f)))
    replay = prepare_search(make_context(4, 3, history=complete, generation=2), search)._runtime.algorithm
    np.testing.assert_array_equal(prefix.pop.get("X"), replay.pop.get("X"))
    np.testing.assert_array_equal(prefix.pop.get("F"), replay.pop.get("F"))
    assert prefix.n_gen == replay.n_gen


@pytest.mark.parametrize("algorithm,objectives", [("ga", 1), ("nsga3", 2)])
def test_long_stagnant_replay_cannot_apply_a_backend_stop(algorithm, objectives):
    import numpy as np
    from yadof.optimize import pymoo_ga
    from yadof.optimize.pymoo import backend
    search = pymoo_ga() if algorithm == "ga" else pymoo_nsga3()
    context = make_context(4, 2)
    problem = ProblemInfo(2, objectives, tuple(f"f{i}" for i in range(objectives)))
    runtime = backend.make_context(context.config, problem, population_size=4,
        seed=733, generation_index=1100, search_algorithm=algorithm, search_settings=search.settings)
    rng = np.random.default_rng(733)
    history = tuple(HistoryRecord(str(i), tuple(rng.uniform(size=2)), (0.5,) * objectives,
        generation_index=0 if i < 12 else 1 + (i - 12) // 2,
        population_index=i if i < 12 else (i - 12) % 2) for i in range(2210))
    replay = backend.history_population(runtime, history)
    assert replay.n_gen == 1101 and len(replay.pop) == 4
    assert replay.has_next()
    assert len(replay.ask()) == 2
