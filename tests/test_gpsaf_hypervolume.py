"""Hypervolume infill behavior, independent of physical benchmark outcomes."""

from dataclasses import asdict
import math

import numpy as np
import pytest

from yadof.optimize import (
    GPSAFErrorState,
    gpsaf_settings,
    prepare_search,
    pymoo_nsga3,
    select_gpsaf_generation,
)
from yadof.optimize.gpsaf import phases
from yadof.optimize.gpsaf.coverage import select_hypervolume_indices
from yadof.optimize.problem_info import ProblemInfo
from yadof.surrogate import SurrogateTrainingData
from test_explicit_search_primitives import (
    HISTORY_MULTI,
    _context,
    _GoldenDeterministicSurrogate,
)


def test_hypervolume_settings_are_explicit_and_validated():
    default = gpsaf_settings()
    explicit = gpsaf_settings(infill_selection="hypervolume")
    assert default == explicit
    controlled = gpsaf_settings(infill_selection=" HYPERVOLUME ")
    assert asdict(controlled)["infill_selection"] == "hypervolume"
    assert default == controlled
    assert default != gpsaf_settings(infill_selection="cluster")
    with pytest.raises(ValueError, match="gpsaf_settings.*infill_selection"):
        gpsaf_settings(infill_selection="unknown")
    with pytest.raises(TypeError, match="gpsaf_settings.*infill_selection"):
        gpsaf_settings(infill_selection=None)


def test_history_changes_which_candidate_improves_coverage():
    costs = ((0.05, 0.8), (0.4, 0.1), (0.9, 0.9))
    empty, _ = select_hypervolume_indices(costs, (True,) * 3, (), 1, (2,))
    occupied, info = select_hypervolume_indices(
        costs, (True,) * 3, ((0.4, 0.2),), 1, (2,)
    )
    assert empty == (1,)  # 0.6 * 0.9 is the largest empty-archive rectangle.
    assert occupied == (0,)  # New area 0.35 * 0.2 beats 0.6 * 0.1.
    assert info["coverage_gain"] == pytest.approx(0.07)


def test_batch_coverage_recomputes_marginal_gain_after_each_choice():
    selected, info = select_hypervolume_indices(
        ((0.1, 0.5), (0.11, 0.5), (0.5, 0.1)),
        (True, True, True), (), 2, (0, 1),
    )
    assert set(selected) == {0, 2}
    assert info["coverage_gain"] == pytest.approx(0.65)
    assert info["coverage_positive_count"] == 2
    assert info["coverage_reference_point"] == (1.0, 1.0)


@pytest.mark.parametrize("objectives", [2, 3, 5])
def test_fast_zero_gain_checks_match_exhaustive_greedy(objectives):
    from pymoo.indicators.hv import HV
    indicator = HV(ref_point=np.ones(objectives))
    for seed in range(12):
        rng = np.random.default_rng(seed)
        costs = rng.uniform(-0.1, 1.2, (24, objectives))
        history = rng.uniform(0, 1, (10, objectives))
        valid = [True] * 23 + [False]
        costs[-1] = math.inf
        fallback = [7, 23, 2, 0]
        front = history.copy()
        expected = []
        for _ in range(8):
            base = float(indicator(front))
            gains = [(max(0., float(indicator(np.vstack((front, row)))) - base), i)
                     for i, row in enumerate(costs) if valid[i] and i not in expected]
            gain, index = max(gains, key=lambda item: (item[0], -item[1]))
            if gain <= 1e-12:
                break
            expected.append(index)
            front = np.vstack((front, costs[index]))
        for is_valid in (True, False):
            for index in fallback + list(range(len(costs))):
                if valid[index] == is_valid and index not in expected and len(expected) < 8:
                    expected.append(index)
        selected, _ = select_hypervolume_indices(costs, valid, history, 8, fallback)
        assert selected == tuple(expected)


