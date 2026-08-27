"""Experimental discrete qLogNEHVI backend boundary for Gate 2 validation.

This module is not a complete optimization strategy. It scores caller-supplied
candidate batches from already projected joint objective samples and keeps the
optional Torch/BoTorch import behind the function call.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from ..job_template.rawdata_projector import JointObjectiveSamples


@dataclass(frozen=True, slots=True)
class DiscreteQLogNEHVIResult:
    """Compact acquisition values with no retained posterior rawData."""

    batch_indices: tuple[tuple[int, ...], ...]
    log_acquisition_values: tuple[float, ...]
    diagnostics: Mapping[str, object]

    def __post_init__(self) -> None:
        batches = tuple(tuple(int(index) for index in batch) for batch in self.batch_indices)
        values = tuple(float(value) for value in self.log_acquisition_values)
        if len(batches) != len(values):
            raise ValueError("qLogNEHVI batches and values must align")
        object.__setattr__(self, "batch_indices", batches)
        object.__setattr__(self, "log_acquisition_values", values)
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))


def score_discrete_qlognehvi(
    *,
    baseline_population: Sequence[Sequence[float]],
    baseline_costs: Sequence[Sequence[float]],
    candidate_samples: JointObjectiveSamples,
    candidate_batches: Sequence[Sequence[int]],
    reference_point: Sequence[float] | None = None,
    seed: int = 0,
    device: str = "cpu",
    minimum_unique_support: int | None = None,
    low_support_policy: str = "reject",
) -> DiscreteQLogNEHVIResult:
    """Score fixed discrete batches with BoTorch's qLogNEHVI implementation.

    Invalid candidate projections reject their complete MC draw. Finite task cost
    ``1.0`` remains valid. ``minimum_unique_support`` is applied only to a source
    explicitly reporting finite support, with either visible warning or rejection.
    """

    if not isinstance(candidate_samples, JointObjectiveSamples):
        raise TypeError("candidate_samples must be JointObjectiveSamples")
    try:
        from ._qlognehvi_backend import score_discrete_qlognehvi as implementation
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] in {
            "botorch",
            "gpytorch",
            "linear_operator",
            "torch",
        }:
            raise RuntimeError(
                "qLogNEHVI requires the optional yadof qnehvi extra "
                "(install yadof[qnehvi])"
            ) from exc
        raise
    payload = implementation(
        baseline_population=baseline_population,
        baseline_costs=baseline_costs,
        candidate_samples=candidate_samples,
        candidate_batches=candidate_batches,
        reference_point=reference_point,
        seed=seed,
        device=device,
        minimum_unique_support=minimum_unique_support,
        low_support_policy=low_support_policy,
    )
    return DiscreteQLogNEHVIResult(**payload)


__all__ = ["DiscreteQLogNEHVIResult", "score_discrete_qlognehvi"]
