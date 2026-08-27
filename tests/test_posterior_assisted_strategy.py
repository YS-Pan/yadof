from __future__ import annotations

from contextlib import contextmanager
import importlib
from types import SimpleNamespace

import numpy as np
import pytest

from yadof.job_template.rawdata_projector import JointObjectiveSamples
from yadof.optimize import (
    PosteriorAssistedStrategy,
    calibrated_applicability_gate,
    posterior_assisted,
    qnehvi,
)
from yadof.optimize.posterior_assisted import (
    _fixed_real_pareto_baseline,
    _partition_candidates,
)
from yadof.optimize.problem_info import ProblemInfo
from yadof.optimize.pymoo.backend import CandidateRecord
from yadof.optimize.qnehvi_acquisition import (
    DiscreteQNEHVIAcquisition,
    QNEHVIConfigurationError,
    QNEHVIFallback,
    QNEHVISelection,
    QNEHVISupportRejected,
)
from yadof.optimize.qnehvi_backend import DiscreteQLogNEHVIResult
from yadof.optimize.strategy import HistoryRecord
from yadof.surrogate import conditional_inr_posterior, hierarchical_cae
from yadof.surrogate.exploitation import (
    APPLICABILITY_CALIBRATED,
    APPLICABILITY_NOT_APPLICABLE,
    PERFORMANCE_ACCEPTED,
    PERFORMANCE_NOT_ACCEPTED,
    POSTERIOR_CALIBRATED,
    POSTERIOR_UNCALIBRATED,
    PosteriorExploitationReadiness,
    require_posterior_exploitation_surrogate,
)
from yadof.surrogate.posterior import RawDataPosteriorDiagnostics, SUPPORT_FINITE


STATE_SHA = "1" * 64
ARTIFACT_SHA = "2" * 64
POLICY_SHA = "3" * 64


class _Search:
    def validate(self, config, problem) -> None:
        del config, problem

    def resolve_algorithm(self, objective_count: int) -> str:
        assert objective_count >= 2
        return "nsga3"

    def semantic_identity(self, config, problem):
        del config
        return {"component": "test-search", "objectives": problem.objective_count}


class _BlockedSurrogate:
    def __init__(self) -> None:
        self.training_requests = 0

    def validate(self, config, problem) -> None:
        del config, problem

    def semantic_identity(self, config, problem):
        del config, problem
        return {"component": "blocked-test-surrogate"}

    def posterior_semantic_identity(self, config, problem):
        del config, problem
        return {"capability": "joint-rawdata-posterior"}

    def make_rawdata_sampler(self, context, *, draw_count: int, seed: int):
        raise AssertionError((context, draw_count, seed))

    def exploitation_semantic_identity(self, config, problem):
        del config, problem
        return {
            "performance_status": PERFORMANCE_NOT_ACCEPTED,
            "posterior_status": POSTERIOR_UNCALIBRATED,
            "applicability_status": APPLICABILITY_NOT_APPLICABLE,
            "transferable": False,
            "observation_noise_included": False,
        }

    def assess_posterior_exploitation(self, context, population):
        del context
        return PosteriorExploitationReadiness.blocked(
            population,
            applicability_status=APPLICABILITY_NOT_APPLICABLE,
            failure_reasons=("synthetic scientific gate",),
        )

    def start_training(self, context):
        del context
        self.training_requests += 1
        return SimpleNamespace(action="started")


class _Sampler:
    def __init__(self) -> None:
        self.schema = SimpleNamespace(signature="schema")
        self._diagnostics = RawDataPosteriorDiagnostics(
            posterior_kind="accepted-test-posterior",
            requested_draw_count=2,
            support_kind=SUPPORT_FINITE,
            unique_support=2,
            seed=19,
            draw_ids=("draw-0", "draw-1"),
            draw_sources=("member-0", "member-1"),
            schema_signature="schema",
            state_signature=STATE_SHA,
            strategy_signature="test-strategy",
            approximate=True,
            limitations=("test-only",),
            field_selectors=(),
            observation_noise_included=False,
            calibrated=True,
            calibration_method="test-calibration",
            calibration_artifact_sha256=ARTIFACT_SHA,
        )

    @property
    def diagnostics(self):
        return self._diagnostics

    def predict(self, population):
        raise AssertionError(population)


