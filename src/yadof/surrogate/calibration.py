"""Signature-bound calibration for joint rawData posterior function draws.

The calibration layer is deliberately backend neutral.  It scales complete
function draws around their empirical ensemble mean and applies one monotone
mapping to every applicability member.  It never invents per-candidate noise,
changes draw identity, or silently reuses parameters from another checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Mapping, Sequence

import numpy as np

from ..job_template.rawdata_template import (
    RawDataFieldSelector,
    RawDataSchemaTemplate,
    StructuredRawDataSample,
)
from .posterior import (
    MaterializedRawDataPosterior,
    RawDataFunctionDraw,
    RawDataPosteriorDiagnostics,
    RawDataPosteriorSampler,
    SUPPORT_FINITE,
)
from .quality import ApplicabilityPrediction


POSTERIOR_CALIBRATION_PROTOCOL = "yadof.posterior-calibration-artifact"
POSTERIOR_CALIBRATION_PROTOCOL_VERSION = 1
FIELD_SPREAD_METHOD = "conservative-central-interval-grid-scale-v1"
APPLICABILITY_METHOD = "monotone-member-logit-affine-v1"
CALIBRATED = "calibrated"
UNCALIBRATED = "uncalibrated"
NOT_APPLICABLE = "not-applicable"
EXPERIMENTAL_PERFORMANCE_STATUS = "experimental-performance-not-accepted"
_CALIBRATION_STATUSES = frozenset({CALIBRATED, UNCALIBRATED})
_APPLICABILITY_STATUSES = frozenset(
    {CALIBRATED, UNCALIBRATED, NOT_APPLICABLE}
)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("calibration values must be finite and JSON-safe") from exc


def calibration_identity_signature(value: object) -> str:
    """Return the canonical SHA-256 identity used by calibration bindings."""

    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_sha256(value: object, name: str) -> str:
    text = str(value).lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{name} must be a lowercase SHA-256 value")
    return text


def _selector(value: Sequence[object]) -> RawDataFieldSelector:
    if len(value) != 2:
        raise ValueError("a calibrated rawData field selector must have two items")
    filename, key = (str(item) for item in value)
    if (
        not filename
        or not filename.lower().endswith(".npz")
        or "/" in filename
        or "\\" in filename
        or key not in {"values", "data"}
    ):
        raise ValueError("invalid calibrated rawData field selector")
    return filename, key


def _finite_float(value: object, name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted


@dataclass(frozen=True, slots=True)
class FieldSpreadCalibration:
    """One conservative multiplier for one exact rawData field."""

    selector: RawDataFieldSelector
    scale: float
    fit_design_count: int
    candidate_scales: tuple[float, ...]
    target_coverages: tuple[float, ...]
    method: str = FIELD_SPREAD_METHOD
    selection_rule: str = (
        "minimize-design-macro-undercoverage-plus-absolute-error-and-energy-v1"
    )

    def __post_init__(self) -> None:
        selector = _selector(self.selector)
        scale = _finite_float(self.scale, "field spread scale")
        if scale < 1.0:
            raise ValueError("posterior spread calibration may not shrink a field")
        count = int(self.fit_design_count)
        if count <= 0:
            raise ValueError("field spread calibration needs calibration designs")
        candidates = tuple(
            _finite_float(value, "candidate field spread scale")
            for value in self.candidate_scales
        )
        if (
            not candidates
            or tuple(sorted(set(candidates))) != candidates
            or candidates[0] < 1.0
            or scale not in candidates
        ):
            raise ValueError(
                "candidate field scales must be unique, sorted, conservative, "
                "and include the selected scale"
            )
        coverages = tuple(
            _finite_float(value, "target coverage")
            for value in self.target_coverages
        )
        if (
            not coverages
            or tuple(sorted(set(coverages))) != coverages
            or any(not 0.0 < value < 1.0 for value in coverages)
        ):
            raise ValueError("target coverages must be unique values in (0, 1)")
        if str(self.method) != FIELD_SPREAD_METHOD:
            raise ValueError("unsupported field spread calibration method")
        if not str(self.selection_rule):
            raise ValueError("field spread selection rule must not be empty")
        object.__setattr__(self, "selector", selector)
        object.__setattr__(self, "scale", scale)
        object.__setattr__(self, "fit_design_count", count)
        object.__setattr__(self, "candidate_scales", candidates)
        object.__setattr__(self, "target_coverages", coverages)
        object.__setattr__(self, "method", str(self.method))
        object.__setattr__(self, "selection_rule", str(self.selection_rule))

    def as_dict(self) -> dict[str, object]:
        return {
            "selector": list(self.selector),
            "scale": self.scale,
            "fit_design_count": self.fit_design_count,
            "candidate_scales": list(self.candidate_scales),
            "target_coverages": list(self.target_coverages),
            "method": self.method,
            "selection_rule": self.selection_rule,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "FieldSpreadCalibration":
        return cls(
            selector=_selector(tuple(value["selector"])),
            scale=float(value["scale"]),
            fit_design_count=int(value["fit_design_count"]),
            candidate_scales=tuple(float(item) for item in value["candidate_scales"]),
            target_coverages=tuple(
                float(item) for item in value["target_coverages"]
            ),
            method=str(value["method"]),
            selection_rule=str(value["selection_rule"]),
        )


@dataclass(frozen=True, slots=True)
class ApplicabilityCalibration:
    """One monotone mapping shared by all persistent predictor members."""

    status: str
    policy_signature: str
    fit_design_count: int
    positive_count: int
    negative_count: int
    minimum_class_count: int
    slope: float | None = None
    intercept: float | None = None
    failure_reason: str | None = None
    method: str = APPLICABILITY_METHOD
    fit_input: str = "flattened-predictor-member-probability-logit-by-design"

    def __post_init__(self) -> None:
        status = str(self.status)
        if status not in _APPLICABILITY_STATUSES:
            raise ValueError("unsupported applicability calibration status")
        policy_signature = _require_sha256(
            self.policy_signature, "applicability policy signature"
        )
        counts = (
            int(self.fit_design_count),
            int(self.positive_count),
            int(self.negative_count),
            int(self.minimum_class_count),
        )
        if any(value < 0 for value in counts) or counts[3] <= 0:
            raise ValueError("applicability calibration counts are invalid")
        if counts[1] + counts[2] != counts[0]:
            raise ValueError("applicability class counts must equal fit designs")
        if str(self.method) != APPLICABILITY_METHOD:
            raise ValueError("unsupported applicability calibration method")
        if status == CALIBRATED:
            if self.slope is None or self.intercept is None:
                raise ValueError("calibrated applicability requires slope/intercept")
            slope = _finite_float(self.slope, "applicability slope")
            intercept = _finite_float(self.intercept, "applicability intercept")
            if slope <= 0.0:
                raise ValueError("applicability mapping must be strictly monotone")
            if counts[1] < counts[3] or counts[2] < counts[3]:
                raise ValueError("calibrated applicability lacks both class counts")
            if self.failure_reason is not None:
                raise ValueError("calibrated applicability cannot have a failure reason")
        else:
            if self.slope is not None or self.intercept is not None:
                raise ValueError(
                    "uncalibrated/not-applicable applicability cannot carry parameters"
                )
            slope = intercept = None
            if not str(self.failure_reason or ""):
                raise ValueError(
                    "uncalibrated/not-applicable applicability needs a reason"
                )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "policy_signature", policy_signature)
        object.__setattr__(self, "fit_design_count", counts[0])
        object.__setattr__(self, "positive_count", counts[1])
        object.__setattr__(self, "negative_count", counts[2])
        object.__setattr__(self, "minimum_class_count", counts[3])
        object.__setattr__(self, "slope", slope)
        object.__setattr__(self, "intercept", intercept)
        object.__setattr__(
            self,
            "failure_reason",
            None if self.failure_reason is None else str(self.failure_reason),
        )
        object.__setattr__(self, "method", str(self.method))
        object.__setattr__(self, "fit_input", str(self.fit_input))

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "policy_signature": self.policy_signature,
            "fit_design_count": self.fit_design_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "minimum_class_count": self.minimum_class_count,
            "slope": self.slope,
            "intercept": self.intercept,
            "failure_reason": self.failure_reason,
            "method": self.method,
            "fit_input": self.fit_input,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ApplicabilityCalibration":
        return cls(
            status=str(value["status"]),
            policy_signature=str(value["policy_signature"]),
            fit_design_count=int(value["fit_design_count"]),
            positive_count=int(value["positive_count"]),
            negative_count=int(value["negative_count"]),
            minimum_class_count=int(value["minimum_class_count"]),
            slope=(None if value.get("slope") is None else float(value["slope"])),
            intercept=(
                None if value.get("intercept") is None else float(value["intercept"])
            ),
            failure_reason=(
                None
                if value.get("failure_reason") is None
                else str(value["failure_reason"])
            ),
            method=str(value["method"]),
            fit_input=str(value["fit_input"]),
        )


@dataclass(frozen=True, slots=True)
class PosteriorCalibrationArtifact:
    """Immutable exact-checkpoint calibration parameters and evidence identity."""

    artifact_id: str
    rawdata_status: str
    state_signature: str
    strategy_signature: str
    schema_signature: str
    posterior_kind: str
    support_kind: str
    unique_support: int
    checkpoint_hashes: Mapping[str, str]
    training_provenance_sha256: str
    dataset_manifest_sha256: str
    calibration_locator_sha256: str
    calibration_design_ids_sha256: str
    calibration_design_count: int
    fold_count: int
    seed: int
    field_calibrations: tuple[FieldSpreadCalibration, ...]
    applicability: ApplicabilityCalibration
    policy_identity: Mapping[str, object]
    label_head_loss_identity: Mapping[str, object]
    evidence: Mapping[str, object]
    failure_reasons: tuple[str, ...] = ()
    performance_status: str = EXPERIMENTAL_PERFORMANCE_STATUS
    observation_noise_included: bool = False
    transferable: bool = False

    def __post_init__(self) -> None:
        artifact_id = str(self.artifact_id)
        if not artifact_id or any(char not in "-_.abcdefghijklmnopqrstuvwxyz0123456789" for char in artifact_id):
            raise ValueError("calibration artifact_id must be a lowercase safe name")
        status = str(self.rawdata_status)
        if status not in _CALIBRATION_STATUSES:
            raise ValueError("unsupported rawData calibration status")
        state = _require_sha256(self.state_signature, "state signature")
        strategy = _require_sha256(self.strategy_signature, "strategy signature")
        schema = _require_sha256(self.schema_signature, "schema signature")
        if str(self.support_kind) != SUPPORT_FINITE:
            raise ValueError("v1 calibration only supports honest finite support")
        support = int(self.unique_support)
        if support <= 1:
            raise ValueError("calibration requires at least two unique function draws")
        hashes = {str(key): _require_sha256(value, str(key)) for key, value in self.checkpoint_hashes.items()}
        if not hashes or any(not key for key in hashes):
            raise ValueError("calibration must bind checkpoint artifact hashes")
        selectors = tuple(item.selector for item in self.field_calibrations)
        if selectors != tuple(sorted(selectors, key=lambda item: (item[0].casefold(), item[0], item[1]))) or len(selectors) != len(set(selectors)):
            raise ValueError("field calibrations must use unique canonical selector order")
        if not selectors:
            raise ValueError("calibration artifact must describe every rawData field")
        if status == CALIBRATED and self.failure_reasons:
            raise ValueError("calibrated rawData cannot carry failure reasons")
        if status == UNCALIBRATED and not self.failure_reasons:
            raise ValueError("uncalibrated rawData requires explicit failure reasons")
        if status == UNCALIBRATED and any(item.scale != 1.0 for item in self.field_calibrations):
            raise ValueError("uncalibrated artifacts must retain identity field scales")
        policy = json.loads(_canonical_json(dict(self.policy_identity)).decode("ascii"))
        identity = json.loads(
            _canonical_json(dict(self.label_head_loss_identity)).decode("ascii")
        )
        evidence = json.loads(_canonical_json(dict(self.evidence)).decode("ascii"))
        expected_policy = calibration_identity_signature(policy)
        if self.applicability.policy_signature != expected_policy:
            raise ValueError("applicability calibration policy identity drifted")
        if str(self.performance_status) != EXPERIMENTAL_PERFORMANCE_STATUS:
            raise ValueError("v1 calibration artifact cannot claim performance acceptance")
        if bool(self.observation_noise_included):
            raise ValueError("v1 deterministic calibration cannot include observation noise")
        if bool(self.transferable):
            raise ValueError("calibration is exact-state-bound and non-transferable")
        count = int(self.calibration_design_count)
        folds = int(self.fold_count)
        if count <= 0 or folds < 2 or folds > count:
            raise ValueError("calibration design/fold counts are invalid")
        object.__setattr__(self, "artifact_id", artifact_id)
        object.__setattr__(self, "rawdata_status", status)
        object.__setattr__(self, "state_signature", state)
        object.__setattr__(self, "strategy_signature", strategy)
        object.__setattr__(self, "schema_signature", schema)
        object.__setattr__(self, "posterior_kind", str(self.posterior_kind))
        object.__setattr__(self, "support_kind", str(self.support_kind))
        object.__setattr__(self, "unique_support", support)
        object.__setattr__(self, "checkpoint_hashes", hashes)
        for name in (
            "training_provenance_sha256",
            "dataset_manifest_sha256",
            "calibration_locator_sha256",
            "calibration_design_ids_sha256",
        ):
            object.__setattr__(self, name, _require_sha256(getattr(self, name), name))
        object.__setattr__(self, "calibration_design_count", count)
        object.__setattr__(self, "fold_count", folds)
        object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "field_calibrations", tuple(self.field_calibrations))
        object.__setattr__(self, "policy_identity", policy)
        object.__setattr__(self, "label_head_loss_identity", identity)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "failure_reasons", tuple(str(value) for value in self.failure_reasons))
        object.__setattr__(self, "observation_noise_included", False)
        object.__setattr__(self, "transferable", False)

    def _payload(self) -> dict[str, object]:
        return {
            "protocol": POSTERIOR_CALIBRATION_PROTOCOL,
            "protocol_version": POSTERIOR_CALIBRATION_PROTOCOL_VERSION,
            "artifact_id": self.artifact_id,
            "rawdata_status": self.rawdata_status,
            "state_signature": self.state_signature,
            "strategy_signature": self.strategy_signature,
            "schema_signature": self.schema_signature,
            "posterior_kind": self.posterior_kind,
            "support_kind": self.support_kind,
            "unique_support": self.unique_support,
            "checkpoint_hashes": dict(self.checkpoint_hashes),
            "training_provenance_sha256": self.training_provenance_sha256,
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "calibration_locator_sha256": self.calibration_locator_sha256,
            "calibration_design_ids_sha256": self.calibration_design_ids_sha256,
            "calibration_design_count": self.calibration_design_count,
            "fold_count": self.fold_count,
            "seed": self.seed,
            "field_calibrations": [item.as_dict() for item in self.field_calibrations],
            "applicability": self.applicability.as_dict(),
            "policy_identity": dict(self.policy_identity),
            "label_head_loss_identity": dict(self.label_head_loss_identity),
            "evidence": dict(self.evidence),
            "failure_reasons": list(self.failure_reasons),
            "performance_status": self.performance_status,
            "observation_noise_included": self.observation_noise_included,
            "transferable": self.transferable,
        }

    @property
    def sha256(self) -> str:
        return calibration_identity_signature(self._payload())

    def as_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["artifact_sha256"] = self.sha256
        return payload

    def write(self, path: str | Path) -> Path:
        """Atomically persist the self-verifying JSON artifact."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    self.as_dict(),
                    stream,
                    sort_keys=True,
                    indent=2,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "PosteriorCalibrationArtifact":
        if str(value.get("protocol")) != POSTERIOR_CALIBRATION_PROTOCOL or int(value.get("protocol_version", -1)) != POSTERIOR_CALIBRATION_PROTOCOL_VERSION:
            raise ValueError("unsupported posterior calibration artifact protocol")
        artifact = cls(
            artifact_id=str(value["artifact_id"]),
            rawdata_status=str(value["rawdata_status"]),
            state_signature=str(value["state_signature"]),
            strategy_signature=str(value["strategy_signature"]),
            schema_signature=str(value["schema_signature"]),
            posterior_kind=str(value["posterior_kind"]),
            support_kind=str(value["support_kind"]),
            unique_support=int(value["unique_support"]),
            checkpoint_hashes=dict(value["checkpoint_hashes"]),
            training_provenance_sha256=str(value["training_provenance_sha256"]),
            dataset_manifest_sha256=str(value["dataset_manifest_sha256"]),
            calibration_locator_sha256=str(value["calibration_locator_sha256"]),
            calibration_design_ids_sha256=str(value["calibration_design_ids_sha256"]),
            calibration_design_count=int(value["calibration_design_count"]),
            fold_count=int(value["fold_count"]),
            seed=int(value["seed"]),
            field_calibrations=tuple(
                FieldSpreadCalibration.from_mapping(dict(item))
                for item in value["field_calibrations"]
            ),
            applicability=ApplicabilityCalibration.from_mapping(
                dict(value["applicability"])
            ),
            policy_identity=dict(value["policy_identity"]),
            label_head_loss_identity=dict(value["label_head_loss_identity"]),
            evidence=dict(value["evidence"]),
            failure_reasons=tuple(str(item) for item in value["failure_reasons"]),
            performance_status=str(value["performance_status"]),
            observation_noise_included=bool(value["observation_noise_included"]),
            transferable=bool(value["transferable"]),
        )
        if str(value.get("artifact_sha256")) != artifact.sha256:
            raise ValueError("posterior calibration artifact hash mismatch")
        return artifact

    @classmethod
    def read(cls, path: str | Path) -> "PosteriorCalibrationArtifact":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise TypeError("posterior calibration artifact must be a JSON object")
        return cls.from_mapping(value)


