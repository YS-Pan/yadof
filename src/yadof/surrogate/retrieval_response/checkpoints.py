"""Atomic, namespace-isolated JSON/NPZ checkpoints with no pickle loading."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Mapping
import zipfile

import numpy as np

from .._shared.artifacts import atomic_write_json, new_publication_paths, run_namespace_for_signature
from .settings import RetrievalResponseSettings

COMPONENT_NAMESPACE = "retrieval-response"
MODEL_NAME = "joint-retrieval-response-delta"
FORMAT = "yadof.retrieval-response-checkpoint/v1"
RECOVERY_ERRORS = (KeyError, OSError, TypeError, ValueError, EOFError, zipfile.BadZipFile)


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def namespace(root, strategy):
    return Path(root) / "runs" / run_namespace_for_signature(strategy) / "components" / COMPONENT_NAMESPACE


def publication_paths(root, generation, strategy):
    return new_publication_paths(root, generation_index=generation,
                                 strategy_signature=strategy, component_namespace=COMPONENT_NAMESPACE)


def validate_manifest(payload):
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ValueError("not an retrieval_response checkpoint")
    if payload.get("component") != COMPONENT_NAMESPACE or payload.get("model") != MODEL_NAME:
        raise ValueError("retrieval_response checkpoint component mismatch")
    if payload.get("artifact_file") != "model.npz":
        raise ValueError("retrieval_response checkpoint artifact filename mismatch")
    identity = payload["identity"]
    if not isinstance(identity, dict) or hash_json(identity) != payload["state_signature"]:
        raise ValueError("retrieval_response checkpoint state signature mismatch")
    for name in ("state_signature", "training_data_digest", "training_provenance_digest", "artifact_sha256"):
        digest = payload[name]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"retrieval_response invalid {name}")
    for name, minimum in (("generation_index", 0), ("sample_count", 2)):
        value = payload[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"retrieval_response invalid {name}")
    row_ids = payload["training_row_ids"]
    if not isinstance(row_ids, list) or len(set(row_ids)) != len(row_ids) or len(row_ids) < payload["sample_count"]:
        raise ValueError("retrieval_response checkpoint row identities are invalid")
    if identity["training_data_digest"] != payload["training_data_digest"]:
        raise ValueError("retrieval_response checkpoint evidence digest mismatch")
    return payload


def resolve_artifact_dir(root, payload):
    root = Path(root).resolve()
    relative = Path(payload["artifact_dir"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("retrieval_response artifact path must stay below checkpoint root")
    result = (root / relative).resolve()
    expected = namespace(root, payload["identity"]["strategy_signature"]).resolve()
    if result.parent != expected:
        raise ValueError("retrieval_response artifact is outside its declared namespace")
    return result


def load_training_inputs(root, payload):
    """Read exact fitted coordinates for verified physical-record reconciliation."""
    payload = validate_manifest(payload)
    path = resolve_artifact_dir(root, payload) / "model.npz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != payload["artifact_sha256"]:
        raise ValueError("retrieval_response checkpoint artifact digest mismatch")
    with np.load(path, allow_pickle=False) as arrays:
        values = np.asarray(arrays["training_inputs"])
        shape = (len(payload["training_row_ids"]), len(payload["identity"]["parameter_names"]))
        if values.dtype.kind != "f" or values.shape != shape or not np.all(np.isfinite(values)):
            raise ValueError("retrieval_response fitted coordinate array is invalid")
        if np.any(values < 0) or np.any(values > 1):
            raise ValueError("retrieval_response fitted coordinates are outside [0, 1]")
        return tuple(tuple(float(value) for value in row) for row in values)


def _pack(value, arrays):
    from collections.abc import Mapping
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise ValueError("object arrays cannot enter retrieval_response checkpoints")
        key = f"schema_{len(arrays)}"
        arrays[key] = value
        return {"array": key}
    if isinstance(value, Mapping):
        return {"mapping": {str(k): _pack(v, arrays) for k, v in value.items()}}
    if isinstance(value, (tuple, list)):
        return {"sequence": [_pack(v, arrays) for v in value]}
    if isinstance(value, np.generic):
        value = value.item()
    return {"value": value}


def _unpack(value, arrays, used):
    if set(value) == {"array"}:
        key = value["array"]
        data = arrays[key]
        if data.dtype.hasobject:
            raise ValueError("object array in retrieval_response schema")
        used.add(key)
        return data.copy()
    if set(value) == {"mapping"}:
        return {k: _unpack(v, arrays, used) for k, v in value["mapping"].items()}
    if set(value) == {"sequence"}:
        return [_unpack(v, arrays, used) for v in value["sequence"]]
    if set(value) == {"value"}:
        return value["value"]
    raise ValueError("invalid retrieval_response schema encoding")


def write_checkpoint(state, *, root, staging_dir, cancel_event=None):
    from .model import check_cancelled
    root, staging, artifact = Path(root).resolve(), Path(staging_dir).resolve(), state.artifact_dir.resolve()
    expected = namespace(root, state.identity["strategy_signature"]).resolve()
    if staging.parent != expected or artifact.parent != expected or artifact.exists():
        raise ValueError("retrieval_response publication must stay inside a new namespace artifact")
    model = state.model
    arrays = {"training_inputs": np.asarray(state.training_normalized_variables, dtype=np.float64),
              "context_x": model.x, "context_z": model.z, "loss_weights": model.codec.weights}
    fields = []
    for index, codec in enumerate(model.codec.fields):
        prefix = f"field{index}"
        field = codec.field
        payload = dict(field.payload)
        payload[field.main_key] = np.zeros(field.main_shape, dtype=field.main_dtype)
        info = {"filename": field.filename, "main_key": field.main_key,
                "payload": _pack(payload, arrays), "rank": codec.rank}
        for key in ("low_center", "low_scale", "span_floor", "log_center", "log_scale", "shape_scale"):
            info[key] = getattr(codec, key)
        arrays[prefix + "_mean"] = codec.shape_mean
        if codec.components is not None:
            arrays[prefix + "_components"] = codec.components
        fields.append(info)
    for member_index, member in enumerate(model.members):
        for key, tensor in member.state_dict().items():
            arrays[f"member{member_index}_{key}"] = tensor.detach().cpu().numpy().copy()
    check_cancelled(cancel_event)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        np.savez_compressed(staging / "model.npz", **arrays)
        payload = {
            "format": FORMAT, "component": COMPONENT_NAMESPACE, "model": MODEL_NAME,
            "generation_index": state.generation_index, "sample_count": state.sample_count,
            "state_signature": state.state_signature, "identity": state.identity,
            "training_data_digest": state.training_data_digest,
            "training_provenance_digest": state.training_provenance_digest,
            "training_row_ids": list(state.training_row_ids), "training_provenance": state.training_provenance,
            "train_history": state.train_history, "fields": fields,
            "artifact_dir": artifact.relative_to(root).as_posix(), "artifact_file": "model.npz",
            "artifact_sha256": hashlib.sha256((staging / "model.npz").read_bytes()).hexdigest(),
        }
        json.dumps(payload, allow_nan=False)
        validate_manifest(payload)
        # Validate the complete numerical/schema payload before publication.
        _load_arrays(staging / "model.npz", payload, template=model.schema)
        check_cancelled(cancel_event)
        os.replace(staging, artifact)
        atomic_write_json(state.namespace_manifest_path, payload)
        atomic_write_json(state.checkpoint_path, payload)
    finally:
        if staging.is_dir():
            shutil.rmtree(staging)


def _load_arrays(path, payload, *, template):
    import torch
    from ...job_template.rawdata_template import RawDataFieldTemplate, RawDataSchemaTemplate
    from .model import FieldCodec, ResponseCodec, NeighborDeltaNet, RetrievalResponseModel, _runtime
    settings = RetrievalResponseSettings.from_parameters(payload["identity"]["settings"])
    parameters = settings.semantic_parameters()
    width, count = len(payload["identity"]["parameter_names"]), payload["sample_count"]
    with np.load(path, allow_pickle=False) as arrays:
        used = set()
        def array(key, shape, dtype):
            data = arrays[key]
            if data.dtype != np.dtype(dtype) or data.shape != shape or not np.all(np.isfinite(data)):
                raise ValueError(f"invalid retrieval_response checkpoint array: {key}")
            used.add(key)
            return data.copy()
        inputs = array("training_inputs", (len(payload["training_row_ids"]), width), "float64")
        x = array("context_x", (count, width), "float64")
        if np.any(inputs < 0) or np.any(inputs > 1):
            raise ValueError("retrieval_response fitted inputs outside [0,1]")
        ids = payload["train_history"]["context_row_ids"]
        if len(ids) != count or len(set(ids)) != count:
            raise ValueError("retrieval_response context IDs are invalid")
        lookup = {row: i for i, row in enumerate(payload["training_row_ids"])}
        if not np.array_equal(x, inputs[[lookup[row] for row in ids]]):
            raise ValueError("retrieval_response context coordinates do not match fitted identities")
        fields = []
        for index, info in enumerate(payload["fields"]):
            field = RawDataFieldTemplate(info["filename"], info["main_key"], _unpack(info["payload"], arrays, used))
            field_width = int(np.prod(field.main_shape))
            rank = info["rank"]
            if isinstance(rank, bool) or not isinstance(rank, int) or not 0 <= rank <= min(settings.shape_rank, count-1, field_width):
                raise ValueError("invalid retrieval_response codec rank")
            mean = array(f"field{index}_mean", (field_width,), "float64")
            components = array(f"field{index}_components", (rank, field_width), "float64") if rank else None
            for key in ("low_center", "low_scale", "log_center", "log_scale", "shape_scale"):
                if not isinstance(info[key], (int, float)) or not np.isfinite(info[key]):
                    raise ValueError("invalid retrieval_response codec scalar")
            if min(info["low_scale"], info["log_scale"], info["shape_scale"]) <= 0:
                raise ValueError("retrieval_response codec scales must be positive")
            floor = info["span_floor"]
            if floor is not None and (not isinstance(floor, (int, float)) or not np.isfinite(floor) or floor <= 0):
                raise ValueError("invalid retrieval_response span floor")
            fields.append(FieldCodec(field, info["low_center"], info["low_scale"], floor,
                info["log_center"], info["log_scale"], components, mean, info["shape_scale"]))
        schema = RawDataSchemaTemplate(tuple(c.field for c in fields))
        if schema.signature != payload["identity"]["schema_signature"] or schema.signature != template.signature:
            raise ValueError("retrieval_response checkpoint schema mismatch")
        codec = ResponseCodec(schema, fields)
        z = array("context_z", (count, codec.width), "float32")
        weights = array("loss_weights", (codec.width,), "float32")
        if not np.array_equal(weights, codec.weights):
            raise ValueError("retrieval_response loss weights mismatch")
        members = []
        with _runtime(parameters):
            for index in range(settings.members):
                member = NeighborDeltaNet(width, codec.width, settings.hidden_width)
                tensors = {key: torch.from_numpy(array(f"member{index}_{key}", tuple(value.shape), "float32"))
                           for key, value in member.state_dict().items()}
                member.load_state_dict(tensors, strict=True)
                member.eval()
                members.append(member)
        if used != set(arrays.files):
            raise ValueError("retrieval_response checkpoint has unexpected arrays")
    return RetrievalResponseModel(codec, x, z, members, parameters, dict(payload["train_history"]))


def load_model(root, payload, *, template):
    payload = validate_manifest(payload)
    path = resolve_artifact_dir(root, payload) / "model.npz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != payload["artifact_sha256"]:
        raise ValueError("retrieval_response artifact hash mismatch")
    return _load_arrays(path, payload, template=template)