def test_dominated_pool_avoids_per_candidate_hypervolume_calls(monkeypatch):
    from pymoo.indicators.hv import HV
    calls = []
    original = HV.__call__
    def counted(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(HV, "__call__", counted)
    selected, _ = select_hypervolume_indices([(0.5, 0.5)] * 200,
        [True] * 200, [(0.1, 0.1)], 20, list(reversed(range(200))))
    assert selected == tuple(reversed(range(180, 200)))
    assert len(calls) == 1


@pytest.mark.parametrize("count", (4, 5))
def test_no_gain_fallback_keeps_finite_penalties_and_defers_failures(count):
    costs = ((0.2, 0.7), (0.7, 0.2), (0.6, 0.6), (1.0, 0.0), (math.inf, math.inf))
    selected, info = select_hypervolume_indices(
        costs, (True, True, True, True, False), ((0.0, 0.0),), count, (3, 4, 1),
    )
    assert selected == (3, 1, 0, 2, 4)[:count]
    assert info["coverage_gain"] == 0.0
    assert info["coverage_positive_count"] == 0


def test_hypervolume_infill_keeps_queries_exploration_and_prediction_bindings(monkeypatch):
    context = _context(
        ProblemInfo(2, 2, ("a", "b")), history=HISTORY_MULTI, generation=3, seed=271828,
    )
    training = SurrogateTrainingData(("left", "right"), (), ())
    original_predict = phases.predict_pool
    original_search = phases.search_candidates
    calls, predictions, exploration = [], {}, []

    def predict(*args, **kwargs):
        rows = original_predict(*args, **kwargs)
        calls.extend(rows.normalized_variables)
        predictions.update(zip(rows.normalized_variables, rows.costs))
        return rows

    def ask(*args, **kwargs):
        pool = original_search(*args, **kwargs)
        if kwargs.get("origin") == "gpsaf_exploration":
            exploration.extend(pool.population)
        return pool

    monkeypatch.setattr(phases, "predict_pool", predict)
    monkeypatch.setattr(phases, "search_candidates", ask)

    def run(selection):
        return select_gpsaf_generation(
            context, search=pymoo_nsga3(), surrogate=_GoldenDeterministicSurrogate(),
            settings=gpsaf_settings(alpha=3, beta=2, exploration_fraction=0.25,
                                    infill_selection=selection),
            training_data=training, error_state=GPSAFErrorState(initial_error=(0.0, 0.0)),
        )

    run("cluster")
    original_queries = tuple(calls)
    calls.clear()
    exploration.clear()
    selected = run("hypervolume")
    assert tuple(calls) == original_queries
    assert len(calls) == len(set(calls)) == 15
    assert selected.surrogate_used
    assert selected.diagnostics["infill_selection"] == "hypervolume"
    assert selected.diagnostics["beta_selection"] == "history-hypervolume-greedy"
    assert len(selected.population) == len(set(selected.population)) == 4
    assert selected.population[-1:] == tuple(exploration)
    assert selected.predicted_costs[-1] is None
    for row, predicted in zip(selected.population[:-1], selected.predicted_costs[:-1]):
        assert predicted == predictions[row]
    assert context.history == HISTORY_MULTI
    default = select_gpsaf_generation(
        context, search=pymoo_nsga3(), surrogate=_GoldenDeterministicSurrogate(),
        settings=gpsaf_settings(alpha=3, beta=2, exploration_fraction=0.25),
        training_data=training, error_state=GPSAFErrorState(initial_error=(0.0, 0.0)),
    )
    assert default.population == selected.population
    assert default.predicted_costs == selected.predicted_costs
    assert default.diagnostics == selected.diagnostics


@pytest.mark.parametrize("beta,errors", ((0, (0.0, 0.0)), (2, None)))
def test_inactive_beta_preserves_alpha_even_when_coverage_is_requested(beta, errors):
    context = _context(ProblemInfo(2, 2, ("a", "b")), history=HISTORY_MULTI, generation=1)
    provider = _GoldenDeterministicSurrogate()
    training = SurrogateTrainingData(("left", "right"), (), ())
    settings = gpsaf_settings(alpha=2, beta=beta, infill_selection="hypervolume")
    anchors, prediction, _ = phases.run_alpha_phase(
        prepare_search(context, pymoo_nsga3()), 4, surrogate=provider,
        generation_context=context, settings=settings, training_data=training,
    )
    selected, info = phases.run_beta_phase(
        anchors, prediction, 4, surrogate=provider, generation_context=context,
        settings=settings, training_data=training, error_scales=errors,
    )
    assert selected.population == anchors.population
    assert info["beta_iterations"] == 0
    np.testing.assert_array_equal(
        selected.state._runtime.algorithm.pop.get("F"),
        anchors.state._runtime.algorithm.pop.get("F"),
    )