def _spread_arrays(
    member_values: object, truth: object
) -> tuple[np.ndarray, np.ndarray]:
    members = np.asarray(member_values, dtype=np.float64)
    target = np.asarray(truth, dtype=np.float64)
    if members.ndim < 2 or target.shape != members.shape[1:]:
        raise ValueError("spread calibration expects members[S,N,...] and truth[N,...]")
    if members.shape[0] < 2 or members.shape[1] < 2:
        raise ValueError("spread calibration needs at least two members and designs")
    if not np.all(np.isfinite(members)) or not np.all(np.isfinite(target)):
        raise ValueError("spread calibration values must be finite")
    return members, target


def assess_spread_scale(
    member_values: object,
    truth: object,
    *,
    scale: float,
    target_coverages: Sequence[float],
) -> dict[str, object]:
    """Evaluate one scale using design-macro coverage and energy score."""

    members, target = _spread_arrays(member_values, truth)
    factor = _finite_float(scale, "spread scale")
    if factor < 1.0:
        raise ValueError("spread scale must be conservative")
    coverages = tuple(float(value) for value in target_coverages)
    if any(not 0.0 < value < 1.0 for value in coverages):
        raise ValueError("target coverages must be in (0, 1)")
    mean = np.mean(members, axis=0, dtype=np.float64)
    adjusted = mean[None, ...] + factor * (members - mean[None, ...])
    marginal = []
    absolute_error = 0.0
    undercoverage = 0.0
    for nominal in coverages:
        alpha = (1.0 - nominal) / 2.0
        lower = np.quantile(adjusted, alpha, axis=0)
        upper = np.quantile(adjusted, 1.0 - alpha, axis=0)
        inside = (target >= lower) & (target <= upper)
        design_coverage = inside.reshape(inside.shape[0], -1).mean(axis=1)
        observed = float(np.mean(design_coverage))
        error = abs(observed - nominal)
        absolute_error += error
        undercoverage += max(0.0, nominal - observed)
        marginal.append(
            {
                "nominal": nominal,
                "observed_design_macro": observed,
                "absolute_error": error,
                "design_coverage_median": float(np.median(design_coverage)),
            }
        )
    flattened = adjusted.reshape(adjusted.shape[0], adjusted.shape[1], -1)
    target_flat = target.reshape(target.shape[0], -1)
    normalization = math.sqrt(float(target_flat.shape[1]))
    first = np.linalg.norm(flattened - target_flat[None, ...], axis=2) / normalization
    pairwise = np.linalg.norm(
        flattened[:, None, ...] - flattened[None, :, ...], axis=3
    ) / normalization
    design_energy = np.mean(first, axis=0) - 0.5 * np.mean(pairwise, axis=(0, 1))
    return {
        "scale": factor,
        "coverage": marginal,
        "mean_absolute_coverage_error": absolute_error / len(coverages),
        "mean_undercoverage": undercoverage / len(coverages),
        "energy_score_design_macro": float(np.mean(design_energy)),
        "energy_score_design_median": float(np.median(design_energy)),
    }