class _AcceptedSurrogate:
    def __init__(self, probabilities=None) -> None:
        self.probabilities = probabilities
        self.training_requests = 0

    def validate(self, config, problem) -> None:
        del config, problem

    def semantic_identity(self, config, problem):
        del config, problem
        return {"component": "accepted-test-surrogate"}

    def posterior_semantic_identity(self, config, problem):
        del config, problem
        return {"capability": "joint-rawdata-posterior"}

    def exploitation_semantic_identity(self, config, problem):
        del config, problem
        return {
            "performance_status": PERFORMANCE_ACCEPTED,
            "posterior_status": POSTERIOR_CALIBRATED,
            "applicability_status": (
                APPLICABILITY_NOT_APPLICABLE
                if self.probabilities is None
                else APPLICABILITY_CALIBRATED
            ),
            "transferable": True,
            "observation_noise_included": False,
        }

    def assess_posterior_exploitation(self, context, population):
        del context
        return PosteriorExploitationReadiness(
            population=population,
            performance_status=PERFORMANCE_ACCEPTED,
            posterior_status=POSTERIOR_CALIBRATED,
            applicability_status=(
                APPLICABILITY_NOT_APPLICABLE
                if self.probabilities is None
                else APPLICABILITY_CALIBRATED
            ),
            transferable=True,
            observation_noise_included=False,
            state_signature=STATE_SHA,
            calibration_artifact_sha256=ARTIFACT_SHA,
            smooth_probabilities=self.probabilities,
        )

    def ensure_fresh_enough(self, context):
        del context
        return SimpleNamespace(
            action="ready",
            pending_generation_index=None,
            latest_completed_generation_index=3,
            error="",
        )

    def has_trained_state(self, context) -> bool:
        del context
        return True

    def make_rawdata_sampler(self, context, *, draw_count: int, seed: int):
        del context, seed
        assert draw_count == 2
        return _Sampler()

    def start_training(self, context):
        del context
        self.training_requests += 1
        return SimpleNamespace(action="started")


def _problem() -> ProblemInfo:
    return ProblemInfo(
        variable_count=2,
        objective_count=2,
        objective_names=("drag", "mass"),
    )


def _config(population_size: int = 2):
    return SimpleNamespace(
        OPTIMIZE_POPULATION_SIZE=population_size,
        OPTIMIZE_ARCHIVE_KEY_DECIMALS=10,
        OPTIMIZE_REFILL_ATTEMPTS=4,
        OPTIMIZE_NSGA3_REF_DIR_METHOD="das-dennis",
        OPTIMIZE_NSGA3_PARTITIONS=1,
        OPTIMIZE_CROSSOVER_PROBABILITY=0.8,
        OPTIMIZE_MUTATION_PROBABILITY=0.35,
        OPTIMIZE_CROSSOVER_ETA=20.0,
        OPTIMIZE_MUTATION_ETA=20.0,
        OPTIMIZE_DIM_MUT_PER_INDIVIDUAL=1,
    )


def _context(*, history=(), population_size: int = 2):
    config = _config(population_size)
    return SimpleNamespace(
        config=config,
        generation_index=1,
        population_size=population_size,
        random_seed=17,
        history=tuple(history),
        problem=_problem(),
        snapshot=SimpleNamespace(
            config=SimpleNamespace(workspace=SimpleNamespace())
        ),
        session=SimpleNamespace(),
        run_id="test-run",
        optimization_index=0,
        strategy_signature="test-strategy",
        strategy_identity={},
    )


def _samples(
    population=((0.2,), (0.4,), (0.6,)),
    *,
    support_kind="finite",
    draw_sources=("member-0", "member-1"),
) -> JointObjectiveSamples:
    rows = tuple(tuple(float(value) for value in row) for row in population)
    draw_count = len(draw_sources)
    costs = np.empty((draw_count, len(rows), 2), dtype=np.float64)
    for draw_index in range(draw_count):
        for candidate_index, row in enumerate(rows):
            costs[draw_index, candidate_index] = (
                0.1 + 0.1 * draw_index + 0.2 * row[0],
                0.8 - 0.1 * draw_index - 0.2 * row[0],
            )
    source = {
        "support_kind": support_kind,
        "draw_sources": list(draw_sources),
    }
    if support_kind == "finite":
        source["unique_support"] = len(set(draw_sources))
        source["effective_unique_support"] = len(set(draw_sources))
    return JointObjectiveSamples.from_arrays(
        cost_samples=costs,
        valid_mask=np.ones((draw_count, len(rows)), dtype=bool),
        draw_ids=tuple(f"draw-{index}" for index in range(draw_count)),
        normalized_population=rows,
        objective_names=("drag", "mass"),
        source_diagnostics=source,
    )


