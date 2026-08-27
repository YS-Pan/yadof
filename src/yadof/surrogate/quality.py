"""Typed, declarative rawData quality/regime assessment capability."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Mapping, Sequence

import numpy as np

from ..job_template.rawdata_template import (
    RawDataFieldSelector,
    StructuredRawDataSample,
)


RAWDATA_QUALITY_ASSESSMENT_PROTOCOL = "yadof.rawdata-quality-assessment"
RAWDATA_QUALITY_ASSESSMENT_VERSION = 1
RAWDATA_QUALITY_POLICY_PROTOCOL = "yadof.rawdata-quality-policy"
RAWDATA_QUALITY_POLICY_VERSION = 1
REGIME_SMOOTH = "smooth"
REGIME_CHATTER = "chatter"
REGIME_FAILURE = "failure"
REGIME_UNKNOWN = "unknown"
_REGIMES = frozenset(
    {REGIME_SMOOTH, REGIME_CHATTER, REGIME_FAILURE, REGIME_UNKNOWN}
)


def _selector(value: object) -> RawDataFieldSelector:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError("quality selector must be ('.npz filename', 'values|data')")
    selector = (str(value[0]), str(value[1]))
    if (
        not selector[0].lower().endswith(".npz")
        or "/" in selector[0]
        or "\\" in selector[0]
        or selector[1] not in {"values", "data"}
    ):
        raise ValueError("quality selector must use a direct NPZ basename and main key")
    return selector


def selector_key(selector: RawDataFieldSelector) -> str:
    normalized = _selector(selector)
    return f"{normalized[0]}::{normalized[1]}"


@dataclass(frozen=True, slots=True)
class ShapeQualityRule:
    """Task-owned declarative fallback when explicit diagnostics are unavailable."""

    selector: RawDataFieldSelector
    second_difference_rms_max: float | None = None
    high_frequency_energy_ratio_max: float | None = None
    derivative_reversal_fraction_max: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "selector", _selector(self.selector))
        names = (
            "second_difference_rms_max",
            "high_frequency_energy_ratio_max",
            "derivative_reversal_fraction_max",
        )
        if all(getattr(self, name) is None for name in names):
            raise ValueError("a shape-quality rule must declare at least one threshold")
        for name in names:
            raw = getattr(self, name)
            if raw is None:
                continue
            value = float(raw)
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)

    def as_dict(self) -> dict[str, object]:
        return {
            "selector": list(self.selector),
            "second_difference_rms_max": self.second_difference_rms_max,
            "high_frequency_energy_ratio_max": self.high_frequency_energy_ratio_max,
            "derivative_reversal_fraction_max": self.derivative_reversal_fraction_max,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticCondition:
    """One JSON-safe comparison against task-owned record diagnostics."""

    path: tuple[str, ...]
    operator: str
    value: object = None

    def __post_init__(self) -> None:
        path = tuple(str(part) for part in self.path)
        if not path or any(not part for part in path):
            raise ValueError("diagnostic condition path must contain non-empty keys")
        operator = str(self.operator).strip().lower()
        if operator not in {
            "equals",
            "not-equals",
            "greater-than",
            "greater-or-equal",
            "less-than",
            "less-or-equal",
            "truthy",
            "falsy",
        }:
            raise ValueError(f"unsupported diagnostic condition operator {operator!r}")
        if operator in {"truthy", "falsy"} and self.value is not None:
            raise ValueError(f"{operator} diagnostic conditions do not accept a value")
        try:
            json.dumps(self.value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("diagnostic condition value must be JSON-safe") from exc
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "operator", operator)

    def as_dict(self) -> dict[str, object]:
        return {
            "path": list(self.path),
            "operator": self.operator,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticRegimeRule:
    """Ordered declarative rule evaluated inside task diagnostic metadata."""

    regime: str
    conditions: tuple[DiagnosticCondition, ...]
    match: str = "all"

    def __post_init__(self) -> None:
        conditions = tuple(self.conditions)
        if not conditions:
            raise ValueError("a diagnostic regime rule requires conditions")
        match = str(self.match).strip().lower()
        if match not in {"all", "any"}:
            raise ValueError("diagnostic regime rule match must be all or any")
        object.__setattr__(self, "regime", _regime(self.regime))
        object.__setattr__(self, "conditions", conditions)
        object.__setattr__(self, "match", match)

    def as_dict(self) -> dict[str, object]:
        return {
            "regime": self.regime,
            "match": self.match,
            "conditions": [condition.as_dict() for condition in self.conditions],
        }


@dataclass(frozen=True, slots=True)
class RawDataQualityPolicy:
    """Versioned, JSON-identity-safe policy; no executable callback is accepted."""

    policy_id: str
    policy_version: int
    assessment_path: tuple[str, ...] = (
        "task_diagnostics",
        "yadof_rawdata_quality_assessment",
    )
    diagnostic_path: tuple[str, ...] = ("task_diagnostics",)
    diagnostic_rules: tuple[DiagnosticRegimeRule, ...] = ()
    diagnostic_field_selectors: tuple[RawDataFieldSelector, ...] = ()
    diagnostic_default_regime: str = REGIME_SMOOTH
    shape_fallback_rules: tuple[ShapeQualityRule, ...] = ()
    missing_assessment: str = "uniform"
    smooth_field_weight: float = 1.0
    chatter_field_weight: float = 0.25
    failure_field_weight: float = 0.20
    unknown_field_weight: float = 1.0
    smooth_shared_weight: float = 1.0
    chatter_shared_weight: float = 0.0
    failure_shared_weight: float = 0.0
    unknown_shared_weight: float = 1.0

    def __post_init__(self) -> None:
        if not str(self.policy_id).strip():
            raise ValueError("quality policy_id must not be empty")
        if int(self.policy_version) <= 0:
            raise ValueError("quality policy_version must be positive")
        path = tuple(str(value) for value in self.assessment_path)
        if not path or any(not value for value in path):
            raise ValueError("quality assessment_path must contain non-empty keys")
        diagnostic_path = tuple(str(value) for value in self.diagnostic_path)
        if not diagnostic_path or any(not value for value in diagnostic_path):
            raise ValueError("quality diagnostic_path must contain non-empty keys")
        diagnostic_rules = tuple(self.diagnostic_rules)
        diagnostic_selectors = tuple(
            _selector(selector) for selector in self.diagnostic_field_selectors
        )
        if len(diagnostic_selectors) != len(set(diagnostic_selectors)):
            raise ValueError("diagnostic field selectors must be unique")
        diagnostic_default = _regime(self.diagnostic_default_regime)
        missing = str(self.missing_assessment).strip().lower()
        if missing not in {"uniform", "shape-fallback", "error"}:
            raise ValueError(
                "missing_assessment must be uniform, shape-fallback, or error"
            )
        rules = tuple(self.shape_fallback_rules)
        selectors = tuple(rule.selector for rule in rules)
        if len(selectors) != len(set(selectors)):
            raise ValueError("shape fallback rules must use unique selectors")
        if missing == "shape-fallback" and not rules:
            raise ValueError("shape-fallback behavior requires shape rules")
        for name in (
            "smooth_field_weight",
            "chatter_field_weight",
            "failure_field_weight",
            "unknown_field_weight",
            "smooth_shared_weight",
            "chatter_shared_weight",
            "failure_shared_weight",
            "unknown_shared_weight",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and in [0, 1]")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "policy_id", str(self.policy_id).strip())
        object.__setattr__(self, "policy_version", int(self.policy_version))
        object.__setattr__(self, "assessment_path", path)
        object.__setattr__(self, "diagnostic_path", diagnostic_path)
        object.__setattr__(self, "diagnostic_rules", diagnostic_rules)
        object.__setattr__(
            self, "diagnostic_field_selectors", diagnostic_selectors
        )
        object.__setattr__(self, "diagnostic_default_regime", diagnostic_default)
        object.__setattr__(self, "shape_fallback_rules", rules)
        object.__setattr__(self, "missing_assessment", missing)

    def field_weight(self, regime: str) -> float:
        return {
            REGIME_SMOOTH: self.smooth_field_weight,
            REGIME_CHATTER: self.chatter_field_weight,
            REGIME_FAILURE: self.failure_field_weight,
            REGIME_UNKNOWN: self.unknown_field_weight,
        }[_regime(regime)]

    def shared_weight(self, regime: str) -> float:
        return {
            REGIME_SMOOTH: self.smooth_shared_weight,
            REGIME_CHATTER: self.chatter_shared_weight,
            REGIME_FAILURE: self.failure_shared_weight,
            REGIME_UNKNOWN: self.unknown_shared_weight,
        }[_regime(regime)]

    def as_dict(self) -> dict[str, object]:
        return {
            "protocol": RAWDATA_QUALITY_POLICY_PROTOCOL,
            "protocol_version": RAWDATA_QUALITY_POLICY_VERSION,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "assessment_path": list(self.assessment_path),
            "diagnostic_path": list(self.diagnostic_path),
            "diagnostic_rules": [rule.as_dict() for rule in self.diagnostic_rules],
            "diagnostic_field_selectors": [
                list(selector) for selector in self.diagnostic_field_selectors
            ],
            "diagnostic_default_regime": self.diagnostic_default_regime,
            "shape_fallback_rules": [rule.as_dict() for rule in self.shape_fallback_rules],
            "missing_assessment": self.missing_assessment,
            "regime_weights": {
                REGIME_SMOOTH: {
                    "field": self.smooth_field_weight,
                    "shared": self.smooth_shared_weight,
                },
                REGIME_CHATTER: {
                    "field": self.chatter_field_weight,
                    "shared": self.chatter_shared_weight,
                },
                REGIME_FAILURE: {
                    "field": self.failure_field_weight,
                    "shared": self.failure_shared_weight,
                },
                REGIME_UNKNOWN: {
                    "field": self.unknown_field_weight,
                    "shared": self.unknown_shared_weight,
                },
            },
            "residual_target_semantics": {
                REGIME_SMOOTH: 0.0,
                REGIME_CHATTER: 1.0,
                REGIME_FAILURE: 1.0,
                REGIME_UNKNOWN: 0.0,
            },
            "applicability_target_semantics": {
                REGIME_SMOOTH: 1.0,
                REGIME_CHATTER: 0.0,
                REGIME_FAILURE: 0.0,
                REGIME_UNKNOWN: 1.0,
            },
        }


@dataclass(frozen=True, slots=True)
class QualityAssessmentBatch:
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
            regime: self.design_regimes.count(regime) for regime in sorted(_REGIMES)
        }
        field_counts = {
            regime: sum(row.count(regime) for row in self.field_regimes)
            for regime in sorted(_REGIMES)
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


def _regime(value: object) -> str:
    regime = str(value).strip().lower()
    if regime not in _REGIMES:
        raise ValueError(
            f"quality regime must be one of {tuple(sorted(_REGIMES))!r}, got {value!r}"
        )
    return regime


def _mapping_at_path(
    metadata: Mapping[str, object], path: Sequence[str]
) -> Mapping[str, object] | None:
    current: object = metadata
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current if isinstance(current, Mapping) else None


def _value_at_path(root: object, path: Sequence[str]) -> tuple[bool, object]:
    current = root
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _condition_matches(
    diagnostics: Mapping[str, object], condition: DiagnosticCondition
) -> bool:
    present, actual = _value_at_path(diagnostics, condition.path)
    if not present:
        return False
    operator = condition.operator
    if operator == "truthy":
        return bool(actual)
    if operator == "falsy":
        return not bool(actual)
    if operator == "equals":
        return actual == condition.value
    if operator == "not-equals":
        return actual != condition.value
    try:
        actual_number = float(actual)
        expected_number = float(condition.value)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(actual_number) or not np.isfinite(expected_number):
        return False
    return {
        "greater-than": actual_number > expected_number,
        "greater-or-equal": actual_number >= expected_number,
        "less-than": actual_number < expected_number,
        "less-or-equal": actual_number <= expected_number,
    }[operator]


def _diagnostic_assessment(
    diagnostics: Mapping[str, object],
    policy: RawDataQualityPolicy,
    selectors: Sequence[RawDataFieldSelector],
) -> tuple[str, tuple[str, ...]]:
    design = policy.diagnostic_default_regime
    for rule in policy.diagnostic_rules:
        matches = tuple(
            _condition_matches(diagnostics, condition)
            for condition in rule.conditions
        )
        if (rule.match == "all" and all(matches)) or (
            rule.match == "any" and any(matches)
        ):
            design = rule.regime
            break
    scoped = set(policy.diagnostic_field_selectors)
    if scoped.difference(selectors):
        unknown = tuple(sorted(scoped.difference(selectors)))
        raise ValueError(
            f"diagnostic policy references unknown rawData fields: {unknown!r}"
        )
    fields = tuple(
        design if not scoped or selector in scoped else REGIME_SMOOTH
        for selector in selectors
    )
    return design, fields


def _validate_explicit_assessment(
    payload: Mapping[str, object],
    policy: RawDataQualityPolicy,
    selectors: Sequence[RawDataFieldSelector],
) -> tuple[str, tuple[str, ...]]:
    if payload.get("protocol") != RAWDATA_QUALITY_ASSESSMENT_PROTOCOL:
        raise ValueError("task quality assessment has an unsupported protocol")
    if int(payload.get("protocol_version", -1)) != RAWDATA_QUALITY_ASSESSMENT_VERSION:
        raise ValueError("task quality assessment has an unsupported protocol version")
    if str(payload.get("policy_id", "")) != policy.policy_id or int(
        payload.get("policy_version", -1)
    ) != policy.policy_version:
        raise ValueError("task quality assessment does not match the selected policy")
    design = _regime(payload.get("design_regime", REGIME_UNKNOWN))
    raw_fields = payload.get("fields", {})
    if not isinstance(raw_fields, Mapping):
        raise ValueError("task quality assessment fields must be an object")
    expected = {selector_key(selector) for selector in selectors}
    extra = set(str(key) for key in raw_fields).difference(expected)
    if extra:
        raise ValueError(
            f"task quality assessment references unknown fields: {tuple(sorted(extra))!r}"
        )
    fields = []
    for selector in selectors:
        raw = raw_fields.get(selector_key(selector), design)
        if isinstance(raw, Mapping):
            raw = raw.get("regime", design)
        fields.append(_regime(raw))
    return design, tuple(fields)


def _shape_features(values: np.ndarray) -> dict[str, float]:
    vector = np.asarray(values, dtype=np.float64).reshape(-1)
    if vector.size < 4 or not np.all(np.isfinite(vector)):
        return {
            "second_difference_rms": 0.0,
            "high_frequency_energy_ratio": 0.0,
            "derivative_reversal_fraction": 0.0,
        }
    centered = vector - np.median(vector)
    robust = float(np.quantile(centered, 0.95) - np.quantile(centered, 0.05))
    scale = max(abs(robust), float(np.std(centered)), 1.0e-12)
    differences = np.diff(centered)
    second = np.diff(centered, n=2)
    spectrum = np.fft.rfft(centered)
    power = np.square(np.abs(spectrum))
    cutoff = max(1, int(math.ceil(power.size * 0.75)))
    total = float(np.sum(power[1:]))
    reversals = np.count_nonzero(differences[1:] * differences[:-1] < 0)
    return {
        "second_difference_rms": float(np.sqrt(np.mean(np.square(second))) / scale),
        "high_frequency_energy_ratio": (
            float(np.sum(power[cutoff:]) / total) if total > 0 else 0.0
        ),
        "derivative_reversal_fraction": float(
            reversals / max(1, differences.size - 1)
        ),
    }


def _shape_fallback(
    sample: StructuredRawDataSample,
    policy: RawDataQualityPolicy,
    selectors: Sequence[RawDataFieldSelector],
) -> tuple[str, tuple[str, ...]]:
    rules = {rule.selector: rule for rule in policy.shape_fallback_rules}
    field_regimes = []
    for field, item in zip(sample.items, selectors):
        rule = rules.get(item)
        if rule is None:
            field_regimes.append(REGIME_SMOOTH)
            continue
        sample_item = next(entry for entry in sample.items if entry.filename == item[0])
        features = _shape_features(np.asarray(sample_item.payload[item[1]]))
        exceeded = (
            rule.second_difference_rms_max is not None
            and features["second_difference_rms"] > rule.second_difference_rms_max
        ) or (
            rule.high_frequency_energy_ratio_max is not None
            and features["high_frequency_energy_ratio"]
            > rule.high_frequency_energy_ratio_max
        ) or (
            rule.derivative_reversal_fraction_max is not None
            and features["derivative_reversal_fraction"]
            > rule.derivative_reversal_fraction_max
        )
        field_regimes.append(REGIME_CHATTER if exceeded else REGIME_SMOOTH)
    design = (
        REGIME_CHATTER
        if any(value == REGIME_CHATTER for value in field_regimes)
        else REGIME_SMOOTH
    )
    return design, tuple(field_regimes)


def assess_quality(
    *,
    policy: RawDataQualityPolicy | None,
    samples: Sequence[StructuredRawDataSample],
    record_metadata: Sequence[Mapping[str, object]] = (),
) -> QualityAssessmentBatch:
    if not samples:
        raise ValueError("quality assessment requires design rows")
    selectors = samples[0].field_selectors
    if any(sample.field_selectors != selectors for sample in samples):
        raise ValueError("quality assessment requires a fixed field selector set")
    if record_metadata and len(record_metadata) != len(samples):
        raise ValueError("quality record metadata must align with design rows")
    if policy is None:
        row_count = len(samples)
        field_count = len(selectors)
        return QualityAssessmentBatch(
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

    metadata_rows = (
        tuple(record_metadata)
        if record_metadata
        else tuple({} for _sample in samples)
    )
    design_regimes = []
    field_regimes = []
    explicit_count = 0
    diagnostic_count = 0
    shape_count = 0
    for row_index, (sample, metadata) in enumerate(zip(samples, metadata_rows)):
        explicit = _mapping_at_path(metadata, policy.assessment_path)
        if explicit is not None:
            design, fields = _validate_explicit_assessment(
                explicit, policy, selectors
            )
            explicit_count += 1
        elif policy.diagnostic_rules and (
            diagnostics := _mapping_at_path(metadata, policy.diagnostic_path)
        ) is not None:
            design, fields = _diagnostic_assessment(
                diagnostics, policy, selectors
            )
            diagnostic_count += 1
        elif policy.missing_assessment == "shape-fallback":
            design, fields = _shape_fallback(sample, policy, selectors)
            shape_count += 1
        elif policy.missing_assessment == "uniform":
            design = REGIME_UNKNOWN
            fields = (REGIME_UNKNOWN,) * len(selectors)
        else:
            raise ValueError(
                f"design row {row_index} has no task-owned quality assessment"
            )
        design_regimes.append(design)
        field_regimes.append(fields)

    field_weights = np.asarray(
        [
            [policy.field_weight(regime) for regime in fields]
            for fields in field_regimes
        ],
        dtype=np.float32,
    )
    shared_weights = np.asarray(
        [
            [policy.shared_weight(regime) for regime in fields]
            for fields in field_regimes
        ],
        dtype=np.float32,
    )
    residual_targets = np.asarray(
        [
            [
                1.0 if regime in {REGIME_CHATTER, REGIME_FAILURE} else 0.0
                for regime in fields
            ]
            for fields in field_regimes
        ],
        dtype=np.float32,
    )
    applicability = np.asarray(
        [1.0 if regime in {REGIME_SMOOTH, REGIME_UNKNOWN} else 0.0 for regime in design_regimes],
        dtype=np.float32,
    )
    return QualityAssessmentBatch(
        field_weights=field_weights,
        shared_weights=shared_weights,
        residual_targets=residual_targets,
        applicability_targets=applicability,
        design_regimes=tuple(design_regimes),
        field_regimes=tuple(field_regimes),
        explicit_assessment_count=explicit_count,
        diagnostic_assessment_count=diagnostic_count,
        shape_fallback_count=shape_count,
    )


def quality_policy_from_mapping(
    value: Mapping[str, object] | RawDataQualityPolicy | None,
) -> RawDataQualityPolicy | None:
    if value is None or isinstance(value, RawDataQualityPolicy):
        return value
    payload = json.loads(json.dumps(dict(value), allow_nan=False))
    payload.pop("protocol", None)
    payload.pop("protocol_version", None)
    regime_weights = payload.pop("regime_weights", None)
    payload.pop("residual_target_semantics", None)
    payload.pop("applicability_target_semantics", None)
    if regime_weights is not None:
        for regime in _REGIMES:
            values = regime_weights.get(regime, {})
            if values:
                payload[f"{regime}_field_weight"] = values["field"]
                payload[f"{regime}_shared_weight"] = values["shared"]
    diagnostic_rules = tuple(
        DiagnosticRegimeRule(
            regime=rule["regime"],
            match=rule.get("match", "all"),
            conditions=tuple(
                DiagnosticCondition(
                    path=tuple(condition["path"]),
                    operator=condition["operator"],
                    value=condition.get("value"),
                )
                for condition in rule["conditions"]
            ),
        )
        for rule in payload.pop("diagnostic_rules", ())
    )
    rules = tuple(
        ShapeQualityRule(
            selector=_selector(rule["selector"]),
            second_difference_rms_max=rule.get("second_difference_rms_max"),
            high_frequency_energy_ratio_max=rule.get(
                "high_frequency_energy_ratio_max"
            ),
            derivative_reversal_fraction_max=rule.get(
                "derivative_reversal_fraction_max"
            ),
        )
        for rule in payload.pop("shape_fallback_rules", ())
    )
    return RawDataQualityPolicy(
        diagnostic_rules=diagnostic_rules,
        shape_fallback_rules=rules,
        **payload,
    )


__all__ = [
    "ApplicabilityPrediction",
    "DiagnosticCondition",
    "DiagnosticRegimeRule",
    "QualityAssessmentBatch",
    "RAWDATA_QUALITY_ASSESSMENT_PROTOCOL",
    "RAWDATA_QUALITY_ASSESSMENT_VERSION",
    "RAWDATA_QUALITY_POLICY_PROTOCOL",
    "RAWDATA_QUALITY_POLICY_VERSION",
    "REGIME_CHATTER",
    "REGIME_FAILURE",
    "REGIME_SMOOTH",
    "REGIME_UNKNOWN",
    "RawDataQualityPolicy",
    "ShapeQualityRule",
    "assess_quality",
    "quality_policy_from_mapping",
    "selector_key",
]