def select_conservative_spread_scale(
    member_values: object,
    truth: object,
    *,
    candidate_scales: Sequence[float],
    target_coverages: Sequence[float],
) -> tuple[float, tuple[dict[str, object], ...]]:
    """Select a preregistered conservative scale without changing the mean."""

    candidates = tuple(float(value) for value in candidate_scales)
    if tuple(sorted(set(candidates))) != candidates or not candidates or candidates[0] < 1.0:
        raise ValueError("candidate spread scales must be sorted, unique, and >= 1")
    table = tuple(
        assess_spread_scale(
            member_values,
            truth,
            scale=value,
            target_coverages=target_coverages,
        )
        for value in candidates
    )
    identity_energy = max(
        float(table[0]["energy_score_design_macro"]), np.finfo(np.float64).eps
    )
    selected = min(
        table,
        key=lambda row: (
            2.0 * float(row["mean_undercoverage"])
            + float(row["mean_absolute_coverage_error"])
            + 0.05
            * max(
                0.0,
                float(row["energy_score_design_macro"]) / identity_energy - 1.0,
            ),
            float(row["scale"]),
        ),
    )
    return float(selected["scale"]), table


def _sigmoid(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    output = np.empty_like(array)
    positive = array >= 0
    output[positive] = 1.0 / (1.0 + np.exp(-array[positive]))
    exponential = np.exp(array[~positive])
    output[~positive] = exponential / (1.0 + exponential)
    return output


def fit_monotone_applicability_calibration(
    member_probabilities: object,
    labels: object,
    *,
    minimum_class_count: int,
    maximum_iterations: int = 100,
) -> tuple[float, float, dict[str, object]]:
    """Fit one strictly monotone logit-affine mapping to all member scores."""

    probabilities = np.asarray(member_probabilities, dtype=np.float64)
    target = np.asarray(labels, dtype=np.float64)
    if probabilities.ndim != 2 or target.shape != (probabilities.shape[1],):
        raise ValueError("applicability fit expects probabilities[S,N] and labels[N]")
    if probabilities.shape[0] < 2 or probabilities.shape[1] < 2:
        raise ValueError("applicability fit needs at least two members/designs")
    if not np.all(np.isfinite(probabilities)) or np.any((probabilities < 0.0) | (probabilities > 1.0)):
        raise ValueError("applicability probabilities must be finite and in [0, 1]")
    if not np.all(np.isin(target, (0.0, 1.0))):
        raise ValueError("applicability labels must be binary")
    positives = int(np.count_nonzero(target == 1.0))
    negatives = int(np.count_nonzero(target == 0.0))
    minimum = int(minimum_class_count)
    if minimum <= 0 or positives < minimum or negatives < minimum:
        raise ValueError("applicability calibration has insufficient class support")
    epsilon = 1.0e-6
    logits = np.log(
        np.clip(probabilities, epsilon, 1.0 - epsilon)
        / (1.0 - np.clip(probabilities, epsilon, 1.0 - epsilon))
    ).reshape(-1)
    repeated = np.tile(target, probabilities.shape[0])
    ridge = 1.0e-6

    def objective(slope: float, intercept: float) -> float:
        predicted = np.clip(_sigmoid(slope * logits + intercept), epsilon, 1.0 - epsilon)
        loss = -np.mean(
            repeated * np.log(predicted)
            + (1.0 - repeated) * np.log(1.0 - predicted)
        )
        return float(loss + 0.5 * ridge * ((slope - 1.0) ** 2 + intercept**2))

    slope = 1.0
    intercept = 0.0
    initial = objective(slope, intercept)
    completed = 0
    for iteration in range(max(1, int(maximum_iterations))):
        predicted = _sigmoid(slope * logits + intercept)
        residual = predicted - repeated
        weights = predicted * (1.0 - predicted)
        gradient = np.asarray(
            [
                np.mean(residual * logits) + ridge * (slope - 1.0),
                np.mean(residual) + ridge * intercept,
            ],
            dtype=np.float64,
        )
        hessian = np.asarray(
            [
                [np.mean(weights * logits * logits) + ridge, np.mean(weights * logits)],
                [np.mean(weights * logits), np.mean(weights) + ridge],
            ],
            dtype=np.float64,
        )
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.pinv(hessian) @ gradient
        current = objective(slope, intercept)
        accepted = False
        multiplier = 1.0
        for _line_search in range(30):
            candidate_slope = max(1.0e-6, float(slope - multiplier * step[0]))
            candidate_intercept = float(intercept - multiplier * step[1])
            candidate = objective(candidate_slope, candidate_intercept)
            if candidate <= current + 1.0e-14:
                slope, intercept = candidate_slope, candidate_intercept
                accepted = True
                break
            multiplier *= 0.5
        completed = iteration + 1
        if not accepted or float(np.linalg.norm(multiplier * step)) <= 1.0e-9:
            break
    final = objective(slope, intercept)
    if not math.isfinite(final) or final > initial + 1.0e-10:
        raise RuntimeError("applicability calibrator did not converge conservatively")
    return (
        float(slope),
        float(intercept),
        {
            "fit_design_count": int(target.size),
            "member_count": int(probabilities.shape[0]),
            "positive_count": positives,
            "negative_count": negatives,
            "minimum_class_count": minimum,
            "iterations": completed,
            "initial_regularized_log_loss": initial,
            "final_regularized_log_loss": final,
        },
    )


def transform_applicability_members(
    member_probabilities: object, *, slope: float, intercept: float
) -> np.ndarray:
    probabilities = np.asarray(member_probabilities, dtype=np.float64)
    if not np.all(np.isfinite(probabilities)) or np.any((probabilities < 0.0) | (probabilities > 1.0)):
        raise ValueError("applicability probabilities must be finite and in [0, 1]")
    slope_value = _finite_float(slope, "applicability slope")
    intercept_value = _finite_float(intercept, "applicability intercept")
    if slope_value <= 0.0:
        raise ValueError("applicability mapping must be strictly monotone")
    epsilon = 1.0e-6
    clipped = np.clip(probabilities, epsilon, 1.0 - epsilon)
    logits = np.log(clipped / (1.0 - clipped))
    return np.ascontiguousarray(
        _sigmoid(slope_value * logits + intercept_value), dtype=np.float64
    )


class CalibratedRawDataPosteriorSampler:
    """Apply exact-state field scales while retaining persistent draw identity."""

    def __init__(
        self,
        sampler: RawDataPosteriorSampler,
        artifact: PosteriorCalibrationArtifact,
    ) -> None:
        if not isinstance(sampler, RawDataPosteriorSampler):
            raise TypeError("sampler must implement RawDataPosteriorSampler")
        if artifact.rawdata_status != CALIBRATED:
            raise RuntimeError("rawData posterior calibration is not available")
        base = sampler.diagnostics
        _require_matching_posterior_identity(base, artifact)
        if base.actual_draw_count != int(base.unique_support) or len(set(base.draw_sources)) != base.actual_draw_count:
            raise ValueError(
                "calibrated finite posterior must enumerate every unique member once"
            )
        scales = {item.selector: item.scale for item in artifact.field_calibrations}
        if tuple(scales) != base.field_selectors:
            raise ValueError("calibration fields do not match posterior field order")
        self._sampler = sampler
        self._artifact = artifact
        self._scales = scales
        self._diagnostics = _calibrated_diagnostics(base, artifact)

    @property
    def diagnostics(self) -> RawDataPosteriorDiagnostics:
        return self._diagnostics

    @property
    def artifact(self) -> PosteriorCalibrationArtifact:
        return self._artifact

    def predict(
        self, population: Sequence[Sequence[float]]
    ) -> MaterializedRawDataPosterior:
        posterior = self._sampler.predict(population)
        draws = tuple(posterior.iter_draws())
        if tuple(draw.draw_id for draw in draws) != self._diagnostics.draw_ids:
            raise ValueError("posterior draw identity changed before calibration")
        samples = [list(draw.samples) for draw in draws]
        for candidate_index in range(len(posterior.population)):
            structured = []
            for draw_index in range(len(draws)):
                sample = samples[draw_index][candidate_index]
                try:
                    current = (
                        sample
                        if isinstance(sample, StructuredRawDataSample)
                        else StructuredRawDataSample.from_items(sample)
                    )
                except (TypeError, ValueError):
                    structured = []
                    break
                structured.append(current)
            if not structured:
                continue
            schema = RawDataSchemaTemplate.from_items(structured[0].items)
            if schema.signature != self._diagnostics.schema_signature or any(
                schema.validate_sample(sample).field_selectors
                != self._diagnostics.field_selectors
                for sample in structured
            ):
                raise ValueError("posterior rawData schema changed before calibration")
            calibrated_by_draw = [sample.as_mapping() for sample in structured]
            for field_index, field in enumerate(schema.fields):
                arrays = np.stack(
                    [
                        np.asarray(sample.items[field_index].payload[field.main_key])
                        for sample in structured
                    ],
                    axis=0,
                )
                if not np.issubdtype(arrays.dtype, np.floating):
                    raise ValueError("posterior calibration requires floating rawData")
                values = np.asarray(arrays, dtype=np.float64)
                mean = np.mean(values, axis=0, dtype=np.float64)
                adjusted = mean[None, ...] + self._scales[field.selector] * (
                    values - mean[None, ...]
                )
                adjusted += mean[None, ...] - np.mean(
                    adjusted, axis=0, dtype=np.float64
                )[None, ...]
                for draw_index, payload in enumerate(calibrated_by_draw):
                    converted = np.asarray(adjusted[draw_index], dtype=arrays.dtype)
                    payload[field.filename][field.main_key] = converted.copy()
            for draw_index, payload in enumerate(calibrated_by_draw):
                samples[draw_index][candidate_index] = schema.validate_sample(payload)
        calibrated_draws = tuple(
            RawDataFunctionDraw(draw.draw_id, tuple(current))
            for draw, current in zip(draws, samples)
        )
        diagnostics = _calibrated_diagnostics(
            posterior.diagnostics, self._artifact
        )
        return MaterializedRawDataPosterior(
            posterior.population,
            calibrated_draws,
            diagnostics,
        )


def _require_matching_posterior_identity(
    diagnostics: RawDataPosteriorDiagnostics,
    artifact: PosteriorCalibrationArtifact,
) -> None:
    mismatches = []
    for name in (
        "state_signature",
        "strategy_signature",
        "schema_signature",
        "posterior_kind",
        "support_kind",
        "unique_support",
    ):
        if getattr(diagnostics, name) != getattr(artifact, name):
            mismatches.append(name)
    if diagnostics.observation_noise_included:
        mismatches.append("observation_noise_included")
    if diagnostics.calibrated:
        mismatches.append("already_calibrated")
    if mismatches:
        raise ValueError(
            "posterior calibration artifact is incompatible: "
            + ", ".join(mismatches)
        )


def _calibrated_diagnostics(
    diagnostics: RawDataPosteriorDiagnostics,
    artifact: PosteriorCalibrationArtifact,
) -> RawDataPosteriorDiagnostics:
    return replace(
        diagnostics,
        calibrated=True,
        calibration_method=FIELD_SPREAD_METHOD,
        calibration_artifact_sha256=artifact.sha256,
        limitations=tuple(diagnostics.limitations)
        + (
            "field spread calibrated around the unchanged ensemble mean",
            "calibration is exact-checkpoint-bound and non-transferable",
            "calibration remains experimental and performance-not-accepted",
        ),
    )


def calibrated_applicability_prediction(
    prediction: ApplicabilityPrediction,
    artifact: PosteriorCalibrationArtifact,
) -> ApplicabilityPrediction:
    """Apply one mapping to every member while preserving member pairing."""

    calibration = artifact.applicability
    if calibration.status != CALIBRATED:
        raise RuntimeError("applicability calibration is not available")
    if prediction.calibrated:
        raise ValueError("applicability prediction is already calibrated")
    mismatches = []
    if prediction.state_signature != artifact.state_signature:
        mismatches.append("state_signature")
    if prediction.strategy_signature != artifact.strategy_signature:
        mismatches.append("strategy_signature")
    if calibration_identity_signature(dict(prediction.policy_identity)) != calibration.policy_signature:
        mismatches.append("policy_identity")
    if mismatches:
        raise ValueError(
            "applicability calibration artifact is incompatible: "
            + ", ".join(mismatches)
        )
    assert calibration.slope is not None and calibration.intercept is not None
    members = transform_applicability_members(
        prediction.member_smooth_probabilities,
        slope=calibration.slope,
        intercept=calibration.intercept,
    )
    means = np.mean(members, axis=0, dtype=np.float64)
    return ApplicabilityPrediction(
        population=prediction.population,
        mean_smooth_probability=tuple(float(value) for value in means),
        member_smooth_probabilities=tuple(
            tuple(float(value) for value in row) for row in members
        ),
        policy_identity=prediction.policy_identity,
        state_signature=prediction.state_signature,
        strategy_signature=prediction.strategy_signature,
        calibrated=True,
        limitations=(
            "monotone probability calibration shared by persistent members",
            "member epistemic spread is retained and is not observation noise",
            "calibration is exact-checkpoint-bound and non-transferable",
            "calibration remains experimental and performance-not-accepted",
        ),
    )


__all__ = [
    "APPLICABILITY_METHOD",
    "CALIBRATED",
    "EXPERIMENTAL_PERFORMANCE_STATUS",
    "FIELD_SPREAD_METHOD",
    "NOT_APPLICABLE",
    "POSTERIOR_CALIBRATION_PROTOCOL",
    "POSTERIOR_CALIBRATION_PROTOCOL_VERSION",
    "UNCALIBRATED",
    "ApplicabilityCalibration",
    "CalibratedRawDataPosteriorSampler",
    "FieldSpreadCalibration",
    "PosteriorCalibrationArtifact",
    "assess_spread_scale",
    "calibrated_applicability_prediction",
    "calibration_identity_signature",
    "fit_monotone_applicability_calibration",
    "select_conservative_spread_scale",
    "transform_applicability_members",
]
