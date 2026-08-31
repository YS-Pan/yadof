from __future__ import annotations

import pickle
from types import SimpleNamespace

import numpy as np
import pytest

from yadof.job_template import RAWDATA_SCHEMA_VERSION
from yadof.job_template.rawdata_projector import JointObjectiveSamples
from yadof.optimize import (
    CandidatePool,
    InsufficientCandidatePoolError,
    PredictedCostRows,
    SearchState,
    advance_search,
    bind_predicted_costs,
    bind_surrogate_prediction,
    combine_candidate_pools,
    combine_predicted_cost_rows,
    continue_search_from,
    fork_search_state,
    full_real_search,
    finish_explicit_surrogate_training,
    gpsaf,
    gpsaf_settings,
    prepare_search,
    pymoo_ga,
    pymoo_nsga3,
    search_candidates,
    select_gpsaf_generation,
    select_candidates,
    start_explicit_surrogate_training,
    warm_start_candidates,
)
from yadof.optimize.gpsaf.phases import surrogate_population
from yadof.optimize.gpsaf.settings import create_settings as create_gpsaf_settings
from yadof.optimize.problem_info import ProblemInfo
from yadof.optimize.strategy import HistoryRecord
from yadof.recorded_data.dataset import CostTable
from yadof.job_template.rawdata_template import StructuredRawDataSample
from yadof.surrogate.training import SurrogatePrediction, SurrogateTrainingData


HISTORY_SINGLE = (
    HistoryRecord("h0", (0.05, 0.15), (0.20,), candidate_id="e0"),
    HistoryRecord("h1", (0.25, 0.75), (0.65,), candidate_id="e1"),
    HistoryRecord("h2", (0.45, 0.35), (0.40,), candidate_id="e2"),
    HistoryRecord("h3", (0.65, 0.85), (0.90,), candidate_id="e3"),
    HistoryRecord("h4", (0.85, 0.25), (0.55,), candidate_id="e4"),
)
HISTORY_MULTI = tuple(
    HistoryRecord(
        row.job_name,
        row.x,
        (row.costs[0], 1.0 - row.costs[0]),
        candidate_id=row.candidate_id,
    )
    for row in HISTORY_SINGLE
)


def _config(*, population_size: int = 4, decimals: int = 10):
    return SimpleNamespace(
        OPTIMIZE_ARCHIVE_KEY_DECIMALS=decimals,
        OPTIMIZE_POPULATION_SIZE=population_size,
        OPTIMIZE_SURROGATE_MAX_TRAINING_LAG=1,
    )


def _context(
    problem: ProblemInfo,
    *,
    history=(),
    generation: int = 0,
    seed: int = 314159,
    population_size: int = 4,
    decimals: int = 10,
    signature: str = "1" * 64,
):
    return SimpleNamespace(
        config=_config(population_size=population_size, decimals=decimals),
        generation_index=generation,
        population_size=population_size,
        random_seed=seed,
        history=tuple(history),
        problem=problem,
        strategy_signature=signature,
        strategy_identity={},
        snapshot=SimpleNamespace(interpretation_fingerprint="2" * 64),
        session=None,
    )


