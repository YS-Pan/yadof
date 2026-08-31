"""Atomic, no-pickle checkpoint contract for the PCA/SVD surrogate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

import numpy as np

from .._shared.artifacts import atomic_write_json, new_publication_paths, run_namespace_for_signature
from .settings import LinearSubspaceSettings
from .types import FieldBasis, LinearSubspaceModel, LinearSubspaceState


SURROGATE_METHOD = "pca_svd"
TRAINING_POLICY = "per_field_lowrank_ridge"
COMPONENT_NAMESPACE = "pca-svd"
MODEL_NAME = "pca-svd-ridge-rawdata"


def state_signature(
    *, strategy_signature: str, parameter_names: tuple[str, ...],
    parameter_definition_signature: Mapping[str, object], schema_signature: str,
    training_data_digest: str, settings: LinearSubspaceSettings,
    numpy_version: str, torch_version: str,
) -> str:
    return _hash_json({
        "strategy_signature": strategy_signature,
        "surrogate_method": SURROGATE_METHOD,
        "training_policy": TRAINING_POLICY,
        "parameter_names": list(parameter_names),
        "parameter_definition_signature": dict(parameter_definition_signature),
        "schema_signature": schema_signature,
        "training_data_digest": training_data_digest,
        "settings": settings.semantic_parameters(),
        "numpy_version": numpy_version,
        "torch_version": torch_version,
    })


def publication_paths(checkpoint_dir: Path, generation_index: int, strategy_signature: str):
    return new_publication_paths(
        checkpoint_dir, generation_index=generation_index,
        strategy_signature=strategy_signature, component_namespace=COMPONENT_NAMESPACE,
    )


def write_checkpoint(state: LinearSubspaceState, *, staging_dir: Path) -> None:
    root = state.checkpoint_path.parent.resolve()
    staging = Path(staging_dir).resolve()
    artifact_dir = state.artifact_dir.resolve()
    if staging.parent != artifact_dir.parent:
        raise ValueError("checkpoint staging and artifact directories must share a parent")
    if artifact_dir.exists():
        raise FileExistsError(artifact_dir)
    staging.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {
        "ridge_weights": np.ascontiguousarray(state.model.ridge_weights),
        "coefficient_offsets": np.asarray(state.model.coefficient_offsets, dtype=np.int64),
    }
    for index, field in enumerate(state.model.fields):
        prefix = f"field_{index:04d}_"
        arrays[prefix + "mean"] = np.ascontiguousarray(field.mean)
        arrays[prefix + "basis"] = np.ascontiguousarray(field.basis)
        arrays[prefix + "singular_values"] = np.ascontiguousarray(field.singular_values)
    np.savez_compressed(staging / state.artifact_path.name, **arrays)
    artifact_hash = hashlib.sha256((staging / state.artifact_path.name).read_bytes()).hexdigest()
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, artifact_dir)
    payload = _manifest_payload(state, root, artifact_hash)
    validate_manifest(payload)
    atomic_write_json(state.checkpoint_path, payload)
    atomic_write_json(state.namespace_manifest_path, payload)


def load_model(checkpoint_root: Path, payload: Mapping[str, object], *, template) -> LinearSubspaceModel:
    manifest = validate_manifest(dict(payload))
    artifact_dir = resolve_artifact_dir(checkpoint_root, manifest)
    artifact_path = artifact_dir / str(manifest["artifact_file"])
    if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != str(manifest["artifact_sha256"]):
        raise ValueError("pca_svd checkpoint artifact digest mismatch")
    raw_fields = manifest["fields"]
    if not isinstance(raw_fields, list):
        raise ValueError("pca_svd checkpoint fields must be a list")
    with np.load(artifact_path, allow_pickle=False) as arrays:
        fields = []
        for index, raw in enumerate(raw_fields):
            if not isinstance(raw, Mapping):
                raise ValueError("pca_svd checkpoint field must be an object")
            prefix = f"field_{index:04d}_"
            selector = tuple(str(value) for value in raw["selector"])
            fields.append(FieldBasis(
                selector=(selector[0], selector[1]),
                shape=tuple(int(value) for value in raw["shape"]),
                dtype=str(raw["dtype"]),
                mean=np.ascontiguousarray(arrays[prefix + "mean"], dtype=np.float64),
                basis=np.ascontiguousarray(arrays[prefix + "basis"], dtype=np.float64),
                singular_values=np.ascontiguousarray(arrays[prefix + "singular_values"], dtype=np.float64),
                requested_rank=int(raw["requested_rank"]),
                effective_rank=int(raw["effective_rank"]),
                rank_reason=str(raw["rank_reason"]),
            ))
        offsets = tuple(int(value) for value in arrays["coefficient_offsets"])
        weights = np.ascontiguousarray(arrays["ridge_weights"], dtype=np.float64)
    settings_payload = manifest["settings"]
    if not isinstance(settings_payload, Mapping):
        raise ValueError("pca_svd checkpoint settings must be an object")
    settings = LinearSubspaceSettings(**{
        key: settings_payload[key] for key in LinearSubspaceSettings.__dataclass_fields__
    })
    model = LinearSubspaceModel(
        settings=settings,
        parameter_names=tuple(str(value) for value in manifest["parameter_names"]),
        template=template,
        fields=tuple(fields),
        coefficient_offsets=offsets,
        ridge_weights=weights,
    )
    if template.signature != str(manifest["schema_signature"]):
        raise ValueError("pca_svd checkpoint schema no longer matches current rawData")
    if tuple(field.selector for field in fields) != template.field_selectors:
        raise ValueError("pca_svd checkpoint selectors no longer match current rawData")
    expected = (len(model.parameter_names) + int(settings.fit_intercept), model.coefficient_count)
    if weights.shape != expected:
        raise ValueError("pca_svd checkpoint ridge dimensions are inconsistent")
    return model


def validate_manifest(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("pca_svd checkpoint manifest must be a JSON object")
    if payload.get("surrogate_method") != SURROGATE_METHOD or payload.get("training_policy") != TRAINING_POLICY:
        raise ValueError("unsupported pca_svd checkpoint identity")
    strategy_signature = str(payload["strategy_signature"])
    if str(payload["run_namespace"]) != run_namespace_for_signature(strategy_signature):
        raise ValueError("pca_svd checkpoint run namespace mismatch")
    if payload.get("component_namespace") != COMPONENT_NAMESPACE:
        raise ValueError("unsupported pca_svd component namespace")
    for key in (
        "state_signature",
        "training_data_digest",
        "training_provenance_digest",
        "artifact_sha256",
    ):
        value = str(payload[key])
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"invalid pca_svd {key}")
    return payload


def resolve_artifact_dir(checkpoint_root: Path, payload: Mapping[str, object]) -> Path:
    root = Path(checkpoint_root).resolve()
    relative = Path(str(payload["artifact_dir"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("pca_svd artifact path must stay below checkpoint root")
    resolved = (root / relative).resolve()
    expected_parent = root / "runs" / str(payload["run_namespace"]) / "components" / COMPONENT_NAMESPACE
    if resolved.parent != expected_parent.resolve() or not resolved.is_relative_to(root):
        raise ValueError("pca_svd artifact is outside its declared namespace")
    return resolved


def _manifest_payload(state: LinearSubspaceState, root: Path, artifact_hash: str) -> dict[str, object]:
    model = state.model
    prefix = f"generation_{state.generation_index:04d}_"
    return {
        "surrogate_method": SURROGATE_METHOD,
        "training_policy": TRAINING_POLICY,
        "model": MODEL_NAME,
        "strategy_signature": state.strategy_signature,
        "state_signature": state.state_signature,
        "training_data_digest": state.training_data_digest,
        "training_provenance_digest": state.training_provenance_digest,
        "run_namespace": state.run_namespace,
        "component_namespace": state.component_namespace,
        "publication_id": state.namespace_manifest_path.stem[len(prefix):],
        "generation_index": state.generation_index,
        "sample_count": state.sample_count,
        "parameter_names": list(model.parameter_names),
        "parameter_definition_signature": dict(state.parameter_definition_signature),
        "training_row_ids": list(state.training_row_ids),
        "training_transform_id": state.training_transform_id,
        "training_provenance": dict(state.training_provenance),
        "settings": model.settings.semantic_parameters(),
        "numpy_version": np.__version__,
        "torch_version": _torch_version(),
        "schema_signature": model.template.signature,
        "fields": [{
            "selector": list(field.selector), "shape": list(field.shape),
            "dtype": field.dtype, "requested_rank": field.requested_rank,
            "effective_rank": field.effective_rank, "rank_reason": field.rank_reason,
        } for field in model.fields],
        "artifact_file": state.artifact_path.name,
        "artifact_sha256": artifact_hash,
        "artifact_dir": state.artifact_dir.relative_to(root).as_posix(),
        "namespace_manifest": state.namespace_manifest_path.relative_to(root).as_posix(),
        "train_history": dict(state.train_history),
        "note": "Deterministic parameters-to-ridge-coefficients-to-rawData surrogate. The reconstruction oracle is diagnostic-only and no posterior is exposed.",
    }


def _torch_version() -> str:
    from importlib import metadata

    return metadata.version("torch")


def _hash_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "COMPONENT_NAMESPACE", "MODEL_NAME", "SURROGATE_METHOD", "TRAINING_POLICY",
    "load_model", "publication_paths", "resolve_artifact_dir",
    "run_namespace_for_signature", "state_signature",
    "validate_manifest", "write_checkpoint",
]
