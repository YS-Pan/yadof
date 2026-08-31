"""Backend-neutral joint rawData function-sampler protocol."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import json
from typing import Iterable, Mapping, Protocol, Sequence, runtime_checkable

import numpy as np

from ..job_template.rawdata_projector import (
    CostProjectionFailure,
    JointObjectiveSamples,
    RawDataCostProjector,
)
from ..job_template.rawdata_template import (
    RawDataFieldSelector,
    RawDataSampleLike,
    RawDataSchemaTemplate,
)


RAWDATA_POSTERIOR_PROTOCOL = "yadof.joint-rawdata-function-sampler"
RAWDATA_POSTERIOR_PROTOCOL_VERSION = 1
SUPPORT_FINITE = "finite"
SUPPORT_CONTINUOUS_OR_UNKNOWN = "continuous_or_unknown"
_SUPPORT_KINDS = frozenset({SUPPORT_FINITE, SUPPORT_CONTINUOUS_OR_UNKNOWN})

Population = tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class RawDataPosteriorDiagnostics:
    """JSON-safe identity, support, and bounded prediction diagnostics."""

    posterior_kind: str
    requested_draw_count: int
    support_kind: str
    unique_support: int | None
    seed: int
    draw_ids: tuple[str, ...]
    draw_sources: tuple[str, ...]
    schema_signature: str
    state_signature: str
    strategy_signature: str
    approximate: bool
    limitations: tuple[str, ...]
    field_selectors: tuple[RawDataFieldSelector, ...]
    candidate_count: int = 0
    prediction_failure_count: int = 0
    retained_prediction_failures: tuple[Mapping[str, object], ...] = ()
    observation_noise_included: bool = False
    effective_unique_support: int | None = None
    calibrated: bool = False
    calibration_method: str | None = None
    calibration_artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        posterior_kind = str(self.posterior_kind)
        if not posterior_kind:
            raise ValueError("posterior_kind must not be empty")
        requested = int(self.requested_draw_count)
        if requested <= 0:
            raise ValueError("requested_draw_count must be positive")
        if self.support_kind not in _SUPPORT_KINDS:
            raise ValueError(
                "support_kind must be 'finite' or 'continuous_or_unknown'"
            )
        if self.support_kind == SUPPORT_FINITE:
            if self.unique_support is None or int(self.unique_support) < 0:
                raise ValueError(
                    "finite posterior support requires non-negative unique_support"
                )
        elif self.unique_support is not None:
            raise ValueError(
                "continuous or unknown posterior support must use unique_support=None"
            )
        ids = tuple(str(value) for value in self.draw_ids)
        if len(ids) > requested:
            raise ValueError("actual draw count cannot exceed requested draw count")
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            raise ValueError("draw IDs must be non-empty and unique")
        if ids and self.support_kind == SUPPORT_FINITE and int(self.unique_support) == 0:
            raise ValueError("finite posterior draws require positive unique_support")
        sources = tuple(str(value) for value in self.draw_sources)
        if len(sources) != len(ids):
            raise ValueError("draw_sources must align with draw_ids")
        if any(not source for source in sources):
            raise ValueError("draw_sources must be non-empty")
        unique_support = (
            None if self.unique_support is None else int(self.unique_support)
        )
        if (
            self.support_kind == SUPPORT_FINITE
            and len(set(sources)) > int(unique_support)
        ):
            raise ValueError(
                "finite posterior draw sources exceed reported unique support"
            )
        effective_support = (
            None
            if self.effective_unique_support is None
            else int(self.effective_unique_support)
        )
        if effective_support is not None:
            if self.support_kind != SUPPORT_FINITE:
                raise ValueError(
                    "effective_unique_support is only defined for finite support"
                )
            if effective_support < 0 or effective_support > int(unique_support):
                raise ValueError(
                    "effective_unique_support must be between zero and unique_support"
                )
        selectors = tuple(
            (str(selector[0]), str(selector[1]))
            for selector in self.field_selectors
        )
        if len(selectors) != len(set(selectors)):
            raise ValueError("posterior field selectors must be unique")
        if any(
            not filename
            or not filename.lower().endswith(".npz")
            or "/" in filename
            or "\\" in filename
            or key not in {"values", "data"}
            for filename, key in selectors
        ):
            raise ValueError(
                "posterior field selectors require an exact .npz basename and "
                "resolved values/data key"
            )
        signatures = {
            "schema_signature": str(self.schema_signature),
            "state_signature": str(self.state_signature),
            "strategy_signature": str(self.strategy_signature),
        }
        for name, value in signatures.items():
            if not value:
                raise ValueError(f"{name} must not be empty")
        if int(self.candidate_count) < 0:
            raise ValueError("candidate_count must be non-negative")
        failures = int(self.prediction_failure_count)
        retained = tuple(dict(item) for item in self.retained_prediction_failures)
        if failures < len(retained):
            raise ValueError(
                "prediction_failure_count cannot be smaller than retained failures"
            )
        for item in retained:
            _require_json_mapping(item, "posterior prediction failure")
        object.__setattr__(self, "posterior_kind", posterior_kind)
        object.__setattr__(self, "requested_draw_count", requested)
        object.__setattr__(self, "unique_support", unique_support)
        object.__setattr__(self, "effective_unique_support", effective_support)
        object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "draw_ids", ids)
        object.__setattr__(self, "draw_sources", sources)
        object.__setattr__(self, "field_selectors", selectors)
        for name, value in signatures.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "approximate", bool(self.approximate))
        object.__setattr__(
            self,
            "observation_noise_included",
            bool(self.observation_noise_included),
        )
        calibrated = bool(self.calibrated)
        method = (
            None
            if self.calibration_method is None
            else str(self.calibration_method)
        )
        artifact_sha256 = (
            None
            if self.calibration_artifact_sha256 is None
            else str(self.calibration_artifact_sha256).lower()
        )
        if calibrated:
            if not method:
                raise ValueError(
                    "calibrated posterior diagnostics require a method"
                )
            if artifact_sha256 is None or len(artifact_sha256) != 64 or any(
                char not in "0123456789abcdef" for char in artifact_sha256
            ):
                raise ValueError(
                    "calibrated posterior diagnostics require an artifact SHA-256"
                )
        elif method is not None or artifact_sha256 is not None:
            raise ValueError(
                "uncalibrated posterior diagnostics cannot name calibration state"
            )
        object.__setattr__(self, "calibrated", calibrated)
        object.__setattr__(self, "calibration_method", method)
        object.__setattr__(
            self, "calibration_artifact_sha256", artifact_sha256
        )
        object.__setattr__(self, "candidate_count", int(self.candidate_count))
        object.__setattr__(self, "prediction_failure_count", failures)
        object.__setattr__(self, "retained_prediction_failures", retained)
        object.__setattr__(
            self,
            "limitations",
            tuple(str(value) for value in self.limitations),
        )
        _require_json_mapping(self.as_dict(), "posterior diagnostics")

    @property
    def actual_draw_count(self) -> int:
        return len(self.draw_ids)

    def for_prediction(
        self,
        candidate_count: int,
        *,
        prediction_failure_count: int = 0,
        retained_prediction_failures: Sequence[Mapping[str, object]] = (),
        effective_unique_support: int | None = None,
    ) -> "RawDataPosteriorDiagnostics":
        return replace(
            self,
            candidate_count=int(candidate_count),
            prediction_failure_count=int(prediction_failure_count),
            retained_prediction_failures=tuple(retained_prediction_failures),
            effective_unique_support=effective_unique_support,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "protocol": RAWDATA_POSTERIOR_PROTOCOL,
            "protocol_version": RAWDATA_POSTERIOR_PROTOCOL_VERSION,
            "posterior_kind": self.posterior_kind,
            "requested_draw_count": self.requested_draw_count,
            "actual_draw_count": self.actual_draw_count,
            "support_kind": self.support_kind,
            "unique_support": self.unique_support,
            "effective_unique_support": self.effective_unique_support,
            "seed": self.seed,
            "draw_ids": list(self.draw_ids),
            "draw_sources": list(self.draw_sources),
            "schema_signature": self.schema_signature,
            "state_signature": self.state_signature,
            "strategy_signature": self.strategy_signature,
            "approximate": self.approximate,
            "limitations": list(self.limitations),
            "field_selectors": [list(selector) for selector in self.field_selectors],
            "candidate_count": self.candidate_count,
            "prediction_failure_count": self.prediction_failure_count,
            "retained_prediction_failures": [
                dict(item) for item in self.retained_prediction_failures
            ],
            "observation_noise_included": self.observation_noise_included,
            "calibrated": self.calibrated,
            "calibration_method": self.calibration_method,
            "calibration_artifact_sha256": self.calibration_artifact_sha256,
        }


@dataclass(frozen=True, slots=True)
class RawDataFunctionDraw:
    """One fixed possible function evaluated for a candidate chunk."""

    draw_id: str
    samples: tuple[RawDataSampleLike, ...]

    def __post_init__(self) -> None:
        if not str(self.draw_id):
            raise ValueError("draw_id must not be empty")
        object.__setattr__(self, "draw_id", str(self.draw_id))
        object.__setattr__(self, "samples", tuple(self.samples))


@runtime_checkable
class RawDataPosterior(Protocol):
    """One candidate-chunk posterior view that can stream function draws."""

    @property
    def population(self) -> Population: ...

    @property
    def diagnostics(self) -> RawDataPosteriorDiagnostics: ...

    def iter_draws(self) -> Iterable[RawDataFunctionDraw]: ...


@dataclass(frozen=True, slots=True)
class MaterializedRawDataPosterior:
    """Small-population convenience container; streaming backends need not use it."""

    population: Population
    draws: tuple[RawDataFunctionDraw, ...]
    diagnostics: RawDataPosteriorDiagnostics

    def __post_init__(self) -> None:
        population = tuple(
            tuple(float(value) for value in row) for row in self.population
        )
        draws = tuple(self.draws)
        if self.diagnostics.candidate_count != len(population):
            raise ValueError(
                "posterior diagnostics candidate_count does not match population"
            )
        if tuple(draw.draw_id for draw in draws) != self.diagnostics.draw_ids:
            raise ValueError("posterior draw order does not match diagnostic draw IDs")
        if any(len(draw.samples) != len(population) for draw in draws):
            raise ValueError("each posterior draw must align with the candidate chunk")
        object.__setattr__(self, "population", population)
        object.__setattr__(self, "draws", draws)

    def iter_draws(self) -> Iterable[RawDataFunctionDraw]:
        return iter(self.draws)


@runtime_checkable
class RawDataPosteriorSampler(Protocol):
    """Persistent fixed-draw sampler reusable across candidate chunks."""

    @property
    def schema(self) -> RawDataSchemaTemplate: ...

    @property
    def diagnostics(self) -> RawDataPosteriorDiagnostics: ...

    def predict(
        self,
        population: Sequence[Sequence[float]],
    ) -> RawDataPosterior: ...


@runtime_checkable
class RawDataPosteriorSurrogate(Protocol):
    """Explicit posterior capability implemented by a surrogate component."""

    def semantic_identity(self, config, problem) -> Mapping[str, object]: ...

    def posterior_semantic_identity(self, config, problem) -> Mapping[str, object]: ...

    def make_rawdata_sampler(
        self,
        context,
        *,
        draw_count: int,
        seed: int,
        training_data=None,
    ) -> RawDataPosteriorSampler: ...


def require_rawdata_posterior_surrogate(component: object) -> RawDataPosteriorSurrogate:
    """Validate explicit capability without scattered ``hasattr`` checks."""

    if not isinstance(component, RawDataPosteriorSurrogate):
        raise TypeError(
            "surrogate component must implement RawDataPosteriorSurrogate "
            "(semantic_identity, posterior_semantic_identity, and "
            "make_rawdata_sampler)"
        )
    return component


def posterior_capability_identity(
    *,
    posterior_kind: str,
    support_kind: str,
    backend_distribution: str,
    backend_version: str,
    controlled_parameters: Mapping[str, object],
) -> dict[str, object]:
    """Build the semantic-identity block required of posterior consumers."""

    if support_kind not in _SUPPORT_KINDS:
        raise ValueError(
            "support_kind must be 'finite' or 'continuous_or_unknown'"
        )
    identity = {
        "capability": "joint-rawdata-posterior",
        "protocol": RAWDATA_POSTERIOR_PROTOCOL,
        "protocol_version": RAWDATA_POSTERIOR_PROTOCOL_VERSION,
        "posterior_kind": str(posterior_kind),
        "support_kind": str(support_kind),
        "backend_distribution": str(backend_distribution),
        "backend_version": str(backend_version),
        "controlled_parameters": dict(controlled_parameters),
    }
    if not all(
        identity[name]
        for name in ("posterior_kind", "backend_distribution", "backend_version")
    ):
        raise ValueError("posterior and backend identity values must not be empty")
    _require_json_mapping(identity, "posterior capability identity")
    return identity


class _StreamingFailureCollector:
    def __init__(self, limit: int) -> None:
        self.limit = int(limit)
        self.total = 0
        self.retained: list[CostProjectionFailure] = []
        self.counts: Counter[str] = Counter()

    def add(self, failure: CostProjectionFailure) -> None:
        self.total += 1
        self.counts[failure.error_type] += 1
        if len(self.retained) < self.limit:
            self.retained.append(failure)


def project_rawdata_sampler(
    sampler: RawDataPosteriorSampler,
    projector: RawDataCostProjector,
    population: Sequence[Sequence[float]],
    *,
    candidate_chunk_size: int | None = None,
) -> JointObjectiveSamples:
    """Stream candidate chunks and function draws into joint objective samples.

    Only the final ``[draw, candidate, objective]`` tensor remains resident.  Each
    structured rawData draw is projected immediately and then released.
    """

    if not isinstance(sampler, RawDataPosteriorSampler):
        raise TypeError("sampler must implement RawDataPosteriorSampler")
    if not isinstance(projector, RawDataCostProjector):
        raise TypeError("projector must be a RawDataCostProjector")
    rows = tuple(tuple(float(value) for value in row) for row in population)
    base = sampler.diagnostics
    draw_ids = base.draw_ids
    draw_count = len(draw_ids)
    objective_count = len(projector.objective_names)
    costs = np.full(
        (draw_count, len(rows), objective_count),
        np.nan,
        dtype=np.float64,
    )
    valid = np.zeros((draw_count, len(rows)), dtype=bool)
    failures = _StreamingFailureCollector(projector.max_diagnostic_failures)

    if candidate_chunk_size is None:
        chunk_size = max(1, len(rows))
    else:
        chunk_size = int(candidate_chunk_size)
        if chunk_size <= 0:
            raise ValueError("candidate_chunk_size must be positive")

    prediction_failure_count = 0
    retained_prediction_failures: list[dict[str, object]] = []
    chunk_count = 0
    for start in range(0, len(rows), chunk_size):
        stop = min(len(rows), start + chunk_size)
        chunk = rows[start:stop]
        chunk_count += 1
        try:
            posterior = sampler.predict(chunk)
            _validate_chunk_posterior(posterior, base, chunk)
        except Exception as exc:
            _invalidate_chunk(
                failures,
                draw_ids,
                start,
                stop,
                "posterior_prediction",
                str(exc),
            )
            prediction_failure_count += (stop - start) * draw_count
            if len(retained_prediction_failures) < 32:
                retained_prediction_failures.append(
                    {
                        "error_type": "posterior_prediction",
                        "candidate_start": start,
                        "candidate_stop": stop,
                        "message": str(exc).replace("\r", " ").replace("\n", " ")[:512],
                    }
                )
            continue

        prediction_failure_count += posterior.diagnostics.prediction_failure_count
        remaining_failure_slots = 32 - len(retained_prediction_failures)
        if remaining_failure_slots > 0:
            retained_prediction_failures.extend(
                dict(item)
                for item in posterior.diagnostics.retained_prediction_failures[
                    :remaining_failure_slots
                ]
            )
        iterator = iter(posterior.iter_draws())
        contract_error: Exception | None = None
        for draw_index, expected_draw_id in enumerate(draw_ids):
            try:
                draw = next(iterator)
                if not isinstance(draw, RawDataFunctionDraw):
                    raise TypeError("posterior draw must be RawDataFunctionDraw")
                if draw.draw_id != expected_draw_id:
                    raise ValueError(
                        f"posterior draw order changed: expected {expected_draw_id!r}, "
                        f"got {draw.draw_id!r}"
                    )
                projected = projector.project_draw(
                    draw.draw_id,
                    draw.samples,
                    chunk,
                )
            except Exception as exc:
                contract_error = exc
                break
            costs[draw_index, start:stop, :] = projected.cost_samples[0]
            valid[draw_index, start:stop] = projected.valid_mask[0]
            for failure in projected.diagnostics.retained_failures:
                failures.add(
                    CostProjectionFailure(
                        draw_id=failure.draw_id,
                        draw_index=draw_index,
                        candidate_index=start + failure.candidate_index,
                        error_type=failure.error_type,
                        message=failure.message,
                    )
                )
            hidden = (
                projected.diagnostics.failure_count
                - len(projected.diagnostics.retained_failures)
            )
            if hidden:
                failures.total += hidden
                for name, count in projected.diagnostics.failure_type_counts.items():
                    retained_count = sum(
                        failure.error_type == name
                        for failure in projected.diagnostics.retained_failures
                    )
                    failures.counts[str(name)] += max(0, int(count) - retained_count)

        if contract_error is None:
            try:
                next(iterator)
            except StopIteration:
                pass
            except Exception as exc:
                contract_error = exc
            else:
                contract_error = ValueError(
                    "posterior yielded more draws than its diagnostic draw IDs"
                )
        if contract_error is not None:
            costs[:, start:stop, :] = np.nan
            valid[:, start:stop] = False
            _invalidate_chunk(
                failures,
                draw_ids,
                start,
                stop,
                "posterior_contract",
                str(contract_error),
            )

    source = base.as_dict()
    complete_draws = (
        np.all(valid, axis=1)
        if len(rows)
        else np.zeros((draw_count,), dtype=bool)
    )
    effective_sources = {
        base.draw_sources[index]
        for index in np.flatnonzero(complete_draws)
    }
    source.update(
        {
            "candidate_count": len(rows),
            "candidate_chunk_count": chunk_count,
            "candidate_chunk_size": chunk_size,
            "prediction_failure_count": prediction_failure_count,
            "retained_prediction_failures": retained_prediction_failures,
            "truncated_prediction_failure_count": max(
                0,
                prediction_failure_count - len(retained_prediction_failures),
            ),
            "effective_draw_count": int(np.count_nonzero(complete_draws)),
            "effective_unique_support": (
                len(effective_sources)
                if base.support_kind == SUPPORT_FINITE
                else None
            ),
        }
    )
    return JointObjectiveSamples.from_arrays(
        cost_samples=costs,
        valid_mask=valid,
        draw_ids=draw_ids,
        normalized_population=rows,
        objective_names=projector.objective_names,
        failures=failures.retained,
        total_failure_count=failures.total,
        failure_type_counts=failures.counts,
        source_diagnostics=source,
    )


def _validate_chunk_posterior(
    posterior: object,
    base: RawDataPosteriorDiagnostics,
    population: Population,
) -> None:
    if not isinstance(posterior, RawDataPosterior):
        raise TypeError("sampler.predict() must return RawDataPosterior")
    if posterior.population != population:
        raise ValueError("posterior population does not match the requested chunk")
    current = posterior.diagnostics
    stable_fields = (
        "posterior_kind",
        "requested_draw_count",
        "support_kind",
        "unique_support",
        "seed",
        "draw_ids",
        "draw_sources",
        "schema_signature",
        "state_signature",
        "strategy_signature",
        "approximate",
        "limitations",
        "field_selectors",
        "observation_noise_included",
        "calibrated",
        "calibration_method",
        "calibration_artifact_sha256",
    )
    changed = tuple(
        name for name in stable_fields if getattr(current, name) != getattr(base, name)
    )
    if changed:
        raise ValueError(
            "posterior identity changed across candidate chunks: "
            + ", ".join(changed)
        )
    if current.candidate_count != len(population):
        raise ValueError("posterior diagnostics candidate_count does not match chunk")


def _invalidate_chunk(
    collector: _StreamingFailureCollector,
    draw_ids: Sequence[str],
    start: int,
    stop: int,
    error_type: str,
    message: str,
) -> None:
    bounded = str(message).replace("\r", " ").replace("\n", " ")[:512]
    for draw_index, draw_id in enumerate(draw_ids):
        for candidate_index in range(start, stop):
            collector.add(
                CostProjectionFailure(
                    draw_id=str(draw_id),
                    draw_index=draw_index,
                    candidate_index=candidate_index,
                    error_type=str(error_type),
                    message=bounded,
                )
            )


def _require_json_mapping(value: Mapping[str, object], label: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    try:
        json.dumps(value, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must contain JSON-safe finite values") from exc


__all__ = [
    "MaterializedRawDataPosterior",
    "Population",
    "RAWDATA_POSTERIOR_PROTOCOL",
    "RAWDATA_POSTERIOR_PROTOCOL_VERSION",
    "RawDataFunctionDraw",
    "RawDataPosterior",
    "RawDataPosteriorDiagnostics",
    "RawDataPosteriorSampler",
    "RawDataPosteriorSurrogate",
    "SUPPORT_CONTINUOUS_OR_UNKNOWN",
    "SUPPORT_FINITE",
    "posterior_capability_identity",
    "project_rawdata_sampler",
    "require_rawdata_posterior_surrogate",
]
