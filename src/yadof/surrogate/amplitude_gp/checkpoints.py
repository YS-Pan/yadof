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
from .settings import AmplitudeGPSettings

COMPONENT_NAMESPACE = "amplitude-gp"
MODEL_NAME = "amplitude-shape-gaussian-process"
FORMAT = "yadof.amplitude-gp-checkpoint/v2"
RECOVERY_ERRORS = (KeyError, OSError, TypeError, ValueError, EOFError, zipfile.BadZipFile)


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def namespace(root, strategy):
    return Path(root) / "runs" / run_namespace_for_signature(strategy) / "components" / COMPONENT_NAMESPACE


def publication_paths(root, generation, strategy):
    return new_publication_paths(root, generation_index=generation,
                                 strategy_signature=strategy, component_namespace=COMPONENT_NAMESPACE)


def _save_map(arrays, prefix, response):
    if response is None:
        return None
    description = {"scale": response.scale, "diagnostics": response.diagnostics}
    if response.model is None:
        arrays[prefix + "_constant"] = response.constant
        description["kind"] = "constant"
    else:
        model = response.model
        for key, value in (("theta", model.kernel.theta), ("x", model.x_train),
                           ("alpha", model.alpha), ("mean", model.mean), ("std", model.std)):
            arrays[prefix + "_" + key] = np.asarray(value)
        description["kind"] = "gp-mean"
    return description


def write_checkpoint(state, *, root, staging_dir, cancel_event=None):
    from .model import check_cancelled

    root, staging, artifact = Path(root).resolve(), Path(staging_dir).resolve(), state.artifact_dir.resolve()
    expected = namespace(root, state.identity["strategy_signature"]).resolve()
    if staging.parent != expected or artifact.parent != expected or artifact.exists():
        raise ValueError("amplitude_gp publication paths must be new and inside their namespace")
    arrays = {"training_inputs": np.asarray(state.training_normalized_variables, dtype=np.float64)}
    fields = []
    for index, field in enumerate(state.model.fields):
        prefix = f"field{index}"
        description = {
            "minimum": _save_map(arrays, prefix + "_minimum", field.minimum),
            "span": _save_map(arrays, prefix + "_span", field.span),
            "shape": _save_map(arrays, prefix + "_shape", field.shape),
            "low_center": field.low_center, "low_scale": field.low_scale,
            "diagnostics": field.diagnostics,
        }
        if field.codec is None:
            arrays[prefix + "_constant_shape"] = field.constant_shape
            description["codec"] = "constant"
        else:
            arrays[prefix + "_components"] = field.codec.components
            arrays[prefix + "_mean"] = field.codec.mean
            description["codec"] = "pca"
        fields.append(description)
    check_cancelled(cancel_event)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        np.savez_compressed(staging / "model.npz", **arrays)
        artifact_hash = hashlib.sha256((staging / "model.npz").read_bytes()).hexdigest()
        payload = {
            "format": FORMAT, "component": COMPONENT_NAMESPACE, "model": MODEL_NAME,
            "generation_index": state.generation_index, "sample_count": state.sample_count,
            "state_signature": state.state_signature, "identity": state.identity,
            "training_data_digest": state.training_data_digest,
            "training_provenance_digest": state.training_provenance_digest,
            "training_row_ids": list(state.training_row_ids),
            "training_provenance": state.training_provenance,
            "train_history": state.train_history, "fields": fields,
            "artifact_dir": artifact.relative_to(root).as_posix(),
            "artifact_file": "model.npz", "artifact_sha256": artifact_hash,
        }
        # Validate JSON before making a publication visible.
        json.dumps(payload, allow_nan=False)
        check_cancelled(cancel_event)
        os.replace(staging, artifact)
        atomic_write_json(state.namespace_manifest_path, payload)
        atomic_write_json(state.checkpoint_path, payload)
    finally:
        # Only this call owns this unique staging directory; never remove publications.
        if staging.is_dir():
            shutil.rmtree(staging)


