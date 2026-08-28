"""Discrete qNEHVI-family batch selection over projected joint samples."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import math
import time
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from ...job_template.rawdata_projector import JointObjectiveSamples
from .backend import score_discrete_qlognehvi


class QNEHVIFallback(RuntimeError):
    """A configured soft failure that requests full real-search fallback."""


class QNEHVISupportRejected(RuntimeError):
    """A configured hard support gate that must stop the campaign."""


class QNEHVIConfigurationError(ValueError):
    """A runtime source capability is incompatible with acquisition settings."""


@dataclass(frozen=True, slots=True)
class QNEHVISelection:
    selected_indices: tuple[int, ...]
    log_acquisition_value: float
    diagnostics: Mapping[str, object]

    def __post_init__(self) -> None:
        indices = tuple(int(value) for value in self.selected_indices)
        if not indices or len(indices) != len(set(indices)) or min(indices) < 0:
            raise ValueError("qNEHVI selection indices must be unique and non-negative")
        value = float(self.log_acquisition_value)
        if not math.isfinite(value):
            raise ValueError("qNEHVI selection value must be finite")
        object.__setattr__(self, "selected_indices", indices)
        object.__setattr__(self, "log_acquisition_value", value)
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))


@dataclass(frozen=True, slots=True)
class DiscreteQNEHVIAcquisition:
    """Greedy multi-start selection using BoTorch for every numeric score."""

    batch_size: int
    greedy_restarts: int
    reference_point: tuple[float, ...] | None = None
    device: str = "cpu"
    minimum_unique_support: int | None = None
    low_support_policy: str = "reject"

    def __post_init__(self) -> None:
        batch = int(self.batch_size)
        restarts = int(self.greedy_restarts)
        if batch <= 0:
            raise ValueError("qNEHVI batch_size must be positive")
        if restarts <= 0:
            raise ValueError("qNEHVI greedy_restarts must be positive")
        reference = (
            None
            if self.reference_point is None
            else tuple(float(value) for value in self.reference_point)
        )
        if reference is not None and any(
            not math.isfinite(value) or value < 0.0 or value > 1.0
            for value in reference
        ):
            raise ValueError(
                "qNEHVI reference_point must contain finite costs in [0, 1]"
            )
        device = str(self.device).strip()
        if not device:
            raise ValueError("qNEHVI device must not be empty")
        minimum = (
            None
            if self.minimum_unique_support is None
            else int(self.minimum_unique_support)
        )
        if minimum is not None and minimum <= 0:
            raise ValueError("minimum_unique_support must be positive")
        policy = str(self.low_support_policy).strip().lower()
        if policy not in {"warn", "fallback", "reject"}:
            raise ValueError(
                "low_support_policy must be 'warn', 'fallback', or 'reject'"
            )
        object.__setattr__(self, "batch_size", batch)
        object.__setattr__(self, "greedy_restarts", restarts)
        object.__setattr__(self, "reference_point", reference)
        object.__setattr__(self, "device", device)
        object.__setattr__(self, "minimum_unique_support", minimum)
        object.__setattr__(self, "low_support_policy", policy)

    def validate(self, config, problem) -> None:
        del config
        objective_count = int(problem.objective_count)
        if objective_count < 2:
            raise ValueError("qNEHVI requires at least two objectives")
        if self.reference_point is not None and len(self.reference_point) != objective_count:
            raise ValueError(
                "qNEHVI reference_point must have one value per objective"
            )
        try:
            metadata.version("botorch")
            metadata.version("torch")
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "qNEHVI requires the optional yadof qnehvi extra "
                "(install yadof[qnehvi])"
            ) from exc

    def semantic_identity(self, config, problem) -> Mapping[str, object]:
        del config
        objective_count = int(problem.objective_count)
        reference = (
            tuple(1.0 for _ in range(objective_count))
            if self.reference_point is None
            else self.reference_point
        )
        return {
            "component": "discrete-qnehvi-acquisition",
            "component_version": 1,
            "family": "qnehvi",
            "backend_distribution": "botorch",
            "backend_version": metadata.version("botorch"),
            "backend_class": "qLogNoisyExpectedHypervolumeImprovement",
            "objective_names": list(problem.objective_names),
            "controlled_parameters": {
                "batch_size": self.batch_size,
                "greedy_restarts": self.greedy_restarts,
                "reference_point_cost": list(reference),
                "device": self.device,
                "minimum_unique_support": self.minimum_unique_support,
                "low_support_policy": self.low_support_policy,
                "seed_policy": "generation-context-derived-v1",
                "candidate_optimization": "discrete-greedy-multistart-v1",
                "observation_noise_included": False,
                "pending_points": "unsupported",
                "outcome_constraints": "unsupported",
            },
        }

    def select_batch(
        self,
        *,
        baseline_population: Sequence[Sequence[float]],
        baseline_costs: Sequence[Sequence[float]],
        candidate_samples: JointObjectiveSamples,
        seed: int,
    ) -> QNEHVISelection:
        if not isinstance(candidate_samples, JointObjectiveSamples):
            raise TypeError("candidate_samples must be JointObjectiveSamples")
        population = candidate_samples.normalized_population
        candidate_count = len(population)
        if candidate_count == 0:
            raise QNEHVIFallback("candidate pool is empty")
        width = len(population[0])
        if width == 0 or any(len(row) != width for row in population):
            raise QNEHVIConfigurationError(
                "candidate pool must have one positive parameter width"
            )
        if any(
            not math.isfinite(value) or value < 0.0 or value > 1.0
            for row in population
            for value in row
        ):
            raise QNEHVIConfigurationError(
                "candidate pool must contain finite normalized parameters"
            )
        if len(set(population)) != candidate_count:
            raise QNEHVIConfigurationError("candidate pool must be unique")
        if candidate_count < self.batch_size:
            raise QNEHVIFallback(
                "candidate pool is smaller than the configured qNEHVI batch"
            )
        support = self._support_diagnostics(candidate_samples)
        if support["low_support"]:
            message = (
                "finite posterior effective support "
                f"{support['effective_unique_support']} is below required minimum "
                f"{self.minimum_unique_support}"
            )
            if self.low_support_policy == "fallback":
                raise QNEHVIFallback(message)
            if self.low_support_policy == "reject":
                raise QNEHVISupportRejected(message)

        started = time.perf_counter()
        call_count = 0
        scored_batch_count = 0
        backend_elapsed = 0.0
        maximum_resident = 0
        maximum_cuda = 0
        last_backend: Mapping[str, object] = {}

        def score(batches: Sequence[Sequence[int]]) -> tuple[float, ...]:
            nonlocal call_count, scored_batch_count, backend_elapsed
            nonlocal maximum_resident, maximum_cuda, last_backend
            result = score_discrete_qlognehvi(
                baseline_population=baseline_population,
                baseline_costs=baseline_costs,
                candidate_samples=candidate_samples,
                candidate_batches=batches,
                reference_point=self.reference_point,
                seed=int(seed),
                device=self.device,
                minimum_unique_support=self.minimum_unique_support,
                low_support_policy=(
                    "warn" if self.low_support_policy == "warn" else "reject"
                ),
            )
            call_count += 1
            scored_batch_count += len(batches)
            last_backend = result.diagnostics
            backend_elapsed += float(result.diagnostics.get("elapsed_sec", 0.0))
            maximum_resident = max(
                maximum_resident,
                int(result.diagnostics.get("resident_tensor_bytes", 0)),
            )
            maximum_cuda = max(
                maximum_cuda,
                int(result.diagnostics.get("cuda_peak_allocated_bytes", 0)),
            )
            return result.log_acquisition_values

        singleton_batches = tuple((index,) for index in range(candidate_count))
        singleton_values = score(singleton_batches)
        ranked_starts = sorted(
            range(candidate_count),
            key=lambda index: (-singleton_values[index], index),
        )[: min(self.greedy_restarts, candidate_count)]
        finals: list[tuple[tuple[int, ...], float]] = []
        for start_index in ranked_starts:
            selected = [start_index]
            selected_value = singleton_values[start_index]
            while len(selected) < self.batch_size:
                remaining = tuple(
                    index for index in range(candidate_count) if index not in selected
                )
                proposed = tuple(tuple(selected + [index]) for index in remaining)
                values = score(proposed)
                best_position = min(
                    range(len(remaining)),
                    key=lambda position: (-values[position], remaining[position]),
                )
                selected.append(remaining[best_position])
                selected_value = values[best_position]
            finals.append((tuple(selected), float(selected_value)))
        selected_indices, selected_value = min(
            finals,
            key=lambda item: (-item[1], tuple(sorted(item[0])), item[0]),
        )
        top_singletons = sorted(
            (
                (index, float(singleton_values[index]))
                for index in range(candidate_count)
            ),
            key=lambda item: (-item[1], item[0]),
        )[:10]
        diagnostics = {
            "acquisition": "discrete-qnehvi",
            "selection_algorithm": "greedy-multistart-v1",
            "batch_size": self.batch_size,
            "greedy_restart_count": len(ranked_starts),
            "backend_call_count": call_count,
            "scored_batch_count": scored_batch_count,
            "selected_indices": list(selected_indices),
            "selected_log_acquisition_value": selected_value,
            "top_singletons": [
                {"candidate_index": index, "log_acquisition_value": value}
                for index, value in top_singletons
            ],
            "elapsed_sec": float(time.perf_counter() - started),
            "backend_elapsed_sec": backend_elapsed,
            "maximum_resident_tensor_bytes": maximum_resident,
            "maximum_cuda_allocated_bytes": maximum_cuda,
            "support": support,
            "backend": dict(last_backend),
        }
        return QNEHVISelection(selected_indices, selected_value, diagnostics)

    def _support_diagnostics(
        self, samples: JointObjectiveSamples
    ) -> dict[str, object]:
        source = dict(samples.source_diagnostics)
        support_kind = source.get("support_kind")
        nominal = source.get("unique_support")
        minimum = self.minimum_unique_support
        if support_kind != "finite":
            if minimum is not None:
                raise QNEHVIConfigurationError(
                    "minimum_unique_support applies only to explicitly finite support"
                )
            return {
                "support_kind": support_kind,
                "nominal_unique_support": None,
                "effective_unique_support": None,
                "minimum_unique_support": None,
                "low_support_policy": self.low_support_policy,
                "low_support": False,
            }
        if nominal is None:
            raise QNEHVIConfigurationError(
                "finite objective samples must report unique_support"
            )
        in_contract = np.all(np.isfinite(samples.cost_samples), axis=2) & np.all(
            (samples.cost_samples >= 0.0) & (samples.cost_samples <= 1.0),
            axis=2,
        )
        usable_draws = np.all(samples.valid_mask & in_contract, axis=1)
        sources = tuple(source.get("draw_sources") or samples.draw_ids)
        if len(sources) != len(samples.draw_ids):
            raise QNEHVIConfigurationError(
                "source draw_sources must align with objective sample draws"
            )
        effective = len(
            {sources[index] for index in np.flatnonzero(usable_draws)}
        )
        reported = source.get("effective_unique_support")
        if reported is not None:
            effective = min(effective, int(reported))
        return {
            "support_kind": "finite",
            "nominal_unique_support": int(nominal),
            "effective_unique_support": effective,
            "minimum_unique_support": minimum,
            "low_support_policy": self.low_support_policy,
            "low_support": minimum is not None and effective < minimum,
        }


def qnehvi(
    *,
    batch_size: int,
    greedy_restarts: int,
    reference_point: Sequence[float] | None = None,
    device: str = "cpu",
    minimum_unique_support: int | None = None,
    low_support_policy: str = "reject",
    pending_points=None,
    outcome_constraints=None,
) -> DiscreteQNEHVIAcquisition:
    """Build the qNEHVI-family selector; unsupported v1 contracts fail early."""

    if pending_points is not None:
        raise NotImplementedError(
            "qNEHVI v1 has no pending-state contract; generation evaluation is synchronous"
        )
    if outcome_constraints is not None:
        raise NotImplementedError(
            "qNEHVI v1 has no stochastic outcome-constraint rawData contract"
        )
    return DiscreteQNEHVIAcquisition(
        batch_size=batch_size,
        greedy_restarts=greedy_restarts,
        reference_point=(
            None
            if reference_point is None
            else tuple(float(value) for value in reference_point)
        ),
        device=device,
        minimum_unique_support=minimum_unique_support,
        low_support_policy=low_support_policy,
    )


__all__ = [
    "DiscreteQNEHVIAcquisition",
    "QNEHVIConfigurationError",
    "QNEHVIFallback",
    "QNEHVISelection",
    "QNEHVISupportRejected",
    "qnehvi",
]
