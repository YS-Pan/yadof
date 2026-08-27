"""Run the frozen Gate 0 v3 development/validation representation matrix.

This command can only open the development locator.  It never accepts a test
locator or threshold file and writes one immutable result per model cell before
building an aggregate summary.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import tempfile
import threading
import time
from typing import Iterable, Mapping, Sequence

import numpy as np
import psutil
from scipy.stats import spearmanr
import torch

from yadof.job_template import api as job_template_api
from yadof.job_template.rawdata_template import StructuredRawDataSample
from yadof.surrogate import (
    CAETrainConfig,
    DiagnosticCondition,
    DiagnosticRegimeRule,
    RawDataQualityPolicy,
)
from yadof.surrogate.conditional_inr import modeling as inr_modeling
from yadof.surrogate.conditional_inr import runtime as inr_runtime
from yadof.surrogate.hierarchical_cae import modeling as cae_modeling
from yadof.surrogate.hierarchical_cae.schema import (
    build_schema,
    field_matrices,
    fit_scalers,
    reconstruct_samples,
    standardized_field_matrices,
)
from yadof.surrogate.quality import QualityAssessmentBatch, assess_quality

try:
    from benchmark_automation.hierarchical_cae_dataset import (
        load_locator_rows,
        load_selected_records,
    )
except ModuleNotFoundError:
    from hierarchical_cae_dataset import (
        load_locator_rows,
        load_selected_records,
    )


AUTOMATION_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = AUTOMATION_ROOT.parent
INVENTORY_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi"
    / "schema_inventory.json"
)
V3_ROOT = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v3"
)
POLICY_PATH = V3_ROOT / "quality_regime_protocol.json"
PLAN_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v4"
    / "validation_plan_v2.json"
)
VALIDATION_PROTOCOL = "yadof.gate0-v3.hierarchical-cae-validation"
VALIDATION_PROTOCOL_VERSION = 1


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: float) -> float | None:
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _rank3_layouts(case: Mapping[str, object]) -> dict[tuple[str, str], dict[str, object]]:
    output = {}
    for raw_field in case["fields"]:
        field = dict(raw_field)
        if len(field["shape"]) != 3:
            continue
        layout = field["layout"]
        output[tuple(str(value) for value in field["selector"])] = {
            "channel_axes": tuple(str(value) for value in layout["channel_axes"]),
            "spatial_axes": tuple(str(value) for value in layout["spatial_axes"]),
        }
    return output


def _explicit_groups(case: Mapping[str, object]) -> tuple[tuple[tuple[str, str], ...], ...]:
    return tuple(
        tuple(tuple(str(value) for value in selector) for selector in group)
        for group in case.get("explicit_groups_for_required_ablation", ())
    )


def _chrono_policy() -> RawDataQualityPolicy:
    protocol = _json(POLICY_PATH)["chrono_task_policy"]
    rules = tuple(
        DiagnosticRegimeRule(
            regime=rule["regime"],
            match=rule["match"],
            conditions=tuple(
                DiagnosticCondition(
                    path=tuple(condition["path"]),
                    operator=condition["operator"],
                    value=condition.get("value"),
                )
                for condition in rule["conditions"]
            ),
        )
        for rule in protocol["ordered_rules"]
    )
    weights = protocol["field_weights"]
    shared = protocol["shared_weights"]
    return RawDataQualityPolicy(
        policy_id=str(protocol["policy_id"]),
        policy_version=int(protocol["policy_version"]),
        assessment_path=tuple(protocol["assessment_path"]),
        diagnostic_path=tuple(protocol["diagnostic_path"]),
        diagnostic_rules=rules,
        diagnostic_field_selectors=tuple(
            tuple(selector) for selector in protocol["design_regime_fields"]
        ),
        diagnostic_default_regime=str(protocol["default_regime"]),
        missing_assessment="error",
        smooth_field_weight=float(weights["smooth"]),
        chatter_field_weight=float(weights["chatter"]),
        failure_field_weight=float(weights["failure"]),
        unknown_field_weight=float(weights["unknown"]),
        smooth_shared_weight=float(shared["smooth"]),
        chatter_shared_weight=float(shared["chatter"]),
        failure_shared_weight=float(shared["failure"]),
        unknown_shared_weight=float(shared["unknown"]),
    )


def _quality_subset(
    quality: QualityAssessmentBatch, indices: np.ndarray
) -> QualityAssessmentBatch:
    selected = tuple(int(value) for value in indices)
    full_count = len(quality.design_regimes)
    return QualityAssessmentBatch(
        field_weights=np.ascontiguousarray(quality.field_weights[indices]),
        shared_weights=np.ascontiguousarray(quality.shared_weights[indices]),
        residual_targets=np.ascontiguousarray(quality.residual_targets[indices]),
        applicability_targets=np.ascontiguousarray(
            quality.applicability_targets[indices]
        ),
        design_regimes=tuple(quality.design_regimes[index] for index in selected),
        field_regimes=tuple(quality.field_regimes[index] for index in selected),
        explicit_assessment_count=(
            len(selected)
            if quality.explicit_assessment_count == full_count
            else 0
        ),
        diagnostic_assessment_count=(
            len(selected)
            if quality.diagnostic_assessment_count == full_count
            else 0
        ),
        shape_fallback_count=(
            len(selected) if quality.shape_fallback_count == full_count else 0
        ),
    )


@dataclass(slots=True)
class CaseData:
    case_id: str
    task_fingerprint: str
    workspace: Path
    parameter_names: tuple[str, ...]
    design_ids: tuple[str, ...]
    parameters: np.ndarray
    samples: tuple[StructuredRawDataSample, ...]
    metadata: tuple[Mapping[str, object], ...]
    schema: object
    matrices: tuple[np.ndarray, ...]
    quality: QualityAssessmentBatch

    @property
    def train_pool_count(self) -> int:
        return 2000

    @property
    def validation_count(self) -> int:
        return 200


def _load_case(
    manifest_path: Path,
    case_id: str,
    inventory: Mapping[str, object],
) -> CaseData:
    locator = load_locator_rows(manifest_path, scope="development")
    rows = [row for row in locator if row["case"] == case_id]
    train_rows = sorted(
        (row for row in rows if row["partition"] == "train_pool"),
        key=lambda row: int(row["training_rank"]),
    )
    validation_rows = sorted(
        (row for row in rows if row["partition"] == "validation"),
        key=lambda row: str(row["design_id"]),
    )
    if len(train_rows) != 2000 or len(validation_rows) != 200:
        raise ValueError(f"{case_id}: development partition counts drifted")
    records = load_selected_records((*train_rows, *validation_rows))
    by_id = {
        str(record["locator"]["design_id"]): record for record in records
    }
    ordered_rows = (*train_rows, *validation_rows)
    ordered = tuple(by_id[str(row["design_id"])] for row in ordered_rows)
    samples = tuple(record["sample"] for record in ordered)
    metadata = tuple(record["record_metadata"] for record in ordered)
    parameters = np.ascontiguousarray(
        [record["normalized_variables"] for record in ordered], dtype=np.float32
    )
    case = inventory["cases"][case_id]
    schema = build_schema(samples[0], field_layouts=_rank3_layouts(case))
    matrices = field_matrices(schema, samples)
    policy = _chrono_policy() if case_id == "chrono" else None
    quality = assess_quality(
        policy=policy, samples=samples, record_metadata=metadata
    )
    return CaseData(
        case_id=case_id,
        task_fingerprint=str(case["task_fingerprint"]),
        workspace=Path(str(ordered_rows[0]["workspace"])),
        parameter_names=tuple(case["parameter_contract"]["names"]),
        design_ids=tuple(str(row["design_id"]) for row in ordered_rows),
        parameters=parameters,
        samples=samples,
        metadata=metadata,
        schema=schema,
        matrices=matrices,
        quality=quality,
    )


class _ResourceMonitor:
    def __init__(self) -> None:
        self.process = psutil.Process()
        self.stop_event = threading.Event()
        self.peak_rss = int(self.process.memory_info().rss)
        self.cpu_samples: list[float] = []
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        self.process.cpu_percent(None)
        while not self.stop_event.wait(0.2):
            try:
                self.peak_rss = max(
                    self.peak_rss, int(self.process.memory_info().rss)
                )
                self.cpu_samples.append(float(self.process.cpu_percent(None)))
            except (psutil.Error, OSError):
                return

    def __enter__(self):
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        self.started = time.perf_counter()
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.wall_sec = time.perf_counter() - self.started
        self.stop_event.set()
        self.thread.join(timeout=2.0)
        self.peak_vram = (
            int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else 0
        )

    def payload(self) -> dict[str, object]:
        return {
            "wall_sec": float(self.wall_sec),
            "peak_process_rss_bytes": int(self.peak_rss),
            "peak_torch_vram_bytes": int(self.peak_vram),
            "mean_process_cpu_percent": (
                float(np.mean(self.cpu_samples)) if self.cpu_samples else 0.0
            ),
        }


def _shape_features(values: np.ndarray) -> dict[str, float]:
    vector = np.asarray(values, dtype=np.float64).reshape(-1)
    if vector.size < 4 or not np.all(np.isfinite(vector)):
        return {
            "second_difference_rms": 0.0,
            "high_frequency_energy_ratio": 0.0,
            "derivative_reversal_fraction": 0.0,
        }
    centered = vector - np.median(vector)
    scale = max(
        abs(float(np.quantile(centered, 0.95) - np.quantile(centered, 0.05))),
        float(np.std(centered)),
        1.0e-12,
    )
    first = np.diff(centered)
    second = np.diff(centered, n=2)
    power = np.square(np.abs(np.fft.rfft(centered)))
    cutoff = max(1, int(math.ceil(power.size * 0.75)))
    non_dc = float(np.sum(power[1:]))
    return {
        "second_difference_rms": float(
            np.sqrt(np.mean(np.square(second))) / scale
        ),
        "high_frequency_energy_ratio": (
            float(np.sum(power[cutoff:]) / non_dc) if non_dc > 0 else 0.0
        ),
        "derivative_reversal_fraction": float(
            np.count_nonzero(first[1:] * first[:-1] < 0)
            / max(1, first.size - 1)
        ),
    }


def _auprc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    labels = np.asarray(labels, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    positives = int(np.sum(labels == 1.0))
    if positives == 0:
        return None
    order = np.lexsort((np.arange(labels.size), -scores))
    ranked = labels[order]
    precision = np.cumsum(ranked) / np.arange(1, ranked.size + 1)
    return float(np.sum(precision * ranked) / positives)


def _calibration_metrics(
    labels: np.ndarray, scores: np.ndarray
) -> dict[str, object]:
    labels = np.asarray(labels, dtype=np.float64)
    scores = np.clip(np.asarray(scores, dtype=np.float64), 0.0, 1.0)
    order = np.lexsort((np.arange(labels.size), scores))
    bins = np.array_split(order, 10)
    reliability = []
    ece = 0.0
    for index, indices in enumerate(bins):
        if indices.size == 0:
            continue
        confidence = float(np.mean(scores[indices]))
        observed = float(np.mean(labels[indices]))
        weight = float(indices.size / labels.size)
        ece += weight * abs(confidence - observed)
        reliability.append(
            {
                "bin": index,
                "count": int(indices.size),
                "mean_predicted_smooth_probability": confidence,
                "observed_smooth_fraction": observed,
            }
        )
    return {
        "auprc": _auprc(labels, scores),
        "brier_score": float(np.mean(np.square(scores - labels))),
        "expected_calibration_error": float(ece),
        "reliability_equal_mass_10_bin": reliability,
    }


def _pareto_relation(left: np.ndarray, right: np.ndarray) -> int:
    if np.all(left <= right) and np.any(left < right):
        return -1
    if np.all(right <= left) and np.any(right < left):
        return 1
    return 0


def _pareto_consistency(true_cost: np.ndarray, predicted_cost: np.ndarray) -> float:
    matches = 0
    total = 0
    for left in range(true_cost.shape[0]):
        for right in range(left + 1, true_cost.shape[0]):
            matches += int(
                _pareto_relation(true_cost[left], true_cost[right])
                == _pareto_relation(predicted_cost[left], predicted_cost[right])
            )
            total += 1
    return float(matches / max(1, total))


def _costs(
    workspace: Path,
    parameters: np.ndarray,
    samples: Sequence[StructuredRawDataSample],
) -> np.ndarray:
    raw_variables = tuple(
        tuple(
            float(value)
            for value in job_template_api.denormalize_variables(workspace, row)
        )
        for row in parameters
    )
    payloads = tuple(
        tuple(dict(item.payload) for item in sample.items) for sample in samples
    )
    values = job_template_api.calculate_cost(workspace, payloads, raw_variables)
    return np.ascontiguousarray(values, dtype=np.float64)


def _boundary_mask(
    train_x: np.ndarray,
    validation_x: np.ndarray,
    train_labels: np.ndarray,
    train_ids: Sequence[str],
) -> np.ndarray:
    mask = []
    ids = np.asarray(train_ids, dtype="U64")
    for row in validation_x:
        distances = np.sum(np.square(train_x - row), axis=1, dtype=np.float64)
        nearest = np.lexsort((ids, distances))[:10]
        values = set(float(value) for value in train_labels[nearest])
        mask.append(values == {0.0, 1.0})
    return np.asarray(mask, dtype=bool)


def _evaluate(
    *,
    data: CaseData,
    train_size: int,
    schema,
    scalers,
    predicted_samples: Sequence[StructuredRawDataSample],
    applicability_scores: np.ndarray | None,
    model_quality: QualityAssessmentBatch,
) -> dict[str, object]:
    validation_start = data.train_pool_count
    validation_samples = data.samples[validation_start:]
    validation_x = data.parameters[validation_start:]
    true_matrices = tuple(matrix[validation_start:] for matrix in data.matrices)
    predicted_matrices = field_matrices(schema, predicted_samples)
    fields = []
    per_design_standardized = []
    for layout, scaler, true_values, predicted_values in zip(
        schema.layouts, scalers, true_matrices, predicted_matrices
    ):
        errors = predicted_values - true_values
        standardized = errors / scaler.scale.reshape(1, -1)
        design_mae = np.mean(np.abs(standardized), axis=1)
        design_rmse = np.sqrt(np.mean(np.square(standardized), axis=1))
        per_design_standardized.append(design_mae)
        fields.append(
            {
                "selector": list(layout.selector),
                "physical_mae": float(np.mean(np.abs(errors))),
                "physical_rmse": float(np.sqrt(np.mean(np.square(errors)))),
                "standardized_mae": float(np.mean(np.abs(standardized))),
                "standardized_rmse": float(
                    np.sqrt(np.mean(np.square(standardized)))
                ),
                "per_design_standardized_mae_median": float(
                    np.median(design_mae)
                ),
                "per_design_standardized_rmse_median": float(
                    np.median(design_rmse)
                ),
            }
        )
    field_macro_mae = float(np.mean([field["standardized_mae"] for field in fields]))
    field_macro_rmse = float(
        np.mean([field["standardized_rmse"] for field in fields])
    )
    design_macro = np.mean(np.stack(per_design_standardized, axis=1), axis=1)

    invalid_cost = 0
    try:
        true_cost = _costs(data.workspace, validation_x, validation_samples)
        predicted_cost = _costs(data.workspace, validation_x, predicted_samples)
        if true_cost.shape != predicted_cost.shape or not np.all(
            np.isfinite(predicted_cost)
        ):
            raise ValueError("predicted current-cost matrix is invalid")
    except (OSError, TypeError, ValueError, KeyError):
        invalid_cost = len(validation_samples)
        true_cost = np.zeros((0, 0), dtype=np.float64)
        predicted_cost = np.zeros((0, 0), dtype=np.float64)
    if invalid_cost:
        cost_metrics = {
            "mae_per_objective": [],
            "rmse_per_objective": [],
            "spearman_per_objective": [],
            "pareto_pairwise_consistency": None,
        }
    else:
        cost_error = predicted_cost - true_cost
        cost_metrics = {
            "mae_per_objective": np.mean(np.abs(cost_error), axis=0).tolist(),
            "rmse_per_objective": np.sqrt(
                np.mean(np.square(cost_error), axis=0)
            ).tolist(),
            "spearman_per_objective": [
                _finite(spearmanr(true_cost[:, index], predicted_cost[:, index]).statistic)
                for index in range(true_cost.shape[1])
            ],
            "pareto_pairwise_consistency": _pareto_consistency(
                true_cost, predicted_cost
            ),
        }

    quality_metrics: dict[str, object] = {}
    if data.case_id == "chrono":
        train_quality = _quality_subset(
            data.quality, np.arange(train_size, dtype=np.int64)
        )
        validation_quality = _quality_subset(
            data.quality,
            np.arange(
                data.train_pool_count,
                data.train_pool_count + data.validation_count,
                dtype=np.int64,
            ),
        )
        labels = validation_quality.applicability_targets.astype(np.float64)
        strata = {}
        boundary = _boundary_mask(
            data.parameters[:train_size],
            validation_x,
            train_quality.applicability_targets,
            data.design_ids[:train_size],
        )
        for name, mask in {
            "smooth": np.asarray(validation_quality.design_regimes) == "smooth",
            "chatter": np.asarray(validation_quality.design_regimes) == "chatter",
            "failure": np.asarray(validation_quality.design_regimes) == "failure",
            "boundary": boundary,
        }.items():
            strata[name] = {
                "count": int(np.count_nonzero(mask)),
                "field_macro_standardized_mae": (
                    float(np.mean(design_macro[mask]))
                    if np.any(mask)
                    else None
                ),
            }

        curve_indices = [
            index for index, layout in enumerate(schema.layouts) if layout.rank == 1
        ]
        feature_names = (
            "second_difference_rms",
            "high_frequency_energy_ratio",
            "derivative_reversal_fraction",
        )
        roughness = []
        leakage_numerator = 0
        leakage_denominator = 0
        for field_index in curve_indices:
            selector = schema.layouts[field_index].selector
            train_smooth = np.asarray(
                [
                    row[field_index] == "smooth"
                    for row in train_quality.field_regimes
                ],
                dtype=bool,
            )
            train_features = [
                _shape_features(values.reshape(schema.layouts[field_index].shape))
                for values in data.matrices[field_index][:train_size][train_smooth]
            ]
            reference = (
                float(
                    np.quantile(
                        [item["high_frequency_energy_ratio"] for item in train_features],
                        0.95,
                    )
                )
                if train_features
                else 0.0
            )
            true_feature_rows = [
                _shape_features(values.reshape(schema.layouts[field_index].shape))
                for values in true_matrices[field_index]
            ]
            predicted_feature_rows = [
                _shape_features(values.reshape(schema.layouts[field_index].shape))
                for values in predicted_matrices[field_index]
            ]
            smooth_field = np.asarray(
                [
                    row[field_index] == "smooth"
                    for row in validation_quality.field_regimes
                ],
                dtype=bool,
            )
            leakage_numerator += sum(
                predicted_feature_rows[index]["high_frequency_energy_ratio"]
                > reference
                for index in np.flatnonzero(smooth_field)
            )
            leakage_denominator += int(np.count_nonzero(smooth_field))
            for stratum in ("smooth", "chatter", "failure"):
                mask = np.asarray(
                    [row[field_index] == stratum for row in validation_quality.field_regimes],
                    dtype=bool,
                )
                for feature_name in feature_names:
                    real = np.asarray(
                        [item[feature_name] for item in true_feature_rows],
                        dtype=np.float64,
                    )[mask]
                    predicted = np.asarray(
                        [item[feature_name] for item in predicted_feature_rows],
                        dtype=np.float64,
                    )[mask]
                    roughness.append(
                        {
                            "selector": list(selector),
                            "stratum": stratum,
                            "feature": feature_name,
                            "count": int(real.size),
                            "predicted_to_real_median_ratio": (
                                float(
                                    np.median(predicted)
                                    / max(float(np.median(real)), 1.0e-12)
                                )
                                if real.size
                                else None
                            ),
                        }
                    )
        quality_metrics = {
            "assessment": validation_quality.diagnostics(),
            "strata": strata,
            "boundary_definition": "10-nearest-train-mixed-smooth-status-v1",
            "clean_target_high_frequency_reference": "per-field train-smooth p95",
            "clean_target_high_frequency_leakage_rate": (
                float(leakage_numerator / leakage_denominator)
                if leakage_denominator
                else None
            ),
            "clean_target_high_frequency_leakage_count": int(leakage_numerator),
            "clean_target_high_frequency_field_count": int(leakage_denominator),
            "roughness_inflation": roughness,
            "regime_classifier": (
                _calibration_metrics(labels, applicability_scores)
                if applicability_scores is not None
                else {
                    "status": "not-present-in-this-preregistered-ablation",
                    "auprc": None,
                    "brier_score": None,
                    "expected_calibration_error": None,
                    "reliability_equal_mass_10_bin": [],
                }
            ),
            "model_quality_config": model_quality.diagnostics(),
        }

    return {
        "rawdata": {
            "fields": fields,
            "field_macro_standardized_mae": field_macro_mae,
            "field_macro_standardized_rmse": field_macro_rmse,
            "invalid_reconstruction_count": 0,
        },
        "current_cost": {**cost_metrics, "invalid_projection_count": invalid_cost},
        "quality_regime": quality_metrics,
    }


def _cae_config(plan: Mapping[str, object], arm: str) -> CAETrainConfig:
    payload = dict(plan["model_configs"]["hierarchical_cae"])
    if arm == "hierarchical-cae-independent-fields":
        payload["sharing"] = "independent"
    if arm == "no-gating":
        payload.update(
            regime_head=False,
            robust_loss_cap=None,
            quality_weighted_loss=False,
            shared_quality_isolation=False,
            gated_private_residual=False,
        )
    elif arm == "robust-weighting-only":
        payload.update(
            regime_head=True,
            robust_loss_cap=4.0,
            quality_weighted_loss=True,
            shared_quality_isolation=False,
            gated_private_residual=False,
        )
    elif arm == "shared-latent-isolation":
        payload.update(
            regime_head=True,
            robust_loss_cap=4.0,
            quality_weighted_loss=True,
            shared_quality_isolation=True,
            gated_private_residual=False,
        )
    elif arm == "gated-private-residual":
        payload.update(
            regime_head=True,
            robust_loss_cap=4.0,
            quality_weighted_loss=True,
            shared_quality_isolation=True,
            gated_private_residual=True,
        )
    return CAETrainConfig(**payload)


def _cae_cell(
    *,
    data: CaseData,
    case: Mapping[str, object],
    train_size: int,
    seed: int,
    arm: str,
    plan: Mapping[str, object],
) -> dict[str, object]:
    groups = (
        _explicit_groups(case)
        if arm == "hierarchical-cae-mean-explicit-s11-gain-groups"
        else ()
    )
    schema = build_schema(
        data.samples[0], groups=groups, field_layouts=_rank3_layouts(case)
    )
    scalers = fit_scalers(
        tuple(matrix[:train_size] for matrix in data.matrices),
        scale_floor=float(plan["model_configs"]["hierarchical_cae"]["scale_floor"]),
    )
    schema = replace(schema, scalers=scalers)
    indices = np.concatenate(
        (
            np.arange(train_size, dtype=np.int64),
            np.arange(
                data.train_pool_count,
                data.train_pool_count + data.validation_count,
                dtype=np.int64,
            ),
        )
    )
    matrices = tuple(matrix[indices] for matrix in data.matrices)
    standardized = standardized_field_matrices(schema, matrices)
    quality = _quality_subset(data.quality, indices)
    cfg = _cae_config(plan, arm)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    with _ResourceMonitor() as monitor:
        model, history = cae_modeling.fit_hierarchical_cae(
            input_dim=data.parameters.shape[1],
            schema=schema,
            parameters=data.parameters[indices],
            standardized_fields=standardized,
            quality=quality,
            device=device,
            train_cfg=cfg,
            seed=seed,
            train_indices=np.arange(train_size, dtype=np.int64),
            validation_indices=np.arange(
                train_size, train_size + data.validation_count, dtype=np.int64
            ),
        )
        member_fields, applicability, _residual = (
            cae_modeling.predict_hierarchical_members(
                model=model,
                parameters=data.parameters[data.train_pool_count :],
                device=device,
                batch_size=cfg.inference_batch_size,
            )
        )
        mean_fields = tuple(np.mean(values, axis=0) for values in member_fields)
        predicted = reconstruct_samples(schema, mean_fields)
    metrics = _evaluate(
        data=data,
        train_size=train_size,
        schema=schema,
        scalers=scalers,
        predicted_samples=predicted,
        applicability_scores=(
            np.mean(applicability, axis=0) if cfg.regime_head else None
        ),
        model_quality=quality,
    )
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    result = {
        "model_config": asdict(cfg),
        "semantic_groups": [
            [list(selector) for selector in group] for group in groups
        ],
        "training_history": history,
        "resources": {
            **monitor.payload(),
            "parameter_count": int(parameter_count),
            "parameter_bytes_float32": int(parameter_count * 4),
        },
        "metrics": metrics,
    }
    del model, member_fields, mean_fields, predicted, standardized, matrices
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


def _conditional_named_samples(
    metric_schema,
    samples: Sequence[Sequence[Mapping[str, object]]],
) -> tuple[StructuredRawDataSample, ...]:
    fields = metric_schema.template.fields
    if any(len(row) != len(fields) for row in samples):
        raise ValueError("conditional-INR prediction item count drifted")
    rebuilt = []
    for row in samples:
        arrays = {
            field.selector: np.asarray(payload[field.main_key])
            for field, payload in zip(fields, row)
        }
        rebuilt.append(metric_schema.template.reconstruct(arrays))
    return tuple(rebuilt)


def _conditional_cell(
    *,
    data: CaseData,
    train_size: int,
    seed: int,
    plan: Mapping[str, object],
) -> dict[str, object]:
    config = inr_modeling.INRTrainConfig(
        **dict(plan["model_configs"]["conditional_inr"])
    )
    raw_train = tuple(
        tuple(dict(item.payload) for item in sample.items)
        for sample in data.samples[:train_size]
    )
    schema, y_train = inr_runtime._flatten_raw_samples(raw_train)
    if schema is None:
        raise RuntimeError("conditional-INR baseline produced no schema")
    scaler = inr_runtime._fit_scaler(y_train, scale_floor=1.0e-6)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    with _ResourceMonitor() as monitor:
        model, history = inr_modeling.fit_deep_ensemble_conditional_inr(
            input_dim=data.parameters.shape[1],
            n_fields=schema.n_fields,
            X_train=data.parameters[:train_size],
            Y_train=scaler.transform(y_train),
            coord_table=schema.coord_table,
            field_ids=schema.field_ids,
            device=device,
            train_cfg=config,
            seed=seed,
        )
        members = inr_modeling.predict_conditional_inr_members(
            model=model,
            X=data.parameters[data.train_pool_count :],
            coord_table=schema.coord_table,
            field_ids=schema.field_ids,
            device=device,
            sample_batch=config.sample_batch_eval,
            query_batch=config.query_batch_eval,
        )
        mean_flat = scaler.inverse(np.mean(members, axis=0))
        raw_predicted = inr_runtime._raw_samples_from_flat(schema, mean_flat)
        predicted = _conditional_named_samples(data.schema, raw_predicted)
    scalers = fit_scalers(
        tuple(matrix[:train_size] for matrix in data.matrices), scale_floor=1.0e-6
    )
    metric_schema = replace(data.schema, scalers=scalers)
    quality_indices = np.concatenate(
        (
            np.arange(train_size, dtype=np.int64),
            np.arange(
                data.train_pool_count,
                data.train_pool_count + data.validation_count,
                dtype=np.int64,
            ),
        )
    )
    metrics = _evaluate(
        data=data,
        train_size=train_size,
        schema=metric_schema,
        scalers=scalers,
        predicted_samples=predicted,
        applicability_scores=None,
        model_quality=_quality_subset(data.quality, quality_indices),
    )
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    result = {
        "model_config": asdict(config),
        "training_history": history,
        "resources": {
            **monitor.payload(),
            "parameter_count": int(parameter_count),
            "parameter_bytes_float32": int(parameter_count * 4),
        },
        "metrics": metrics,
    }
    del model, members, mean_flat, predicted, raw_predicted, y_train
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


def _pca_cell(
    *, data: CaseData, train_size: int, plan: Mapping[str, object]
) -> dict[str, object]:
    rank = int(plan["model_configs"]["pca_svd"]["rank_per_field"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(int(plan["model_configs"]["pca_svd"]["seed"]))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(
            int(plan["model_configs"]["pca_svd"]["seed"])
        )
    predictions = []
    effective_ranks = []
    with _ResourceMonitor() as monitor, torch.no_grad():
        for matrix in data.matrices:
            train = torch.as_tensor(
                matrix[:train_size], dtype=torch.float32, device=device
            )
            validation = torch.as_tensor(
                matrix[data.train_pool_count :],
                dtype=torch.float32,
                device=device,
            )
            mean = torch.mean(train, dim=0, keepdim=True)
            centered = train - mean
            q = max(1, min(rank, centered.shape[0] - 1, centered.shape[1]))
            _u, _s, vectors = torch.pca_lowrank(
                centered, q=q, center=False, niter=3
            )
            reconstructed = (validation - mean) @ vectors @ vectors.T + mean
            predictions.append(reconstructed.cpu().numpy())
            effective_ranks.append(int(q))
            del train, validation, mean, centered, vectors, reconstructed
        scalers = fit_scalers(
            tuple(matrix[:train_size] for matrix in data.matrices),
            scale_floor=1.0e-6,
        )
        schema = replace(data.schema, scalers=scalers)
        shaped = tuple(
            scaler.transform(values).reshape((values.shape[0],) + layout.shape)
            for values, layout, scaler in zip(
                predictions, schema.layouts, scalers
            )
        )
        predicted_samples = reconstruct_samples(schema, shaped)
    quality_indices = np.concatenate(
        (
            np.arange(train_size, dtype=np.int64),
            np.arange(
                data.train_pool_count,
                data.train_pool_count + data.validation_count,
                dtype=np.int64,
            ),
        )
    )
    metrics = _evaluate(
        data=data,
        train_size=train_size,
        schema=schema,
        scalers=scalers,
        predicted_samples=predicted_samples,
        applicability_scores=None,
        model_quality=_quality_subset(data.quality, quality_indices),
    )
    return {
        "model_config": {"rank_per_field": rank},
        "effective_rank_per_field": effective_ranks,
        "diagnostic_only": True,
        "resources": monitor.payload(),
        "metrics": metrics,
    }


def _arms_for_case(plan: Mapping[str, object], case_id: str) -> tuple[str, ...]:
    return tuple(
        arm["id"]
        for arm in plan["matrix"]
        if case_id in arm["cases"]
    )


def _cell_id(case_id: str, arm: str, train_size: int, seed: int | None) -> str:
    suffix = "deterministic" if seed is None else f"seed-{seed}"
    return f"{case_id}__{arm}__train-{train_size}__{suffix}"


def run_validation(
    *,
    manifest_path: Path,
    output_dir: Path,
    cases_filter: set[str] | None,
    arms_filter: set[str] | None,
    sizes_filter: set[int] | None,
    seeds_filter: set[int] | None,
) -> dict[str, object]:
    plan = _json(PLAN_PATH)
    inventory = _json(INVENTORY_PATH)
    manifest_path = manifest_path.resolve()
    output_dir = output_dir.resolve()
    if _sha256(manifest_path) != str(plan["dataset_manifest_sha256"]):
        raise ValueError("validation plan does not bind this dataset manifest")
    if _sha256(Path(__file__).resolve()) != str(
        plan["metric_implementation_sha256"]
    ):
        raise ValueError("validation metric implementation hash drifted")
    output_dir.mkdir(parents=True, exist_ok=True)
    run_spec = {
        "protocol": VALIDATION_PROTOCOL,
        "protocol_version": VALIDATION_PROTOCOL_VERSION,
        "status": "running-development-validation-only",
        "dataset_manifest": str(manifest_path),
        "dataset_manifest_sha256": _sha256(manifest_path),
        "plan": str(PLAN_PATH),
        "plan_sha256": _sha256(PLAN_PATH),
        "metric_implementation": str(Path(__file__).resolve()),
        "metric_implementation_sha256": _sha256(Path(__file__).resolve()),
        "offline_test_locator_accessed": False,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device": (
                torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
            ),
            "host_ram_bytes": int(psutil.virtual_memory().total),
        },
    }
    _write_json_atomic(output_dir / "run_spec.json", run_spec)
    selected_cases = tuple(
        case_id
        for case_id in plan["cases"]
        if cases_filter is None or case_id in cases_filter
    )
    completed = []
    started = time.perf_counter()
    for case_id in selected_cases:
        print(f"[validation] loading development rows for {case_id}", flush=True)
        with _ResourceMonitor() as load_monitor:
            data = _load_case(manifest_path, case_id, inventory)
        preflight = {
            "case": case_id,
            "rows": len(data.samples),
            "fields": [layout.as_dict() for layout in data.schema.layouts],
            "quality": data.quality.diagnostics(),
            "data_load_resources": load_monitor.payload(),
            "offline_test_locator_accessed": False,
        }
        _write_json_atomic(output_dir / f"preflight_{case_id}.json", preflight)
        case = inventory["cases"][case_id]
        for train_size in plan["train_sizes"]:
            train_size = int(train_size)
            if sizes_filter is not None and train_size not in sizes_filter:
                continue
            for arm in _arms_for_case(plan, case_id):
                if arms_filter is not None and arm not in arms_filter:
                    continue
                seeds: tuple[int | None, ...] = (
                    (None,)
                    if arm == "pca-svd-reconstruction"
                    else tuple(int(seed) for seed in plan["model_fit_seeds"])
                )
                for seed in seeds:
                    if (
                        seed is not None
                        and seeds_filter is not None
                        and seed not in seeds_filter
                    ):
                        continue
                    cell_id = _cell_id(case_id, arm, train_size, seed)
                    result_path = output_dir / "cells" / f"{cell_id}.json"
                    if result_path.is_file():
                        existing = _json(result_path)
                        if (
                            existing.get("status") == "completed"
                            and existing.get("plan_sha256") == _sha256(PLAN_PATH)
                            and existing.get("dataset_manifest_sha256")
                            == _sha256(manifest_path)
                        ):
                            print(f"[validation] {cell_id} already complete", flush=True)
                            completed.append(cell_id)
                            continue
                        raise RuntimeError(f"stale validation cell exists: {result_path}")
                    print(f"[validation] start {cell_id}", flush=True)
                    cell_started = time.perf_counter()
                    if arm == "conditional-inr-mean":
                        payload = _conditional_cell(
                            data=data,
                            train_size=train_size,
                            seed=int(seed),
                            plan=plan,
                        )
                    elif arm == "pca-svd-reconstruction":
                        payload = _pca_cell(
                            data=data, train_size=train_size, plan=plan
                        )
                    else:
                        payload = _cae_cell(
                            data=data,
                            case=case,
                            train_size=train_size,
                            seed=int(seed),
                            arm=arm,
                            plan=plan,
                        )
                    result = {
                        "protocol": VALIDATION_PROTOCOL,
                        "protocol_version": VALIDATION_PROTOCOL_VERSION,
                        "status": "completed",
                        "cell_id": cell_id,
                        "case": case_id,
                        "arm": arm,
                        "train_size": train_size,
                        "seed": seed,
                        "validation_design_count": data.validation_count,
                        "dataset_manifest_sha256": _sha256(manifest_path),
                        "plan_sha256": _sha256(PLAN_PATH),
                        "offline_test_locator_accessed": False,
                        "cell_wall_sec": time.perf_counter() - cell_started,
                        **payload,
                    }
                    _write_json_atomic(result_path, result)
                    completed.append(cell_id)
                    print(
                        f"[validation] done {cell_id} "
                        f"mae={result['metrics']['rawdata']['field_macro_standardized_mae']:.6g} "
                        f"sec={result['cell_wall_sec']:.1f}",
                        flush=True,
                    )
        del data
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    summary = {
        **run_spec,
        "status": "completed-development-validation-only",
        "completed_cell_count": len(completed),
        "completed_cells": completed,
        "wall_sec": time.perf_counter() - started,
        "offline_test_locator_accessed": False,
    }
    _write_json_atomic(output_dir / "validation_summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--arms", nargs="*")
    parser.add_argument("--train-sizes", nargs="*", type=int)
    parser.add_argument("--seeds", nargs="*", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = run_validation(
        manifest_path=args.dataset_manifest,
        output_dir=args.output_dir,
        cases_filter=set(args.cases) if args.cases else None,
        arms_filter=set(args.arms) if args.arms else None,
        sizes_filter=set(args.train_sizes) if args.train_sizes else None,
        seeds_filter=set(args.seeds) if args.seeds else None,
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