def _strategy(surrogate) -> PosteriorAssistedStrategy:
    return posterior_assisted(
        search=_Search(),
        surrogate=surrogate,
        acquisition=qnehvi(batch_size=1, greedy_restarts=2),
        candidate_pool_size=4,
        posterior_draws=2,
        candidate_chunk_size=2,
        exploration_fraction=0.5,
    )


def test_qnehvi_rejects_pending_outcomes_and_single_objective() -> None:
    with pytest.raises(NotImplementedError, match="pending-state"):
        qnehvi(batch_size=1, greedy_restarts=1, pending_points=())
    with pytest.raises(NotImplementedError, match="outcome-constraint"):
        qnehvi(batch_size=1, greedy_restarts=1, outcome_constraints=())
    component = qnehvi(batch_size=1, greedy_restarts=1)
    with pytest.raises(ValueError, match="at least two objectives"):
        component.validate(
            SimpleNamespace(),
            ProblemInfo(1, 1, ("cost",)),
        )


def test_qnehvi_greedy_multistart_delegates_every_numeric_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yadof.optimize.qnehvi_acquisition as module

    calls = []

    def fake_backend(**kwargs):
        batches = tuple(tuple(batch) for batch in kwargs["candidate_batches"])
        calls.append((int(kwargs["seed"]), batches))
        weights = (1.0, 3.0, 2.0)
        values = tuple(
            sum(weights[index] for index in batch)
            + (5.0 if {1, 2}.issubset(batch) else 0.0)
            for batch in batches
        )
        return DiscreteQLogNEHVIResult(
            batch_indices=batches,
            log_acquisition_values=values,
            diagnostics={
                "elapsed_sec": 0.01,
                "resident_tensor_bytes": 128,
                "cuda_peak_allocated_bytes": 0,
                "backend_distribution": "spy",
            },
        )

    monkeypatch.setattr(module, "score_discrete_qlognehvi", fake_backend)
    acquisition = qnehvi(batch_size=2, greedy_restarts=2)
    first = acquisition.select_batch(
        baseline_population=((0.0,),),
        baseline_costs=((0.8, 0.8),),
        candidate_samples=_samples(),
        seed=29,
    )
    second = acquisition.select_batch(
        baseline_population=((0.0,),),
        baseline_costs=((0.8, 0.8),),
        candidate_samples=_samples(),
        seed=29,
    )

    assert set(first.selected_indices) == {1, 2}
    assert first.selected_indices == second.selected_indices
    assert first.log_acquisition_value == second.log_acquisition_value
    assert calls
    assert all(seed == 29 for seed, _batches in calls)
    assert first.diagnostics["backend_call_count"] == 3
    assert first.diagnostics["maximum_resident_tensor_bytes"] == 128