@pytest.mark.parametrize(
    ("algorithm", "problem", "history", "generation", "source", "expected"),
    (
        (
            "ga",
            ProblemInfo(2, 1, ("single",)),
            HISTORY_SINGLE,
            0,
            "gpsaf_warm_start",
            ((0.05, 0.15), (0.45, 0.35), (0.85, 0.25), (0.25, 0.75)),
        ),
        (
            "ga",
            ProblemInfo(2, 1, ("single",)),
            HISTORY_SINGLE,
            2,
            "gpsaf_offspring",
            (
                (0.04390260626204329, 0.36319260365315437),
                (0.47061671416777034, 0.32144786419631644),
                (0.4576658032255102, 0.13680886730048727),
                (0.03555001906147122, 0.16299075375652947),
            ),
        ),
        (
            "nsga3",
            ProblemInfo(2, 2, ("first", "second")),
            HISTORY_MULTI,
            0,
            "gpsaf_warm_start",
            ((0.25, 0.75), (0.45, 0.35), (0.05, 0.15), (0.65, 0.85)),
        ),
        (
            "nsga3",
            ProblemInfo(2, 2, ("first", "second")),
            HISTORY_MULTI,
            2,
            "gpsaf_offspring",
            (
                (0.6783800566483025, 0.23975673662717967),
                (0.21442814571916458, 0.7624062503784522),
                (0.04683870025805721, 0.7884728795689759),
                (0.24776082252193266, 0.28618532170093136),
            ),
        ),
    ),
)
def test_full_real_search_preserves_seeded_golden_population(
    algorithm,
    problem,
    history,
    generation,
    source,
    expected,
) -> None:
    context = _context(problem, history=history, generation=generation)
    search = (
        pymoo_ga()
        if algorithm == "ga"
        else pymoo_nsga3(reference_direction_partitions=3)
    )

    selected = full_real_search(
        context,
        search,
        algorithm_seed=context.random_seed,
        random_seed=context.random_seed + generation * 1009,
        origin_prefix="gpsaf",
    )

    assert selected.source == source
    assert selected.population == expected
    assert selected.diagnostics["evaluation_handoff"] == (
        "common-real-evaluate-population"
    )


def test_search_state_is_functional_forkable_and_not_durable() -> None:
    context = _context(
        ProblemInfo(2, 1, ("single",)),
        population_size=3,
        seed=271828,
    )
    state = prepare_search(context, pymoo_ga())

    assert isinstance(state, SearchState)
    assert state.revision == 0
    assert state.candidate_count == 0
    with pytest.raises(TypeError, match="generation-local"):
        pickle.dumps(state)

    first = search_candidates(fork_search_state(state), 2, origin="branch")
    repeated = search_candidates(fork_search_state(state), 2, origin="branch")

    assert state.revision == 0
    assert state.candidate_count == 0
    assert first.population == repeated.population
    assert tuple(row.candidate_id for row in first.candidates) == tuple(
        row.candidate_id for row in repeated.candidates
    )
    continued = continue_search_from(state, first.state)
    follow = search_candidates(continued, 1, origin="follow")
    assert follow.candidates[0].duplicate_key not in {
        row.duplicate_key for row in first.candidates
    }
    assert follow.candidates[0].candidate_id not in {
        row.candidate_id for row in first.candidates
    }


def test_candidate_identity_is_distinct_from_history_evidence_identity() -> None:
    context = _context(
        ProblemInfo(2, 1, ("single",)),
        history=HISTORY_SINGLE,
    )
    state = prepare_search(context, pymoo_ga(), history_policy="warm-start")
    warm = warm_start_candidates(state, 1, origin="warm")
    candidate = warm.candidates[0]

    assert candidate.source_evidence_id in {row.candidate_id for row in HISTORY_SINGLE}
    assert candidate.candidate_id != candidate.source_evidence_id
    assert len(candidate.candidate_id) == 64
    assert not hasattr(candidate, "individual")