def validate_manifest(payload):
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ValueError("not an amplitude_gp checkpoint")
    if payload.get("component") != COMPONENT_NAMESPACE or payload.get("model") != MODEL_NAME:
        raise ValueError("amplitude_gp checkpoint component mismatch")
    if payload.get("artifact_file") != "model.npz":
        raise ValueError("amplitude_gp checkpoint artifact filename mismatch")
    identity = payload["identity"]
    if not isinstance(identity, dict) or hash_json(identity) != payload["state_signature"]:
        raise ValueError("amplitude_gp checkpoint state signature mismatch")
    for name in ("state_signature", "training_data_digest", "training_provenance_digest", "artifact_sha256"):
        digest = payload[name]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"amplitude_gp invalid {name}")
    for name, minimum in (("generation_index", 0), ("sample_count", 2)):
        value = payload[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"amplitude_gp invalid {name}")
    row_ids = payload["training_row_ids"]
    if not isinstance(row_ids, list) or len(set(row_ids)) != len(row_ids) or len(row_ids) < payload["sample_count"]:
        raise ValueError("amplitude_gp checkpoint row identities are invalid")
    if identity["training_data_digest"] != payload["training_data_digest"]:
        raise ValueError("amplitude_gp checkpoint evidence digest mismatch")
    return payload