def test_qnehvi_empty_duplicate_and_support_policies_fail_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yadof.optimize.qnehvi_acquisition as module

    empty = JointObjectiveSamples.from_arrays(
        cost_samples=np.empty((2, 0, 2)),
        valid_mask=np.empty((2, 0), dtype=bool),
        draw_ids=("draw-0", "draw-1"),
        normalized_population=(),
        objective_names=("a", "b"),
        source_diagnostics={
            "support_kind": "finite",
            "unique_support": 2,
            "draw_sources": ["one", "two"],
        },
    )
    with pytest.raises(QNEHVIFallback, match="empty"):
        qnehvi(batch_size=1, greedy_restarts=1).select_batch(
            baseline_population=((0.0,),),
            baseline_costs=((0.5, 0.5),),
            candidate_samples=empty,
            seed=1,
        )
    with pytest.raises(QNEHVIConfigurationError, match="unique"):
        qnehvi(batch_size=1, greedy_restarts=1).select_batch(
            baseline_population=((0.0,),),
            baseline_costs=((0.5, 0.5),),
            candidate_samples=_samples(((0.2,), (0.2,))),
            seed=1,
        )

    low = _samples(draw_sources=("member-0", "member-0"))
    with pytest.raises(QNEHVIFallback, match="effective support"):
        qnehvi(
            batch_size=1,
            greedy_restarts=1,
            minimum_unique_support=2,
            low_support_policy="fallback",
        ).select_batch(
            baseline_population=((0.0,),),
            baseline_costs=((0.5, 0.5),),
            candidate_samples=low,
            seed=1,
        )
    with pytest.raises(QNEHVISupportRejected, match="effective support"):
        qnehvi(
            batch_size=1,
            greedy_restarts=1,
            minimum_unique_support=2,
            low_support_policy="reject",
        ).select_batch(
            baseline_population=((0.0,),),
            baseline_costs=((0.5, 0.5),),
            candidate_samples=low,
            seed=1,
        )
    with pytest.raises(QNEHVIConfigurationError, match="explicitly finite"):
        qnehvi(
            batch_size=1,
            greedy_restarts=1,
            minimum_unique_support=2,
        ).select_batch(
            baseline_population=((0.0,),),
            baseline_costs=((0.5, 0.5),),
            candidate_samples=_samples(support_kind="continuous_or_unknown"),
            seed=1,
        )
    monkeypatch.setattr(
        module,
        "score_discrete_qlognehvi",
        lambda **kwargs: DiscreteQLogNEHVIResult(
            batch_indices=tuple(tuple(row) for row in kwargs["candidate_batches"]),
            log_acquisition_values=tuple(
                float(index)
                for index, _row in enumerate(kwargs["candidate_batches"])
            ),
            diagnostics={"elapsed_sec": 0.0},
        ),
    )
    warned = qnehvi(
        batch_size=1,
        greedy_restarts=1,
        minimum_unique_support=2,
        low_support_policy="warn",
    ).select_batch(
        baseline_population=((0.0,),),
        baseline_costs=((0.5, 0.5),),
        candidate_samples=low,
        seed=1,
    )
    assert warned.diagnostics["support"]["low_support"] is True


def test_fixed_real_baseline_filters_contract_failures_and_keeps_finite_one() -> None:
    baseline = _fixed_real_pareto_baseline(
        (
            HistoryRecord("a", (0.1, 0.1), (0.2, 0.8)),
            HistoryRecord("a-copy", (0.1, 0.1), (0.2, 0.8)),
            HistoryRecord("dominated", (0.2, 0.2), (1.0, 1.0)),
            HistoryRecord("tradeoff", (0.3, 0.3), (0.8, 0.2)),
            HistoryRecord("bad-width", (0.4,), (0.1, 0.1)),
            HistoryRecord("nan", (0.4, 0.4), (float("nan"), 0.1)),
            HistoryRecord("out", (0.5, 0.5), (1.1, 0.1)),
            HistoryRecord("conflict-a", (0.6, 0.6), (0.4, 0.4)),
            HistoryRecord("conflict-b", (0.6, 0.6), (0.5, 0.5)),
        ),
        variable_count=2,
        objective_count=2,
        decimals=10,
    )

    assert baseline.population == ((0.1, 0.1), (0.3, 0.3))
    assert baseline.costs == ((0.2, 0.8), (0.8, 0.2))
    assert baseline.diagnostics["identical_duplicate_count"] == 1
    assert baseline.diagnostics["conflicting_duplicate_key_count"] == 1
    assert baseline.diagnostics["finite_one_is_valid"] is True
    assert baseline.diagnostics["excluded_by_reason"] == {
        "conflicting_duplicate": 2,
        "objective_nonfinite": 1,
        "objective_out_of_contract": 1,
        "parameter_width": 1,
    }


def test_current_posterior_components_are_typed_and_fail_closed() -> None:
    for component in (conditional_inr_posterior(), hierarchical_cae()):
        identity = component.exploitation_semantic_identity(None, None)
        readiness = component.assess_posterior_exploitation(
            SimpleNamespace(), ((0.2, 0.4),)
        )
        assert identity["performance_status"] == PERFORMANCE_NOT_ACCEPTED
        assert identity["posterior_status"] == POSTERIOR_UNCALIBRATED
        assert identity["transferable"] is False
        assert readiness.ready is False
        assert readiness.smooth_probabilities is None
        assert readiness.failure_reasons


def test_member_variance_is_not_a_typed_exploitation_capability() -> None:
    variance_only = SimpleNamespace(
        predict_population=lambda *_args: (((0.2, 0.3), (0.5, 0.5)),)
    )
    with pytest.raises(TypeError, match="variance alone"):
        require_posterior_exploitation_surrogate(variance_only)