def test_prediction_binding_rejects_real_posterior_and_unbound_values() -> None:
    context = _context(
        ProblemInfo(2, 1, ("single",)),
        population_size=3,
    )
    pool = search_candidates(
        prepare_search(context, pymoo_ga()),
        3,
        origin="typed",
    )
    predicted = bind_predicted_costs(
        pool,
        tuple((row.normalized_variables[0],) for row in pool.candidates),
        source="test",
    )

    assert isinstance(pool, CandidatePool)
    assert isinstance(predicted, PredictedCostRows)
    selection = select_candidates(pool.state, pool, predicted, 2)
    assert len(selection.candidates) == 2
    assert selection.population == tuple(
        row.normalized_variables for row in selection.candidates
    )
    with pytest.raises(ValueError, match="align"):
        bind_predicted_costs(pool, ((0.1,),), source="partial")
    with pytest.raises(ValueError, match="finite"):
        bind_predicted_costs(
            pool,
            ((0.1,), (float("nan"),), (0.3,)),
            source="nonfinite",
        )
    wrong_width = bind_predicted_costs(
        pool,
        ((0.1, 0.9), (0.2, 0.8), (0.3, 0.7)),
        source="wrong-width",
    )
    with pytest.raises(ValueError, match="objective width"):
        select_candidates(pool.state, pool, wrong_width, 1)
    reversed_prediction = PredictedCostRows(
        candidate_ids=tuple(
            row.candidate_id for row in reversed(pool.candidates)
        ),
        normalized_variables=tuple(reversed(pool.population)),
        costs=tuple(reversed(predicted.costs)),
        interpretation_fingerprint=predicted.interpretation_fingerprint,
        state_signature=predicted.state_signature,
        source="reversed",
    )
    with pytest.raises(ValueError, match="candidate IDs"):
        select_candidates(pool.state, pool, reversed_prediction, 1)

    foreign_values = (
        object.__new__(CostTable),
        object.__new__(JointObjectiveSamples),
        object.__new__(SurrogatePrediction),
    )
    for foreign in foreign_values:
        with pytest.raises(TypeError):
            bind_predicted_costs(pool, foreign, source="wrong")
        with pytest.raises(TypeError):
            select_candidates(pool.state, pool, foreign, 1)
    with pytest.raises(TypeError, match="SurrogatePrediction"):
        bind_surrogate_prediction(pool, object())

    other_state = prepare_search(
        _context(
            ProblemInfo(2, 1, ("single",)),
            population_size=3,
            signature="3" * 64,
        ),
        pymoo_ga(),
    )
    with pytest.raises(ValueError, match="different strategy/generation roots"):
        select_candidates(other_state, pool, predicted, 1)
    other_generation_state = prepare_search(
        _context(
            ProblemInfo(2, 1, ("single",)),
            population_size=3,
            generation=1,
        ),
        pymoo_ga(),
    )
    with pytest.raises(ValueError, match="different strategy/generation roots"):
        select_candidates(other_generation_state, pool, predicted, 1)


def test_combined_prediction_rebinds_by_id_and_rejects_missing_or_mixed_semantics(
) -> None:
    context = _context(
        ProblemInfo(2, 1, ("single",)),
        population_size=4,
    )
    first = search_candidates(
        prepare_search(context, pymoo_ga()),
        2,
        origin="first",
    )
    second = search_candidates(first.state, 2, origin="second")
    fingerprint = "a" * 64
    state_signature = "b" * 64
    first_prediction = bind_predicted_costs(
        first,
        ((1.0,), (2.0,)),
        source="first",
        interpretation_fingerprint=fingerprint,
        state_signature=state_signature,
    )
    second_prediction = bind_predicted_costs(
        second,
        ((3.0,), (4.0,)),
        source="second",
        interpretation_fingerprint=fingerprint,
        state_signature=state_signature,
    )
    combined_pool = combine_candidate_pools(second.state, (second, first))

    combined = combine_predicted_cost_rows(
        combined_pool,
        (first_prediction, second_prediction),
        source="combined",
    )

    assert combined.candidate_ids == tuple(
        candidate.candidate_id for candidate in combined_pool.candidates
    )
    assert combined.costs == ((3.0,), (4.0,), (1.0,), (2.0,))
    assert combined.diagnostics["combined_prediction_count"] == 2

    with pytest.raises(ValueError, match="does not cover every pool candidate"):
        combine_predicted_cost_rows(
            combined_pool,
            (first_prediction,),
            source="missing",
        )
    incompatible = bind_predicted_costs(
        second,
        ((3.0,), (4.0,)),
        source="mixed",
        interpretation_fingerprint="c" * 64,
        state_signature=state_signature,
    )
    with pytest.raises(ValueError, match="different fitted semantics"):
        combine_predicted_cost_rows(
            combined_pool,
            (first_prediction, incompatible),
            source="mixed",
        )


def test_search_exhaustion_is_bounded_for_quantized_archive() -> None:
    context = _context(
        ProblemInfo(1, 1, ("single",)),
        population_size=3,
        decimals=0,
        seed=17,
    )
    state = prepare_search(context, pymoo_ga())

    with pytest.raises(InsufficientCandidatePoolError, match="bounded ask/refill"):
        search_candidates(state, 3, origin="exhaust")


