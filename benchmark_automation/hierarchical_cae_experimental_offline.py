"""Run the preregistered 082608 experimental coordinate/offline mechanism path.

This runner deliberately has no scientific acceptance decision.  It opens the
offline-test locator only after validating the Gate 0 v6 access seal, trains on
development train rows with development-validation early stopping, and writes
one immutable result per fixed mechanism cell.  It never launches a simulator.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import gc
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Mapping, Sequence

import numpy as np
import torch

import hierarchical_cae_validation as validation
from hierarchical_cae_dataset import load_locator_rows, load_selected_records
from yadof.surrogate.hierarchical_cae import modeling as cae_modeling
from yadof.surrogate.hierarchical_cae.coordinates import (
    coordinate_grid,
    stored_coordinate_points,
)
from yadof.surrogate.hierarchical_cae.schema import (
    build_schema,
    field_matrices,
    fit_scalers,
    reconstruct_samples,
    standardized_field_matrices,
)
from yadof.surrogate.quality import QualityAssessmentBatch, assess_quality


AUTOMATION_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = AUTOMATION_ROOT.parent
V4_ROOT = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v4"
)
V5_ROOT = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v5"
)
V6_ROOT = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v6"
)
PLAN_PATH = V6_ROOT / "experimental_framework_plan.json"
ACCESS_SEAL_PATH = V6_ROOT / "experimental_offline_access_seal.json"
V4_PLAN_PATH = V4_ROOT / "validation_plan_v2.json"
V5_DECISION_PATH = V5_ROOT / "validation_decision.json"
INVENTORY_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi"
    / "schema_inventory.json"
)
PROTOCOL = "yadof.gate0-v6.experimental-coordinate-offline-mechanism"
PROTOCOL_VERSION = 1


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
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _model_state_sha256(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        values = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(values.dtype).encode("ascii"))
        digest.update(json.dumps(list(values.shape)).encode("ascii"))
        digest.update(values.numpy().tobytes(order="C"))
    return digest.hexdigest()


@dataclass(slots=True)
class OfflineCaseData:
    case_id: str
    task_fingerprint: str
    workspace: Path
    parameter_names: tuple[str, ...]
    design_ids: tuple[str, ...]
    parameters: np.ndarray
    samples: tuple[object, ...]
    metadata: tuple[Mapping[str, object], ...]
    schema: object
    matrices: tuple[np.ndarray, ...]
    quality: QualityAssessmentBatch
    train_count: int
    test_count: int

    @property
    def train_pool_count(self) -> int:
        return self.train_count

    @property
    def validation_count(self) -> int:
        return self.test_count


def _offline_case(
    *,
    development,
    test_rows: Sequence[Mapping[str, object]],
    inventory: Mapping[str, object],
) -> OfflineCaseData:
    ordered_rows = tuple(sorted(test_rows, key=lambda row: str(row["design_id"])))
    if len(ordered_rows) != 400:
        raise ValueError(
            f"{development.case_id}: offline-test count drifted from 400"
        )
    records = load_selected_records(ordered_rows)
    by_id = {
        str(record["locator"]["design_id"]): record for record in records
    }
    ordered = tuple(by_id[str(row["design_id"])] for row in ordered_rows)
    test_samples = tuple(record["sample"] for record in ordered)
    test_metadata = tuple(record["record_metadata"] for record in ordered)
    test_parameters = np.ascontiguousarray(
        [record["normalized_variables"] for record in ordered], dtype=np.float32
    )
    test_matrices = field_matrices(development.schema, test_samples)
    train_count = development.train_pool_count
    train_samples = development.samples[:train_count]
    train_metadata = development.metadata[:train_count]
    train_parameters = development.parameters[:train_count]
    train_matrices = tuple(
        matrix[:train_count] for matrix in development.matrices
    )
    samples = (*train_samples, *test_samples)
    metadata = (*train_metadata, *test_metadata)
    case_id = development.case_id
    policy = validation._chrono_policy() if case_id == "chrono" else None
    quality = assess_quality(
        policy=policy,
        samples=samples,
        record_metadata=metadata,
    )
    case = inventory["cases"][case_id]
    return OfflineCaseData(
        case_id=case_id,
        task_fingerprint=str(case["task_fingerprint"]),
        workspace=Path(str(ordered_rows[0]["workspace"])),
        parameter_names=tuple(case["parameter_contract"]["names"]),
        design_ids=(
            *development.design_ids[:train_count],
            *(str(row["design_id"]) for row in ordered_rows),
        ),
        parameters=np.ascontiguousarray(
            np.concatenate((train_parameters, test_parameters), axis=0),
            dtype=np.float32,
        ),
        samples=samples,
        metadata=metadata,
        schema=development.schema,
        matrices=tuple(
            np.ascontiguousarray(
                np.concatenate((train, test), axis=0), dtype=np.float64
            )
            for train, test in zip(train_matrices, test_matrices)
        ),
        quality=quality,
        train_count=train_count,
        test_count=len(test_samples),
    )


def _coordinate_config(
    base_plan: Mapping[str, object],
    experiment_plan: Mapping[str, object],
    arm: str,
):
    base = asdict(validation._cae_config(base_plan, arm))
    base.update(dict(experiment_plan["coordinate_configuration"]))
    return validation.CAETrainConfig(**base)


def _coordinate_metrics(
    *,
    model,
    schema,
    test_parameters: np.ndarray,
    true_test_matrices: Sequence[np.ndarray],
    full_grid_members: Sequence[np.ndarray],
    device: torch.device,
    cfg,
    plan: Mapping[str, object],
) -> dict[str, object]:
    before = _model_state_sha256(model)
    fields = []
    point_limit = int(plan["stored_grid_metric_points_per_field"])
    probe_designs = min(
        int(plan["off_grid_probe_design_count"]), len(test_parameters)
    )
    off_grid_finite = True
    off_grid_queries = 0
    for field_index, (layout, scaler, grid_values, true_values) in enumerate(
        zip(schema.layouts, schema.scalers, full_grid_members, true_test_matrices)
    ):
        point_count = layout.point_count
        selected = np.unique(
            np.linspace(
                0,
                point_count - 1,
                num=min(point_count, point_limit),
                dtype=np.int64,
            )
        )
        points = stored_coordinate_points(layout)[selected]
        coordinate_members = cae_modeling.predict_hierarchical_coordinate_members(
            model=model,
            parameters=test_parameters,
            field_index=field_index,
            coordinate_points=points,
            device=device,
            batch_size=cfg.inference_batch_size,
            query_batch_size=cfg.coordinate_query_batch_size,
        )
        grid_selected = np.asarray(grid_values, dtype=np.float64).reshape(
            grid_values.shape[0], grid_values.shape[1], -1
        )[:, :, selected]
        differences = np.asarray(coordinate_members, dtype=np.float64) - grid_selected
        coordinate_mean = np.mean(coordinate_members, axis=0, dtype=np.float64)
        true_standardized = scaler.transform(true_values).reshape(
            len(test_parameters), -1
        )[:, selected]
        truth_error = coordinate_mean - true_standardized
        fields.append(
            {
                "selector": list(layout.selector),
                "stored_grid_point_count": int(point_count),
                "sampled_stored_grid_point_count": int(len(selected)),
                "member_coordinate_vs_grid_standardized_mae": float(
                    np.mean(np.abs(differences))
                ),
                "member_coordinate_vs_grid_standardized_rmse": float(
                    np.sqrt(np.mean(np.square(differences)))
                ),
                "mean_coordinate_vs_true_standardized_mae": float(
                    np.mean(np.abs(truth_error))
                ),
                "mean_coordinate_vs_true_standardized_rmse": float(
                    np.sqrt(np.mean(np.square(truth_error)))
                ),
                "finite": bool(
                    np.all(np.isfinite(coordinate_members))
                    and np.all(np.isfinite(differences))
                ),
            }
        )
        if layout.rank:
            probe_axes = []
            for axis in layout.axis_values:
                values = np.asarray(axis, dtype=np.float64)
                if values.size == 1:
                    probe_axes.append(values.copy())
                    continue
                midpoints = (values[:-1] + values[1:]) / 2.0
                probe_axes.append(
                    midpoints[
                        np.unique(
                            np.linspace(
                                0,
                                len(midpoints) - 1,
                                num=min(
                                    len(midpoints),
                                    int(plan["off_grid_probe_points_per_axis"]),
                                ),
                                dtype=np.int64,
                            )
                        )
                    ]
                )
            off_points, _shape, _axes = coordinate_grid(layout, probe_axes)
            probe = cae_modeling.predict_hierarchical_coordinate_members(
                model=model,
                parameters=test_parameters[:probe_designs],
                field_index=field_index,
                coordinate_points=off_points,
                device=device,
                batch_size=cfg.inference_batch_size,
                query_batch_size=cfg.coordinate_query_batch_size,
            )
            off_grid_queries += int(probe.size)
            off_grid_finite = off_grid_finite and bool(np.all(np.isfinite(probe)))
    after = _model_state_sha256(model)
    return {
        "contract": "yadof.hierarchical-cae-coordinate-readout-v1",
        "status": "experimental-performance-not-accepted",
        "authority": "viewer/off-grid-only; full-grid decoder remains authoritative",
        "fields": fields,
        "all_queries_finite": bool(
            off_grid_finite and all(field["finite"] for field in fields)
        ),
        "off_grid_probe_value_count": int(off_grid_queries),
        "checkpoint_state_sha256_before_query": before,
        "checkpoint_state_sha256_after_query": after,
        "query_state_unchanged": before == after,
        "numeric_acceptance_thresholds": None,
        "scientific_acceptance_claimed": False,
    }


def _cae_cell(
    *,
    development,
    offline: OfflineCaseData,
    case: Mapping[str, object],
    train_size: int,
    seed: int,
    arm: str,
    base_plan: Mapping[str, object],
    experiment_plan: Mapping[str, object],
) -> dict[str, object]:
    groups = (
        validation._explicit_groups(case)
        if arm == "hierarchical-cae-mean-explicit-s11-gain-groups"
        else ()
    )
    schema = build_schema(
        development.samples[0],
        groups=groups,
        field_layouts=validation._rank3_layouts(case),
    )
    scalers = fit_scalers(
        tuple(matrix[:train_size] for matrix in development.matrices),
        scale_floor=float(
            base_plan["model_configs"]["hierarchical_cae"]["scale_floor"]
        ),
    )
    schema = replace(schema, scalers=scalers)
    indices = np.concatenate(
        (
            np.arange(train_size, dtype=np.int64),
            np.arange(
                development.train_pool_count,
                development.train_pool_count + development.validation_count,
                dtype=np.int64,
            ),
        )
    )
    matrices = tuple(matrix[indices] for matrix in development.matrices)
    standardized = standardized_field_matrices(schema, matrices)
    quality = validation._quality_subset(development.quality, indices)
    cfg = _coordinate_config(base_plan, experiment_plan, arm)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    test_parameters = offline.parameters[offline.train_pool_count :]
    with validation._ResourceMonitor() as monitor:
        model, history = cae_modeling.fit_hierarchical_cae(
            input_dim=development.parameters.shape[1],
            schema=schema,
            parameters=development.parameters[indices],
            standardized_fields=standardized,
            quality=quality,
            device=device,
            train_cfg=cfg,
            seed=seed,
            train_indices=np.arange(train_size, dtype=np.int64),
            validation_indices=np.arange(
                train_size,
                train_size + development.validation_count,
                dtype=np.int64,
            ),
        )
        member_fields, applicability, _residual = (
            cae_modeling.predict_hierarchical_members(
                model=model,
                parameters=test_parameters,
                device=device,
                batch_size=cfg.inference_batch_size,
            )
        )
        mean_fields = tuple(
            np.mean(values, axis=0, dtype=np.float64)
            for values in member_fields
        )
        predicted = reconstruct_samples(schema, mean_fields)
        coordinate = _coordinate_metrics(
            model=model,
            schema=schema,
            test_parameters=test_parameters,
            true_test_matrices=tuple(
                matrix[offline.train_pool_count :] for matrix in offline.matrices
            ),
            full_grid_members=member_fields,
            device=device,
            cfg=cfg,
            plan=experiment_plan,
        )
    metrics = validation._evaluate(
        data=offline,
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
        "training_partition": {
            "train_design_count": int(train_size),
            "early_stopping_design_count": int(development.validation_count),
            "early_stopping_scope": "development-validation-only",
            "offline_test_used_for_training_or_early_stopping": False,
        },
        "training_history": history,
        "resources": {
            **monitor.payload(),
            "parameter_count": int(parameter_count),
            "parameter_bytes_float32": int(parameter_count * 4),
        },
        "metrics": metrics,
        "coordinate_readout": coordinate,
    }
    del model, member_fields, mean_fields, predicted, standardized, matrices
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return result


def _conditional_cell(
    *,
    development,
    offline: OfflineCaseData,
    train_size: int,
    seed: int,
    base_plan: Mapping[str, object],
) -> dict[str, object]:
    config = validation.inr_modeling.INRTrainConfig(
        **dict(base_plan["model_configs"]["conditional_inr"])
    )
    raw_train = tuple(
        tuple(dict(item.payload) for item in sample.items)
        for sample in development.samples[:train_size]
    )
    schema, y_train = validation.inr_runtime._flatten_raw_samples(raw_train)
    if schema is None:
        raise RuntimeError("conditional-INR baseline produced no schema")
    scaler = validation.inr_runtime._fit_scaler(y_train, scale_floor=1.0e-6)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    test_parameters = offline.parameters[offline.train_pool_count :]
    with validation._ResourceMonitor() as monitor:
        model, history = (
            validation.inr_modeling.fit_deep_ensemble_conditional_inr(
                input_dim=development.parameters.shape[1],
                n_fields=schema.n_fields,
                X_train=development.parameters[:train_size],
                Y_train=scaler.transform(y_train),
                coord_table=schema.coord_table,
                field_ids=schema.field_ids,
                device=device,
                train_cfg=config,
                seed=seed,
            )
        )
        members = validation.inr_modeling.predict_conditional_inr_members(
            model=model,
            X=test_parameters,
            coord_table=schema.coord_table,
            field_ids=schema.field_ids,
            device=device,
            sample_batch=config.sample_batch_eval,
            query_batch=config.query_batch_eval,
        )
        mean_flat = scaler.inverse(np.mean(members, axis=0))
        raw_predicted = validation.inr_runtime._raw_samples_from_flat(
            schema, mean_flat
        )
        predicted = validation._conditional_named_samples(
            offline.schema, raw_predicted
        )
    scalers = fit_scalers(
        tuple(matrix[:train_size] for matrix in offline.matrices),
        scale_floor=1.0e-6,
    )
    metric_schema = replace(offline.schema, scalers=scalers)
    model_quality = validation._quality_subset(
        development.quality,
        np.concatenate(
            (
                np.arange(train_size, dtype=np.int64),
                np.arange(
                    development.train_pool_count,
                    development.train_pool_count + development.validation_count,
                    dtype=np.int64,
                ),
            )
        ),
    )
    metrics = validation._evaluate(
        data=offline,
        train_size=train_size,
        schema=metric_schema,
        scalers=scalers,
        predicted_samples=predicted,
        applicability_scores=None,
        model_quality=model_quality,
    )
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    result = {
        "model_config": asdict(config),
        "training_partition": {
            "train_design_count": int(train_size),
            "development_validation_not_used_by_baseline_trainer": True,
            "offline_test_used_for_training_or_early_stopping": False,
        },
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


def _cell_id(case_id: str, model: str, train_size: int, seed: int) -> str:
    return f"{case_id}__{model}__train-{train_size}__seed-{seed}"


def _paired_summary(cells: Mapping[str, Mapping[str, object]]) -> list[dict[str, object]]:
    rows = []
    identities = sorted(
        {
            (
                str(cell["case"]),
                int(cell["train_size"]),
                int(cell["seed"]),
            )
            for cell in cells.values()
        }
    )
    for case_id, train_size, seed in identities:
        matching = {
            str(cell["model"]): cell
            for cell in cells.values()
            if str(cell["case"]) == case_id
            and int(cell["train_size"]) == train_size
            and int(cell["seed"]) == seed
        }
        if set(matching) != {"conditional-inr-mean", "hierarchical-cae-coordinate"}:
            continue
        baseline = matching["conditional-inr-mean"]["result"]["metrics"]
        candidate = matching["hierarchical-cae-coordinate"]["result"]["metrics"]
        baseline_mae = float(baseline["rawdata"]["field_macro_standardized_mae"])
        candidate_mae = float(candidate["rawdata"]["field_macro_standardized_mae"])
        rows.append(
            {
                "case": case_id,
                "train_size": train_size,
                "seed": seed,
                "candidate_to_conditional_field_macro_mae_ratio": (
                    candidate_mae / baseline_mae
                ),
                "descriptive_only": True,
                "acceptance_decision": None,
            }
        )
    return rows


def validate_preregistration(
    manifest_path: Path,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    """Validate the frozen v6 chain without opening any protected locator."""

    manifest_path = manifest_path.resolve()
    plan = _json(PLAN_PATH)
    access_seal = _json(ACCESS_SEAL_PATH)
    base_plan = _json(V4_PLAN_PATH)
    inventory = _json(INVENTORY_PATH)
    if plan.get("protocol") != PROTOCOL:
        raise ValueError("unsupported experimental offline plan")
    if int(plan.get("protocol_version", -1)) != PROTOCOL_VERSION:
        raise ValueError("unsupported experimental offline plan version")
    if _sha256(Path(__file__).resolve()) != str(
        plan["artifact_integrity"]["runner_sha256"]
    ):
        raise ValueError("experimental offline runner hash drifted")
    if _sha256(V4_PLAN_PATH) != str(
        plan["artifact_integrity"]["v4_validation_plan_sha256"]
    ):
        raise ValueError("frozen v4 plan hash drifted")
    if _sha256(V5_DECISION_PATH) != str(
        plan["artifact_integrity"]["v5_decision_sha256"]
    ):
        raise ValueError("frozen v5 decision hash drifted")
    if _sha256(manifest_path) != str(plan["dataset_manifest_sha256"]):
        raise ValueError("experimental plan does not bind this dataset manifest")
    if _sha256(ACCESS_SEAL_PATH) != str(
        plan["artifact_integrity"]["access_seal_sha256"]
    ):
        raise ValueError("experimental offline access seal hash drifted")
    for relative, expected in plan["artifact_integrity"][
        "source_artifacts"
    ].items():
        path = REPOSITORY_ROOT / str(relative)
        if _sha256(path) != str(expected):
            raise ValueError(f"experimental source artifact drifted: {relative}")
    if access_seal.get("status") != "sealed":
        raise PermissionError("experimental offline access seal is not sealed")
    if access_seal.get("scientific_acceptance_authorized") is not False:
        raise ValueError("access seal must not authorize scientific acceptance")
    return plan, access_seal, base_plan, inventory


def run(
    *,
    manifest_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    manifest_path = manifest_path.resolve()
    output_dir = output_dir.resolve()
    plan, access_seal, base_plan, inventory = validate_preregistration(
        manifest_path
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    cells_dir = output_dir / "cells"
    cells_dir.mkdir(parents=True, exist_ok=True)
    run_spec = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "status": "running-experimental-performance-not-accepted",
        "started_unix_ns": time.time_ns(),
        "plan": str(PLAN_PATH.resolve()),
        "plan_sha256": _sha256(PLAN_PATH),
        "access_seal": str(ACCESS_SEAL_PATH.resolve()),
        "access_seal_sha256": _sha256(ACCESS_SEAL_PATH),
        "dataset_manifest": str(manifest_path),
        "dataset_manifest_sha256": _sha256(manifest_path),
        "v5_decision_sha256": _sha256(V5_DECISION_PATH),
        "offline_test_locator_access_authorized": True,
        "calibration_locator_accessed": False,
        "simulator_launched": False,
        "scientific_acceptance_claimed": False,
    }
    _write_json_atomic(output_dir / "run_spec.json", run_spec)

    # This is the first and only offline-test locator open in this runner.
    offline_rows = load_locator_rows(
        manifest_path,
        scope="offline-test",
        sealed_threshold_path=ACCESS_SEAL_PATH,
    )
    expected_rows = int(plan["offline_test_designs_per_case"]) * len(
        plan["cases"]
    )
    if len(offline_rows) != expected_rows:
        raise ValueError("offline-test locator row count drifted")

    completed: dict[str, dict[str, object]] = {}
    started = time.perf_counter()
    total_cells = (
        len(plan["cases"])
        * len(plan["train_sizes"])
        * 2
        * len(plan["model_fit_seeds"])
    )
    for case_id in plan["cases"]:
        case_id = str(case_id)
        print(f"[experimental-offline] load development/test {case_id}", flush=True)
        development = validation._load_case(
            manifest_path, case_id, inventory
        )
        offline = _offline_case(
            development=development,
            test_rows=[row for row in offline_rows if row["case"] == case_id],
            inventory=inventory,
        )
        case = inventory["cases"][case_id]
        arm = str(plan["production_arms"][case_id])
        for train_size in plan["train_sizes"]:
            for seed in plan["model_fit_seeds"]:
                for model_name in (
                    "conditional-inr-mean",
                    "hierarchical-cae-coordinate",
                ):
                    cell_id = _cell_id(
                        case_id, model_name, int(train_size), int(seed)
                    )
                    path = cells_dir / f"{cell_id}.json"
                    if path.is_file():
                        existing = _json(path)
                        if existing.get("status") != "completed":
                            raise RuntimeError(f"incomplete existing cell {cell_id}")
                        completed[cell_id] = existing
                        print(
                            f"[experimental-offline] {cell_id} already complete",
                            flush=True,
                        )
                        continue
                    print(f"[experimental-offline] start {cell_id}", flush=True)
                    cell_started = time.perf_counter()
                    if model_name == "conditional-inr-mean":
                        result = _conditional_cell(
                            development=development,
                            offline=offline,
                            train_size=int(train_size),
                            seed=int(seed),
                            base_plan=base_plan,
                        )
                    else:
                        result = _cae_cell(
                            development=development,
                            offline=offline,
                            case=case,
                            train_size=int(train_size),
                            seed=int(seed),
                            arm=arm,
                            base_plan=base_plan,
                            experiment_plan=plan,
                        )
                    cell = {
                        "protocol": PROTOCOL,
                        "protocol_version": PROTOCOL_VERSION,
                        "status": "completed",
                        "case": case_id,
                        "model": model_name,
                        "production_arm": arm if model_name.startswith("hierarchical") else None,
                        "train_size": int(train_size),
                        "seed": int(seed),
                        "offline_test_design_count": offline.validation_count,
                        "offline_test_locator_accessed": True,
                        "calibration_locator_accessed": False,
                        "simulator_launched": False,
                        "scientific_acceptance_claimed": False,
                        "acceptance_status": "experimental-performance-not-accepted",
                        "cell_wall_sec": time.perf_counter() - cell_started,
                        "result": result,
                    }
                    _write_json_atomic(path, cell)
                    completed[cell_id] = cell
                    print(
                        f"[experimental-offline] done {cell_id} "
                        f"({len(completed)}/{total_cells}) "
                        f"sec={cell['cell_wall_sec']:.1f}",
                        flush=True,
                    )
        del development, offline
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    if len(completed) != total_cells:
        raise RuntimeError("experimental offline cell count is incomplete")
    summary = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "status": "completed-experimental-performance-not-accepted",
        "completed_cell_count": len(completed),
        "expected_cell_count": total_cells,
        "wall_sec": time.perf_counter() - started,
        "offline_test_locator_accessed": True,
        "offline_test_design_count": len(offline_rows),
        "calibration_locator_accessed": False,
        "simulator_launched": False,
        "v5_failure_unchanged": True,
        "coordinate_numeric_acceptance_thresholds": None,
        "scientific_acceptance_claimed": False,
        "todo_082608_may_archive": False,
        "paired_descriptive_results": _paired_summary(completed),
        "cells": [
            {
                "cell_id": cell_id,
                "sha256": _sha256(cells_dir / f"{cell_id}.json"),
            }
            for cell_id in sorted(completed)
        ],
    }
    _write_json_atomic(output_dir / "offline_summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="validate the v6 chain without opening the offline-test locator",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.preflight:
        plan, _seal, _base, _inventory = validate_preregistration(
            args.manifest
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "status": "preflight-only-offline-test-unaccessed",
                    "plan_id": plan["plan_id"],
                    "offline_test_locator_accessed": False,
                    "simulator_launched": False,
                    "scientific_acceptance_claimed": False,
                },
                sort_keys=True,
            )
        )
        return 0
    summary = run(manifest_path=args.manifest, output_dir=args.output_dir)
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
