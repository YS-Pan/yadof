"""Streaming projection of structured posterior rawData through current task cost."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
from typing import Iterator, Mapping, Sequence

import numpy as np

from .api import (
    CostInterpreter,
    CostNonFiniteError,
    CostObjectiveWidthError,
    WorkspaceLike,
    task_cost_interpreter,
)
from .rawdata_template import RawDataSampleLike, RawDataSchemaTemplate


@dataclass(frozen=True, slots=True)
class CostProjectionFailure:
    """One invalid posterior draw/candidate projection outcome."""

    draw_id: str
    draw_index: int
    candidate_index: int
    error_type: str
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "draw_id": self.draw_id,
            "draw_index": self.draw_index,
            "candidate_index": self.candidate_index,
            "error_type": self.error_type,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class CostProjectionDiagnostics:
    """Bounded aggregate diagnostics for one objective-sample tensor."""

    draw_count: int
    candidate_count: int
    objective_count: int
    valid_count: int
    invalid_count: int
    failure_count: int
    retained_failures: tuple[CostProjectionFailure, ...]
    truncated_failure_count: int
    failure_type_counts: Mapping[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "draw_count": self.draw_count,
            "candidate_count": self.candidate_count,
            "objective_count": self.objective_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "failure_count": self.failure_count,
            "retained_failures": [
                failure.as_dict() for failure in self.retained_failures
            ],
            "truncated_failure_count": self.truncated_failure_count,
            "failure_type_counts": dict(self.failure_type_counts),
        }


@dataclass(frozen=True, slots=True)
class JointObjectiveSamples:
    """Joint ``[draw, candidate, objective]`` costs and validity mask."""

    cost_samples: np.ndarray
    valid_mask: np.ndarray
    draw_ids: tuple[str, ...]
    normalized_population: tuple[tuple[float, ...], ...]
    objective_names: tuple[str, ...]
    diagnostics: CostProjectionDiagnostics
    source_diagnostics: Mapping[str, object]

    def __post_init__(self) -> None:
        costs = np.ascontiguousarray(self.cost_samples, dtype=np.float64)
        valid = np.ascontiguousarray(self.valid_mask, dtype=bool)
        expected = (
            len(self.draw_ids),
            len(self.normalized_population),
            len(self.objective_names),
        )
        if costs.shape != expected:
            raise ValueError(
                f"cost samples must have shape {expected}, got {costs.shape}"
            )
        if valid.shape != expected[:2]:
            raise ValueError(
                f"valid mask must have shape {expected[:2]}, got {valid.shape}"
            )
        if len(self.draw_ids) != len(set(self.draw_ids)) or any(
            not draw_id for draw_id in self.draw_ids
        ):
            raise ValueError("draw IDs must be non-empty and unique")
        if (
            self.diagnostics.draw_count != expected[0]
            or self.diagnostics.candidate_count != expected[1]
            or self.diagnostics.objective_count != expected[2]
            or self.diagnostics.valid_count != int(np.count_nonzero(valid))
            or self.diagnostics.invalid_count
            != int(valid.size - np.count_nonzero(valid))
        ):
            raise ValueError("projection diagnostics do not match sample arrays")
        _require_json_mapping(self.source_diagnostics, "source diagnostics")
        costs.setflags(write=False)
        valid.setflags(write=False)
        object.__setattr__(self, "cost_samples", costs)
        object.__setattr__(self, "valid_mask", valid)
        object.__setattr__(
            self,
            "normalized_population",
            tuple(tuple(float(value) for value in row) for row in self.normalized_population),
        )
        object.__setattr__(self, "source_diagnostics", dict(self.source_diagnostics))

    @classmethod
    def from_arrays(
        cls,
        *,
        cost_samples: object,
        valid_mask: object,
        draw_ids: Sequence[str],
        normalized_population: Sequence[Sequence[float]],
        objective_names: Sequence[str],
        failures: Sequence[CostProjectionFailure] = (),
        total_failure_count: int | None = None,
        failure_type_counts: Mapping[str, int] | None = None,
        source_diagnostics: Mapping[str, object] | None = None,
    ) -> "JointObjectiveSamples":
        costs = np.asarray(cost_samples, dtype=np.float64)
        valid = np.asarray(valid_mask, dtype=bool)
        ids = tuple(str(value) for value in draw_ids)
        population = tuple(
            tuple(float(value) for value in row)
            for row in normalized_population
        )
        names = tuple(str(value) for value in objective_names)
        retained = tuple(failures)
        total = len(retained) if total_failure_count is None else int(total_failure_count)
        if total < len(retained):
            raise ValueError("total failure count cannot be smaller than retained failures")
        counts = (
            Counter(failure.error_type for failure in retained)
            if failure_type_counts is None
            else Counter({str(key): int(value) for key, value in failure_type_counts.items()})
        )
        diagnostics = CostProjectionDiagnostics(
            draw_count=len(ids),
            candidate_count=len(population),
            objective_count=len(names),
            valid_count=int(np.count_nonzero(valid)),
            invalid_count=int(valid.size - np.count_nonzero(valid)),
            failure_count=total,
            retained_failures=retained,
            truncated_failure_count=total - len(retained),
            failure_type_counts=dict(sorted(counts.items())),
        )
        return cls(
            cost_samples=costs,
            valid_mask=valid,
            draw_ids=ids,
            normalized_population=population,
            objective_names=names,
            diagnostics=diagnostics,
            source_diagnostics=dict(source_diagnostics or {}),
        )


class _FailureCollector:
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


class RawDataCostProjector:
    """Thin per-draw adapter over one frozen :class:`CostInterpreter`.

    Invalid projections retain ``NaN`` in ``cost_samples`` and ``False`` in the
    validity mask.  A finite task-level fallback such as ``error_cost=1.0`` is a
    valid result because the existing callback contract does not expose its origin.
    """

    def __init__(
        self,
        interpreter: CostInterpreter,
        schema: RawDataSchemaTemplate,
        *,
        max_diagnostic_failures: int = 32,
    ) -> None:
        if not isinstance(interpreter, CostInterpreter):
            raise TypeError("RawDataCostProjector requires a CostInterpreter")
        if not isinstance(schema, RawDataSchemaTemplate):
            raise TypeError("RawDataCostProjector requires a RawDataSchemaTemplate")
        limit = int(max_diagnostic_failures)
        if limit < 0:
            raise ValueError("max_diagnostic_failures must be non-negative")
        self.interpreter = interpreter
        self.schema = schema
        self.max_diagnostic_failures = limit

    @property
    def objective_names(self) -> tuple[str, ...]:
        return self.interpreter.objective_names

    def project_draw(
        self,
        draw_id: str,
        rawdata_samples: Sequence[RawDataSampleLike],
        normalized_population: Sequence[Sequence[float]],
    ) -> JointObjectiveSamples:
        """Project and release one coherent rawData function draw."""

        return self.project(
            (tuple(rawdata_samples),),
            normalized_population,
            draw_ids=(str(draw_id),),
        )

    def project(
        self,
        rawdata_draws: Sequence[Sequence[RawDataSampleLike]],
        normalized_population: Sequence[Sequence[float]],
        *,
        draw_ids: Sequence[str] | None = None,
    ) -> JointObjectiveSamples:
        """Project a materialized ``[draw, candidate]`` rawData collection."""

        population = tuple(
            tuple(float(value) for value in row) for row in normalized_population
        )
        draws = tuple(tuple(draw) for draw in rawdata_draws)
        ids = (
            tuple(f"draw-{index:06d}" for index in range(len(draws)))
            if draw_ids is None
            else tuple(str(value) for value in draw_ids)
        )
        if len(ids) != len(draws):
            raise ValueError(f"expected {len(draws)} draw IDs, got {len(ids)}")
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            raise ValueError("draw IDs must be non-empty and unique")

        objective_count = len(self.objective_names)
        costs = np.full(
            (len(draws), len(population), objective_count),
            np.nan,
            dtype=np.float64,
        )
        valid = np.zeros((len(draws), len(population)), dtype=bool)
        failures = _FailureCollector(self.max_diagnostic_failures)
        raw_variables: list[tuple[float, ...] | Exception] = []
        for row in population:
            try:
                raw_variables.append(self.interpreter.denormalize_variables(row))
            except Exception as exc:
                raw_variables.append(exc)

        for draw_index, (draw_id, draw) in enumerate(zip(ids, draws)):
            if len(draw) != len(population):
                for candidate_index in range(len(population)):
                    failures.add(
                        self._failure(
                            draw_id,
                            draw_index,
                            candidate_index,
                            "posterior_shape",
                            f"draw contains {len(draw)} candidates; expected {len(population)}",
                        )
                    )
                continue
            for candidate_index, (sample, variables) in enumerate(
                zip(draw, raw_variables)
            ):
                if isinstance(variables, Exception):
                    failures.add(
                        self._failure(
                            draw_id,
                            draw_index,
                            candidate_index,
                            "normalized_variables",
                            str(variables),
                        )
                    )
                    continue
                try:
                    structured = self.schema.validate_sample(sample)
                except Exception as exc:
                    failures.add(
                        self._failure(
                            draw_id,
                            draw_index,
                            candidate_index,
                            "rawdata_schema",
                            str(exc),
                        )
                    )
                    continue
                try:
                    row = self.interpreter.calculate_costs(
                        (structured.cost_items(),),
                        raw_variables=(variables,),
                    )[0]
                except CostObjectiveWidthError as exc:
                    failures.add(
                        self._failure(
                            draw_id,
                            draw_index,
                            candidate_index,
                            "objective_width",
                            str(exc),
                        )
                    )
                    continue
                except CostNonFiniteError as exc:
                    failures.add(
                        self._failure(
                            draw_id,
                            draw_index,
                            candidate_index,
                            "non_finite_objective",
                            str(exc),
                        )
                    )
                    continue
                except Exception as exc:
                    failures.add(
                        self._failure(
                            draw_id,
                            draw_index,
                            candidate_index,
                            "cost_callback",
                            str(exc),
                        )
                    )
                    continue
                if not all(math.isfinite(float(value)) for value in row):
                    failures.add(
                        self._failure(
                            draw_id,
                            draw_index,
                            candidate_index,
                            "non_finite_objective",
                            "cost callback returned a non-finite objective",
                        )
                    )
                    continue
                costs[draw_index, candidate_index, :] = row
                valid[draw_index, candidate_index] = True

        return JointObjectiveSamples.from_arrays(
            cost_samples=costs,
            valid_mask=valid,
            draw_ids=ids,
            normalized_population=population,
            objective_names=self.objective_names,
            failures=failures.retained,
            total_failure_count=failures.total,
            failure_type_counts=failures.counts,
        )

    @staticmethod
    def _failure(
        draw_id: str,
        draw_index: int,
        candidate_index: int,
        error_type: str,
        message: str,
    ) -> CostProjectionFailure:
        bounded = str(message).replace("\r", " ").replace("\n", " ")[:512]
        return CostProjectionFailure(
            draw_id=str(draw_id),
            draw_index=int(draw_index),
            candidate_index=int(candidate_index),
            error_type=str(error_type),
            message=bounded,
        )


@contextmanager
def task_rawdata_cost_projector(
    workspace: WorkspaceLike,
    schema: RawDataSchemaTemplate,
    *,
    max_diagnostic_failures: int = 32,
) -> Iterator[RawDataCostProjector]:
    """Freeze task parameters/callback and yield their narrow projector."""

    with task_cost_interpreter(workspace) as interpreter:
        yield RawDataCostProjector(
            interpreter,
            schema,
            max_diagnostic_failures=max_diagnostic_failures,
        )


def _require_json_mapping(value: Mapping[str, object], label: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    try:
        json.dumps(value, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must contain JSON-safe finite values") from exc


__all__ = [
    "CostProjectionDiagnostics",
    "CostProjectionFailure",
    "JointObjectiveSamples",
    "RawDataCostProjector",
    "task_rawdata_cost_projector",
]
