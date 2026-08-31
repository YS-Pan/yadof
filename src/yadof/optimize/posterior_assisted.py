"""Independent posterior-assisted generation orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import random
from types import MappingProxyType
from typing import Mapping, Sequence

from ..surrogate.exploitation import (
    APPLICABILITY_CALIBRATED,
    APPLICABILITY_NOT_APPLICABLE,
    PERFORMANCE_ACCEPTED,
    POSTERIOR_CALIBRATED,
    PosteriorExploitationReadiness,
    require_posterior_exploitation_surrogate,
)
from ..surrogate.posterior import (
    RawDataPosteriorSampler,
    project_rawdata_sampler,
    require_rawdata_posterior_surrogate,
)
from ..surrogate.training import (
    DeterministicSurrogateComponent,
    SurrogateTrainingData,
    assess_surrogate_selection_freshness,
)
from .primitives import (
    CandidatePool,
    full_real_search,
    prepare_search,
    search_candidates,
)
from .qnehvi.acquisition import (
    DiscreteQNEHVIAcquisition,
    QNEHVIConfigurationError,
    QNEHVIFallback,
    QNEHVISupportRejected,
)
from .strategy import (
    GenerationContext,
    HistoryRecord,
    Population,
)


@dataclass(frozen=True, slots=True)
class CalibratedApplicabilityGate:
    """Pre-registered threshold and real-exploration ordering."""

    minimum_smooth_probability: float
    boundary_width: float
    policy_version: str
    calibration_policy_sha256: str
    exploration_priority: str

    def __post_init__(self) -> None:
        threshold = float(self.minimum_smooth_probability)
        width = float(self.boundary_width)
        if not math.isfinite(threshold) or threshold < 0.0 or threshold > 1.0:
            raise ValueError(
                "minimum_smooth_probability must be finite and in [0, 1]"
            )
        if not math.isfinite(width) or width < 0.0 or width > 1.0:
            raise ValueError("applicability boundary_width must be in [0, 1]")
        version = str(self.policy_version).strip()
        if not version:
            raise ValueError("applicability policy_version must not be empty")
        signature = str(self.calibration_policy_sha256).lower()
        if len(signature) != 64 or any(
            char not in "0123456789abcdef" for char in signature
        ):
            raise ValueError(
                "calibration_policy_sha256 must be a lowercase SHA-256 value"
            )
        priority = str(self.exploration_priority).strip().lower()
        if priority not in {"boundary-then-low", "low-then-boundary"}:
            raise ValueError(
                "exploration_priority must be 'boundary-then-low' or "
                "'low-then-boundary'"
            )
        object.__setattr__(self, "minimum_smooth_probability", threshold)
        object.__setattr__(self, "boundary_width", width)
        object.__setattr__(self, "policy_version", version)
        object.__setattr__(self, "calibration_policy_sha256", signature)
        object.__setattr__(self, "exploration_priority", priority)

    def semantic_identity(self) -> Mapping[str, object]:
        return {
            "gate": "calibrated-applicability-exploitation",
            "gate_version": 1,
            "minimum_smooth_probability": self.minimum_smooth_probability,
            "boundary_width": self.boundary_width,
            "policy_version": self.policy_version,
            "calibration_policy_sha256": self.calibration_policy_sha256,
            "exploitation_policy": "exclude-below-threshold-v1",
            "exploration_priority": self.exploration_priority,
        }


@dataclass(frozen=True, slots=True)
class _Baseline:
    population: Population
    costs: tuple[tuple[float, ...], ...]
    diagnostics: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PosteriorGenerationSelection:
    """One typed posterior-assisted or full-real selection awaiting evaluation."""

    population: Population
    source: str
    surrogate_used: bool
    diagnostics: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PosteriorAssistedSelector:
    """Select posterior-assisted or full-real candidates without orchestration."""

    search: object
    surrogate: object
    acquisition: DiscreteQNEHVIAcquisition
    candidate_pool_size: int
    posterior_draws: int
    candidate_chunk_size: int
    exploration_fraction: float
    applicability_gate: CalibratedApplicabilityGate | None = None

    def __post_init__(self) -> None:
        pool = int(self.candidate_pool_size)
        draws = int(self.posterior_draws)
        chunk = int(self.candidate_chunk_size)
        fraction = float(self.exploration_fraction)
        if pool <= 0:
            raise ValueError("candidate_pool_size must be positive")
        if draws <= 0:
            raise ValueError("posterior_draws must be positive")
        if chunk <= 0:
            raise ValueError("candidate_chunk_size must be positive")
        if not math.isfinite(fraction) or fraction <= 0.0 or fraction >= 1.0:
            raise ValueError("exploration_fraction must be strictly between 0 and 1")
        if not isinstance(self.acquisition, DiscreteQNEHVIAcquisition):
            raise TypeError("posterior_assisted_selector acquisition must be qnehvi()")
        if self.applicability_gate is not None and not isinstance(
            self.applicability_gate, CalibratedApplicabilityGate
        ):
            raise TypeError(
                "applicability_gate must be calibrated_applicability_gate()"
            )
        object.__setattr__(self, "candidate_pool_size", pool)
        object.__setattr__(self, "posterior_draws", draws)
        object.__setattr__(self, "candidate_chunk_size", chunk)
        object.__setattr__(self, "exploration_fraction", fraction)

    def validate(self, config, problem) -> None:
        if int(problem.objective_count) < 2:
            raise ValueError("posterior-assisted qNEHVI requires at least two objectives")
        search_validate = getattr(self.search, "validate", None)
        if not callable(search_validate):
            raise TypeError("posterior selector search must define validate()")
        search_validate(config, problem)
        surrogate_validate = getattr(self.surrogate, "validate", None)
        if not callable(surrogate_validate):
            raise TypeError("posterior selector surrogate must define validate()")
        surrogate_validate(config, problem)
        posterior = require_rawdata_posterior_surrogate(self.surrogate)
        exploitation = require_posterior_exploitation_surrogate(self.surrogate)
        self.acquisition.validate(config, problem)

        population_size = int(config.OPTIMIZE_POPULATION_SIZE)
        exploration_count = _exploration_count(
            population_size, self.exploration_fraction
        )
        if self.candidate_pool_size < population_size:
            raise ValueError(
                "candidate_pool_size must be at least OPTIMIZE_POPULATION_SIZE"
            )
        expected_batch = population_size - exploration_count
        if self.acquisition.batch_size != expected_batch:
            raise ValueError(
                "qNEHVI batch_size must equal population size minus the explicit "
                f"exploration quota ({expected_batch})"
            )
        identity = dict(exploitation.exploitation_semantic_identity(config, problem))
        applicability_status = identity.get("applicability_status")
        if (
            applicability_status == APPLICABILITY_CALIBRATED
            and self.applicability_gate is None
        ):
            raise ValueError(
                "calibrated applicability exploitation requires a pre-registered gate"
            )
        if (
            applicability_status == APPLICABILITY_NOT_APPLICABLE
            and self.applicability_gate is not None
        ):
            raise ValueError(
                "an applicability gate cannot be attached to a not-applicable capability"
            )
        del posterior

    def semantic_identity(self, config, problem) -> Mapping[str, object]:
        search_identity = getattr(self.search, "semantic_identity", None)
        surrogate_identity = getattr(self.surrogate, "semantic_identity", None)
        posterior = require_rawdata_posterior_surrogate(self.surrogate)
        exploitation = require_posterior_exploitation_surrogate(self.surrogate)
        if not callable(search_identity) or not callable(surrogate_identity):
            raise TypeError(
                "posterior selector components must expose semantic identities"
            )
        return {
            "component": "posterior-assisted-selector",
            "component_version": 1,
            "objective_names": list(problem.objective_names),
            "search": search_identity(config, problem),
            "surrogate": surrogate_identity(config, problem),
            "posterior": posterior.posterior_semantic_identity(config, problem),
            "exploitation_capability": exploitation.exploitation_semantic_identity(
                config, problem
            ),
            "acquisition": self.acquisition.semantic_identity(config, problem),
            "controlled_parameters": {
                "candidate_pool_size": self.candidate_pool_size,
                "posterior_draws": self.posterior_draws,
                "candidate_chunk_size": self.candidate_chunk_size,
                "exploration_fraction": self.exploration_fraction,
                "exploration_count_policy": "ceil-with-one-real-point-v1",
                "candidate_pool_adapter": "explicit-search-primitives-v1",
                "projection": "persistent-draw-streaming-current-cost-v1",
                "fixed_real_baseline": "nondominated-current-cost-v1",
                "applicability_gate": (
                    None
                    if self.applicability_gate is None
                    else self.applicability_gate.semantic_identity()
                ),
            },
        }

    def select_generation(
        self,
        context: GenerationContext,
        *,
        training_data: SurrogateTrainingData,
    ) -> PosteriorGenerationSelection:
        """Select candidates without owning evaluation, training, or commit."""

        if not isinstance(training_data, SurrogateTrainingData):
            raise TypeError(
                "posterior selection requires explicit SurrogateTrainingData"
            )
        self.validate(context.config, context.problem)
        diagnostics = _search_diagnostics(self, context)
        static_identity = dict(
            require_posterior_exploitation_surrogate(
                self.surrogate
            ).exploitation_semantic_identity(context.config, context.problem)
        )
        diagnostics["exploitation_capability"] = static_identity
        if not _static_exploitation_ready(static_identity):
            return self._real_fallback_selection(
                context,
                diagnostics,
                reason="typed-exploitation-capability-blocked",
                detail=(
                    "posterior exploitation requires performance acceptance, "
                    "calibration, transferability, and zero observation noise"
                ),
            )

        baseline = _fixed_real_pareto_baseline(
            context.history,
            variable_count=context.problem.variable_count,
            objective_count=context.problem.objective_count,
            decimals=int(context.config.OPTIMIZE_ARCHIVE_KEY_DECIMALS),
        )
        diagnostics["baseline"] = dict(baseline.diagnostics)
        if not baseline.population:
            return self._real_fallback_selection(
                context,
                diagnostics,
                reason="fixed-real-baseline-unavailable",
                detail="no unique finite in-contract real Pareto baseline is available",
            )

        freshness = _surrogate_selection_freshness(
            self.surrogate,
            context,
            training_data,
        )
        diagnostics.update(freshness)
        if not _surrogate_state_ready(self.surrogate, context, training_data):
            return self._real_fallback_selection(
                context,
                diagnostics,
                reason="surrogate-state-unavailable",
                detail="no trained state is available in the active strategy namespace",
            )

        try:
            selected = self._select_generation(
                context,
                baseline,
                training_data=training_data,
            )
        except QNEHVISupportRejected:
            raise
        except QNEHVIConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001 - selection failures must evaluate real points.
            reason = (
                "configured-acquisition-fallback"
                if isinstance(exc, QNEHVIFallback)
                else "posterior-selection-failure"
            )
            return self._real_fallback_selection(
                context,
                diagnostics,
                reason=reason,
                detail=_bounded_error(exc),
            )

        diagnostics.update(dict(selected.diagnostics))
        return PosteriorGenerationSelection(
            population=selected.population,
            source="posterior_assisted_qnehvi",
            surrogate_used=True,
            diagnostics=diagnostics,
        )

    def _select_generation(
        self,
        context: GenerationContext,
        baseline: _Baseline,
        *,
        training_data: SurrogateTrainingData,
    ) -> PosteriorGenerationSelection:
        candidate_pool = _candidate_pool(self, context)
        candidates = candidate_pool.candidates
        if len(candidates) != self.candidate_pool_size:
            raise QNEHVIFallback(
                "pymoo candidate pool did not reach the configured unique size"
            )
        pool = candidate_pool.population
        readiness = require_posterior_exploitation_surrogate(
            self.surrogate
        ).assess_posterior_exploitation(context, pool)
        if not isinstance(readiness, PosteriorExploitationReadiness):
            raise TypeError(
                "assess_posterior_exploitation must return "
                "PosteriorExploitationReadiness"
            )
        if readiness.population != pool:
            raise ValueError("exploitation readiness population does not match the pool")
        if not readiness.ready:
            raise QNEHVIFallback(
                "typed exploitation readiness is blocked: "
                + "; ".join(readiness.failure_reasons)
            )

        exploration_count = _exploration_count(
            context.population_size, self.exploration_fraction
        )
        if context.population_size - exploration_count != self.acquisition.batch_size:
            raise QNEHVIConfigurationError(
                "runtime population size changed the pre-registered qNEHVI/exploration split"
            )
        exploration, eligible, applicability = _partition_candidates(
            readiness,
            self.applicability_gate,
            exploration_count,
            random.Random(
                context.random_seed + context.generation_index * 1009 + 41047
            ),
        )
        if len(eligible) < self.acquisition.batch_size:
            raise QNEHVIFallback(
                "applicability gate left fewer exploitation candidates than batch_size"
            )
        exploitation_candidates = tuple(candidates[index] for index in eligible)

        posterior_surrogate = require_rawdata_posterior_surrogate(self.surrogate)
        sampler_seed = (
            context.random_seed + context.generation_index * 1009 + 73013
        )
        sampler = posterior_surrogate.make_rawdata_sampler(
            context,
            draw_count=self.posterior_draws,
            seed=sampler_seed,
            training_data=training_data,
        )
        if not isinstance(sampler, RawDataPosteriorSampler):
            raise TypeError(
                "make_rawdata_sampler must return a schema-bearing "
                "RawDataPosteriorSampler"
            )
        _require_sampler_matches_readiness(sampler, readiness)
        from ..job_template.rawdata_projector import task_rawdata_cost_projector

        with task_rawdata_cost_projector(
            context.snapshot.config.workspace,
            sampler.schema,
        ) as projector:
            samples = project_rawdata_sampler(
                sampler,
                projector,
                tuple(
                    candidate.normalized_variables
                    for candidate in exploitation_candidates
                ),
                candidate_chunk_size=self.candidate_chunk_size,
            )
        selection = self.acquisition.select_batch(
            baseline_population=baseline.population,
            baseline_costs=baseline.costs,
            candidate_samples=samples,
            seed=context.random_seed + context.generation_index * 1009 + 97001,
        )
        chosen_exploitation = tuple(
            exploitation_candidates[index].normalized_variables
            for index in selection.selected_indices
        )
        chosen_exploration = tuple(
            candidates[index].normalized_variables for index in exploration
        )
        population = chosen_exploitation + chosen_exploration
        if len(population) != context.population_size or len(set(population)) != len(
            population
        ):
            raise RuntimeError(
                "posterior-assisted selection did not produce one unique real population"
            )
        return PosteriorGenerationSelection(
            population=population,
            source="posterior_assisted_qnehvi",
            surrogate_used=True,
            diagnostics={
                **dict(candidate_pool.state.diagnostics),
                **dict(candidate_pool.diagnostics),
                "candidate_pool_count": len(candidates),
                "candidate_id_count": len(candidates),
                "posterior_draw_count": self.posterior_draws,
                "candidate_chunk_size": self.candidate_chunk_size,
                "readiness": readiness.as_dict(),
                "applicability": applicability,
                "real_exploration_count": len(chosen_exploration),
                "exploitation_count": len(chosen_exploitation),
                "projection": _compact_projection_diagnostics(samples),
                "acquisition": dict(selection.diagnostics),
                "predicted_rawdata_retained": False,
                "evaluation_handoff": "workspace-program-real-evaluation",
            },
        )

    def _real_fallback_selection(
        self,
        context: GenerationContext,
        diagnostics: dict[str, object],
        *,
        reason: str,
        detail: str,
    ) -> PosteriorGenerationSelection:
        selected = full_real_search(
            context,
            self.search,
            population_size=context.population_size,
            algorithm_seed=context.random_seed,
            random_seed=(
                context.random_seed + context.generation_index * 1009 + 19001
            ),
            origin_prefix="posterior_assisted_real",
        )
        population = selected.population
        diagnostics.update(dict(selected.state.diagnostics))
        diagnostics.update(dict(selected.diagnostics))
        diagnostics.update(
            {
                "optimizer": "posterior-assisted",
                "strategy": "posterior-assisted",
                "surrogate_used": False,
                "fallback": True,
                "fallback_reason": str(reason),
                "fallback_detail": str(detail)[:512],
                "evaluation_handoff": "workspace-program-real-evaluation",
            }
        )
        return PosteriorGenerationSelection(
            population=population,
            source=selected.source,
            surrogate_used=False,
            diagnostics=diagnostics,
        )


def calibrated_applicability_gate(
    *,
    minimum_smooth_probability: float,
    boundary_width: float,
    policy_version: str,
    calibration_policy_sha256: str,
    exploration_priority: str,
) -> CalibratedApplicabilityGate:
    return CalibratedApplicabilityGate(
        minimum_smooth_probability=minimum_smooth_probability,
        boundary_width=boundary_width,
        policy_version=policy_version,
        calibration_policy_sha256=calibration_policy_sha256,
        exploration_priority=exploration_priority,
    )


def posterior_assisted_selector(
    *,
    search: object,
    surrogate: object,
    acquisition: DiscreteQNEHVIAcquisition,
    candidate_pool_size: int,
    posterior_draws: int,
    candidate_chunk_size: int,
    exploration_fraction: float,
    applicability_gate: CalibratedApplicabilityGate | None = None,
) -> PosteriorAssistedSelector:
    return PosteriorAssistedSelector(
        search=search,
        surrogate=surrogate,
        acquisition=acquisition,
        candidate_pool_size=candidate_pool_size,
        posterior_draws=posterior_draws,
        candidate_chunk_size=candidate_chunk_size,
        exploration_fraction=exploration_fraction,
        applicability_gate=applicability_gate,
    )


def _search_diagnostics(
    strategy: PosteriorAssistedSelector,
    context: GenerationContext,
) -> dict[str, object]:
    return {
        "strategy": "posterior-assisted",
        "objective_count": int(context.problem.objective_count),
        "objective_names": list(context.problem.objective_names),
        "variable_count": int(context.problem.variable_count),
        "candidate_pool_size": strategy.candidate_pool_size,
        "posterior_draws": strategy.posterior_draws,
        "candidate_chunk_size": strategy.candidate_chunk_size,
        "exploration_fraction": strategy.exploration_fraction,
    }


def _candidate_pool(
    strategy: PosteriorAssistedSelector,
    context: GenerationContext,
) -> CandidatePool:
    state = prepare_search(
        context,
        strategy.search,
        population_size=strategy.candidate_pool_size,
        algorithm_seed=(
            context.random_seed + context.generation_index * 1009 + 27011
        ),
        random_seed=(
            context.random_seed + context.generation_index * 1009 + 35023
        ),
        history_policy="survivor",
    )
    return search_candidates(
        state,
        strategy.candidate_pool_size,
        origin="posterior_assisted_pool",
    )


def _fixed_real_pareto_baseline(
    history: Sequence[HistoryRecord],
    *,
    variable_count: int,
    objective_count: int,
    decimals: int,
) -> _Baseline:
    excluded: Counter[str] = Counter()
    rows: dict[tuple[float, ...], tuple[tuple[float, ...], tuple[float, ...]]] = {}
    conflicts: set[tuple[float, ...]] = set()
    duplicate_count = 0
    for record in history:
        if len(record.x) != int(variable_count):
            excluded["parameter_width"] += 1
            continue
        x = tuple(float(value) for value in record.x)
        if any(not math.isfinite(value) for value in x):
            excluded["parameter_nonfinite"] += 1
            continue
        if any(value < 0.0 or value > 1.0 for value in x):
            excluded["parameter_out_of_contract"] += 1
            continue
        if len(record.costs) != int(objective_count):
            excluded["objective_width"] += 1
            continue
        costs = tuple(float(value) for value in record.costs)
        if any(not math.isfinite(value) for value in costs):
            excluded["objective_nonfinite"] += 1
            continue
        if any(value < 0.0 or value > 1.0 for value in costs):
            excluded["objective_out_of_contract"] += 1
            continue
        key = tuple(round(value, int(decimals)) for value in x)
        if key in conflicts:
            excluded["conflicting_duplicate"] += 1
            continue
        previous = rows.get(key)
        if previous is None:
            rows[key] = (x, costs)
            continue
        if previous[1] == costs:
            duplicate_count += 1
            continue
        rows.pop(key, None)
        conflicts.add(key)
        excluded["conflicting_duplicate"] += 2

    valid = list(rows.values())
    nondominated = []
    for index, row in enumerate(valid):
        costs = row[1]
        dominated = any(
            other_index != index
            and all(left <= right for left, right in zip(other[1], costs))
            and any(left < right for left, right in zip(other[1], costs))
            for other_index, other in enumerate(valid)
        )
        if not dominated:
            nondominated.append(row)
    nondominated.sort(key=lambda item: (item[1], item[0]))
    return _Baseline(
        population=tuple(item[0] for item in nondominated),
        costs=tuple(item[1] for item in nondominated),
        diagnostics=MappingProxyType(
            {
                "history_input_count": len(history),
                "valid_unique_count": len(valid),
                "pareto_count": len(nondominated),
                "identical_duplicate_count": duplicate_count,
                "conflicting_duplicate_key_count": len(conflicts),
                "excluded_count": sum(excluded.values()),
                "excluded_by_reason": dict(sorted(excluded.items())),
                "finite_one_is_valid": True,
                "fixed_real_truth": True,
            }
        ),
    )


def _partition_candidates(
    readiness: PosteriorExploitationReadiness,
    gate: CalibratedApplicabilityGate | None,
    exploration_count: int,
    rng: random.Random,
) -> tuple[tuple[int, ...], tuple[int, ...], dict[str, object]]:
    candidate_count = len(readiness.population)
    if exploration_count <= 0 or exploration_count >= candidate_count:
        raise ValueError("real exploration quota must leave exploitation candidates")
    probabilities = readiness.smooth_probabilities
    if readiness.applicability_status == APPLICABILITY_NOT_APPLICABLE:
        if gate is not None or probabilities is not None:
            raise ValueError("not-applicable readiness cannot use an applicability gate")
        exploration = tuple(sorted(rng.sample(range(candidate_count), exploration_count)))
        eligible = tuple(
            index for index in range(candidate_count) if index not in exploration
        )
        return exploration, eligible, {
            "status": APPLICABILITY_NOT_APPLICABLE,
            "gate_applied": False,
            "excluded_from_exploitation_count": 0,
            "boundary_exploration_count": 0,
            "low_probability_exploration_count": 0,
        }
    if readiness.applicability_status != APPLICABILITY_CALIBRATED:
        raise QNEHVIFallback("applicability probability capability is not calibrated")
    if gate is None or probabilities is None:
        raise QNEHVIFallback(
            "calibrated applicability requires a pre-registered strategy gate"
        )

    threshold = gate.minimum_smooth_probability
    boundary = tuple(
        sorted(
            (
                index
                for index, probability in enumerate(probabilities)
                if abs(probability - threshold) <= gate.boundary_width
            ),
            key=lambda index: (abs(probabilities[index] - threshold), index),
        )
    )
    low = tuple(
        sorted(
            (
                index
                for index, probability in enumerate(probabilities)
                if probability < threshold and index not in boundary
            ),
            key=lambda index: (probabilities[index], index),
        )
    )
    priority_groups = (
        (boundary, low)
        if gate.exploration_priority == "boundary-then-low"
        else (low, boundary)
    )
    ordered = []
    for group in priority_groups:
        ordered.extend(index for index in group if index not in ordered)
    remaining = [index for index in range(candidate_count) if index not in ordered]
    rng.shuffle(remaining)
    ordered.extend(remaining)
    exploration = tuple(sorted(ordered[:exploration_count]))
    exploitation_eligible = tuple(
        index
        for index, probability in enumerate(probabilities)
        if probability >= threshold and index not in exploration
    )
    return exploration, exploitation_eligible, {
        "status": APPLICABILITY_CALIBRATED,
        "gate_applied": True,
        "policy": dict(gate.semantic_identity()),
        "candidate_count": candidate_count,
        "excluded_from_exploitation_count": sum(
            probability < threshold for probability in probabilities
        ),
        "boundary_candidate_count": len(boundary),
        "boundary_exploration_count": sum(
            index in boundary for index in exploration
        ),
        "low_probability_exploration_count": sum(
            probabilities[index] < threshold for index in exploration
        ),
        "probability_minimum": min(probabilities),
        "probability_maximum": max(probabilities),
    }


def _require_sampler_matches_readiness(
    sampler: RawDataPosteriorSampler,
    readiness: PosteriorExploitationReadiness,
) -> None:
    diagnostics = sampler.diagnostics
    mismatches = []
    if diagnostics.state_signature != readiness.state_signature:
        mismatches.append("state_signature")
    if not diagnostics.calibrated:
        mismatches.append("posterior_calibrated")
    if diagnostics.calibration_artifact_sha256 != readiness.calibration_artifact_sha256:
        mismatches.append("calibration_artifact_sha256")
    if diagnostics.observation_noise_included:
        mismatches.append("observation_noise_included")
    if mismatches:
        raise QNEHVIFallback(
            "sampler does not match typed exploitation readiness: "
            + ", ".join(mismatches)
        )


def _compact_projection_diagnostics(samples) -> dict[str, object]:
    source = dict(samples.source_diagnostics)
    return {
        **samples.diagnostics.as_dict(),
        "support_kind": source.get("support_kind"),
        "unique_support": source.get("unique_support"),
        "effective_unique_support": source.get("effective_unique_support"),
        "effective_draw_count": source.get("effective_draw_count"),
        "candidate_chunk_count": source.get("candidate_chunk_count"),
        "candidate_chunk_size": source.get("candidate_chunk_size"),
        "state_signature": source.get("state_signature"),
        "schema_signature": source.get("schema_signature"),
        "calibrated": source.get("calibrated"),
        "calibration_artifact_sha256": source.get(
            "calibration_artifact_sha256"
        ),
    }


def _static_exploitation_ready(identity: Mapping[str, object]) -> bool:
    return bool(
        identity.get("performance_status") == PERFORMANCE_ACCEPTED
        and identity.get("posterior_status") == POSTERIOR_CALIBRATED
        and bool(identity.get("transferable"))
        and not bool(identity.get("observation_noise_included"))
        and identity.get("applicability_status")
        in {APPLICABILITY_CALIBRATED, APPLICABILITY_NOT_APPLICABLE}
    )


def _exploration_count(population_size: int, fraction: float) -> int:
    size = int(population_size)
    if size < 2:
        raise ValueError(
            "posterior-assisted selector requires population_size at least two"
        )
    return min(size - 1, max(1, int(math.ceil(size * float(fraction)))))


def _surrogate_selection_freshness(
    surrogate: object,
    context: GenerationContext,
    training_data: SurrogateTrainingData,
) -> dict[str, object]:
    if isinstance(surrogate, DeterministicSurrogateComponent):
        if not isinstance(training_data, SurrogateTrainingData):
            return {
                "surrogate_training_gate": "failed",
                "surrogate_training_gate_error": (
                    "posterior freshness requires explicit SurrogateTrainingData"
                ),
            }
        return dict(
            assess_surrogate_selection_freshness(
                surrogate,
                context,
                training_data,
            ).diagnostics()
        )
    try:
        function = getattr(surrogate, "ensure_fresh_enough", None)
        if not callable(function):
            return {"surrogate_training_gate": "unavailable"}
        status = function(context)
    except Exception as exc:  # noqa: BLE001 - stale models fall back to real search.
        return {
            "surrogate_training_gate": "failed",
            "surrogate_training_gate_error": _bounded_error(exc),
        }
    return {
        "surrogate_training_gate": str(getattr(status, "action", "unknown")),
        "surrogate_training_pending_generation": getattr(
            status, "pending_generation_index", None
        ),
        "surrogate_training_latest_generation": getattr(
            status, "latest_completed_generation_index", None
        ),
        "surrogate_training_gate_error": str(getattr(status, "error", ""))[:512],
    }


def _surrogate_state_ready(
    surrogate: object,
    context: GenerationContext,
    training_data: SurrogateTrainingData,
) -> bool:
    try:
        if isinstance(surrogate, DeterministicSurrogateComponent):
            if not isinstance(training_data, SurrogateTrainingData):
                return False
            return bool(surrogate.has_trained_state(context, training_data))
        function = getattr(surrogate, "has_trained_state", None)
        return True if not callable(function) else bool(function(context))
    except Exception:
        return False


def _bounded_error(exc: BaseException) -> str:
    return (
        f"{exc.__class__.__name__}: {exc}"
        .replace("\r", " ")
        .replace("\n", " ")[:512]
    )


__all__ = [
    "CalibratedApplicabilityGate",
    "PosteriorGenerationSelection",
    "PosteriorAssistedSelector",
    "calibrated_applicability_gate",
    "posterior_assisted_selector",
]
