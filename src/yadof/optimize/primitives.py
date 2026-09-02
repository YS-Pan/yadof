"""Explicit backend-neutral search, predicted-cost, and selection primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import random
from types import MappingProxyType
from typing import Mapping, Sequence

from .strategy import GenerationContext, HistoryRecord, Population


_STATE_DOMAIN = "yadof.search-state:v1"
_CANDIDATE_DOMAIN = "yadof.search-candidate:v1"
_PREDICTION_DOMAIN = "yadof.predicted-cost-rows:v1"
_PRIVATE_TOKEN = object()


class InsufficientCandidatePoolError(RuntimeError):
    """Raised when bounded ask/refill cannot produce the requested unique pool."""


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """One transient search candidate, distinct from design and evidence identity."""

    candidate_id: str
    normalized_variables: tuple[float, ...]
    duplicate_key: tuple[float, ...]
    origin: str
    state_id: str
    ordinal: int
    source_evidence_id: str = ""

    def __post_init__(self) -> None:
        candidate_id = _sha256(self.candidate_id, "candidate_id")
        state_id = _sha256(self.state_id, "state_id")
        row = tuple(float(value) for value in self.normalized_variables)
        if not row or any(not math.isfinite(value) for value in row):
            raise ValueError("search candidate variables must be finite and non-empty")
        if any(value < -1.0e-9 or value > 1.0 + 1.0e-9 for value in row):
            raise ValueError("search candidate variables must stay in [0, 1]")
        row = tuple(max(0.0, min(1.0, value)) for value in row)
        duplicate_key = tuple(float(value) for value in self.duplicate_key)
        if len(duplicate_key) != len(row):
            raise ValueError("search candidate duplicate key width must match variables")
        origin = str(self.origin).strip()
        if not origin:
            raise ValueError("search candidate origin must be non-empty")
        ordinal = int(self.ordinal)
        if ordinal < 0:
            raise ValueError("search candidate ordinal must be non-negative")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "state_id", state_id)
        object.__setattr__(self, "normalized_variables", row)
        object.__setattr__(self, "duplicate_key", duplicate_key)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "ordinal", ordinal)
        object.__setattr__(self, "source_evidence_id", str(self.source_evidence_id))

    @property
    def x(self) -> tuple[float, ...]:
        return self.normalized_variables


@dataclass(frozen=True, slots=True)
class _SearchRuntime:
    context: object
    algorithm: object
    history: tuple[HistoryRecord, ...]
    history_evidence_by_key: Mapping[tuple[float, ...], str]
    used_keys: frozenset[tuple[float, ...]]
    rng_state: object
    next_ordinal: int


@dataclass(frozen=True, slots=True)
class SearchState:
    """Opaque generation-local continuation; its pymoo payload is package-private."""

    state_id: str
    strategy_signature: str
    generation_index: int
    variable_count: int
    objective_count: int
    population_size: int
    algorithm: str
    algorithm_seed: int
    random_seed: int
    archive_key_decimals: int
    revision: int
    candidate_count: int
    diagnostics: Mapping[str, object] = field(repr=False)
    _runtime: _SearchRuntime = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PRIVATE_TOKEN:
            raise TypeError("SearchState values are created by prepare_search()")
        object.__setattr__(self, "state_id", _sha256(self.state_id, "state_id"))
        object.__setattr__(
            self,
            "strategy_signature",
            _sha256(self.strategy_signature, "strategy_signature"),
        )
        if int(self.generation_index) < 0:
            raise ValueError("search generation_index must be non-negative")
        if int(self.variable_count) <= 0 or int(self.objective_count) <= 0:
            raise ValueError("search variable/objective counts must be positive")
        if int(self.population_size) <= 0:
            raise ValueError("search population_size must be positive")
        if int(self.revision) < 0 or int(self.candidate_count) < 0:
            raise ValueError("search revision/candidate count must be non-negative")
        object.__setattr__(self, "generation_index", int(self.generation_index))
        object.__setattr__(self, "variable_count", int(self.variable_count))
        object.__setattr__(self, "objective_count", int(self.objective_count))
        object.__setattr__(self, "population_size", int(self.population_size))
        object.__setattr__(self, "algorithm_seed", int(self.algorithm_seed))
        object.__setattr__(self, "random_seed", int(self.random_seed))
        object.__setattr__(self, "archive_key_decimals", int(self.archive_key_decimals))
        object.__setattr__(self, "revision", int(self.revision))
        object.__setattr__(self, "candidate_count", int(self.candidate_count))
        object.__setattr__(self, "algorithm", str(self.algorithm))
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))

    def __reduce__(self):
        raise TypeError(
            "SearchState is generation-local; rebuild durable resume state from history"
        )

    def __reduce_ex__(self, _protocol):
        return self.__reduce__()


@dataclass(frozen=True, slots=True)
class CandidatePool:
    """Ordered unique candidates plus the next opaque search state."""

    candidates: tuple[SearchCandidate, ...]
    state: SearchState
    input_revision: int
    diagnostics: Mapping[str, object]
    _records: tuple[object, ...] = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PRIVATE_TOKEN:
            raise TypeError("CandidatePool values are created by search primitives")
        candidates = tuple(self.candidates)
        records = tuple(self._records)
        if len(candidates) != len(records):
            raise ValueError("candidate pool backend records must align")
        if len({row.candidate_id for row in candidates}) != len(candidates):
            raise ValueError("candidate pool IDs must be unique")
        if len({row.duplicate_key for row in candidates}) != len(candidates):
            raise ValueError("candidate pool designs must be unique")
        if any(row.state_id != self.state.state_id for row in candidates):
            raise ValueError("candidate pool rows must belong to one search state")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "_records", records)
        object.__setattr__(self, "input_revision", int(self.input_revision))
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))

    @property
    def population(self) -> Population:
        return tuple(row.normalized_variables for row in self.candidates)


@dataclass(frozen=True, slots=True)
class PredictedCostRows:
    """Candidate-bound deterministic current-cost means for survival selection."""

    candidate_ids: tuple[str, ...]
    normalized_variables: Population
    costs: tuple[tuple[float, ...], ...]
    interpretation_fingerprint: str
    state_signature: str
    source: str
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    prediction_id: str = field(init=False)
    valid_mask: tuple[bool, ...] = ()

    def __post_init__(self) -> None:
        candidate_ids = tuple(
            _sha256(value, "predicted candidate_id") for value in self.candidate_ids
        )
        rows = tuple(
            tuple(float(value) for value in row)
            for row in self.normalized_variables
        )
        costs = tuple(tuple(float(value) for value in row) for row in self.costs)
        count = len(candidate_ids)
        if len(rows) != count or len(costs) != count:
            raise ValueError("predicted cost rows must align with candidate IDs")
        if len(set(candidate_ids)) != count:
            raise ValueError("predicted candidate IDs must be unique")
        variable_width = len(rows[0]) if rows else 0
        objective_width = len(costs[0]) if costs else 0
        if count and (variable_width <= 0 or objective_width <= 0):
            raise ValueError("predicted rows require positive variable/objective widths")
        if any(len(row) != variable_width for row in rows):
            raise ValueError("predicted variable rows must have one width")
        if any(len(row) != objective_width for row in costs):
            raise ValueError("predicted cost rows must have one width")
        if any(
            not math.isfinite(value) or value < -1.0e-9 or value > 1.0 + 1.0e-9
            for row in rows
            for value in row
        ):
            raise ValueError("predicted variables must be finite in [0, 1]")
        valid = tuple(self.valid_mask) if self.valid_mask else (True,) * count
        if len(valid) != count or any(type(value) is not bool for value in valid):
            raise ValueError("prediction valid_mask must align and be boolean")
        for row, is_valid in zip(costs, valid):
            if (is_valid and any(not math.isfinite(value) for value in row)) or (
                not is_valid and any(value != math.inf for value in row)
            ):
                raise ValueError("predicted current costs must be finite or explicit failed +inf rows")
        source = str(self.source).strip()
        if not source:
            raise ValueError("predicted cost source must be non-empty")
        interpretation = _sha256(
            self.interpretation_fingerprint,
            "interpretation_fingerprint",
        )
        state_signature = _sha256(self.state_signature, "prediction state_signature")
        diagnostics = _freeze_mapping(self.diagnostics)
        prediction_id = _hash_json(
            {
                "domain": _PREDICTION_DOMAIN,
                "candidate_ids": candidate_ids,
                "normalized_variables": rows,
                "costs": [row if ok else None for row, ok in zip(costs, valid)],
                "valid_mask": valid,
                "interpretation_fingerprint": interpretation,
                "state_signature": state_signature,
                "source": source,
            }
        )
        object.__setattr__(self, "candidate_ids", candidate_ids)
        object.__setattr__(self, "normalized_variables", rows)
        object.__setattr__(self, "costs", costs)
        object.__setattr__(self, "valid_mask", valid)
        object.__setattr__(self, "interpretation_fingerprint", interpretation)
        object.__setattr__(self, "state_signature", state_signature)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(self, "prediction_id", prediction_id)

    @property
    def objective_count(self) -> int:
        return 0 if not self.costs else len(self.costs[0])


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    """Ordered candidates committed for later real-evaluation handoff."""

    candidates: tuple[SearchCandidate, ...]
    state: SearchState
    source: str
    diagnostics: Mapping[str, object]
    _records: tuple[object, ...] = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PRIVATE_TOKEN:
            raise TypeError("CandidateSelection values are created by selection primitives")
        candidates = tuple(self.candidates)
        records = tuple(self._records)
        if len(candidates) != len(records):
            raise ValueError("selection backend records must align")
        if len({row.candidate_id for row in candidates}) != len(candidates):
            raise ValueError("selected candidate IDs must be unique")
        if len({row.duplicate_key for row in candidates}) != len(candidates):
            raise ValueError("selected real designs must be unique")
        source = str(self.source).strip()
        if not source:
            raise ValueError("candidate selection source must be non-empty")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "_records", records)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))

    @property
    def population(self) -> Population:
        return tuple(row.normalized_variables for row in self.candidates)


def prepare_search(
    context: GenerationContext,
    search,
    *,
    population_size: int | None = None,
    algorithm_seed: int | None = None,
    random_seed: int | None = None,
    history_policy: str = "survivor",
) -> SearchState:
    """Build one deterministic opaque pymoo continuation from real history."""

    from .gpsaf.records import history_keys, key
    from .pymoo import backend

    size = int(context.population_size if population_size is None else population_size)
    if size <= 0:
        raise ValueError("search population_size must be positive")
    policy = str(history_policy).strip().lower()
    if policy not in {"survivor", "warm-start"}:
        raise ValueError("history_policy must be 'survivor' or 'warm-start'")
    selected_algorithm_seed = int(
        context.random_seed if algorithm_seed is None else algorithm_seed
    )
    selected_random_seed = int(
        context.random_seed + context.generation_index * 1009
        if random_seed is None
        else random_seed
    )
    selected_algorithm = search.resolve_algorithm(context.problem.objective_count)
    selected_settings = search.backend_settings(context.problem.objective_count)
    pymoo_context = backend.make_context(
        context.config,
        context.problem,
        population_size=size,
        seed=selected_algorithm_seed,
        generation_index=context.generation_index,
        search_algorithm=selected_algorithm,
        search_settings=selected_settings,
    )
    history = tuple(context.history)
    snapshot_fingerprint = _sha256(
        getattr(
            context.snapshot,
            "interpretation_fingerprint",
            context.strategy_signature,
        ),
        "search snapshot interpretation_fingerprint",
    )
    algorithm = (
        backend.history_population(pymoo_context, history)
        if policy == "warm-start"
        else backend.survivor_state_from_history(pymoo_context, history, size)
    )
    decimals = int(context.config.OPTIMIZE_ARCHIVE_KEY_DECIMALS)
    used = frozenset(history_keys(history, decimals))
    evidence_by_key: dict[tuple[float, ...], str] = {}
    for row in history:
        evidence_by_key.setdefault(key(row.x, decimals), str(row.candidate_id))
    search_identity = search.semantic_identity(context.config, context.problem)
    state_id = _hash_json(
        {
            "domain": _STATE_DOMAIN,
            "strategy_signature": context.strategy_signature,
            "snapshot_interpretation_fingerprint": snapshot_fingerprint,
            "generation_index": int(context.generation_index),
            "population_size": size,
            "variable_count": int(context.problem.variable_count),
            "objective_count": int(context.problem.objective_count),
            "algorithm_seed": selected_algorithm_seed,
            "random_seed": selected_random_seed,
            "history_policy": policy,
            "search_identity": search_identity,
            "history": [
                {
                    "candidate_id": row.candidate_id,
                    "row_id": row.row_id,
                    "interpretation_id": row.interpretation_id,
                    "generation_index": row.generation_index,
                    "optimization_index": row.optimization_index,
                    "population_index": row.population_index,
                    "x": row.x,
                    "costs": row.costs,
                }
                for row in history
            ],
        }
    )
    rng = random.Random(selected_random_seed)
    diagnostics = {
        **backend.diagnostics(pymoo_context),
        "search_state_id": state_id,
        "search_state_revision": 0,
        "search_history_policy": policy,
        "search_history_count": len(history),
        "search_archive_count": len(used),
        "search_snapshot_interpretation_fingerprint": snapshot_fingerprint,
        "search_algorithm_seed": selected_algorithm_seed,
        "search_random_seed": selected_random_seed,
    }
    return SearchState(
        state_id=state_id,
        strategy_signature=context.strategy_signature,
        generation_index=context.generation_index,
        variable_count=context.problem.variable_count,
        objective_count=context.problem.objective_count,
        population_size=size,
        algorithm=selected_algorithm,
        algorithm_seed=selected_algorithm_seed,
        random_seed=selected_random_seed,
        archive_key_decimals=decimals,
        revision=0,
        candidate_count=0,
        diagnostics=diagnostics,
        _runtime=_SearchRuntime(
            context=pymoo_context,
            algorithm=algorithm,
            history=history,
            history_evidence_by_key=MappingProxyType(evidence_by_key),
            used_keys=used,
            rng_state=rng.getstate(),
            next_ordinal=0,
        ),
        _token=_PRIVATE_TOKEN,
    )


def fork_search_state(state: SearchState) -> SearchState:
    """Clone one continuation so independent branches cannot mutate each other."""

    from .pymoo.backend import clone_algorithm

    selected = _require_state(state)
    return _next_state(
        selected,
        algorithm=clone_algorithm(selected._runtime.algorithm),
        runtime=selected._runtime,
        action="fork",
    )


def continue_search_from(
    algorithm_state: SearchState,
    bookkeeping_state: SearchState,
) -> SearchState:
    """Keep one branch's algorithm and another same-root branch's archive/RNG."""

    from .pymoo.backend import clone_algorithm

    algorithm_source = _require_state(algorithm_state)
    bookkeeping = _require_state(bookkeeping_state)
    _require_same_state_root(algorithm_source, bookkeeping)
    runtime = _SearchRuntime(
        context=algorithm_source._runtime.context,
        algorithm=clone_algorithm(algorithm_source._runtime.algorithm),
        history=algorithm_source._runtime.history,
        history_evidence_by_key=algorithm_source._runtime.history_evidence_by_key,
        used_keys=bookkeeping._runtime.used_keys,
        rng_state=bookkeeping._runtime.rng_state,
        next_ordinal=bookkeeping._runtime.next_ordinal,
    )
    return _next_state(
        algorithm_source,
        algorithm=runtime.algorithm,
        runtime=runtime,
        action="continue-from-branch",
        revision=max(algorithm_source.revision, bookkeeping.revision) + 1,
        candidate_count=max(
            algorithm_source.candidate_count,
            bookkeeping.candidate_count,
        ),
    )


def search_candidates(
    state: SearchState,
    count: int,
    *,
    origin: str,
) -> CandidatePool:
    """Ask for one bounded unique candidate pool and return its next state."""

    from .pymoo import backend

    selected = _require_state(state)
    requested = int(count)
    if requested < 0:
        raise ValueError("search candidate count must be non-negative")
    algorithm = backend.clone_algorithm(selected._runtime.algorithm)
    rng = random.Random()
    rng.setstate(selected._runtime.rng_state)
    used = set(selected._runtime.used_keys)
    stats: dict[str, object] = {}
    records = backend.generate_candidate_pool(
        selected._runtime.context,
        algorithm,
        requested,
        used,
        rng,
        origin=origin,
        stats=stats,
    )
    candidates = _candidate_rows(
        selected,
        records,
        start_ordinal=selected._runtime.next_ordinal,
    )
    runtime = _SearchRuntime(
        context=selected._runtime.context,
        algorithm=algorithm,
        history=selected._runtime.history,
        history_evidence_by_key=selected._runtime.history_evidence_by_key,
        used_keys=frozenset(used),
        rng_state=rng.getstate(),
        next_ordinal=selected._runtime.next_ordinal + len(candidates),
    )
    next_state = _next_state(
        selected,
        algorithm=algorithm,
        runtime=runtime,
        action="search",
        candidate_count=selected.candidate_count + len(candidates),
        extra_diagnostics={
            "search_requested_count": requested,
            "search_returned_count": len(candidates),
            "search_origin": str(origin),
            **stats,
        },
    )
    return _pool(
        candidates,
        records,
        state=next_state,
        input_revision=selected.revision,
        diagnostics={
            "requested_count": requested,
            "returned_count": len(candidates),
            "origin": str(origin),
            **stats,
        },
    )


def warm_start_candidates(
    state: SearchState,
    count: int,
    *,
    origin: str,
) -> CandidatePool:
    """Select current real-history survivors without evaluating or recording."""

    from .pymoo import backend

    selected = _require_state(state)
    requested = max(0, int(count))
    algorithm = backend.clone_algorithm(selected._runtime.algorithm)
    records = backend.selected_records_from_state(
        selected._runtime.context,
        algorithm,
        requested,
        origin=origin,
    )
    unique_records = []
    seen: set[tuple[float, ...]] = set()
    from .gpsaf.records import key

    for record in records:
        duplicate = key(record.x, selected.archive_key_decimals)
        if duplicate in seen:
            continue
        seen.add(duplicate)
        unique_records.append(record)
    candidates = _candidate_rows(
        selected,
        unique_records,
        start_ordinal=selected._runtime.next_ordinal,
    )
    runtime = _SearchRuntime(
        context=selected._runtime.context,
        algorithm=algorithm,
        history=selected._runtime.history,
        history_evidence_by_key=selected._runtime.history_evidence_by_key,
        used_keys=selected._runtime.used_keys,
        rng_state=selected._runtime.rng_state,
        next_ordinal=selected._runtime.next_ordinal + len(candidates),
    )
    next_state = _next_state(
        selected,
        algorithm=algorithm,
        runtime=runtime,
        action="warm-start",
        candidate_count=selected.candidate_count + len(candidates),
        extra_diagnostics={
            "warm_start_requested_count": requested,
            "warm_start_returned_count": len(candidates),
        },
    )
    return _pool(
        candidates,
        unique_records,
        state=next_state,
        input_revision=selected.revision,
        diagnostics={
            "requested_count": requested,
            "returned_count": len(candidates),
            "origin": str(origin),
        },
    )


def bind_surrogate_prediction(
    pool: CandidatePool,
    prediction,
) -> PredictedCostRows:
    """Bind one Stage 4 deterministic surrogate value to exact candidate IDs."""

    from ..surrogate.training import SurrogatePrediction

    selected_pool = _require_pool(pool)
    if not isinstance(prediction, SurrogatePrediction):
        raise TypeError("bind_surrogate_prediction requires SurrogatePrediction")
    if prediction.normalized_variables != selected_pool.population:
        raise ValueError("surrogate prediction rows do not match the candidate pool")
    return PredictedCostRows(
        candidate_ids=tuple(row.candidate_id for row in selected_pool.candidates),
        normalized_variables=selected_pool.population,
        costs=prediction.costs,
        valid_mask=prediction.valid_mask,
        interpretation_fingerprint=prediction.interpretation_fingerprint,
        state_signature=prediction.state_signature,
        source="surrogate-prediction",
        diagnostics={
            "surrogate_prediction_kind": prediction.kind,
            "surrogate_training_data_digest": prediction.training_data_digest,
            **dict(prediction.diagnostics),
        },
    )


def bind_predicted_costs(
    pool: CandidatePool,
    costs,
    *,
    source: str,
    interpretation_fingerprint: str | None = None,
    state_signature: str | None = None,
    diagnostics: Mapping[str, object] | None = None,
    valid_mask: Sequence[bool] = (),
) -> PredictedCostRows:
    """Bind custom/legacy deterministic current-cost rows at one explicit edge."""

    from ..job_template.rawdata_projector import JointObjectiveSamples
    from ..recorded_data.dataset import CostTable
    from ..surrogate.training import SurrogatePrediction

    selected_pool = _require_pool(pool)
    if isinstance(costs, (CostTable, JointObjectiveSamples, SurrogatePrediction)):
        raise TypeError(
            "predicted cost binding requires plain current-cost rows, not real, "
            "posterior, or unbound surrogate values"
        )
    cost_rows = tuple(tuple(float(value) for value in row) for row in costs)
    validity = tuple(valid_mask) if valid_mask else (True,) * len(cost_rows)
    if any(not math.isfinite(value) for row, ok in zip(cost_rows, validity) if ok for value in row):
        raise ValueError("predicted current costs must be finite")
    fallback_signature = _hash_json(
        {
            "domain": _PREDICTION_DOMAIN,
            "state_id": selected_pool.state.state_id,
            "candidate_ids": [row.candidate_id for row in selected_pool.candidates],
            "costs": [row if ok else None for row, ok in zip(cost_rows, validity)],
            "source": str(source),
        }
    )
    return PredictedCostRows(
        candidate_ids=tuple(row.candidate_id for row in selected_pool.candidates),
        normalized_variables=selected_pool.population,
        costs=cost_rows,
        valid_mask=validity,
        interpretation_fingerprint=(
            fallback_signature
            if interpretation_fingerprint is None
            else interpretation_fingerprint
        ),
        state_signature=(
            fallback_signature if state_signature is None else state_signature
        ),
        source=source,
        diagnostics={} if diagnostics is None else diagnostics,
    )


def combine_predicted_cost_rows(
    pool: CandidatePool,
    predictions: Sequence[PredictedCostRows],
    *,
    source: str,
) -> PredictedCostRows:
    """Rebind disjoint same-semantics predictions to one exact combined pool."""

    selected_pool = _require_pool(pool)
    groups = tuple(predictions)
    if not groups:
        raise ValueError("combined prediction requires at least one input")
    by_id = {}
    interpretation_fingerprint = ""
    state_signature = ""
    for prediction in groups:
        if not isinstance(prediction, PredictedCostRows):
            raise TypeError("combined prediction inputs must be PredictedCostRows")
        if not interpretation_fingerprint:
            interpretation_fingerprint = prediction.interpretation_fingerprint
            state_signature = prediction.state_signature
        elif (
            prediction.interpretation_fingerprint != interpretation_fingerprint
            or prediction.state_signature != state_signature
        ):
            raise ValueError("combined predictions use different fitted semantics")
        for candidate_id, variables, costs, valid in zip(
            prediction.candidate_ids,
            prediction.normalized_variables,
            prediction.costs,
            prediction.valid_mask,
        ):
            if candidate_id in by_id:
                raise ValueError("combined predictions repeat a candidate ID")
            by_id[candidate_id] = (variables, costs, valid)

    expected = {
        candidate.candidate_id: candidate.normalized_variables
        for candidate in selected_pool.candidates
    }
    if not set(expected).issubset(by_id):
        missing = tuple(sorted(set(expected) - set(by_id)))
        raise ValueError(
            "combined prediction does not cover every pool candidate ID; "
            f"missing={missing!r}"
        )
    if any(by_id[candidate_id][0] != variables for candidate_id, variables in expected.items()):
        raise ValueError("combined prediction variables do not match the pool")
    ordered_ids = tuple(candidate.candidate_id for candidate in selected_pool.candidates)
    return bind_predicted_costs(
        selected_pool,
        tuple(by_id[candidate_id][1] for candidate_id in ordered_ids),
        source=source,
        interpretation_fingerprint=interpretation_fingerprint,
        state_signature=state_signature,
        valid_mask=tuple(by_id[candidate_id][2] for candidate_id in ordered_ids),
        diagnostics={
            "combined_prediction_count": len(groups),
            "combined_candidate_count": len(ordered_ids),
            "ignored_prediction_count": len(set(by_id) - set(expected)),
        },
    )


def select_candidate_indices(
    state: SearchState,
    pool: CandidatePool,
    indices: Sequence[int],
    *,
    source: str,
) -> CandidateSelection:
    """Select an ordered subset without imposing an environmental survival rule."""
    selected_state = _require_state(state)
    selected_pool = _require_pool(pool)
    _require_pool_state(selected_state, selected_pool)
    selected = tuple(indices)
    if any(type(index) is not int or not 0 <= index < len(pool.candidates) for index in selected):
        raise ValueError("selected candidate indices must be in range")
    if len(set(selected)) != len(selected):
        raise ValueError("selected candidate indices must be unique")
    return _selection(
        tuple(pool.candidates[index] for index in selected),
        tuple(pool._records[index] for index in selected),
        state=selected_state,
        source=source,
        diagnostics={"selected_count": len(selected)},
    )


def select_candidates(
    state: SearchState,
    pool: CandidatePool,
    predicted: PredictedCostRows,
    count: int,
    *,
    source: str = "predicted-survival",
) -> CandidateSelection:
    """Delegate deterministic current-cost survival to pymoo."""

    from .gpsaf.records import CandidateRecord
    from .pymoo.backend import select_records_by_survival

    selected_state = _require_state(state)
    selected_pool = _require_pool(pool)
    _require_pool_state(selected_state, selected_pool)
    if not isinstance(predicted, PredictedCostRows):
        raise TypeError("select_candidates requires PredictedCostRows")
    expected_ids = tuple(row.candidate_id for row in selected_pool.candidates)
    if predicted.candidate_ids != expected_ids:
        raise ValueError("predicted candidate IDs do not match the pool")
    if predicted.normalized_variables != selected_pool.population:
        raise ValueError("predicted variables do not match the pool")
    if predicted.objective_count != selected_state.objective_count:
        raise ValueError("predicted objective width does not match search state")
    records = tuple(
        CandidateRecord(
            x=candidate.normalized_variables,
            origin=candidate.origin,
            individual=backend_record.individual,
            pred_costs=cost_row,
        )
        for candidate, backend_record, cost_row in zip(
            selected_pool.candidates,
            selected_pool._records,
            predicted.costs,
        )
    )
    by_record = {
        id(record): (candidate, record)
        for candidate, record in zip(selected_pool.candidates, records)
    }
    selected_records = select_records_by_survival(
        selected_state._runtime.context,
        records,
        int(count),
    )
    selected_pairs = tuple(by_record[id(record)] for record in selected_records)
    next_state = _next_state(
        selected_state,
        algorithm=selected_state._runtime.algorithm,
        runtime=selected_state._runtime,
        action="select",
        extra_diagnostics={
            "selection_requested_count": int(count),
            "selection_returned_count": len(selected_pairs),
            "selection_prediction_id": predicted.prediction_id,
        },
    )
    return _selection(
        tuple(pair[0] for pair in selected_pairs),
        tuple(pair[1] for pair in selected_pairs),
        state=next_state,
        source=source,
        diagnostics={
            "selection_requested_count": int(count),
            "selection_returned_count": len(selected_pairs),
            "selection_prediction_id": predicted.prediction_id,
            "selection_backend": "pymoo-survival",
        },
    )


def advance_search(
    state: SearchState,
    pool: CandidatePool,
    predicted: PredictedCostRows,
) -> SearchState:
    """Advance a cloned pymoo ask/tell state using typed predicted costs."""

    from .gpsaf.records import CandidateRecord
    from .pymoo import backend

    selected_state = _require_state(state)
    selected_pool = _require_pool(pool)
    _require_pool_state(selected_state, selected_pool)
    if not isinstance(predicted, PredictedCostRows):
        raise TypeError("advance_search requires PredictedCostRows")
    if predicted.candidate_ids != tuple(
        row.candidate_id for row in selected_pool.candidates
    ):
        raise ValueError("predicted candidate IDs do not match the pool")
    algorithm = backend.clone_algorithm(selected_state._runtime.algorithm)
    records = tuple(
        CandidateRecord(
            x=candidate.normalized_variables,
            origin=candidate.origin,
            individual=backend_record.individual,
            pred_costs=cost_row,
        )
        for candidate, backend_record, cost_row in zip(
            selected_pool.candidates,
            selected_pool._records,
            predicted.costs,
        )
    )
    backend.advance_population_with_records(
        selected_state._runtime.context,
        algorithm,
        records,
        selected_state.population_size,
    )
    runtime = _SearchRuntime(
        context=selected_state._runtime.context,
        algorithm=algorithm,
        history=selected_state._runtime.history,
        history_evidence_by_key=selected_state._runtime.history_evidence_by_key,
        used_keys=selected_state._runtime.used_keys,
        rng_state=selected_state._runtime.rng_state,
        next_ordinal=selected_state._runtime.next_ordinal,
    )
    return _next_state(
        selected_state,
        algorithm=algorithm,
        runtime=runtime,
        action="advance",
        extra_diagnostics={
            "advance_count": len(records),
            "advance_prediction_id": predicted.prediction_id,
        },
    )


def combine_candidate_pools(
    state: SearchState,
    pools: Sequence[CandidatePool | CandidateSelection],
) -> CandidatePool:
    """Concatenate same-root pools/selections without losing backend ownership."""

    selected_state = _require_state(state)
    candidates: list[SearchCandidate] = []
    records: list[object] = []
    revisions: list[int] = []
    for pool in pools:
        if isinstance(pool, CandidatePool):
            group_candidates = pool.candidates
            group_records = pool._records
            group_state = pool.state
            input_revision = pool.input_revision
        elif isinstance(pool, CandidateSelection):
            group_candidates = pool.candidates
            group_records = pool._records
            group_state = pool.state
            input_revision = pool.state.revision
        else:
            raise TypeError("combined candidate groups must be pools or selections")
        _require_same_state_root(selected_state, group_state)
        candidates.extend(group_candidates)
        records.extend(group_records)
        revisions.append(input_revision)
    return _pool(
        tuple(candidates),
        tuple(records),
        state=selected_state,
        input_revision=min(revisions, default=selected_state.revision),
        diagnostics={
            "combined_pool_count": len(tuple(pools)),
            "combined_candidate_count": len(candidates),
        },
    )


def compose_real_population(
    state: SearchState,
    groups: Sequence[CandidatePool | CandidateSelection],
    *,
    size: int,
    source: str,
    refill_origin: str,
) -> CandidateSelection:
    """Combine ordered groups, then bounded-refill one unique real population."""

    selected_state = _require_state(state)
    candidates: list[SearchCandidate] = []
    records: list[object] = []
    seen_ids: set[str] = set()
    seen_keys: set[tuple[float, ...]] = set()
    for group in groups:
        if isinstance(group, CandidatePool):
            group_candidates = group.candidates
            group_records = group._records
            group_state = group.state
        elif isinstance(group, CandidateSelection):
            group_candidates = group.candidates
            group_records = group._records
            group_state = group.state
        else:
            raise TypeError("real population groups must be pools or selections")
        _require_same_state_root(selected_state, group_state)
        for candidate, record in zip(group_candidates, group_records):
            if candidate.candidate_id in seen_ids or candidate.duplicate_key in seen_keys:
                raise ValueError("real population groups contain duplicate candidates/designs")
            seen_ids.add(candidate.candidate_id)
            seen_keys.add(candidate.duplicate_key)
            candidates.append(candidate)
            records.append(record)
    target = int(size)
    if target <= 0:
        raise ValueError("real population size must be positive")
    if len(candidates) < target:
        refill = search_candidates(
            selected_state,
            target - len(candidates),
            origin=refill_origin,
        )
        selected_state = refill.state
        candidates.extend(refill.candidates)
        records.extend(refill._records)
    candidates = candidates[:target]
    records = records[:target]
    if len(candidates) != target:
        raise InsufficientCandidatePoolError(
            f"real population requested {target} unique candidates, got {len(candidates)}"
        )
    next_state = _next_state(
        selected_state,
        algorithm=selected_state._runtime.algorithm,
        runtime=selected_state._runtime,
        action="compose-real-population",
        extra_diagnostics={
            "real_population_count": len(candidates),
            "real_population_group_count": len(tuple(groups)),
        },
    )
    return _selection(
        tuple(candidates),
        tuple(records),
        state=next_state,
        source=source,
        diagnostics={
            "real_population_count": len(candidates),
            "real_population_group_count": len(tuple(groups)),
            "evaluation_handoff": "common-real-evaluate-population",
        },
    )


def full_real_search(
    context: GenerationContext,
    search,
    *,
    population_size: int | None = None,
    algorithm_seed: int | None = None,
    random_seed: int | None = None,
    origin_prefix: str = "pymoo",
) -> CandidateSelection:
    """Compose the sole complete real-only/fallback search path."""

    size = int(context.population_size if population_size is None else population_size)
    history = tuple(context.history)
    warm_start = bool(history and int(context.generation_index) <= 0)
    state = prepare_search(
        context,
        search,
        population_size=size,
        algorithm_seed=algorithm_seed,
        random_seed=random_seed,
        history_policy="warm-start" if warm_start else "survivor",
    )
    prefix = str(origin_prefix).strip()
    if not prefix:
        raise ValueError("real search origin_prefix must be non-empty")
    if not history:
        pool = search_candidates(state, size, origin=f"{prefix}_random")
        return compose_real_population(
            pool.state,
            (pool,),
            size=size,
            source=f"{prefix}_random",
            refill_origin=f"{prefix}_random_refill",
        )
    if warm_start:
        warm = warm_start_candidates(
            state,
            size,
            origin=f"{prefix}_warm_start",
        )
        source = (
            f"{prefix}_warm_start"
            if len(warm.candidates) >= size
            else f"{prefix}_random_refill"
        )
        return compose_real_population(
            warm.state,
            (warm,),
            size=size,
            source=source,
            refill_origin=f"{prefix}_random_refill",
        )
    pool = search_candidates(state, size, origin=f"{prefix}_offspring")
    return compose_real_population(
        pool.state,
        (pool,),
        size=size,
        source=f"{prefix}_offspring",
        refill_origin=f"{prefix}_random_refill",
    )


def _candidate_rows(
    state: SearchState,
    records: Sequence[object],
    *,
    start_ordinal: int,
) -> tuple[SearchCandidate, ...]:
    from .gpsaf.records import key

    output = []
    for offset, record in enumerate(records):
        ordinal = int(start_ordinal) + offset
        row = tuple(float(value) for value in record.x)
        duplicate_key = key(row, state.archive_key_decimals)
        candidate_id = _hash_json(
            {
                "domain": _CANDIDATE_DOMAIN,
                "state_id": state.state_id,
                "ordinal": ordinal,
                "origin": str(record.origin),
                "normalized_variables": row,
            }
        )
        output.append(
            SearchCandidate(
                candidate_id=candidate_id,
                normalized_variables=row,
                duplicate_key=duplicate_key,
                origin=str(record.origin),
                state_id=state.state_id,
                ordinal=ordinal,
                source_evidence_id=state._runtime.history_evidence_by_key.get(
                    duplicate_key,
                    "",
                ),
            )
        )
    return tuple(output)


def _next_state(
    state: SearchState,
    *,
    algorithm: object,
    runtime: _SearchRuntime,
    action: str,
    revision: int | None = None,
    candidate_count: int | None = None,
    extra_diagnostics: Mapping[str, object] | None = None,
) -> SearchState:
    selected_revision = state.revision + 1 if revision is None else int(revision)
    diagnostics = {
        **dict(state.diagnostics),
        "search_state_id": state.state_id,
        "search_state_revision": selected_revision,
        "search_state_action": str(action),
    }
    if extra_diagnostics:
        diagnostics.update(dict(extra_diagnostics))
    selected_runtime = _SearchRuntime(
        context=runtime.context,
        algorithm=algorithm,
        history=runtime.history,
        history_evidence_by_key=runtime.history_evidence_by_key,
        used_keys=runtime.used_keys,
        rng_state=runtime.rng_state,
        next_ordinal=runtime.next_ordinal,
    )
    return SearchState(
        state_id=state.state_id,
        strategy_signature=state.strategy_signature,
        generation_index=state.generation_index,
        variable_count=state.variable_count,
        objective_count=state.objective_count,
        population_size=state.population_size,
        algorithm=state.algorithm,
        algorithm_seed=state.algorithm_seed,
        random_seed=state.random_seed,
        archive_key_decimals=state.archive_key_decimals,
        revision=selected_revision,
        candidate_count=(
            state.candidate_count if candidate_count is None else int(candidate_count)
        ),
        diagnostics=diagnostics,
        _runtime=selected_runtime,
        _token=_PRIVATE_TOKEN,
    )


def _pool(
    candidates: Sequence[SearchCandidate],
    records: Sequence[object],
    *,
    state: SearchState,
    input_revision: int,
    diagnostics: Mapping[str, object],
) -> CandidatePool:
    return CandidatePool(
        candidates=tuple(candidates),
        state=state,
        input_revision=input_revision,
        diagnostics=diagnostics,
        _records=tuple(records),
        _token=_PRIVATE_TOKEN,
    )


def _selection(
    candidates: Sequence[SearchCandidate],
    records: Sequence[object],
    *,
    state: SearchState,
    source: str,
    diagnostics: Mapping[str, object],
) -> CandidateSelection:
    return CandidateSelection(
        candidates=tuple(candidates),
        state=state,
        source=source,
        diagnostics=diagnostics,
        _records=tuple(records),
        _token=_PRIVATE_TOKEN,
    )


def _require_state(value: object) -> SearchState:
    if not isinstance(value, SearchState) or value._token is not _PRIVATE_TOKEN:
        raise TypeError("search primitive requires a framework-owned SearchState")
    return value


def _require_pool(value: object) -> CandidatePool:
    if not isinstance(value, CandidatePool) or value._token is not _PRIVATE_TOKEN:
        raise TypeError("search primitive requires a framework-owned CandidatePool")
    return value


def _require_same_state_root(left: SearchState, right: SearchState) -> None:
    if (
        left.state_id != right.state_id
        or left.strategy_signature != right.strategy_signature
        or left.generation_index != right.generation_index
    ):
        raise ValueError("search states belong to different strategy/generation roots")


def _require_pool_state(state: SearchState, pool: CandidatePool) -> None:
    _require_same_state_root(state, pool.state)
    if state.revision < pool.state.revision:
        raise ValueError("search state predates the candidate pool continuation")


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {
            str(key): _freeze_json(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    )


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("search diagnostics must be finite JSON values")
        return value
    raise TypeError(f"search diagnostics contain unsupported value {type(value).__name__}")


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return text


__all__ = [
    "CandidatePool",
    "CandidateSelection",
    "InsufficientCandidatePoolError",
    "PredictedCostRows",
    "SearchCandidate",
    "SearchState",
    "advance_search",
    "bind_predicted_costs",
    "bind_surrogate_prediction",
    "combine_candidate_pools",
    "combine_predicted_cost_rows",
    "compose_real_population",
    "continue_search_from",
    "fork_search_state",
    "full_real_search",
    "prepare_search",
    "search_candidates",
    "select_candidates",
    "select_candidate_indices",
    "warm_start_candidates",
]