def test_pymoo_remains_owner_of_algorithm_ask_tell_and_survival(monkeypatch) -> None:
    from yadof.optimize.pymoo import backend

    calls = {"new": 0, "ask": 0, "tell": 0, "survival": 0}

    def wrap(name, counter):
        original = getattr(backend, name)

        def spy(*args, **kwargs):
            calls[counter] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(backend, name, spy)

    wrap("new_algorithm", "new")
    wrap("generate_candidate_pool", "ask")
    wrap("advance_population_with_records", "tell")
    wrap("select_records_by_survival", "survival")

    context = _context(
        ProblemInfo(2, 1, ("single",)),
        population_size=3,
    )
    state = prepare_search(context, pymoo_ga())
    pool = search_candidates(state, 3, origin="owner")
    predicted = bind_predicted_costs(
        pool,
        tuple((float(index),) for index in range(3)),
        source="owner-test",
    )
    select_candidates(pool.state, pool, predicted, 2)
    advance_search(pool.state, pool, predicted)

    assert all(count >= 1 for count in calls.values())
    assert not hasattr(state, "ask")
    assert not hasattr(state, "tell")
    assert not hasattr(state, "survival")


class _DeterministicLegacySurrogate:
    def has_trained_state(self, _context):
        return True

    def predict_population(self, _context, rows):
        output = []
        for left, right in rows:
            first = 0.7 * float(left) + 0.3 * float(right)
            costs = (first, 1.0 - first)
            output.append((costs, tuple((value, value) for value in costs)))
        return tuple(output)

    def semantic_identity(self, _config, _problem):
        return {"component": "deterministic-legacy-test"}


class _ExplicitDeterministicSurrogate:
    def __init__(self) -> None:
        self.events = []

    def validate(self, _config, _problem) -> None:
        self.events.append("validate")

    def semantic_identity(self, _config, _problem):
        return {"component": "explicit-deterministic-test"}

    def training_data(self, _dataset, _cost_table, *, row_ids=None, transform_id=None):
        del row_ids, transform_id
        raise AssertionError("the program owns training-data materialization")

    def ensure_fresh_enough(self, _context, training_data):
        assert isinstance(training_data, SurrogateTrainingData)
        self.events.append("freshness")
        return SimpleNamespace(
            action="fresh",
            pending_generation_index=None,
            latest_completed_generation_index=2,
            error="",
        )

    def latest_trained_generation(self, _context, training_data) -> int | None:
        assert isinstance(training_data, SurrogateTrainingData)
        self.events.append("freshness")
        return 2

    def has_trained_state(self, _context, training_data) -> bool:
        assert isinstance(training_data, SurrogateTrainingData)
        self.events.append("readiness")
        return True

    def start_training(self, _context, training_data):
        assert isinstance(training_data, SurrogateTrainingData)
        self.events.append("start-training")
        return SimpleNamespace(
            action="started",
            pending_generation_index=3,
            latest_completed_generation_index=2,
            error="",
        )

    def finish_training(self, _context):
        self.events.append("finish-training")
        return SimpleNamespace(
            action="completed",
            pending_generation_index=None,
            latest_completed_generation_index=3,
            error="",
        )

    def predict_for_selection(self, context, rows, training_data=None):
        assert isinstance(training_data, SurrogateTrainingData)
        self.events.append("predict")
        population = tuple(tuple(float(value) for value in row) for row in rows)
        costs = tuple(
            (0.7 * left + 0.3 * right, 0.3 * left + 0.7 * right)
            for left, right in population
        )
        raw_data = tuple(
            StructuredRawDataSample.from_items(
                {
                    "response.npz": {
                        "values": np.asarray(cost_row),
                        "metadata": {
                            "schema_version": RAWDATA_SCHEMA_VERSION,
                            "shape": [2],
                            "rawdata_name": "response",
                        },
                    }
                }
            )
            for cost_row in costs
        )
        return SurrogatePrediction(
            state_signature="3" * 64,
            training_data_digest=training_data.content_digest,
            normalized_variables=population,
            raw_data=raw_data,
            costs=costs,
            intervals=tuple(
                tuple((value, value) for value in cost_row)
                for cost_row in costs
            ),
            interpretation_fingerprint=context.snapshot.interpretation_fingerprint,
        )


