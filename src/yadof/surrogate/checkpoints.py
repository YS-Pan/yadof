from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Mapping
import uuid

import numpy as np
import torch

from .modeling import INRTrainConfig
from .types import RawDataSchema, SurrogateState


CHECKPOINT_FORMAT_VERSION = 2
SURROGATE_METHOD = "conditional_inr"
TRAINING_POLICY = "real_field_balanced"
COMPONENT_NAMESPACE = "conditional-inr"


def _array_signature(values: np.ndarray) -> dict[str, object]:
    array = np.ascontiguousarray(values)
    return {
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
    }


def semantic_state_signature(
    *,
    strategy_signature: str,
    parameter_names: tuple[str, ...],
    parameter_definition_signature: Mapping[str, object],
    schema: RawDataSchema | None,
    train_cfg: INRTrainConfig | None,
    torch_version: str | None = None,
) -> str:
    payload = {
        "format_version": CHECKPOINT_FORMAT_VERSION,
        "strategy_signature": str(strategy_signature),
        "surrogate_method": SURROGATE_METHOD,
        "training_policy": TRAINING_POLICY,
        "parameter_names": list(parameter_names),
        "parameter_definition_signature": dict(parameter_definition_signature),
        "schema": schema_payload(schema),
        "coord_table": _array_signature(
            np.zeros((0, 3), dtype=np.float32)
            if schema is None
            else schema.coord_table
        ),
        "field_ids": _array_signature(
            np.zeros((0,), dtype=np.int64)
            if schema is None
            else schema.field_ids
        ),
        "train_cfg": None if train_cfg is None else asdict(train_cfg),
        "torch_version": (
            str(torch.__version__)
            if torch_version is None
            else str(torch_version)
        ),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_namespace_for_signature(strategy_signature: str) -> str:
    signature = str(strategy_signature).lower()
    if len(signature) != 64 or any(
        char not in "0123456789abcdef" for char in signature
    ):
        raise ValueError(
            "strategy signature must be 64 lowercase hexadecimal characters"
        )
    return f"strategy-{signature[:16]}"


def new_publication_paths(
    checkpoint_dir: Path,
    *,
    generation_index: int,
    strategy_signature: str,
) -> tuple[Path, Path, Path, Path, str, str]:
    root = Path(checkpoint_dir)
    run_namespace = run_namespace_for_signature(strategy_signature)
    component_namespace = COMPONENT_NAMESPACE
    namespace_dir = (
        root
        / "runs"
        / run_namespace
        / "components"
        / component_namespace
    )
    publication_id = f"{time.time_ns():020d}_{uuid.uuid4().hex}"
    stem = f"generation_{int(generation_index):04d}"
    return (
        root / f"{stem}.json",
        namespace_dir / f"{stem}_{publication_id}.json",
        namespace_dir / f"{stem}_{publication_id}",
        namespace_dir / f".{stem}_{publication_id}.tmp",
        run_namespace,
        component_namespace,
    )


def validate_manifest_identity(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("surrogate checkpoint manifest must be a JSON object")
    if int(payload["format_version"]) != CHECKPOINT_FORMAT_VERSION:
        raise ValueError("unsupported surrogate checkpoint format_version")
    if str(payload["surrogate_method"]) != SURROGATE_METHOD:
        raise ValueError("unsupported surrogate checkpoint method")
    if str(payload["training_policy"]) != TRAINING_POLICY:
        raise ValueError("unsupported surrogate checkpoint training policy")
    signature = str(payload["state_signature"])
    if len(signature) != 64 or any(
        char not in "0123456789abcdef" for char in signature
    ):
        raise ValueError(
            "surrogate state signature must be 64 lowercase hexadecimal characters"
        )
    strategy_signature = str(payload["strategy_signature"])
    if str(payload["run_namespace"]) != run_namespace_for_signature(
        strategy_signature
    ):
        raise ValueError(
            "surrogate checkpoint run namespace does not match its signature"
        )
    if str(payload["component_namespace"]) != COMPONENT_NAMESPACE:
        raise ValueError("unsupported surrogate checkpoint component namespace")
    if not isinstance(payload["parameter_definition_signature"], Mapping):
        raise ValueError(
            "surrogate checkpoint parameter definition signature must be an object"
        )
    if not str(payload["torch_version"]):
        raise ValueError("surrogate checkpoint torch version must be non-empty")
    publication_id = str(payload["publication_id"])
    if not publication_id or any(
        char not in "0123456789_abcdef" for char in publication_id
    ):
        raise ValueError("invalid surrogate checkpoint publication id")
    return payload


def resolve_artifact_dir(checkpoint_dir: Path, payload: object) -> Path:
    manifest = validate_manifest_identity(payload)
    root = Path(checkpoint_dir).resolve()
    relative = Path(str(manifest["artifact_dir"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(
            "surrogate checkpoint artifact path must stay below its checkpoint root"
        )
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("surrogate checkpoint artifact path escapes its checkpoint root")
    expected_parent = (
        root
        / "runs"
        / str(manifest["run_namespace"])
        / "components"
        / str(manifest["component_namespace"])
    ).resolve()
    if resolved.parent != expected_parent:
        raise ValueError(
            "surrogate checkpoint artifact is outside its declared namespace"
        )
    expected_name = (
        f"generation_{int(manifest['generation_index']):04d}_"
        f"{manifest['publication_id']}"
    )
    if resolved.name != expected_name:
        raise ValueError(
            "surrogate checkpoint artifact name does not match its publication"
        )
    return resolved


def resolve_namespace_manifest_path(
    checkpoint_dir: Path, payload: object
) -> Path:
    manifest = validate_manifest_identity(payload)
    root = Path(checkpoint_dir).resolve()
    relative = Path(str(manifest["namespace_manifest"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(
            "surrogate namespace manifest path must stay below its checkpoint root"
        )
    resolved = (root / relative).resolve()
    expected_parent = (
        root
        / "runs"
        / str(manifest["run_namespace"])
        / "components"
        / str(manifest["component_namespace"])
    ).resolve()
    expected_name = (
        f"generation_{int(manifest['generation_index']):04d}_"
        f"{manifest['publication_id']}.json"
    )
    if resolved.parent != expected_parent or resolved.name != expected_name:
        raise ValueError(
            "surrogate namespace manifest is outside its declared namespace"
        )
    return resolved


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as stream:
            json.dump(
                payload,
                stream,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def schema_payload(schema: RawDataSchema | None) -> dict[str, object]:
    if schema is None:
        return {"flat_dim": 0, "modeled_slots": []}
    return {
        "rawdata_item_count": len(schema.templates),
        "flat_dim": int(schema.flat_dim),
        "query_count": int(schema.coord_table.shape[0]),
        "n_fields": int(schema.n_fields),
        "modeled_slots": [
            {
                "item_index": int(slot.item_index),
                "key": slot.key,
                "shape": list(slot.shape),
                "dtype": slot.dtype,
                "start": int(slot.start),
                "end": int(slot.end),
                "field_id": int(slot.field_id),
            }
            for slot in schema.modeled_slots
        ],
    }


def _write_auxiliary_artifact(
    state: SurrogateState,
    staging_dir: Path,
) -> None:
    arrays: dict[str, np.ndarray] = {
        "schema_flat_dim": np.asarray(
            0 if state.schema is None else state.schema.flat_dim,
            dtype=np.int64,
        ),
        "training_sample_count": np.asarray(state.sample_count, dtype=np.int64),
    }
    if state.schema is not None:
        arrays["coord_table"] = np.ascontiguousarray(
            state.schema.coord_table,
            dtype=np.float32,
        )
        arrays["field_ids"] = np.ascontiguousarray(
            state.schema.field_ids,
            dtype=np.int64,
        )
    if state.scaler is not None:
        arrays["target_mean"] = np.ascontiguousarray(
            state.scaler.mean,
            dtype=np.float32,
        )
        arrays["target_scale"] = np.ascontiguousarray(
            state.scaler.scale,
            dtype=np.float32,
        )
    np.savez_compressed(staging_dir / state.model_path.name, **arrays)


def _checkpoint_payload(
    state: SurrogateState,
    checkpoint_root: Path,
) -> dict[str, object]:
    prefix = f"generation_{int(state.generation_index):04d}_"
    manifest_stem = state.namespace_manifest_path.stem
    if not manifest_stem.startswith(prefix):
        raise ValueError(
            "surrogate namespace manifest does not encode its generation"
        )
    publication_id = manifest_stem[len(prefix) :]
    return {
        "format_version": CHECKPOINT_FORMAT_VERSION,
        "surrogate_method": SURROGATE_METHOD,
        "training_policy": TRAINING_POLICY,
        "strategy_signature": state.strategy_signature,
        "state_signature": state.state_signature,
        "run_namespace": state.run_namespace,
        "component_namespace": state.component_namespace,
        "publication_id": publication_id,
        "torch_version": str(torch.__version__),
        "generation_index": int(state.generation_index),
        "sample_count": int(state.sample_count),
        "parameter_names": list(state.parameter_names),
        "parameter_definition_signature": dict(
            state.parameter_definition_signature
        ),
        "model": state.model_name,
        "member_count": int(state.train_history.get("member_count", 0)),
        "model_path": state.model_path.name,
        "artifact_dir": state.artifact_dir.relative_to(checkpoint_root).as_posix(),
        "namespace_manifest": state.namespace_manifest_path.relative_to(
            checkpoint_root
        ).as_posix(),
        "schema": schema_payload(state.schema),
        "train_cfg": None if state.train_cfg is None else asdict(state.train_cfg),
        "train_history": state.train_history,
        "note": (
            "The real-field-balanced conditional INR predicts full rawData; "
            "current costs are derived through submit/calc_cost.py. "
            "Ensemble spread is diagnostic, not calibrated confidence."
        ),
    }


def write_checkpoint(
    state: SurrogateState,
    *,
    staged_artifact_dir: Path,
) -> None:
    """Publish an artifact tree and pointer, then commit its namespace manifest."""

    checkpoint_root = state.checkpoint_path.parent.resolve()
    staging = Path(staged_artifact_dir).resolve()
    artifact_dir = state.artifact_dir.resolve()
    if staging.parent != artifact_dir.parent:
        raise ValueError(
            "checkpoint staging and artifact directories must share a parent"
        )
    if artifact_dir.exists():
        raise FileExistsError(artifact_dir)
    staging.mkdir(parents=True, exist_ok=True)
    _write_auxiliary_artifact(state, staging)

    member_count = int(state.train_history.get("member_count", 0))
    if member_count > 0:
        required = [staging / "inr_meta.json"] + [
            staging / f"member_{index:03d}.pt"
            for index in range(member_count)
        ]
        missing = [path.name for path in required if not path.is_file()]
        if missing:
            raise ValueError(
                "checkpoint staging is missing model artifact(s): "
                + ", ".join(missing)
            )

    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, artifact_dir)
    payload = _checkpoint_payload(state, checkpoint_root)
    validate_manifest_identity(payload)
    _atomic_write_json(state.checkpoint_path, payload)
    _atomic_write_json(state.namespace_manifest_path, payload)


__all__ = [
    "CHECKPOINT_FORMAT_VERSION",
    "COMPONENT_NAMESPACE",
    "SURROGATE_METHOD",
    "TRAINING_POLICY",
    "new_publication_paths",
    "resolve_artifact_dir",
    "resolve_namespace_manifest_path",
    "run_namespace_for_signature",
    "schema_payload",
    "semantic_state_signature",
    "validate_manifest_identity",
    "write_checkpoint",
]
