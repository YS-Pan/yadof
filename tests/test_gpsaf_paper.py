"""Acceptance examples from GPSAF Algorithms 2/3, independent of old goldens."""
from dataclasses import replace
import math
from types import SimpleNamespace
import numpy as np
import pytest
from yadof.optimize import GPSAFErrorState, gpsaf_settings, prepare_search, pymoo_nsga3
from yadof.optimize.gpsaf.phases import run_alpha_phase, run_beta_phase, distance_sq
from yadof.optimize.gpsaf.tournament import dominates, tournament_winner, probabilistic_knockout, replacement_probabilities
from yadof.optimize.problem_info import ProblemInfo
from yadof.optimize.pymoo import backend
from yadof.surrogate import SurrogateTrainingData
from test_explicit_search_primitives import _context, _GoldenDeterministicSurrogate, HISTORY_MULTI


class FixedRandom:
    def __init__(self, draw=0.5, normals=()):
        self.draw, self.normals, self.noise_calls = draw, iter(normals), []
    def choice(self, values):
        return values[-1]
    def shuffle(self, values):
        pass
    def random(self):
        return self.draw
    def gauss(self, mean, sigma):
        self.noise_calls.append((mean, sigma))
        return next(self.normals, 0.0)


def test_feasibility_dominance_and_random_ties():
    rng = FixedRandom()
    assert dominates((1, 2), (1, 3))
    assert not dominates((1, 2), (1, 2))
    assert not dominates((1, 3), (2, 2))
    assert tournament_winner([(0,), (9,)], rng, constraints=[(1,), (-1,)]) == 1
    assert tournament_winner([(0,), (9,)], rng, constraints=[(2,), (1,)]) == 1
    assert tournament_winner([(0,), (9,)], rng, constraints=[(1,), (1,)]) == 1
    assert tournament_winner([(1, 3), (2, 2), (3, 3)], rng) == 1
    assert tournament_winner([(0,), (1,)], rng, valid=[False, True]) == 1


def test_pkt_odd_zero_error_and_independent_nonzero_noise():
    assert probabilistic_knockout([(3,), (1,), (2,)], (0,), FixedRandom()) == 1
    rng = FixedRandom(normals=(2.0, -2.0))
    assert probabilistic_knockout([(0,), (1,)], (3,), rng) == 1
    assert rng.noise_calls == [(0.0, 3), (0.0, 3)]
    rng = FixedRandom(normals=(0, 0, 2, -2))
    assert probabilistic_knockout([(0,), (1,)], (1,), rng, constraints=[(-1,), (1,)], constraint_error=(3,)) == 1
    assert rng.noise_calls == [(0.0, 1), (0.0, 1), (0.0, 3), (0.0, 3)]


def test_gamma_controls_cluster_replacement():
    assert replacement_probabilities((0, 1, 4), 0.5) == (0.0, 0.5, 1.0)
    assert replacement_probabilities((0, 1, 4), 1.0) == (0.0, 0.25, 1.0)
    assert replacement_probabilities((0, 1, 4), 0.0) == (0.0, 1.0, 1.0)
    assert replacement_probabilities((0, 0), 0.5) == (0.0, 0.0)
    assert gpsaf_settings(gamma=2.0).gamma == 2.0


def test_alpha_only_competes_at_corresponding_positions():
    context = _context(ProblemInfo(2, 2, ("a", "b")), history=HISTORY_MULTI, generation=1)
    base = prepare_search(context, pymoo_nsga3())
    class Provider(_GoldenDeterministicSurrogate):
        calls = 0
        def predict_for_selection(self, context, population, training_data):
            prediction = super().predict_for_selection(context, population, training_data)
            costs = ((0.1, 0.1), (0.9, 0.9)) if self.calls == 0 else ((0.2, 0.2), (0.8, 0.8))
            self.calls += 1
            return replace(prediction, costs=costs, intervals=tuple(tuple((v, v) for v in r) for r in costs))
    selected, _, info = run_alpha_phase(base, 2, surrogate=Provider(), generation_context=context,
        settings=gpsaf_settings(alpha=2), training_data=SurrogateTrainingData(("a", "b"), (), ()))
    assert info["alpha_selected_indices"] == (0, 3)  # pooled survival would select 0, 2
    assert len(selected.population) == 2


def test_beta_clusters_all_advances_without_leaking_simulated_state():
    context = _context(ProblemInfo(2, 2, ("a", "b")), history=HISTORY_MULTI, generation=1, seed=11)
    base = prepare_search(context, pymoo_nsga3())
    provider, training = _GoldenDeterministicSurrogate(), SurrogateTrainingData(("a", "b"), (), ())
    settings = gpsaf_settings(alpha=2, beta=3, gamma=0)
    anchors, prediction, _ = run_alpha_phase(base, 4, surrogate=provider, generation_context=context, settings=settings, training_data=training)
    real_pop = anchors.state._runtime.algorithm.pop.get("F").copy()
    real_gen = anchors.state._runtime.algorithm.n_gen
    selected, info = run_beta_phase(anchors, prediction, 4, surrogate=provider, generation_context=context,
        settings=settings, training_data=training, error_scales=(0, 0), rng=FixedRandom(0))
    assert info["beta_candidate_count"] == sum(info["beta_cluster_sizes"]) == 12
    assert info["beta_iterations"] == 3
    assert selected.state._runtime.algorithm.n_gen == real_gen
    np.testing.assert_array_equal(selected.state._runtime.algorithm.pop.get("F"), real_pop)
    np.testing.assert_array_equal(anchors.state._runtime.algorithm.pop.get("F"), real_pop)
    for position, candidate in enumerate(selected.candidates):
        if candidate.candidate_id != anchors.candidates[position].candidate_id:
            nearest = min(range(4), key=lambda i: distance_sq(candidate.normalized_variables, anchors.population[i]))
            assert nearest == position