def test_calibrated_applicability_excludes_low_probability_from_exploitation() -> None:
    readiness = PosteriorExploitationReadiness(
        population=((0.1,), (0.2,), (0.3,), (0.4,), (0.5,)),
        performance_status=PERFORMANCE_ACCEPTED,
        posterior_status=POSTERIOR_CALIBRATED,
        applicability_status=APPLICABILITY_CALIBRATED,
        transferable=True,
        observation_noise_included=False,
        state_signature=STATE_SHA,
        calibration_artifact_sha256=ARTIFACT_SHA,
        smooth_probabilities=(0.1, 0.48, 0.51, 0.8, 0.9),
    )
    gate = calibrated_applicability_gate(
        minimum_smooth_probability=0.5,
        boundary_width=0.03,
        policy_version="sealed-test-policy-v1",
        calibration_policy_sha256=POLICY_SHA,
        exploration_priority="boundary-then-low",
    )
    exploration, eligible, diagnostics = _partition_candidates(
        readiness, gate, 2, __import__("random").Random(7)
    )

    assert set(eligible) <= {2, 3, 4}
    assert 0 not in eligible and 1 not in eligible
    assert len(exploration) == 2
    assert diagnostics["gate_applied"] is True
    assert diagnostics["boundary_exploration_count"] >= 1
    assert diagnostics["low_probability_exploration_count"] >= 1


def test_static_scientific_gate_falls_back_through_common_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("yadof.optimize.posterior_assisted")

    surrogate = _BlockedSurrogate()
    strategy = _strategy(surrogate)
    calls = []

    def fake_evaluate(context, population, *, after_jobs_submitted=None):
        calls.append((context, population))
        assert after_jobs_submitted is not None
        after_jobs_submitted()
        return tuple((0.4, 0.6) for _ in population)

    monkeypatch.setattr(module, "evaluate_population", fake_evaluate)
    result = strategy.run_generation(_context())

    assert len(calls) == 1
    assert calls[0][1] == result.population
    assert len(result.population) == 2
    assert result.surrogate_used is False
    assert result.diagnostics["fallback_reason"] == (
        "typed-exploitation-capability-blocked"
    )
    assert result.diagnostics["evaluation_handoff"] == (
        "common-real-evaluate-population"
    )
    assert surrogate.training_requests == 1


def test_common_evaluator_recording_failure_still_aborts_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("yadof.optimize.posterior_assisted")

    def fail_recording(*_args, **_kwargs):
        raise RuntimeError("synthetic recorder failure")

    monkeypatch.setattr(module, "evaluate_population", fail_recording)
    with pytest.raises(RuntimeError, match="recorder failure"):
        _strategy(_BlockedSurrogate()).run_generation(_context())


def test_accepted_path_projects_then_hands_every_selected_point_to_real_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yadof.job_template.rawdata_projector as projector_module
    module = importlib.import_module("yadof.optimize.posterior_assisted")

    surrogate = _AcceptedSurrogate()
    strategy = _strategy(surrogate)
    pool = (
        CandidateRecord(x=(0.1, 0.1), origin="test"),
        CandidateRecord(x=(0.2, 0.2), origin="test"),
        CandidateRecord(x=(0.3, 0.3), origin="test"),
        CandidateRecord(x=(0.4, 0.4), origin="test"),
    )
    monkeypatch.setattr(module, "_candidate_pool", lambda *_args: list(pool))

    @contextmanager
    def fake_projector(*_args, **_kwargs):
        yield object()

    monkeypatch.setattr(
        projector_module, "task_rawdata_cost_projector", fake_projector
    )

    def fake_projection(_sampler, _projector, population, **_kwargs):
        return _samples(population)

    monkeypatch.setattr(module, "project_rawdata_sampler", fake_projection)

    def fake_select(self, **kwargs):
        assert kwargs["baseline_costs"] == ((0.2, 0.8), (0.8, 0.2))
        assert len(kwargs["candidate_samples"].normalized_population) == 3
        return QNEHVISelection((0,), 1.25, {"backend": "spy"})

    monkeypatch.setattr(DiscreteQNEHVIAcquisition, "select_batch", fake_select)
    evaluated = []

    def fake_evaluate(context, population, *, after_jobs_submitted=None):
        del context
        evaluated.append(population)
        after_jobs_submitted()
        return tuple((0.3, 0.7) for _ in population)

    monkeypatch.setattr(module, "evaluate_population", fake_evaluate)
    history = (
        HistoryRecord("left", (0.05, 0.05), (0.2, 0.8)),
        HistoryRecord("right", (0.95, 0.95), (0.8, 0.2)),
    )
    result = strategy.run_generation(_context(history=history))

    assert evaluated == [result.population]
    assert len(result.population) == 2
    assert len(set(result.population)) == 2
    assert result.surrogate_used is True
    assert result.source == "posterior_assisted_qnehvi"
    assert result.diagnostics["real_exploration_count"] == 1
    assert result.diagnostics["exploitation_count"] == 1
    assert result.diagnostics["predicted_rawdata_retained"] is False
    assert result.diagnostics["evaluation_handoff"] == (
        "common-real-evaluate-population"
    )
    assert surrogate.training_requests == 1