def test_explicit_gpsaf_selection_and_training_use_only_materialized_data() -> None:
    context = _context(
        ProblemInfo(2, 2, ("first", "second")),
        history=HISTORY_MULTI,
        generation=3,
        seed=271828,
    )
    training = SurrogateTrainingData(
        ("left", "right"),
        ((0.2, 0.8),),
        (
            StructuredRawDataSample.from_items(
                {
                    "response.npz": {
                        "values": np.asarray((0.25, 0.75)),
                        "metadata": {
                            "schema_version": RAWDATA_SCHEMA_VERSION,
                            "shape": [2],
                            "rawdata_name": "response",
                        },
                    }
                }
            ),
        ),
        row_ids=("evidence-1",),
    )
    surrogate = _ExplicitDeterministicSurrogate()
    selected = select_gpsaf_generation(
        context,
        search=pymoo_nsga3(reference_direction_partitions=3),
        surrogate=surrogate,
        settings=gpsaf_settings(
            alpha=2,
            beta=1,
            gamma=0.5,
            exploration_fraction=0.25,
        ),
        training_data=training,
    )

    assert len(selected.population) == context.population_size
    assert selected.surrogate_used is True, dict(selected.diagnostics)
    assert selected.diagnostics["surrogate_gamma"] == 0.5
    assert selected.diagnostics["surrogate_training_row_ids"] == ("evidence-1",)
    assert surrogate.events[:3] == ["validate", "freshness", "readiness"]
    assert "predict" in surrogate.events
    assert "start-training" not in surrogate.events

    started = start_explicit_surrogate_training(
        surrogate,
        context,
        training,
    )
    finished = finish_explicit_surrogate_training(surrogate, context)
    assert started["surrogate_training_start"] == "started"
    assert finished["surrogate_training_finish"] == "completed"
    assert surrogate.events[-2:] == ["start-training", "finish-training"]


def test_gpsaf_golden_population_and_gamma_semantics_remain_unchanged() -> None:
    seed = 271828
    generation = 3
    problem = ProblemInfo(2, 2, ("first", "second"))
    context = _context(
        problem,
        history=HISTORY_MULTI,
        generation=generation,
        seed=seed,
    )
    search = pymoo_nsga3(reference_direction_partitions=3)
    surrogate = _DeterministicLegacySurrogate()

    def run(gamma):
        return surrogate_population(
            HISTORY_MULTI,
            generation_context=context,
            search=search,
            surrogate=surrogate,
            generation_index=generation,
            population_size=4,
            seed=seed,
            settings=create_gpsaf_settings(
                alpha=3,
                beta=2,
                gamma=gamma,
                exploration_fraction=0.25,
            ),
        )

    expected = (
        (0.9041488429305145, 0.7130378314064403),
        (0.052564070396267565, 0.15),
        (0.12990148399388463, 0.7522338506183172),
        (0.007789022113735958, 0.24176311643493506),
    )
    population, diagnostics = run(0.5)
    other_population, _ = run(0.9)

    assert population == expected
    assert other_population == expected
    assert diagnostics["alpha_candidate_count"] == 9
    assert diagnostics["beta_candidate_count"] == 6
    assert diagnostics["beta_cluster_sizes"] == (2, 1, 3)
    assert diagnostics["beta_replacements"] == 1
    assert diagnostics["exploration_count"] == 1

    first_identity = gpsaf(
        search=search,
        surrogate=surrogate,
        alpha=3,
        beta=2,
        gamma=0.5,
        exploration_fraction=0.25,
    ).semantic_identity(context.config, problem)
    second_identity = gpsaf(
        search=search,
        surrogate=surrogate,
        alpha=3,
        beta=2,
        gamma=0.9,
        exploration_fraction=0.25,
    ).semantic_identity(context.config, problem)
    assert first_identity["gpsaf_parameters"]["gamma"] == 0.5
    assert second_identity["gpsaf_parameters"]["gamma"] == 0.9
    assert first_identity != second_identity