def test_maximum_absolute_error_then_five_batch_average():
    state = GPSAFErrorState()
    selected = SimpleNamespace(population=((0,), (1,)), predicted_costs=((0.1, 0.4), (0.5, 0.6)))
    assert state.error is None
    state.observe(selected, ((0.3, 0.3), (0.6, 0.9)))
    assert state.error == pytest.approx((0.2, 0.3))
    state.observe(selected, ((math.inf, math.inf), (math.inf, math.inf)))
    assert state.observed_rows == 2
    for _ in range(5):
        state.observe(selected, selected.predicted_costs)
    assert state.error == (0.0, 0.0)
    state.for_interpretation("old")
    assert state.for_interpretation("new") is None


def test_gamma_changes_actual_beta_replacement_for_controlled_clusters(monkeypatch):
    from yadof.optimize.gpsaf import phases
    context = _context(ProblemInfo(2, 2, ("a", "b")), history=HISTORY_MULTI, generation=1)
    provider, training = _GoldenDeterministicSurrogate(), SurrogateTrainingData(("a", "b"), (), ())
    settings = gpsaf_settings(alpha=2, beta=3, gamma=0.5)
    anchors, prediction, _ = run_alpha_phase(prepare_search(context, pymoo_nsga3()), 4,
        surrogate=provider, generation_context=context, settings=settings, training_data=training)
    monkeypatch.setattr(phases, "assign_clusters", lambda a, c: [list(c[:3]), list(c[3:]), [], []])
    def select(gamma):
        return run_beta_phase(anchors, prediction, 4, surrogate=provider, generation_context=context,
            settings=replace(settings, gamma=gamma), training_data=training,
            error_scales=(0, 0), rng=FixedRandom(0.5))
    half, info = select(0.5)
    one, _ = select(1.0)
    assert info["beta_cluster_sizes"] == (9, 3, 0, 0)
    assert half.candidates[1].candidate_id != anchors.candidates[1].candidate_id
    assert one.candidates[1].candidate_id == anchors.candidates[1].candidate_id
    assert half.candidates[0].candidate_id != anchors.candidates[0].candidate_id
    assert half.candidates[2:] == anchors.candidates[2:]


def test_contract_errors_do_not_turn_into_real_fallback():
    from yadof.optimize.gpsaf.phases import surrogate_population
    from yadof.surrogate import SurrogateContractError
    class Broken(_GoldenDeterministicSurrogate):
        def predict_for_selection(self, *args):
            raise SurrogateContractError("broken cost payload")
    context = _context(ProblemInfo(2, 2, ("a", "b")), history=HISTORY_MULTI, generation=1)
    with pytest.raises(SurrogateContractError, match="broken cost"):
        surrogate_population(HISTORY_MULTI, generation_context=context, search=pymoo_nsga3(),
            surrogate=Broken(), generation_index=1, population_size=4, seed=101,
            settings=gpsaf_settings(), training_data=SurrogateTrainingData(("a", "b"), (), ()), error_scales=(0, 0))


def test_replay_advances_once_per_real_generation():
    history = tuple(replace(row, generation_index=i // 2, population_index=i % 2)
                    for i, row in enumerate(HISTORY_MULTI[:4]))
    context = _context(ProblemInfo(2, 2, ("a", "b")), history=history, generation=2, seed=101)
    state = prepare_search(context, pymoo_nsga3())
    expected = backend.new_algorithm(state._runtime.context)
    for generation in range(2):
        expected.random_state = np.random.default_rng(101 + generation * 1009 + 701)
        batch = history[generation * 2:(generation + 1) * 2]
        expected.tell(infills=backend.Population.new(X=np.array([r.x for r in batch]), F=np.array([r.costs for r in batch])))
    actual = state._runtime.algorithm
    assert actual.n_gen == expected.n_gen == 3
    np.testing.assert_array_equal(actual.pop.get("X"), expected.pop.get("X"))
    np.testing.assert_array_equal(actual.survival.norm.ideal_point, expected.survival.norm.ideal_point)


def test_five_fold_bootstrap_uses_held_out_rows_and_maximum_error(monkeypatch):
    from yadof.surrogate.linear_subspace import gpsaf_error
    from yadof.job_template import StructuredRawDataSample
    def sample(value):
        return StructuredRawDataSample.from_items({"signal.npz": {"values": np.array([value], dtype=float),
            "metadata": {"schema_version": 1, "shape": [1], "rawdata_name": "signal"}}})
    data = SurrogateTrainingData(("x",), tuple((i / 9,) for i in range(10)), tuple(sample(i) for i in range(10)))
    calls = []
    class Component:
        def fit_deployable(self, rows, samples, *, parameter_names):
            calls.append(tuple(rows))
            return rows
        def predict_rawdata(self, model, rows):
            assert not set(model).intersection(rows)
            return tuple(sample(0) for _ in rows)
    monkeypatch.setattr(gpsaf_error, "assign_parameters", lambda w, row: (SimpleNamespace(name="x", value=row[0]),))
    monkeypatch.setattr(gpsaf_error, "calculate_costs_from_raw_data",
                        lambda w, samples, variables: tuple((float(s[0]["values"][0]),) for s in samples))
    context = SimpleNamespace(random_seed=101, config=SimpleNamespace(workspace=None))
    assert gpsaf_error.estimate_initial_error(Component(), context, data) == (9.0,)
    assert len(calls) == 5 and all(len(rows) == 8 for rows in calls)
