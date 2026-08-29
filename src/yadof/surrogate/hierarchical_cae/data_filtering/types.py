"""Mode-neutral data-filter types for the hierarchical CAE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from ....job_template.rawdata_template import StructuredRawDataSample


REGIME_SMOOTH = "smooth"
REGIME_CHATTER = "chatter"
REGIME_FAILURE = "failure"
REGIME_UNKNOWN = "unknown"
REGIMES = frozenset(
    {REGIME_SMOOTH, REGIME_CHATTER, REGIME_FAILURE, REGIME_UNKNOWN}
)


@dataclass(frozen=True, slots=True)
class DataFilterAssessment:
    field_weights: np.ndarray
    shared_weights: np.ndarray
    residual_targets: np.ndarray
    applicability_targets: np.ndarray
    design_regimes: tuple[str, ...]
    field_regimes: tuple[tuple[str, ...], ...]
    explicit_assessment_count: int
    diagnostic_assessment_count: int
    shape_fallback_count: int

    def diagnostics(self) -> dict[str, object]:
        design_counts = {
            regime: self.design_regimes.count(regime) for regime in sorted(REGIMES)
        }
        field_counts = {
            regime: sum(row.count(regime) for row in self.field_regimes)
            for regime in sorted(REGIMES)
        }
        return {
            "design_regime_counts": design_counts,
            "field_regime_counts": field_counts,
            "explicit_assessment_count": int(self.explicit_assessment_count),
            "diagnostic_assessment_count": int(self.diagnostic_assessment_count),
            "shape_fallback_count": int(self.shape_fallback_count),
            "mean_field_weight": float(np.mean(self.field_weights)),
            "mean_shared_weight": float(np.mean(self.shared_weights)),
            "mean_applicability_target": float(np.mean(self.applicability_targets)),
        }


def uniform_data_filter_assessment(
    samples: Sequence[StructuredRawDataSample],
) -> DataFilterAssessment:
    """Return the immutable ordinary-training view used by mode ``none``."""

    if not samples:
        raise ValueError("data filtering requires design rows")
    selectors = samples[0].field_selectors
    if any(sample.field_selectors != selectors for sample in samples):
        raise ValueError("data filtering requires a fixed field selector set")
    row_count = len(samples)
    field_count = len(selectors)
    return DataFilterAssessment(
        field_weights=np.ones((row_count, field_count), dtype=np.float32),
        shared_weights=np.ones((row_count, field_count), dtype=np.float32),
        residual_targets=np.zeros((row_count, field_count), dtype=np.float32),
        applicability_targets=np.ones((row_count,), dtype=np.float32),
        design_regimes=(REGIME_SMOOTH,) * row_count,
        field_regimes=((REGIME_SMOOTH,) * field_count,) * row_count,
        explicit_assessment_count=0,
        diagnostic_assessment_count=0,
        shape_fallback_count=0,
    )


@dataclass(frozen=True, slots=True)
class ApplicabilityPrediction:
    """Uncalibrated predictor-member applicability scores for one population."""

    population: tuple[tuple[float, ...], ...]
    mean_smooth_probability: tuple[float, ...]
    member_smooth_probabilities: tuple[tuple[float, ...], ...]
    policy_identity: Mapping[str, object]
    state_signature: str
    strategy_signature: str
    calibrated: bool = False
    limitations: tuple[str, ...] = (
        "uncalibrated predictor-ensemble regime score",
        "not independent Gaussian observation noise",
        "not an implicit optimization trust rule",
    )

    def __post_init__(self) -> None:
        population = tuple(tuple(float(value) for value in row) for row in self.population)
        means = tuple(float(value) for value in self.mean_smooth_probability)
        members = tuple(
            tuple(float(value) for value in row)
            for row in self.member_smooth_probabilities
        )
        if len(means) != len(population) or any(
            len(row) != len(population) for row in members
        ):
            raise ValueError("applicability prediction rows do not align")
        if any(not 0.0 <= value <= 1.0 for value in means) or any(
            not 0.0 <= value <= 1.0 for row in members for value in row
        ):
            raise ValueError("applicability probabilities must be in [0, 1]")
        object.__setattr__(self, "population", population)
        object.__setattr__(self, "mean_smooth_probability", means)
        object.__setattr__(self, "member_smooth_probabilities", members)
        object.__setattr__(self, "policy_identity", dict(self.policy_identity))
        object.__setattr__(self, "limitations", tuple(str(value) for value in self.limitations))


__all__ = [
    "ApplicabilityPrediction",
    "DataFilterAssessment",
    "REGIME_CHATTER",
    "REGIME_FAILURE",
    "REGIME_SMOOTH",
    "REGIME_UNKNOWN",
    "REGIMES",
    "uniform_data_filter_assessment",
]
