"""Freeze development-only hierarchical-CAE checkpoints for 082609 calibration.

This command can open only the development locator.  It trains the exact v7
experimental production arm at the frozen 1000/2000 design operating points,
publishes yadof-compatible durable checkpoints, and records the train/validation
provenance needed by the subsequent calibration preregistration.  It never opens
calibration/offline-test locators and never launches a simulator.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import gc
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import tempfile
import time
from typing import Mapping, Sequence

import numpy as np
import torch
import yadof

import hierarchical_cae_validation as validation
from yadof.job_template import api as job_template_api
from yadof.surrogate.hierarchical_cae import checkpoints
from yadof.surrogate.hierarchical_cae import modeling as cae_modeling
from yadof.surrogate.hierarchical_cae.schema import (
    build_schema,
    fit_scalers,
    standardized_field_matrices,
)
from yadof.surrogate.hierarchical_cae.types import HierarchicalState


AUTOMATION_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = AUTOMATION_ROOT.parent
INVENTORY_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi"
    / "schema_inventory.json"
)
V4_PLAN_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v4"
    / "validation_plan_v2.json"
)
V6_PLAN_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v6"
    / "experimental_framework_plan.json"
)
PROTOCOL = "yadof.082609.development-checkpoint-bundle"
PROTOCOL_VERSION = 1
_STRATEGY_PREFIX = b"yadof:082609-development-checkpoint-strategy:v1:"


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


def _array_sha256(value: object) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(_canonical_bytes(list(array.shape)))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _model_state_sha256(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        values = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(values.dtype).encode("ascii"))
        digest.update(_canonical_bytes(list(values.shape)))
        digest.update(values.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _coordinate_config(
    base_plan: Mapping[str, object],
    experiment_plan: Mapping[str, object],
    arm: str,
):
    base = asdict(validation._cae_config(base_plan, arm))
    base.update(dict(experiment_plan["coordinate_configuration"]))
    return validation.CAETrainConfig(**base)


def _case_component(
    *,
    case_id: str,
    case: Mapping[str, object],
    base_plan: Mapping[str, object],
    experiment_plan: Mapping[str, object],
) -> tuple[object, tuple[tuple[tuple[str, str], ...], ...], object | None, str]:
    arm = str(experiment_plan["production_arms"][case_id])
    groups = (
        validation._explicit_groups(case)
        if arm == "hierarchical-cae-mean-explicit-s11-gain-groups"
        else ()
    )
    policy = validation._chrono_policy() if case_id == "chrono" else None
    return _coordinate_config(base_plan, experiment_plan, arm), groups, policy, arm


def _strategy_signature(
    *,
    case_id: str,
    task_fingerprint: str,
    train_cfg,
    groups,
    field_layouts,
    quality_policy,
) -> str:
    payload = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "case": case_id,
        "task_fingerprint": task_fingerprint,
        "component": "hierarchical-cae-coordinate-experimental",
        "configuration": {
            "train_cfg": asdict(train_cfg),
            "groups": [
                [list(selector) for selector in group] for group in groups
            ],
            "field_layouts": [
                {
                    "selector": list(selector),
                    "channel_axes": list(layout["channel_axes"]),
                    "spatial_axes": list(layout["spatial_axes"]),
                }
                for selector, layout in sorted(field_layouts.items())
            ],
            "quality_policy": (
                None if quality_policy is None else quality_policy.as_dict()
            ),
        },
        "performance_status": "experimental-performance-not-accepted",
        "observation_noise_included": False,
    }
    return hashlib.sha256(_STRATEGY_PREFIX + _canonical_bytes(payload)).hexdigest()


def _identity(
    *,
    quality_policy,
    train_cfg,
) -> dict[str, object]:
    return {
        "policy": (
            {"enabled": False, "default": "uniform-smooth"}
            if quality_policy is None
            else quality_policy.as_dict()
        ),
        "label": {
            "contract": "yadof.rawdata-quality-assessment-v1",
            "target": "design-level smooth=1; chatter/failure=0",
            "all_fields_and_coordinates_follow_design_partition": True,
        },
        "head": {
            "contract": "yadof.hierarchical-cae-member-applicability-v1",
            "enabled": bool(train_cfg.regime_head),
            "one_logit_per_predictor_member_and_design": True,
            "member_identity_shared_with_rawdata_draw": True,
        },
        "loss": {
            "applicability": "binary-cross-entropy-with-logits",
            "applicability_loss_weight": float(
                train_cfg.applicability_loss_weight
            ),
            "residual_gate_loss_weight": float(
                train_cfg.residual_gate_loss_weight
            ),
            "quality_weighted_loss": bool(train_cfg.quality_weighted_loss),
            "shared_quality_isolation": bool(
                train_cfg.shared_quality_isolation
            ),
            "gated_private_residual": bool(train_cfg.gated_private_residual),
        },
    }


def _source_artifacts() -> dict[str, object]:
    paths = {
        "installed_yadof": Path(yadof.__file__).resolve(),
        "installed_modeling": Path(cae_modeling.__file__).resolve(),
        "installed_checkpoints": Path(checkpoints.__file__).resolve(),
        "checkpoint_runner": Path(__file__).resolve(),
        "validation_helpers": Path(validation.__file__).resolve(),
    }
    return {
        name: {"path": str(path), "sha256": _sha256(path)}
        for name, path in paths.items()
    }


def _prepare_output(output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"development checkpoint output must be new/empty: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def _train_cell(
    *,
    output_dir: Path,
    manifest_path: Path,
    manifest: Mapping[str, object],
    source_commit: str,
    data,
    case: Mapping[str, object],
    train_size: int,
    seed: int,
    train_cfg,
    groups,
    quality_policy,
    arm: str,
    source_artifacts: Mapping[str, object],
) -> dict[str, object]:
    cell_id = f"{data.case_id}__train-{int(train_size)}__seed-{int(seed)}"
    cell_dir = output_dir / "cells" / cell_id
    checkpoint_root = cell_dir / "checkpoint"
    if cell_dir.exists():
        raise FileExistsError(cell_dir)
    cell_dir.mkdir(parents=True)
    layouts = validation._rank3_layouts(case)
    schema = build_schema(
        data.samples[0], groups=groups, field_layouts=layouts
    )
    scalers = fit_scalers(
        tuple(matrix[:train_size] for matrix in data.matrices),
        scale_floor=float(train_cfg.scale_floor),
    )
    schema = replace(schema, scalers=scalers)
    selected_indices = np.concatenate(
        (
            np.arange(train_size, dtype=np.int64),
            np.arange(
                data.train_pool_count,
                data.train_pool_count + data.validation_count,
                dtype=np.int64,
            ),
        )
    )
    train_indices = np.arange(train_size, dtype=np.int64)
    validation_indices = np.arange(
        train_size,
        train_size + data.validation_count,
        dtype=np.int64,
    )
    parameters = np.ascontiguousarray(
        data.parameters[selected_indices], dtype=np.float32
    )
    matrices = tuple(
        np.ascontiguousarray(matrix[selected_indices], dtype=np.float64)
        for matrix in data.matrices
    )
    standardized = standardized_field_matrices(schema, matrices)
    quality = validation._quality_subset(data.quality, selected_indices)
    strategy_signature = _strategy_signature(
        case_id=data.case_id,
        task_fingerprint=data.task_fingerprint,
        train_cfg=train_cfg,
        groups=groups,
        field_layouts=layouts,
        quality_policy=quality_policy,
    )
    parameter_definition_signature = (
        job_template_api.get_parameter_definition_signature(data.workspace)
    )
    state_signature = checkpoints.semantic_state_signature(
        strategy_signature=strategy_signature,
        parameter_names=data.parameter_names,
        parameter_definition_signature=parameter_definition_signature,
        schema=schema,
        train_cfg=train_cfg,
        quality_policy=quality_policy,
    )
    train_ids = data.design_ids[:train_size]
    validation_ids = data.design_ids[
        data.train_pool_count : data.train_pool_count + data.validation_count
    ]
    identity = _identity(quality_policy=quality_policy, train_cfg=train_cfg)
    development_locator = dict(manifest["partition_locators"]["development"])
    provenance = {
        "contract": "yadof.082609.development-training-provenance",
        "contract_version": 1,
        "case": data.case_id,
        "task_fingerprint": data.task_fingerprint,
        "source_commit": source_commit,
        "installed_distribution": "yadof",
        "installed_version": metadata.version("yadof"),
        "installed_origin": str(Path(yadof.__file__).resolve()),
        "dataset_manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": _sha256(manifest_path),
        },
        "development_locator": {
            "path": str(development_locator["path"]),
            "sha256": str(development_locator["sha256"]),
            "row_count": int(development_locator["row_count"]),
        },
        "partition": {
            "train_design_count": int(train_size),
            "validation_design_count": int(data.validation_count),
            "train_design_ids_sha256": _json_sha256(list(train_ids)),
            "validation_design_ids_sha256": _json_sha256(
                list(validation_ids)
            ),
            "train_parameter_matrix_sha256": _array_sha256(
                parameters[train_indices]
            ),
            "validation_parameter_matrix_sha256": _array_sha256(
                parameters[validation_indices]
            ),
            "train_validation_disjoint": not bool(
                set(train_ids).intersection(validation_ids)
            ),
            "coordinate_level_split_allowed": False,
            "calibration_used_for_training_selection_or_scaling": False,
            "offline_test_used_for_training_or_early_stopping": False,
        },
        "schema": {
            "template_signature": schema.template.signature,
            "field_selectors": [
                list(selector) for selector in schema.field_selectors
            ],
            "field_count": len(schema.field_selectors),
            "field_scaler_fit_scope": "development-train-only",
        },
        "strategy_signature": strategy_signature,
        "state_signature": state_signature,
        "production_arm": arm,
        "train_cfg": asdict(train_cfg),
        "policy_label_head_loss_identity": identity,
        "quality_targets": {
            "applicability_targets_sha256": _array_sha256(
                quality.applicability_targets
            ),
            "design_regimes_sha256": _json_sha256(
                list(quality.design_regimes)
            ),
            "diagnostics": quality.diagnostics(),
        },
        "seed": int(seed),
        "device_selection": "cuda-if-available-else-cpu",
        "observation_noise_included": False,
        "performance_status": "experimental-performance-not-accepted",
        "simulator_launched": False,
        "calibration_locator_accessed": False,
        "offline_test_locator_accessed": False,
        "source_artifacts": dict(source_artifacts),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "torch": torch.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device": (
                torch.cuda.get_device_name(0)
                if torch.cuda.is_available()
                else None
            ),
        },
    }
    provenance_sha256 = _json_sha256(provenance)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"TRAIN_START {cell_id} device={device}", flush=True)
    started = time.perf_counter()
    with validation._ResourceMonitor() as monitor:
        model, history = cae_modeling.fit_hierarchical_cae(
            input_dim=parameters.shape[1],
            schema=schema,
            parameters=parameters,
            standardized_fields=standardized,
            quality=quality,
            device=device,
            train_cfg=train_cfg,
            seed=int(seed),
            train_indices=train_indices,
            validation_indices=validation_indices,
        )
    model_state_sha256 = _model_state_sha256(model)
    history.update(
        {
            "skipped": False,
            "development_only": True,
            "calibration_locator_accessed": False,
            "offline_test_locator_accessed": False,
            "simulator_launched": False,
            "performance_status": "experimental-performance-not-accepted",
            "training_provenance": provenance,
            "training_provenance_sha256": provenance_sha256,
            "policy_label_head_loss_identity": identity,
            "model_state_sha256": model_state_sha256,
            "resources": monitor.payload(),
        }
    )
    (
        checkpoint_path,
        namespace_manifest_path,
        artifact_dir,
        staging_dir,
        run_namespace,
        component_namespace,
    ) = checkpoints.new_publication_paths(
        checkpoint_root,
        generation_index=int(train_size),
        strategy_signature=strategy_signature,
    )
    state = HierarchicalState(
        generation_index=int(train_size),
        sample_count=int(train_size + data.validation_count),
        checkpoint_path=checkpoint_path,
        namespace_manifest_path=namespace_manifest_path,
        artifact_dir=artifact_dir,
        bundle_path=artifact_dir / "model.pt",
        strategy_signature=strategy_signature,
        state_signature=state_signature,
        run_namespace=run_namespace,
        component_namespace=component_namespace,
        parameter_names=data.parameter_names,
        parameter_definition_signature=parameter_definition_signature,
        schema=schema,
        quality_policy=quality_policy,
        model=model,
        train_cfg=train_cfg,
        device=device,
        train_history=history,
    )
    checkpoints.write_checkpoint(state, staged_artifact_dir=staging_dir)
    model_path = artifact_dir / "model.pt"
    scaler_path = artifact_dir / "field_scalers.npz"
    checkpoint_manifest = _json(checkpoint_path)
    if checkpoint_manifest != _json(namespace_manifest_path):
        raise ValueError("active/namespace checkpoint manifests differ")
    if str(checkpoint_manifest["state_signature"]) != state_signature:
        raise ValueError("published checkpoint state signature drifted")
    if str(checkpoint_manifest["train_history"]["training_provenance_sha256"]) != provenance_sha256:
        raise ValueError("published training provenance drifted")
    receipt = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "status": "durable-development-only-experimental-performance-not-accepted",
        "cell_id": cell_id,
        "case": data.case_id,
        "train_size": int(train_size),
        "validation_size": int(data.validation_count),
        "seed": int(seed),
        "production_arm": arm,
        "strategy_signature": strategy_signature,
        "state_signature": state_signature,
        "schema_signature": schema.template.signature,
        "policy_label_head_loss_identity": identity,
        "training_provenance": provenance,
        "training_provenance_sha256": provenance_sha256,
        "checkpoint": {
            "root": str(checkpoint_root.resolve()),
            "active_manifest": str(checkpoint_path.relative_to(cell_dir)),
            "active_manifest_sha256": _sha256(checkpoint_path),
            "namespace_manifest": str(
                namespace_manifest_path.relative_to(cell_dir)
            ),
            "namespace_manifest_sha256": _sha256(
                namespace_manifest_path
            ),
            "artifact_dir": str(artifact_dir.relative_to(cell_dir)),
            "model_path": str(model_path.relative_to(cell_dir)),
            "model_sha256": _sha256(model_path),
            "model_state_sha256": model_state_sha256,
            "scaler_path": str(scaler_path.relative_to(cell_dir)),
            "scaler_sha256": _sha256(scaler_path),
        },
        "resources": monitor.payload(),
        "wall_sec_including_publication": float(time.perf_counter() - started),
        "calibration_locator_accessed": False,
        "offline_test_locator_accessed": False,
        "simulator_launched": False,
    }
    receipt_path = cell_dir / "cell_receipt.json"
    _write_json_atomic(receipt_path, receipt)
    receipt["cell_receipt_path"] = str(receipt_path.relative_to(output_dir))
    receipt["cell_receipt_sha256"] = _sha256(receipt_path)
    print(
        f"TRAIN_COMPLETE {cell_id} wall={receipt['wall_sec_including_publication']:.3f} "
        f"state={state_signature}",
        flush=True,
    )
    del model, state, standardized, matrices, parameters, quality, schema
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return receipt


def run(
    *,
    dataset_manifest: Path,
    output_dir: Path,
    source_commit: str,
) -> dict[str, object]:
    started = time.perf_counter()
    manifest_path = dataset_manifest.resolve()
    manifest = _json(manifest_path)
    base_plan = _json(V4_PLAN_PATH)
    experiment_plan = _json(V6_PLAN_PATH)
    inventory = _json(INVENTORY_PATH)
    commit = str(source_commit).lower()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError("source_commit must be a full lowercase Git commit")
    if _sha256(manifest_path) != str(experiment_plan["dataset_manifest_sha256"]):
        raise ValueError("dataset manifest is not the frozen v6 dataset")
    if experiment_plan["parent_v5_outcome"] != {
        "full_grid_gate_passed": False,
        "representation_passed": False,
        "quality_regime_passed": False,
        "todo_082608_may_archive": False,
        "unchanged": True,
    }:
        raise ValueError("frozen v5 failure identity changed")
    output = output_dir.resolve()
    _prepare_output(output)
    source_artifacts = _source_artifacts()
    cells = []
    for case_id in tuple(str(value) for value in experiment_plan["cases"]):
        data = validation._load_case(manifest_path, case_id, inventory)
        case = dict(inventory["cases"][case_id])
        train_cfg, groups, policy, arm = _case_component(
            case_id=case_id,
            case=case,
            base_plan=base_plan,
            experiment_plan=experiment_plan,
        )
        for train_size in tuple(
            int(value) for value in experiment_plan["train_sizes"]
        ):
            cells.append(
                _train_cell(
                    output_dir=output,
                    manifest_path=manifest_path,
                    manifest=manifest,
                    source_commit=commit,
                    data=data,
                    case=case,
                    train_size=train_size,
                    seed=int(experiment_plan["model_fit_seeds"][0]),
                    train_cfg=train_cfg,
                    groups=groups,
                    quality_policy=policy,
                    arm=arm,
                    source_artifacts=source_artifacts,
                )
            )
        del data
        gc.collect()
    expected = len(experiment_plan["cases"]) * len(
        experiment_plan["train_sizes"]
    )
    if len(cells) != expected:
        raise ValueError("development checkpoint cell count drifted")
    summary = {
        "protocol": PROTOCOL,
        "protocol_version": PROTOCOL_VERSION,
        "status": "complete-development-only-experimental-performance-not-accepted",
        "source_commit": commit,
        "dataset_manifest": {
            "path": str(manifest_path),
            "sha256": _sha256(manifest_path),
        },
        "development_locator": dict(
            manifest["partition_locators"]["development"]
        ),
        "cases": list(experiment_plan["cases"]),
        "train_sizes": list(experiment_plan["train_sizes"]),
        "seed": int(experiment_plan["model_fit_seeds"][0]),
        "cell_count": len(cells),
        "cells": cells,
        "source_artifacts": source_artifacts,
        "wall_sec": float(time.perf_counter() - started),
        "access_state": {
            "development_locator_accessed": True,
            "calibration_locator_accessed": False,
            "offline_test_locator_accessed": False,
            "simulator_launched": False,
        },
        "frozen_v5_performance_failure_unchanged": True,
        "performance_accepted": False,
        "transferable_to_successor_architecture": False,
    }
    _write_json_atomic(output / "development_checkpoint_summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    summary = run(
        dataset_manifest=arguments.dataset_manifest,
        output_dir=arguments.output_dir,
        source_commit=arguments.source_commit,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "cell_count": summary["cell_count"],
                "wall_sec": summary["wall_sec"],
                "calibration_locator_accessed": False,
                "offline_test_locator_accessed": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