def test_backend_failure_falls_back_but_support_reject_stays_hard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yadof.job_template.rawdata_projector as projector_module
    module = importlib.import_module("yadof.optimize.posterior_assisted")

    strategy = _strategy(_AcceptedSurrogate())
    pool = [
        CandidateRecord(x=(value, value), origin="test")
        for value in (0.1, 0.2, 0.3, 0.4)
    ]
    monkeypatch.setattr(module, "_candidate_pool", lambda *_args: pool)

    @contextmanager
    def fake_projector(*_args, **_kwargs):
        yield object()

    monkeypatch.setattr(
        projector_module, "task_rawdata_cost_projector", fake_projector
    )
    monkeypatch.setattr(
        module,
        "project_rawdata_sampler",
        lambda _sampler, _projector, population, **_kwargs: _samples(population),
    )
    evaluations = []

    def fake_evaluate(_context, population, *, after_jobs_submitted=None):
        evaluations.append(population)
        if after_jobs_submitted is not None:
            after_jobs_submitted()
        return tuple((0.5, 0.5) for _ in population)

    monkeypatch.setattr(module, "evaluate_population", fake_evaluate)
    history = (
        HistoryRecord("left", (0.05, 0.05), (0.2, 0.8)),
        HistoryRecord("right", (0.95, 0.95), (0.8, 0.2)),
    )

    monkeypatch.setattr(
        DiscreteQNEHVIAcquisition,
        "select_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("synthetic backend missing")
        ),
    )
    fallback = strategy.run_generation(_context(history=history))
    assert fallback.surrogate_used is False
    assert fallback.diagnostics["fallback_reason"] == "posterior-selection-failure"
    assert len(evaluations) == 1

    evaluations.clear()
    monkeypatch.setattr(
        DiscreteQNEHVIAcquisition,
        "select_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            QNEHVISupportRejected("support rejected")
        ),
    )
    with pytest.raises(QNEHVISupportRejected, match="support rejected"):
        strategy.run_generation(_context(history=history))
    assert evaluations == []


def test_strategy_validation_rejects_variance_only_surrogate() -> None:
    variance_only = SimpleNamespace(
        validate=lambda *_args: None,
        semantic_identity=lambda *_args: {"component": "variance-only"},
        posterior_semantic_identity=lambda *_args: {"capability": "posterior"},
        make_rawdata_sampler=lambda *_args, **_kwargs: None,
        predict_population=lambda *_args: (),
    )
    strategy = _strategy(variance_only)
    with pytest.raises(TypeError, match="variance alone"):
        strategy.validate(_config(), _problem())


def test_strategy_identity_covers_all_controls_and_objective_names() -> None:
    strategy = _strategy(_BlockedSurrogate())
    identity = strategy.semantic_identity(_config(), _problem())

    assert identity["strategy"] == "posterior-assisted"
    assert identity["objective_names"] == ["drag", "mass"]
    controlled = identity["controlled_parameters"]
    assert controlled["candidate_pool_size"] == 4
    assert controlled["posterior_draws"] == 2
    assert controlled["candidate_chunk_size"] == 2
    assert controlled["exploration_fraction"] == 0.5
    acquisition = identity["acquisition"]["controlled_parameters"]
    assert acquisition["batch_size"] == 1
    assert acquisition["greedy_restarts"] == 2
    assert acquisition["pending_points"] == "unsupported"
    assert acquisition["outcome_constraints"] == "unsupported"
