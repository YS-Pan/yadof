"""Run the preregistered 082609 held-out posterior calibration framework.

The runner validates the committed pre-access chain before its single calibration
locator open.  It restores the frozen development-only checkpoints, cross-fits
field spread and applicability calibration by design row, projects every complete
rawData member through the current task cost path, and runs a bounded discrete
qLogNEHVI decision proxy.  It never opens offline-test data, launches a simulator,
implements a complete optimization strategy, or claims CAE performance acceptance.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Mapping, Sequence

import numpy as np
import psutil
from scipy.stats import spearmanr
import torch

import hierarchical_cae_validation as validation
from hierarchical_cae_dataset import load_locator_rows, load_selected_records
from yadof.job_template import JointObjectiveSamples
from yadof.job_template import api as job_template_api
from yadof.optimize.qnehvi_backend import score_discrete_qlognehvi
from yadof.surrogate import (
    CALIBRATED,
    NOT_APPLICABLE,
    SUPPORT_FINITE,
    UNCALIBRATED,
    ApplicabilityCalibration,
    FieldSpreadCalibration,
    PosteriorCalibrationArtifact,
    assess_spread_scale,
    calibration_identity_signature,
    fit_monotone_applicability_calibration,
    select_conservative_spread_scale,
    transform_applicability_members,
)
from yadof.surrogate.hierarchical_cae import checkpoints
from yadof.surrogate.hierarchical_cae import modeling as cae_modeling
from yadof.surrogate.hierarchical_cae.schema import (
    build_schema,
    field_matrices,
    reconstruct_samples,
)
from yadof.surrogate.hierarchical_cae.types import FieldScaler


AUTOMATION_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = AUTOMATION_ROOT.parent
INVENTORY_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi"
    / "schema_inventory.json"
)
PROTOCOL = "yadof.082609.heldout-posterior-calibration"
PROTOCOL_VERSION = 1


def _json(path: Path) -> dict[str, object]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
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


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _model_state_sha256(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        values = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(values.dtype).encode("ascii"))
        digest.update(_canonical_bytes(list(values.shape)))
        digest.update(values.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _finite(value: object) -> float | None:
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _prepare_output(path: Path) -> Path:
    output = path.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"calibration output must be new/empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    return output


def _validate_pre_access(
    *,
    manifest_path: Path,
    checkpoint_summary_path: Path,
    plan_path: Path,
    access_seal_path: Path,
    validation_receipt_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    plan = _json(plan_path)
    seal = _json(access_seal_path)
    receipt = _json(validation_receipt_path)
    manifest = _json(manifest_path)
    checkpoint_summary = _json(checkpoint_summary_path)
    required = {
        "protocol": "yadof.082609.calibration-preregistration",
        "protocol_version": 1,
        "status": "sealed-before-calibration-access",
    }
    for name, expected in required.items():
        if plan.get(name) != expected:
            raise ValueError(f"calibration plan {name} drifted")
    if seal.get("status") != "sealed":
        raise PermissionError("calibration access seal is not sealed")
    if not bool(seal.get("calibration_access_authorized", False)):
        raise PermissionError("calibration access was not authorized")
    if bool(seal.get("offline_test_access_authorized", False)):
        raise PermissionError("082609 seal may not authorize offline-test access")
    bindings = dict(plan["artifact_integrity"])
    expected_hashes = {
        "dataset_manifest_sha256": _sha256(manifest_path),
        "development_checkpoint_summary_sha256": _sha256(
            checkpoint_summary_path
        ),
        "access_seal_sha256": _sha256(access_seal_path),
    }
    for name, actual in expected_hashes.items():
        if str(bindings.get(name)) != actual:
            raise ValueError(f"calibration plan does not bind {name}")
    if str(seal.get("dataset_manifest_sha256")) != expected_hashes[
        "dataset_manifest_sha256"
    ]:
        raise PermissionError("access seal does not bind the dataset manifest")
    calibration_receipt = dict(manifest["partition_locators"]["calibration"])
    frozen_locator = dict(plan["partition"]["calibration_locator"])
    if (
        str(calibration_receipt["sha256"]) != str(frozen_locator["sha256"])
        or int(calibration_receipt["row_count"])
        != int(frozen_locator["row_count"])
        or str(calibration_receipt["path"]) != str(frozen_locator["path"])
    ):
        raise ValueError("calibration locator receipt drifted before access")
    if int(calibration_receipt["row_count"]) != 600:
        raise ValueError("calibration design count drifted")
    if str(checkpoint_summary.get("status")) != (
        "complete-development-only-experimental-performance-not-accepted"
    ):
        raise ValueError("development checkpoint bundle is incomplete")
    if int(checkpoint_summary.get("cell_count", -1)) != 6:
        raise ValueError("development checkpoint cell count drifted")
    if checkpoint_summary.get("access_state") != {
        "development_locator_accessed": True,
        "calibration_locator_accessed": False,
        "offline_test_locator_accessed": False,
        "simulator_launched": False,
    }:
        raise ValueError("development checkpoint access state drifted")
    source_artifacts = dict(bindings["source_artifacts"])
    for relative, expected in source_artifacts.items():
        path = (REPOSITORY_ROOT / str(relative)).resolve()
        if _sha256(path) != str(expected):
            raise ValueError(f"pre-access source artifact drifted: {relative}")
    if receipt.get("status") != "valid-pre-access-chain":
        raise PermissionError("pre-access validation receipt is not valid")
    receipt_bindings = {
        "plan_sha256": _sha256(plan_path),
        "access_seal_sha256": _sha256(access_seal_path),
        "checkpoint_summary_sha256": _sha256(checkpoint_summary_path),
        "dataset_manifest_sha256": _sha256(manifest_path),
    }
    for name, expected in receipt_bindings.items():
        if str(receipt.get(name)) != expected:
            raise PermissionError(f"pre-access validation receipt drifted: {name}")
    commit = str(receipt.get("pre_access_commit", "")).lower()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise PermissionError("pre-access validation receipt lacks a full commit")
    return plan, checkpoint_summary, receipt


@dataclass(slots=True)
class CalibrationCase:
    case_id: str
    workspace: Path
    design_ids: tuple[str, ...]
    parameters: np.ndarray
    samples: tuple[object, ...]
    metadata: tuple[Mapping[str, object], ...]
    schema: object
    matrices: tuple[np.ndarray, ...]
    quality: object
    boundary_mask: np.ndarray


def _load_calibration_case(
    *,
    case_id: str,
    calibration_rows: Sequence[Mapping[str, object]],
    development_rows: Sequence[Mapping[str, object]],
    inventory: Mapping[str, object],
) -> CalibrationCase:
    rows = tuple(
        sorted(
            (row for row in calibration_rows if str(row["case"]) == case_id),
            key=lambda row: str(row["design_id"]),
        )
    )
    if len(rows) != 200 or any(str(row["partition"]) != "calibration" for row in rows):
        raise ValueError(f"{case_id}: calibration partition drifted")
    records = load_selected_records(rows)
    by_id = {
        str(record["locator"]["design_id"]): record for record in records
    }
    ordered = tuple(by_id[str(row["design_id"])] for row in rows)
    samples = tuple(record["sample"] for record in ordered)
    metadata = tuple(record["record_metadata"] for record in ordered)
    parameters = np.ascontiguousarray(
        [record["normalized_variables"] for record in ordered],
        dtype=np.float32,
    )
    case = dict(inventory["cases"][case_id])
    schema = build_schema(
        samples[0], field_layouts=validation._rank3_layouts(case)
    )
    matrices = field_matrices(schema, samples)
    policy = validation._chrono_policy() if case_id == "chrono" else None
    quality = validation.assess_quality(
        policy=policy, samples=samples, record_metadata=metadata
    )
    boundary = np.zeros((len(rows),), dtype=bool)
    if case_id == "chrono":
        train_rows = tuple(
            sorted(
                (
                    row
                    for row in development_rows
                    if str(row["case"]) == case_id
                    and str(row["partition"]) == "train_pool"
                ),
                key=lambda row: int(row["training_rank"]),
            )
        )
        if len(train_rows) != 2000:
            raise ValueError("chrono development train pool drifted")
        train_records = load_selected_records(train_rows)
        train_by_id = {
            str(record["locator"]["design_id"]): record
            for record in train_records
        }
        train_ordered = tuple(
            train_by_id[str(row["design_id"])] for row in train_rows
        )
        train_parameters = np.ascontiguousarray(
            [record["normalized_variables"] for record in train_ordered],
            dtype=np.float32,
        )
        train_samples = tuple(record["sample"] for record in train_ordered)
        train_metadata = tuple(
            record["record_metadata"] for record in train_ordered
        )
        train_quality = validation.assess_quality(
            policy=policy,
            samples=train_samples,
            record_metadata=train_metadata,
        )
        boundary = validation._boundary_mask(
            train_parameters,
            parameters,
            train_quality.applicability_targets,
            tuple(str(row["design_id"]) for row in train_rows),
        )
        del train_records, train_ordered, train_samples, train_metadata
    return CalibrationCase(
        case_id=case_id,
        workspace=Path(str(rows[0]["workspace"])),
        design_ids=tuple(str(row["design_id"]) for row in rows),
        parameters=parameters,
        samples=samples,
        metadata=metadata,
        schema=schema,
        matrices=matrices,
        quality=quality,
        boundary_mask=boundary,
    )


def _cell_receipt(
    summary_path: Path,
    cell: Mapping[str, object],
) -> tuple[Path, dict[str, object]]:
    path = summary_path.parent / str(cell["cell_receipt_path"])
    if _sha256(path) != str(cell["cell_receipt_sha256"]):
        raise ValueError(f"development checkpoint receipt hash drifted: {path}")
    receipt = _json(path)
    if str(receipt["status"]) != (
        "durable-development-only-experimental-performance-not-accepted"
    ):
        raise ValueError("development checkpoint cell is not frozen")
    return path, receipt


def _load_checkpoint(
    *,
    summary_path: Path,
    cell: Mapping[str, object],
    data: CalibrationCase,
    inventory: Mapping[str, object],
    device: torch.device,
):
    receipt_path, receipt = _cell_receipt(summary_path, cell)
    cell_dir = receipt_path.parent
    checkpoint = dict(receipt["checkpoint"])
    manifest_path = cell_dir / str(checkpoint["active_manifest"])
    namespace_path = cell_dir / str(checkpoint["namespace_manifest"])
    model_path = cell_dir / str(checkpoint["model_path"])
    scaler_path = cell_dir / str(checkpoint["scaler_path"])
    expected_hashes = {
        manifest_path: str(checkpoint["active_manifest_sha256"]),
        namespace_path: str(checkpoint["namespace_manifest_sha256"]),
        model_path: str(checkpoint["model_sha256"]),
        scaler_path: str(checkpoint["scaler_sha256"]),
    }
    for path, expected in expected_hashes.items():
        if _sha256(path) != expected:
            raise ValueError(f"checkpoint artifact hash drifted: {path}")
    manifest = checkpoints.validate_manifest_identity(_json(manifest_path))
    if manifest != _json(namespace_path):
        raise ValueError("checkpoint active/namespace manifests drifted")
    if str(manifest["state_signature"]) != str(receipt["state_signature"]):
        raise ValueError("checkpoint state signature drifted")
    groups = tuple(
        tuple(tuple(str(value) for value in selector) for selector in group)
        for group in manifest["schema"]["groups"]
    )
    case = dict(inventory["cases"][data.case_id])
    schema = build_schema(
        data.samples[0],
        groups=groups,
        field_layouts=validation._rank3_layouts(case),
    )
    scalers = []
    with np.load(scaler_path, allow_pickle=False) as stored:
        for field_index, layout in enumerate(schema.layouts):
            mean = np.asarray(
                stored[f"field_{field_index:04d}_mean"], dtype=np.float64
            )
            scale = np.asarray(
                stored[f"field_{field_index:04d}_scale"], dtype=np.float64
            )
            if mean.size != layout.point_count or scale.size != layout.point_count:
                raise ValueError("checkpoint field scalers do not match schema")
            if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(scale)) or np.any(scale <= 0.0):
                raise ValueError("checkpoint field scaler is invalid")
            scalers.append(
                FieldScaler(
                    np.ascontiguousarray(mean), np.ascontiguousarray(scale)
                )
            )
    schema = replace(schema, scalers=tuple(scalers))
    if checkpoints.schema_payload(schema) != dict(manifest["schema"]):
        raise ValueError("checkpoint schema identity drifted")
    policy = validation._chrono_policy() if data.case_id == "chrono" else None
    expected_signature = checkpoints.semantic_state_signature(
        strategy_signature=str(manifest["strategy_signature"]),
        parameter_names=tuple(str(value) for value in manifest["parameter_names"]),
        parameter_definition_signature=dict(
            manifest["parameter_definition_signature"]
        ),
        schema=schema,
        train_cfg=validation.CAETrainConfig(**dict(manifest["train_cfg"])),
        quality_policy=policy,
        torch_version=str(manifest["torch_version"]),
    )
    if expected_signature != str(manifest["state_signature"]):
        raise ValueError("checkpoint semantic state signature is inconsistent")
    model, train_cfg = cae_modeling.load_model_bundle(
        model_path, schema=schema, device=device
    )
    if asdict_safe(train_cfg) != dict(manifest["train_cfg"]):
        raise ValueError("checkpoint model training configuration drifted")
    if _model_state_sha256(model) != str(checkpoint["model_state_sha256"]):
        raise ValueError("checkpoint model state hash drifted")
    return receipt, manifest, schema, model, train_cfg


def asdict_safe(value) -> dict[str, object]:
    from dataclasses import asdict

    return asdict(value)


def _folds(design_ids: Sequence[str], *, seed: int, fold_count: int) -> np.ndarray:
    folds = np.asarray(
        [
            int.from_bytes(
                hashlib.sha256(
                    f"{int(seed)}:{design_id}".encode("utf-8")
                ).digest()[:8],
                "big",
            )
            % int(fold_count)
            for design_id in design_ids
        ],
        dtype=np.int64,
    )
    counts = np.bincount(folds, minlength=int(fold_count))
    if np.any(counts < 2):
        raise ValueError("calibration folds are unexpectedly sparse")
    return folds


def _scaled_members(members: np.ndarray, scales: np.ndarray) -> np.ndarray:
    values = np.asarray(members, dtype=np.float64)
    factors = np.asarray(scales, dtype=np.float64)
    if factors.shape != (values.shape[1],):
        raise ValueError("one spread factor is required per design")
    mean = np.mean(values, axis=0, dtype=np.float64)
    reshape = (1, factors.size) + (1,) * (values.ndim - 2)
    adjusted = mean[None, ...] + factors.reshape(reshape) * (
        values - mean[None, ...]
    )
    adjusted += mean[None, ...] - np.mean(
        adjusted, axis=0, dtype=np.float64
    )[None, ...]
    return np.ascontiguousarray(adjusted, dtype=np.float64)


def _cross_fit_spread(
    *,
    members: np.ndarray,
    truth: np.ndarray,
    folds: np.ndarray,
    candidate_scales: tuple[float, ...],
    target_coverages: tuple[float, ...],
) -> tuple[np.ndarray, float, list[dict[str, object]], tuple[dict[str, object], ...]]:
    design_scales = np.ones((members.shape[1],), dtype=np.float64)
    fold_results = []
    for fold in sorted(set(int(value) for value in folds)):
        fit = folds != fold
        held_out = folds == fold
        scale, table = select_conservative_spread_scale(
            members[:, fit],
            truth[fit],
            candidate_scales=candidate_scales,
            target_coverages=target_coverages,
        )
        design_scales[held_out] = scale
        fold_results.append(
            {
                "fold": fold,
                "fit_design_count": int(np.count_nonzero(fit)),
                "held_out_design_count": int(np.count_nonzero(held_out)),
                "selected_scale": scale,
                "candidate_metrics": list(table),
            }
        )
    final_scale, final_table = select_conservative_spread_scale(
        members,
        truth,
        candidate_scales=candidate_scales,
        target_coverages=target_coverages,
    )
    return (
        _scaled_members(members, design_scales),
        final_scale,
        fold_results,
        final_table,
    )


def _distribution_metrics(
    members: np.ndarray,
    truth: np.ndarray,
    target_coverages: Sequence[float],
) -> dict[str, object]:
    values = np.asarray(members, dtype=np.float64)
    target = np.asarray(truth, dtype=np.float64)
    mean = np.mean(values, axis=0, dtype=np.float64)
    error = mean - target
    coverage = []
    for nominal in target_coverages:
        alpha = (1.0 - float(nominal)) / 2.0
        lower = np.quantile(values, alpha, axis=0)
        upper = np.quantile(values, 1.0 - alpha, axis=0)
        inside = (target >= lower) & (target <= upper)
        design_coverage = inside.reshape(inside.shape[0], -1).mean(axis=1)
        observed = float(np.mean(design_coverage))
        coverage.append(
            {
                "nominal": float(nominal),
                "observed_design_macro": observed,
                "absolute_error": abs(observed - float(nominal)),
                "design_coverage_median": float(np.median(design_coverage)),
            }
        )
    flattened = values.reshape(values.shape[0], values.shape[1], -1)
    target_flat = target.reshape(target.shape[0], -1)
    normalization = math.sqrt(float(target_flat.shape[1]))
    first = np.linalg.norm(
        flattened - target_flat[None, ...], axis=2
    ) / normalization
    pairwise = np.linalg.norm(
        flattened[:, None, ...] - flattened[None, :, ...], axis=3
    ) / normalization
    design_energy = np.mean(first, axis=0) - 0.5 * np.mean(
        pairwise, axis=(0, 1)
    )
    return {
        "mean_standardized_mae": float(np.mean(np.abs(error))),
        "mean_standardized_rmse": float(np.sqrt(np.mean(np.square(error)))),
        "coverage": coverage,
        "mean_absolute_coverage_error": float(
            np.mean([item["absolute_error"] for item in coverage])
        ),
        "energy_score_design_macro": float(np.mean(design_energy)),
        "energy_score_design_median": float(np.median(design_energy)),
    }


def _correlation_metrics(
    truth_fields: Sequence[np.ndarray],
    member_fields: Sequence[np.ndarray],
) -> dict[str, object]:
    true_summary = np.stack(
        [values.reshape(values.shape[0], -1).mean(axis=1) for values in truth_fields],
        axis=1,
    )
    member_summary = np.stack(
        [
            values.reshape(values.shape[0], values.shape[1], -1).mean(axis=2)
            for values in member_fields
        ],
        axis=2,
    )
    field_count = true_summary.shape[1]
    if field_count == 1:
        return {
            "field_summary_definition": "standardized-spatial-mean",
            "correlation_mae": 0.0,
            "covariance_mae": 0.0,
            "field_count": 1,
        }
    true_correlation = np.nan_to_num(
        np.corrcoef(true_summary, rowvar=False), nan=0.0
    )
    true_covariance = np.cov(true_summary, rowvar=False)
    correlations = []
    covariances = []
    for draw in member_summary:
        correlations.append(
            np.nan_to_num(np.corrcoef(draw, rowvar=False), nan=0.0)
        )
        covariances.append(np.cov(draw, rowvar=False))
    mean_correlation = np.mean(correlations, axis=0)
    mean_covariance = np.mean(covariances, axis=0)
    upper = np.triu_indices(field_count, k=1)
    covariance_scale = max(
        float(np.mean(np.abs(true_covariance[upper]))), 1.0e-12
    )
    return {
        "field_summary_definition": "standardized-spatial-mean",
        "correlation_mae": float(
            np.mean(np.abs(mean_correlation[upper] - true_correlation[upper]))
        ),
        "covariance_mae": float(
            np.mean(np.abs(mean_covariance[upper] - true_covariance[upper]))
            / covariance_scale
        ),
        "field_count": field_count,
    }


def _rawdata_metrics(
    *,
    schema,
    truth_fields: Sequence[np.ndarray],
    raw_fields: Sequence[np.ndarray],
    calibrated_fields: Sequence[np.ndarray],
    target_coverages: Sequence[float],
) -> dict[str, object]:
    fields = []
    for layout, truth, raw, calibrated in zip(
        schema.layouts,
        truth_fields,
        raw_fields,
        calibrated_fields,
    ):
        raw_metrics = _distribution_metrics(raw, truth, target_coverages)
        calibrated_metrics = _distribution_metrics(
            calibrated, truth, target_coverages
        )
        fields.append(
            {
                "selector": list(layout.selector),
                "point_count": int(layout.point_count),
                "uncalibrated": raw_metrics,
                "cross_fitted_calibrated": calibrated_metrics,
                "ensemble_mean_shift_max_abs": float(
                    np.max(
                        np.abs(
                            np.mean(calibrated, axis=0, dtype=np.float64)
                            - np.mean(raw, axis=0, dtype=np.float64)
                        )
                    )
                ),
            }
        )
    raw_correlation = _correlation_metrics(truth_fields, raw_fields)
    calibrated_correlation = _correlation_metrics(
        truth_fields, calibrated_fields
    )
    return {
        "fields": fields,
        "field_macro": {
            "uncalibrated_mean_absolute_coverage_error": float(
                np.mean(
                    [
                        field["uncalibrated"][
                            "mean_absolute_coverage_error"
                        ]
                        for field in fields
                    ]
                )
            ),
            "calibrated_mean_absolute_coverage_error": float(
                np.mean(
                    [
                        field["cross_fitted_calibrated"][
                            "mean_absolute_coverage_error"
                        ]
                        for field in fields
                    ]
                )
            ),
            "uncalibrated_energy_score": float(
                np.mean(
                    [
                        field["uncalibrated"][
                            "energy_score_design_macro"
                        ]
                        for field in fields
                    ]
                )
            ),
            "calibrated_energy_score": float(
                np.mean(
                    [
                        field["cross_fitted_calibrated"][
                            "energy_score_design_macro"
                        ]
                        for field in fields
                    ]
                )
            ),
            "ensemble_mean_shift_max_abs": max(
                field["ensemble_mean_shift_max_abs"] for field in fields
            ),
        },
        "cross_field_structure": {
            "uncalibrated": raw_correlation,
            "cross_fitted_calibrated": calibrated_correlation,
            "member_pairing_preserved": True,
            "field_or_objective_draw_reordering": False,
        },
    }


def _project_members(
    *,
    schema,
    fields: Sequence[np.ndarray],
    workspace: Path,
    parameters: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, object]]]:
    member_count = fields[0].shape[0]
    objective_count = job_template_api.get_objective_count(workspace)
    costs = np.full(
        (member_count, len(parameters), objective_count), np.nan, dtype=np.float64
    )
    valid = np.zeros((member_count, len(parameters)), dtype=bool)
    resources = []
    process = psutil.Process()
    for member in range(member_count):
        before = int(process.memory_info().rss)
        reconstruction_started = time.perf_counter()
        try:
            samples = reconstruct_samples(
                schema, tuple(values[member] for values in fields)
            )
            reconstruction_error = None
        except Exception as exc:  # noqa: BLE001 - evidence retains bounded failure.
            samples = ()
            reconstruction_error = (
                f"{type(exc).__name__}: {str(exc)[:512]}"
            )
        reconstruction_wall = time.perf_counter() - reconstruction_started
        projection_started = time.perf_counter()
        projection_error = None
        if samples:
            try:
                projected = validation._costs(workspace, parameters, samples)
                if projected.shape != (len(parameters), objective_count):
                    raise ValueError("current-cost projection shape drifted")
                costs[member] = projected
                valid[member] = np.all(np.isfinite(projected), axis=1)
            except Exception as exc:  # noqa: BLE001 - bounded benchmark evidence.
                projection_error = (
                    f"{type(exc).__name__}: {str(exc)[:512]}"
                )
        projection_wall = time.perf_counter() - projection_started
        after = int(process.memory_info().rss)
        resources.append(
            {
                "member_index": member,
                "rawdata_reconstruction_wall_sec": reconstruction_wall,
                "current_calc_cost_projection_wall_sec": projection_wall,
                "rss_before_bytes": before,
                "rss_after_bytes": after,
                "rss_observed_max_bytes": max(before, after),
                "reconstruction_error": reconstruction_error,
                "projection_error": projection_error,
                "valid_design_count": int(np.count_nonzero(valid[member])),
            }
        )
    return costs, valid, resources


def _pareto_mask(values: np.ndarray) -> np.ndarray:
    costs = np.asarray(values, dtype=np.float64)
    mask = np.ones((costs.shape[0],), dtype=bool)
    for index in range(costs.shape[0]):
        for other in range(costs.shape[0]):
            if other == index:
                continue
            if np.all(costs[other] <= costs[index]) and np.any(
                costs[other] < costs[index]
            ):
                mask[index] = False
                break
    return mask


def _pareto_quality(truth: np.ndarray, predicted: np.ndarray) -> dict[str, object]:
    true_mask = _pareto_mask(truth)
    predicted_mask = _pareto_mask(predicted)
    intersection = int(np.count_nonzero(true_mask & predicted_mask))
    union = int(np.count_nonzero(true_mask | predicted_mask))
    return {
        "true_pareto_count": int(np.count_nonzero(true_mask)),
        "predicted_pareto_count": int(np.count_nonzero(predicted_mask)),
        "precision": float(
            intersection / max(1, int(np.count_nonzero(predicted_mask)))
        ),
        "recall": float(
            intersection / max(1, int(np.count_nonzero(true_mask)))
        ),
        "jaccard": float(intersection / max(1, union)),
        "pairwise_consistency": validation._pareto_consistency(truth, predicted),
    }


def _cost_distribution_metrics(
    *,
    members: np.ndarray,
    valid: np.ndarray,
    truth: np.ndarray,
    target_coverages: Sequence[float],
) -> dict[str, object]:
    complete = np.all(valid, axis=0) & np.all(np.isfinite(truth), axis=1)
    if not np.any(complete):
        return {
            "complete_design_count": 0,
            "invalid_projection_count": int(valid.size - np.count_nonzero(valid)),
            "mean_absolute_coverage_error": None,
            "energy_score": None,
            "spearman_per_objective": [],
            "pareto": None,
        }
    selected = members[:, complete]
    target = truth[complete]
    distribution = _distribution_metrics(selected, target, target_coverages)
    mean = np.mean(selected, axis=0, dtype=np.float64)
    return {
        "complete_design_count": int(np.count_nonzero(complete)),
        "invalid_projection_count": int(valid.size - np.count_nonzero(valid)),
        "coverage": distribution["coverage"],
        "mean_absolute_coverage_error": distribution[
            "mean_absolute_coverage_error"
        ],
        "energy_score": distribution["energy_score_design_macro"],
        "mae_per_objective": np.mean(np.abs(mean - target), axis=0).tolist(),
        "rmse_per_objective": np.sqrt(
            np.mean(np.square(mean - target), axis=0)
        ).tolist(),
        "spearman_per_objective": [
            _finite(spearmanr(target[:, index], mean[:, index]).statistic)
            for index in range(target.shape[1])
        ],
        "pareto": _pareto_quality(target, mean),
    }


def _hypervolume(costs: np.ndarray) -> float:
    from botorch.utils.multi_objective.hypervolume import Hypervolume

    values = np.asarray(costs, dtype=np.float64)
    reference = -torch.ones((values.shape[1],), dtype=torch.float64)
    calculator = Hypervolume(ref_point=reference)
    return float(
        calculator.compute(torch.as_tensor(-values, dtype=torch.float64))
    )


def _acquisition_proxy_one(
    *,
    members: np.ndarray,
    valid: np.ndarray,
    truth: np.ndarray,
    parameters: np.ndarray,
    design_ids: Sequence[str],
    objective_names: Sequence[str],
    seed: int,
    calibrated: bool,
) -> dict[str, object]:
    in_contract = (
        np.all(np.isfinite(truth), axis=1)
        & np.all((truth >= 0.0) & (truth <= 1.0), axis=1)
        & np.all(valid, axis=0)
        & np.all(np.isfinite(members), axis=(0, 2))
        & np.all((members >= 0.0) & (members <= 1.0), axis=(0, 2))
    )
    ordered = sorted(
        np.flatnonzero(in_contract),
        key=lambda index: hashlib.sha256(
            f"{int(seed)}:{design_ids[int(index)]}".encode("utf-8")
        ).digest(),
    )
    baseline_count = min(32, max(8, len(ordered) // 4))
    candidate_count = min(96, len(ordered) - baseline_count)
    if baseline_count < 8 or candidate_count < 8:
        raise ValueError("insufficient fully valid calibration rows for acquisition proxy")
    baseline_indices = np.asarray(ordered[:baseline_count], dtype=np.int64)
    candidate_indices = np.asarray(
        ordered[baseline_count : baseline_count + candidate_count], dtype=np.int64
    )
    candidate_members = np.ascontiguousarray(
        members[:, candidate_indices], dtype=np.float64
    )
    population = tuple(
        tuple(float(value) for value in row)
        for row in parameters[candidate_indices]
    )
    diagnostics = {
        "posterior_kind": "empirical_predictor_ensemble",
        "support_kind": SUPPORT_FINITE,
        "unique_support": int(members.shape[0]),
        "draw_sources": [
            f"hierarchical-cae-predictor-{index:04d}"
            for index in range(members.shape[0])
        ],
        "calibrated": bool(calibrated),
        "observation_noise_included": False,
        "performance_status": "experimental-performance-not-accepted",
    }
    samples = JointObjectiveSamples.from_arrays(
        cost_samples=candidate_members,
        valid_mask=np.ones(candidate_members.shape[:2], dtype=bool),
        draw_ids=tuple(
            f"calibration-member-{index:04d}"
            for index in range(members.shape[0])
        ),
        normalized_population=population,
        objective_names=tuple(str(value) for value in objective_names),
        source_diagnostics=diagnostics,
    )
    q1_batches = tuple((index,) for index in range(candidate_count))
    q2_batches = tuple(
        (index, (index + 1 + index // max(1, candidate_count // 8)) % candidate_count)
        for index in range(min(64, candidate_count))
        if index != (index + 1 + index // max(1, candidate_count // 8)) % candidate_count
    )
    batches = (*q1_batches, *q2_batches)
    scored = score_discrete_qlognehvi(
        baseline_population=tuple(
            tuple(float(value) for value in row)
            for row in parameters[baseline_indices]
        ),
        baseline_costs=truth[baseline_indices],
        candidate_samples=samples,
        candidate_batches=batches,
        reference_point=tuple(1.0 for _ in objective_names),
        seed=int(seed),
        device="cpu",
        minimum_unique_support=int(members.shape[0]),
        low_support_policy="reject",
    )
    baseline_hv = _hypervolume(truth[baseline_indices])
    true_values = []
    candidate_truth = truth[candidate_indices]
    for batch in batches:
        true_values.append(
            max(
                0.0,
                _hypervolume(
                    np.concatenate(
                        (truth[baseline_indices], candidate_truth[list(batch)]),
                        axis=0,
                    )
                )
                - baseline_hv,
            )
        )
    acquisition_values = np.asarray(
        scored.log_acquisition_values, dtype=np.float64
    )
    true_values_array = np.asarray(true_values, dtype=np.float64)

    def summarize(start: int, stop: int) -> dict[str, object]:
        predicted = acquisition_values[start:stop]
        actual = true_values_array[start:stop]
        selected = int(np.argmax(predicted))
        oracle = float(np.max(actual))
        selected_value = float(actual[selected])
        return {
            "batch_count": int(stop - start),
            "selected_batch": list(batches[start + selected]),
            "selected_true_hypervolume_improvement": selected_value,
            "oracle_true_hypervolume_improvement": oracle,
            "selected_to_oracle_efficiency": (
                1.0 if oracle <= 1.0e-15 else selected_value / oracle
            ),
            "spearman_acquisition_vs_true_hvi": _finite(
                spearmanr(predicted, actual).statistic
            ),
        }

    return {
        "proxy_only_not_complete_strategy": True,
        "same_real_evaluation_budget_within_each_q": True,
        "calibration_design_truth_used_only_for_heldout_decision_evidence": True,
        "baseline_design_count": baseline_count,
        "candidate_design_count": candidate_count,
        "excluded_design_count": int(len(design_ids) - len(ordered)),
        "q1": summarize(0, len(q1_batches)),
        "q2": summarize(len(q1_batches), len(batches)),
        "backend_diagnostics": dict(scored.diagnostics),
    }


def _binary_metrics(labels: np.ndarray, members: np.ndarray) -> dict[str, object]:
    means = np.mean(members, axis=0, dtype=np.float64)
    metrics = validation._calibration_metrics(labels, means)
    spread = np.std(members, axis=0, dtype=np.float64)
    metrics["member_epistemic_spread"] = {
        "mean": float(np.mean(spread)),
        "median": float(np.median(spread)),
        "q90": float(np.quantile(spread, 0.9)),
        "max": float(np.max(spread)),
    }
    return metrics


def _applicability_calibration(
    *,
    data: CalibrationCase,
    members: np.ndarray,
    folds: np.ndarray,
    minimum_class_count: int,
) -> tuple[dict[str, object], dict[str, object]]:
    policy_identity = (
        {"enabled": False, "default": "uniform-smooth"}
        if data.case_id != "chrono"
        else validation._chrono_policy().as_dict()
    )
    policy_signature = calibration_identity_signature(policy_identity)
    if data.case_id != "chrono":
        calibration = ApplicabilityCalibration(
            status=NOT_APPLICABLE,
            policy_signature=policy_signature,
            fit_design_count=0,
            positive_count=0,
            negative_count=0,
            minimum_class_count=minimum_class_count,
            failure_reason="quality policy/regime head is not configured for this case",
        )
        return (
            {
                "status": NOT_APPLICABLE,
                "reason": calibration.failure_reason,
                "policy_identity": policy_identity,
            },
            calibration.as_dict(),
        )
    labels = np.asarray(data.quality.applicability_targets, dtype=np.float64)
    positives = int(np.count_nonzero(labels == 1.0))
    negatives = int(np.count_nonzero(labels == 0.0))
    oof = np.empty_like(members, dtype=np.float64)
    fold_results = []
    fit_failure = None
    for fold in sorted(set(int(value) for value in folds)):
        fit = folds != fold
        held_out = folds == fold
        try:
            slope, intercept, diagnostics = (
                fit_monotone_applicability_calibration(
                    members[:, fit],
                    labels[fit],
                    minimum_class_count=minimum_class_count,
                )
            )
            oof[:, held_out] = transform_applicability_members(
                members[:, held_out], slope=slope, intercept=intercept
            )
            fold_results.append(
                {
                    "fold": fold,
                    "fit_design_count": int(np.count_nonzero(fit)),
                    "held_out_design_count": int(np.count_nonzero(held_out)),
                    "slope": slope,
                    "intercept": intercept,
                    "fit_diagnostics": diagnostics,
                }
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            fit_failure = f"{type(exc).__name__}: {str(exc)[:512]}"
            break
    final_slope = final_intercept = None
    final_diagnostics = None
    if fit_failure is None:
        try:
            final_slope, final_intercept, final_diagnostics = (
                fit_monotone_applicability_calibration(
                    members,
                    labels,
                    minimum_class_count=minimum_class_count,
                )
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            fit_failure = f"{type(exc).__name__}: {str(exc)[:512]}"
    if fit_failure is not None:
        oof = np.asarray(members, dtype=np.float64)
    raw_metrics = _binary_metrics(labels, members)
    calibrated_metrics = _binary_metrics(labels, oof)
    strata = {}
    regime_values = np.asarray(data.quality.design_regimes, dtype="U16")
    masks = {
        "smooth": regime_values == "smooth",
        "chatter": regime_values == "chatter",
        "failure": regime_values == "failure",
        "boundary": np.asarray(data.boundary_mask, dtype=bool),
    }
    for name, mask in masks.items():
        if not np.any(mask):
            strata[name] = {"count": 0, "uncalibrated": None, "calibrated": None}
            continue
        strata[name] = {
            "count": int(np.count_nonzero(mask)),
            "uncalibrated": _binary_metrics(labels[mask], members[:, mask]),
            "cross_fitted_calibrated": _binary_metrics(labels[mask], oof[:, mask]),
        }
    result = {
        "status": "fit-complete" if fit_failure is None else UNCALIBRATED,
        "fit_failure": fit_failure,
        "policy_identity": policy_identity,
        "label_counts": {
            "smooth_positive": positives,
            "chatter_or_failure_negative": negatives,
        },
        "folds": fold_results,
        "final_fit": {
            "slope": final_slope,
            "intercept": final_intercept,
            "diagnostics": final_diagnostics,
        },
        "uncalibrated": raw_metrics,
        "cross_fitted_calibrated": calibrated_metrics,
        "strata": strata,
        "member_pairing_preserved": True,
        "observation_noise_included": False,
    }
    candidate = {
        "policy_signature": policy_signature,
        "fit_design_count": len(labels),
        "positive_count": positives,
        "negative_count": negatives,
        "minimum_class_count": minimum_class_count,
        "slope": final_slope,
        "intercept": final_intercept,
        "fit_failure": fit_failure,
    }
    return result, candidate


def _mean_finite(values: Sequence[object]) -> float | None:
    selected = [float(value) for value in values if value is not None]
    return float(np.mean(selected)) if selected else None


def _evaluate_gates(
    *,
    thresholds: Mapping[str, object],
    rawdata: Mapping[str, object],
    cost: Mapping[str, object],
    acquisition: Mapping[str, object],
    applicability: Mapping[str, object],
) -> tuple[dict[str, object], bool, bool]:
    raw_thresholds = dict(thresholds["rawdata"])
    raw_macro = dict(rawdata["field_macro"])
    raw_structure = dict(rawdata["cross_field_structure"])
    raw_correlation = dict(raw_structure["uncalibrated"])
    calibrated_correlation = dict(raw_structure["cross_fitted_calibrated"])
    raw_checks = {
        "coverage_error_nonworse": float(
            raw_macro["calibrated_mean_absolute_coverage_error"]
        )
        <= float(raw_macro["uncalibrated_mean_absolute_coverage_error"])
        + float(raw_thresholds["max_coverage_error_increase"]),
        "energy_score_bounded": float(raw_macro["calibrated_energy_score"])
        <= float(raw_macro["uncalibrated_energy_score"])
        * float(raw_thresholds["max_energy_score_ratio"]),
        "correlation_structure_bounded": float(
            calibrated_correlation["correlation_mae"]
        )
        <= float(raw_correlation["correlation_mae"])
        + float(raw_thresholds["max_correlation_mae_increase"]),
        "mean_unchanged": float(raw_macro["ensemble_mean_shift_max_abs"])
        <= float(raw_thresholds["max_ensemble_mean_shift_abs"]),
        "pairing_preserved": bool(raw_structure["member_pairing_preserved"]),
    }
    cost_thresholds = dict(thresholds["cost"])
    raw_cost = dict(cost["uncalibrated"])
    calibrated_cost = dict(cost["cross_fitted_calibrated"])
    raw_rank = _mean_finite(raw_cost["spearman_per_objective"])
    calibrated_rank = _mean_finite(calibrated_cost["spearman_per_objective"])
    cost_checks = {
        "projection_failures_bounded": int(
            calibrated_cost["invalid_projection_count"]
        )
        <= int(cost_thresholds["max_invalid_projection_count"]),
        "coverage_error_bounded": float(
            calibrated_cost["mean_absolute_coverage_error"]
        )
        <= float(raw_cost["mean_absolute_coverage_error"])
        + float(cost_thresholds["max_coverage_error_increase"]),
        "rank_quality_bounded": calibrated_rank is not None
        and raw_rank is not None
        and calibrated_rank
        >= raw_rank - float(cost_thresholds["max_mean_spearman_drop"]),
        "pareto_quality_bounded": float(
            calibrated_cost["pareto"]["pairwise_consistency"]
        )
        >= float(raw_cost["pareto"]["pairwise_consistency"])
        - float(cost_thresholds["max_pareto_consistency_drop"]),
    }
    acquisition_thresholds = dict(thresholds["acquisition_proxy"])
    raw_acq = dict(acquisition["uncalibrated"])
    calibrated_acq = dict(acquisition["cross_fitted_calibrated"])
    acquisition_checks = {}
    for q in ("q1", "q2"):
        raw_q = dict(raw_acq[q])
        calibrated_q = dict(calibrated_acq[q])
        acquisition_checks[f"{q}_decision_efficiency_bounded"] = float(
            calibrated_q["selected_to_oracle_efficiency"]
        ) >= float(raw_q["selected_to_oracle_efficiency"]) - float(
            acquisition_thresholds["max_selected_to_oracle_efficiency_drop"]
        )
        raw_spearman = raw_q["spearman_acquisition_vs_true_hvi"]
        calibrated_spearman = calibrated_q[
            "spearman_acquisition_vs_true_hvi"
        ]
        acquisition_checks[f"{q}_ranking_bounded"] = (
            raw_spearman is not None
            and calibrated_spearman is not None
            and float(calibrated_spearman)
            >= float(raw_spearman)
            - float(acquisition_thresholds["max_spearman_drop"])
        )
    rawdata_passed = all(raw_checks.values()) and all(cost_checks.values()) and all(
        acquisition_checks.values()
    )
    applicability_checks = {}
    applicability_passed = False
    if applicability.get("status") == NOT_APPLICABLE:
        applicability_checks["not_applicable_is_explicit"] = True
    elif applicability.get("fit_failure") is not None:
        applicability_checks["fit_completed"] = False
    else:
        app_thresholds = dict(thresholds["applicability"])
        raw_app = dict(applicability["uncalibrated"])
        calibrated_app = dict(applicability["cross_fitted_calibrated"])
        applicability_checks = {
            "class_support": int(
                applicability["label_counts"]["smooth_positive"]
            )
            >= int(app_thresholds["minimum_class_count"])
            and int(
                applicability["label_counts"][
                    "chatter_or_failure_negative"
                ]
            )
            >= int(app_thresholds["minimum_class_count"]),
            "brier_nonworse": float(calibrated_app["brier_score"])
            <= float(raw_app["brier_score"])
            + float(app_thresholds["max_brier_increase"]),
            "ece_bounded": float(
                calibrated_app["expected_calibration_error"]
            )
            <= float(raw_app["expected_calibration_error"])
            + float(app_thresholds["max_ece_increase"]),
            "auprc_bounded": float(calibrated_app["auprc"])
            >= float(raw_app["auprc"])
            - float(app_thresholds["max_auprc_drop"]),
            "member_pairing_preserved": bool(
                applicability["member_pairing_preserved"]
            ),
        }
        applicability_passed = all(applicability_checks.values())
    return (
        {
            "rawdata": raw_checks,
            "current_cost": cost_checks,
            "acquisition_proxy": acquisition_checks,
            "applicability": applicability_checks,
            "rawdata_calibration_passed": rawdata_passed,
            "applicability_calibration_passed": applicability_passed,
            "performance_accepted": False,
            "architecture_promoted": False,
        },
        rawdata_passed,
        applicability_passed,
    )


def _run_cell(
    *,
    output_dir: Path,
    summary_path: Path,
    cell: Mapping[str, object],
    data: CalibrationCase,
    inventory: Mapping[str, object],
    plan: Mapping[str, object],
    dataset_manifest_sha256: str,
    calibration_locator_sha256: str,
    preregistration_sha256: str,
    checkpoint_summary_sha256: str,
) -> dict[str, object]:
    cell_id = str(cell["cell_id"])
    print(f"CALIBRATION_START {cell_id}", flush=True)
    started = time.perf_counter()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    receipt, manifest, schema, model, train_cfg = _load_checkpoint(
        summary_path=summary_path,
        cell=cell,
        data=data,
        inventory=inventory,
        device=device,
    )
    with validation._ResourceMonitor() as inference_monitor:
        raw_fields_float, applicability_members, _residual = (
            cae_modeling.predict_hierarchical_members(
                model=model,
                parameters=data.parameters,
                device=device,
                batch_size=train_cfg.inference_batch_size,
            )
        )
    raw_fields = tuple(
        np.asarray(values, dtype=np.float64) for values in raw_fields_float
    )
    truth_fields = tuple(
        scaler.transform(matrix).reshape((len(data.parameters),) + layout.shape)
        for scaler, matrix, layout in zip(
            schema.scalers, data.matrices, schema.layouts
        )
    )
    calibration_config = dict(plan["calibration"])
    candidate_scales = tuple(
        float(value) for value in calibration_config["candidate_field_scales"]
    )
    target_coverages = tuple(
        float(value) for value in calibration_config["target_coverages"]
    )
    fold_count = int(calibration_config["fold_count"])
    seed = int(calibration_config["seed"])
    folds = _folds(data.design_ids, seed=seed, fold_count=fold_count)
    calibrated_fields = []
    field_fit_results = []
    final_scales = []
    for layout, raw, truth in zip(schema.layouts, raw_fields, truth_fields):
        calibrated, final_scale, fold_results, final_table = _cross_fit_spread(
            members=raw,
            truth=truth,
            folds=folds,
            candidate_scales=candidate_scales,
            target_coverages=target_coverages,
        )
        calibrated_fields.append(calibrated)
        final_scales.append(final_scale)
        field_fit_results.append(
            {
                "selector": list(layout.selector),
                "folds": fold_results,
                "final_selected_scale": final_scale,
                "final_candidate_metrics": list(final_table),
            }
        )
    calibrated_fields_tuple = tuple(calibrated_fields)
    rawdata_metrics = _rawdata_metrics(
        schema=schema,
        truth_fields=truth_fields,
        raw_fields=raw_fields,
        calibrated_fields=calibrated_fields_tuple,
        target_coverages=target_coverages,
    )
    true_cost_started = time.perf_counter()
    true_cost = validation._costs(
        data.workspace, data.parameters, data.samples
    )
    true_cost_wall = time.perf_counter() - true_cost_started
    raw_cost, raw_valid, raw_projection_resources = _project_members(
        schema=schema,
        fields=raw_fields,
        workspace=data.workspace,
        parameters=data.parameters,
    )
    calibrated_cost, calibrated_valid, calibrated_projection_resources = (
        _project_members(
            schema=schema,
            fields=calibrated_fields_tuple,
            workspace=data.workspace,
            parameters=data.parameters,
        )
    )
    cost_metrics = {
        "current_cost_path": "task calc_cost.py via yadof.job_template.calculate_cost",
        "true_cost_projection_wall_sec": true_cost_wall,
        "uncalibrated": _cost_distribution_metrics(
            members=raw_cost,
            valid=raw_valid,
            truth=true_cost,
            target_coverages=target_coverages,
        ),
        "cross_fitted_calibrated": _cost_distribution_metrics(
            members=calibrated_cost,
            valid=calibrated_valid,
            truth=true_cost,
            target_coverages=target_coverages,
        ),
        "uncalibrated_per_draw_resources": raw_projection_resources,
        "calibrated_per_draw_resources": calibrated_projection_resources,
        "member_pairing_preserved": True,
        "direct_cost_fitting_used": False,
    }
    objective_names = job_template_api.get_objective_names(data.workspace)
    acquisition = {
        "uncalibrated": _acquisition_proxy_one(
            members=raw_cost,
            valid=raw_valid,
            truth=true_cost,
            parameters=data.parameters,
            design_ids=data.design_ids,
            objective_names=objective_names,
            seed=seed,
            calibrated=False,
        ),
        "cross_fitted_calibrated": _acquisition_proxy_one(
            members=calibrated_cost,
            valid=calibrated_valid,
            truth=true_cost,
            parameters=data.parameters,
            design_ids=data.design_ids,
            objective_names=objective_names,
            seed=seed,
            calibrated=True,
        ),
        "formal_same_budget_optimization_benchmark_deferred_to_082612": True,
        "complete_qnehvi_strategy_implemented": False,
    }
    applicability_result, applicability_candidate = _applicability_calibration(
        data=data,
        members=np.asarray(applicability_members, dtype=np.float64),
        folds=folds,
        minimum_class_count=int(
            plan["thresholds"]["applicability"]["minimum_class_count"]
        ),
    )
    gates, rawdata_passed, applicability_passed = _evaluate_gates(
        thresholds=dict(plan["thresholds"]),
        rawdata=rawdata_metrics,
        cost=cost_metrics,
        acquisition=acquisition,
        applicability=applicability_result,
    )
    checkpoint_hashes = {
        "manifest": str(receipt["checkpoint"]["active_manifest_sha256"]),
        "namespace_manifest": str(
            receipt["checkpoint"]["namespace_manifest_sha256"]
        ),
        "model": str(receipt["checkpoint"]["model_sha256"]),
        "model_state": str(receipt["checkpoint"]["model_state_sha256"]),
        "scalers": str(receipt["checkpoint"]["scaler_sha256"]),
        "cell_receipt": str(cell["cell_receipt_sha256"]),
    }
    rawdata_failure_reasons = ()
    artifact_scales = final_scales
    if not rawdata_passed:
        rawdata_failure_reasons = tuple(
            f"{section}.{name}"
            for section in ("rawdata", "current_cost", "acquisition_proxy")
            for name, passed in dict(gates[section]).items()
            if not passed
        )
        artifact_scales = [1.0 for _ in final_scales]
    field_calibrations = tuple(
        FieldSpreadCalibration(
            selector=layout.selector,
            scale=float(scale),
            fit_design_count=len(data.design_ids),
            candidate_scales=candidate_scales,
            target_coverages=target_coverages,
        )
        for layout, scale in zip(schema.layouts, artifact_scales)
    )
    policy_identity = dict(applicability_result["policy_identity"])
    if applicability_result["status"] == NOT_APPLICABLE:
        applicability_artifact = ApplicabilityCalibration.from_mapping(
            applicability_candidate
        )
    elif applicability_passed:
        applicability_artifact = ApplicabilityCalibration(
            status=CALIBRATED,
            policy_signature=str(applicability_candidate["policy_signature"]),
            fit_design_count=int(applicability_candidate["fit_design_count"]),
            positive_count=int(applicability_candidate["positive_count"]),
            negative_count=int(applicability_candidate["negative_count"]),
            minimum_class_count=int(
                applicability_candidate["minimum_class_count"]
            ),
            slope=float(applicability_candidate["slope"]),
            intercept=float(applicability_candidate["intercept"]),
        )
    else:
        failed_checks = tuple(
            name
            for name, passed in dict(gates["applicability"]).items()
            if not passed
        )
        reason = applicability_candidate.get("fit_failure") or (
            "frozen applicability gates failed: " + ", ".join(failed_checks)
        )
        applicability_artifact = ApplicabilityCalibration(
            status=UNCALIBRATED,
            policy_signature=str(applicability_candidate["policy_signature"]),
            fit_design_count=int(applicability_candidate["fit_design_count"]),
            positive_count=int(applicability_candidate["positive_count"]),
            negative_count=int(applicability_candidate["negative_count"]),
            minimum_class_count=int(
                applicability_candidate["minimum_class_count"]
            ),
            failure_reason=str(reason),
        )
    evidence_payload = {
        "rawdata_metrics": rawdata_metrics,
        "cost_metrics": cost_metrics,
        "acquisition_proxy": acquisition,
        "applicability": applicability_result,
        "gates": gates,
    }
    evidence_sha256 = _json_sha256(evidence_payload)
    artifact = PosteriorCalibrationArtifact(
        artifact_id=f"{data.case_id}-train-{int(cell['train_size'])}-seed-{int(cell['seed'])}",
        rawdata_status=(CALIBRATED if rawdata_passed else UNCALIBRATED),
        state_signature=str(receipt["state_signature"]),
        strategy_signature=str(receipt["strategy_signature"]),
        schema_signature=str(receipt["schema_signature"]),
        posterior_kind="empirical_predictor_ensemble",
        support_kind=SUPPORT_FINITE,
        unique_support=int(manifest["member_count"]),
        checkpoint_hashes=checkpoint_hashes,
        training_provenance_sha256=str(
            receipt["training_provenance_sha256"]
        ),
        dataset_manifest_sha256=dataset_manifest_sha256,
        calibration_locator_sha256=calibration_locator_sha256,
        calibration_design_ids_sha256=_json_sha256(list(data.design_ids)),
        calibration_design_count=len(data.design_ids),
        fold_count=fold_count,
        seed=seed,
        field_calibrations=field_calibrations,
        applicability=applicability_artifact,
        policy_identity=policy_identity,
        label_head_loss_identity=dict(
            receipt["policy_label_head_loss_identity"]
        ),
        evidence={
            "calibration_evidence_sha256": evidence_sha256,
            "preregistration_sha256": preregistration_sha256,
            "development_checkpoint_summary_sha256": checkpoint_summary_sha256,
        },
        failure_reasons=rawdata_failure_reasons,
    )
    artifact_path = output_dir / "artifacts" / f"{cell_id}.json"
    artifact.write(artifact_path)
    result = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "status": "complete-experimental-performance-not-accepted",
        "cell_id": cell_id,
        "case": data.case_id,
        "train_size": int(cell["train_size"]),
        "seed": int(cell["seed"]),
        "checkpoint_binding": checkpoint_hashes,
        "state_signature": str(receipt["state_signature"]),
        "strategy_signature": str(receipt["strategy_signature"]),
        "schema_signature": str(receipt["schema_signature"]),
        "training_provenance_sha256": str(
            receipt["training_provenance_sha256"]
        ),
        "calibration_design_ids_sha256": _json_sha256(list(data.design_ids)),
        "fold_assignment_sha256": _json_sha256(folds.tolist()),
        "fold_counts": np.bincount(folds, minlength=fold_count).tolist(),
        "field_calibration_fit": field_fit_results,
        "rawdata_metrics": rawdata_metrics,
        "current_cost_metrics": cost_metrics,
        "acquisition_proxy": acquisition,
        "applicability_calibration": applicability_result,
        "frozen_gate_decision": gates,
        "artifact": {
            "path": str(artifact_path.relative_to(output_dir)),
            "sha256": _sha256(artifact_path),
            "self_sha256": artifact.sha256,
            "rawdata_status": artifact.rawdata_status,
            "applicability_status": artifact.applicability.status,
            "performance_status": artifact.performance_status,
            "transferable": artifact.transferable,
        },
        "resources": {
            "posterior_all_member_inference": inference_monitor.payload(),
            "per_draw_rawdata_and_cost": {
                "uncalibrated": raw_projection_resources,
                "calibrated": calibrated_projection_resources,
            },
            "cell_wall_sec": float(time.perf_counter() - started),
        },
        "observation_noise_included": False,
        "calibration_locator_accessed": True,
        "offline_test_locator_accessed": False,
        "simulator_launched": False,
        "performance_accepted": False,
        "architecture_promoted": False,
    }
    result_path = output_dir / "cells" / f"{cell_id}.json"
    _write_json_atomic(result_path, result)
    result["result_path"] = str(result_path.relative_to(output_dir))
    result["result_sha256"] = _sha256(result_path)
    print(
        f"CALIBRATION_COMPLETE {cell_id} rawdata={artifact.rawdata_status} "
        f"applicability={artifact.applicability.status} "
        f"wall={result['resources']['cell_wall_sec']:.3f}",
        flush=True,
    )
    del model, raw_fields, calibrated_fields_tuple, truth_fields
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


def run(
    *,
    dataset_manifest: Path,
    checkpoint_summary: Path,
    preregistration_plan: Path,
    access_seal: Path,
    pre_access_validation_receipt: Path,
    output_dir: Path,
) -> dict[str, object]:
    started = time.perf_counter()
    manifest_path = dataset_manifest.resolve()
    summary_path = checkpoint_summary.resolve()
    plan_path = preregistration_plan.resolve()
    seal_path = access_seal.resolve()
    validation_receipt_path = pre_access_validation_receipt.resolve()
    plan, checkpoint_summary_value, validation_receipt = _validate_pre_access(
        manifest_path=manifest_path,
        checkpoint_summary_path=summary_path,
        plan_path=plan_path,
        access_seal_path=seal_path,
        validation_receipt_path=validation_receipt_path,
    )
    output = _prepare_output(output_dir)
    manifest = _json(manifest_path)
    inventory = _json(INVENTORY_PATH)

    # This is the first and only calibration-locator open in this runner.
    calibration_rows = load_locator_rows(
        manifest_path,
        scope="calibration",
        sealed_threshold_path=seal_path,
    )
    if len(calibration_rows) != 600:
        raise ValueError("calibration locator count drifted after access")
    development_rows = load_locator_rows(manifest_path, scope="development")
    run_spec = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "status": "calibration-accessed-run-in-progress",
        "pre_access_commit": validation_receipt["pre_access_commit"],
        "dataset_manifest_sha256": _sha256(manifest_path),
        "calibration_locator_sha256": str(
            manifest["partition_locators"]["calibration"]["sha256"]
        ),
        "development_checkpoint_summary_sha256": _sha256(summary_path),
        "preregistration_plan_sha256": _sha256(plan_path),
        "access_seal_sha256": _sha256(seal_path),
        "pre_access_validation_receipt_sha256": _sha256(
            validation_receipt_path
        ),
        "calibration_design_count": len(calibration_rows),
        "calibration_locator_accessed": True,
        "offline_test_locator_accessed": False,
        "simulator_launched": False,
        "complete_qnehvi_strategy_implemented": False,
        "performance_accepted": False,
    }
    _write_json_atomic(output / "run_spec.json", run_spec)
    cases = {}
    for case_id in tuple(str(value) for value in plan["partition"]["cases"]):
        cases[case_id] = _load_calibration_case(
            case_id=case_id,
            calibration_rows=calibration_rows,
            development_rows=development_rows,
            inventory=inventory,
        )
    results = []
    for cell in checkpoint_summary_value["cells"]:
        case_id = str(cell["case"])
        results.append(
            _run_cell(
                output_dir=output,
                summary_path=summary_path,
                cell=dict(cell),
                data=cases[case_id],
                inventory=inventory,
                plan=plan,
                dataset_manifest_sha256=_sha256(manifest_path),
                calibration_locator_sha256=str(
                    manifest["partition_locators"]["calibration"]["sha256"]
                ),
                preregistration_sha256=_sha256(plan_path),
                checkpoint_summary_sha256=_sha256(summary_path),
            )
        )
    if len(results) != 6:
        raise ValueError("calibration checkpoint cell count drifted")
    summary = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "status": "complete-experimental-calibration-framework-performance-not-accepted",
        "pre_access_commit": validation_receipt["pre_access_commit"],
        "dataset_manifest_sha256": _sha256(manifest_path),
        "calibration_locator_sha256": str(
            manifest["partition_locators"]["calibration"]["sha256"]
        ),
        "development_checkpoint_summary_sha256": _sha256(summary_path),
        "preregistration_plan_sha256": _sha256(plan_path),
        "run_spec_sha256": _sha256(output / "run_spec.json"),
        "calibration_design_count": len(calibration_rows),
        "cell_count": len(results),
        "cells": [
            {
                "cell_id": result["cell_id"],
                "case": result["case"],
                "train_size": result["train_size"],
                "result_path": result["result_path"],
                "result_sha256": result["result_sha256"],
                "artifact": result["artifact"],
                "rawdata_calibration_passed": result[
                    "frozen_gate_decision"
                ]["rawdata_calibration_passed"],
                "applicability_calibration_passed": result[
                    "frozen_gate_decision"
                ]["applicability_calibration_passed"],
                "wall_sec": result["resources"]["cell_wall_sec"],
            }
            for result in results
        ],
        "rawdata_calibrated_cell_count": sum(
            bool(result["frozen_gate_decision"]["rawdata_calibration_passed"])
            for result in results
        ),
        "applicability_calibrated_cell_count": sum(
            bool(
                result["frozen_gate_decision"][
                    "applicability_calibration_passed"
                ]
            )
            for result in results
        ),
        "access_state": {
            "development_locator_accessed": True,
            "calibration_locator_accessed": True,
            "offline_test_locator_accessed": False,
            "simulator_launched": False,
        },
        "scientific_boundary": {
            "v5_performance_failure_unchanged": True,
            "performance_accepted": False,
            "architecture_promoted": False,
            "artifact_transferable_to_successor": False,
            "formal_test_accessed": False,
            "complete_qnehvi_strategy_implemented": False,
            "formal_same_budget_optimization_benchmark_completed": False,
        },
        "wall_sec": float(time.perf_counter() - started),
    }
    _write_json_atomic(output / "calibration_summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint-summary", type=Path, required=True)
    parser.add_argument("--preregistration-plan", type=Path, required=True)
    parser.add_argument("--access-seal", type=Path, required=True)
    parser.add_argument(
        "--pre-access-validation-receipt", type=Path, required=True
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    summary = run(
        dataset_manifest=arguments.dataset_manifest,
        checkpoint_summary=arguments.checkpoint_summary,
        preregistration_plan=arguments.preregistration_plan,
        access_seal=arguments.access_seal,
        pre_access_validation_receipt=arguments.pre_access_validation_receipt,
        output_dir=arguments.output_dir,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "cell_count": summary["cell_count"],
                "rawdata_calibrated_cell_count": summary[
                    "rawdata_calibrated_cell_count"
                ],
                "applicability_calibrated_cell_count": summary[
                    "applicability_calibrated_cell_count"
                ],
                "wall_sec": summary["wall_sec"],
                "calibration_locator_accessed": True,
                "offline_test_locator_accessed": False,
                "simulator_launched": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