def resolve_artifact_dir(root, payload):
    root = Path(root).resolve()
    relative = Path(payload["artifact_dir"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("amplitude_gp artifact path must stay below checkpoint root")
    result = (root / relative).resolve()
    expected = namespace(root, payload["identity"]["strategy_signature"]).resolve()
    if result.parent != expected:
        raise ValueError("amplitude_gp artifact is outside its declared namespace")
    return result


def load_model(root, payload, *, template):
    from .model import AmplitudeModel, FieldModel, GaussianMean, ResponseMap, ShapeCodec, make_kernel

    payload = validate_manifest(payload)
    path = resolve_artifact_dir(root, payload) / "model.npz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != payload["artifact_sha256"]:
        raise ValueError("amplitude_gp checkpoint artifact digest mismatch")
    identity = payload["identity"]
    if identity["schema_signature"] != template.signature:
        raise ValueError("amplitude_gp checkpoint schema mismatch")
    settings = AmplitudeGPSettings(**identity["settings"])
    width = len(identity["parameter_names"])
    fit_rows = min(settings.gp_max_rows, payload["sample_count"])
    descriptions = payload["fields"]
    if not isinstance(descriptions, list) or len(descriptions) != len(template.fields):
        raise ValueError("amplitude_gp checkpoint field count mismatch")
    fields = []
    with np.load(path, allow_pickle=False) as arrays:
        used = set()

        def array(key, shape):
            values = np.asarray(arrays[key])
            if values.dtype.kind != "f" or values.shape != shape or not np.all(np.isfinite(values)):
                raise ValueError(f"amplitude_gp checkpoint array is invalid: {key}")
            used.add(key)
            return values.copy()

        def response(prefix, info, outputs):
            if info is None:
                return None
            scale = float(info["scale"])
            if not np.isfinite(scale) or scale <= 0:
                raise ValueError("amplitude_gp response scale must be positive")
            if info["kind"] == "constant":
                return ResponseMap(None, array(prefix + "_constant", (outputs,)), scale, info["diagnostics"])
            if info["kind"] != "gp-mean":
                raise ValueError("amplitude_gp checkpoint response kind mismatch")
            kernel = make_kernel(width, settings)
            theta = array(prefix + "_theta", (width + 2,))
            if np.any(theta < kernel.bounds[:, 0] - 1e-10) or np.any(theta > kernel.bounds[:, 1] + 1e-10):
                raise ValueError("amplitude_gp checkpoint kernel bounds mismatch")
            kernel.theta = theta
            std = array(prefix + "_std", (outputs,))
            if np.any(std <= 0):
                raise ValueError("amplitude_gp checkpoint target scale mismatch")
            x = array(prefix + "_x", (fit_rows, width))
            if np.any(x < 0) or np.any(x > 1):
                raise ValueError("amplitude_gp checkpoint training parameters out of range")
            if not np.array_equal(x, inputs[gp_indices]):
                raise ValueError("amplitude_gp GP inputs differ from their declared fitted rows")
            model = GaussianMean(kernel, x, array(prefix + "_alpha", (fit_rows, outputs)),
                                 array(prefix + "_mean", (outputs,)), std)
            return ResponseMap(model, None, scale, info["diagnostics"])

        inputs = array("training_inputs", (len(payload["training_row_ids"]), width))
        if np.any(inputs < 0) or np.any(inputs > 1):
            raise ValueError("amplitude_gp fitted inputs are outside [0, 1]")
        lookup = {row_id: i for i, row_id in enumerate(payload["training_row_ids"])}
        gp_ids = payload["train_history"]["gp_row_ids"]
        if len(gp_ids) != fit_rows or len(set(gp_ids)) != fit_rows:
            raise ValueError("amplitude_gp GP row identity count mismatch")
        gp_indices = [lookup[row_id] for row_id in gp_ids]
        for index, (description, field) in enumerate(zip(descriptions, template.fields, strict=True)):
            prefix = f"field{index}"
            field_width = int(np.prod(field.main_shape))
            minimum = response(prefix + "_minimum", description["minimum"], 1)
            span = response(prefix + "_span", description["span"], 1)
            center, scale = float(description["low_center"]), float(description["low_scale"])
            if minimum is None or not np.isfinite(center) or not np.isfinite(scale) or scale <= 0:
                raise ValueError("amplitude_gp checkpoint minimum transform mismatch")
            if description["codec"] == "constant":
                constant_shape = array(prefix + "_constant_shape", (field_width,))
                codec = shape = None
                if description["shape"] is not None:
                    raise ValueError("constant amplitude_gp field cannot contain a shape GP")
            elif description["codec"] == "pca":
                rank = min(settings.shape_rank, payload["sample_count"] - 1, field_width)
                codec = ShapeCodec(array(prefix + "_components", (rank, field_width)),
                                   array(prefix + "_mean", (field_width,)))
                shape = response(prefix + "_shape", description["shape"], rank)
                constant_shape = None
                if shape is None:
                    raise ValueError("amplitude_gp PCA field requires a shape map")
            else:
                raise ValueError("amplitude_gp checkpoint codec kind mismatch")
            fields.append(FieldModel(minimum, center, scale, span, shape, constant_shape, codec,
                                     description["diagnostics"]))
        if used != set(arrays.files):
            raise ValueError("amplitude_gp checkpoint contains unexpected arrays")
    return AmplitudeModel(template, tuple(fields), dict(payload["train_history"]))


def load_training_inputs(root, payload):
    """Read exact fitted coordinates for verified physical-record reconciliation."""
    payload = validate_manifest(payload)
    path = resolve_artifact_dir(root, payload) / "model.npz"
    if hashlib.sha256(path.read_bytes()).hexdigest() != payload["artifact_sha256"]:
        raise ValueError("amplitude_gp checkpoint artifact digest mismatch")
    with np.load(path, allow_pickle=False) as arrays:
        values = np.asarray(arrays["training_inputs"])
        shape = (len(payload["training_row_ids"]), len(payload["identity"]["parameter_names"]))
        if values.dtype.kind != "f" or values.shape != shape or not np.all(np.isfinite(values)):
            raise ValueError("amplitude_gp fitted coordinate array is invalid")
        if np.any(values < 0) or np.any(values > 1):
            raise ValueError("amplitude_gp fitted coordinates are outside [0, 1]")
        return tuple(tuple(float(value) for value in row) for row in values)
