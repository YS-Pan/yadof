"""Owned fitting, exact/lagged recovery, and snapshot-bound current costs."""

from __future__ import annotations

from dataclasses import replace
from importlib import metadata
import json
from numbers import Integral
from pathlib import Path
import threading

import numpy as np

from ...config import load_config
from ...job_template import api as job_template_api
from ...job_template.rawdata_projector import task_rawdata_cost_projector
from ...job_template.rawdata_template import RawDataSchemaTemplate
from ...optimize.state import active_strategy_signature
from ...task_snapshot import GenerationTaskSnapshot, create_generation_snapshot
from ...workspace import WorkspaceContext
from .._shared.training_events import monotonic_time, now_text, record_training_event
from ..training import SurrogatePrediction, SurrogateTrainingData, TrainingHandle
from . import checkpoints
from .settings import DEFAULT_AMPLITUDE_GP_SETTINGS
from .types import AmplitudeGPState

_LOCK = threading.RLock()
_STATES = {}
_STANDALONE = checkpoints.hash_json({"standalone": "amplitude-gp", "version": 1})


def backend_versions():
    try:
        return {name: metadata.version(name) for name in ("numpy", "scipy", "scikit-learn", "threadpoolctl")}
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("amplitude_gp requires yadof[gp] (scipy, scikit-learn, threadpoolctl)") from exc


def strategy_signature(workspace):
    return active_strategy_signature(workspace) or _STANDALONE


def workspace_root(workspace):
    return (workspace.root if isinstance(workspace, WorkspaceContext) else Path(workspace)).resolve()


def selected_workspace(workspace):
    return workspace if isinstance(workspace, WorkspaceContext) else load_config(workspace).workspace


def workspace_state_key(workspace, settings):
    return (str(workspace.root.resolve()), str(workspace.recorded_data_dir.resolve()),
            str(workspace.surrogate_checkpoint_dir.resolve()), strategy_signature(workspace),
            checkpoints.hash_json(settings.semantic_parameters()))


def state_identity(snapshot, data, settings):
    return {
        "component": checkpoints.COMPONENT_NAMESPACE, "version": 2,
        "strategy_signature": strategy_signature(snapshot.config.workspace),
        "parameter_names": list(data.parameter_names),
        "parameter_definition_signature": job_template_api.get_parameter_definition_signature(snapshot.config.workspace),
        "schema_signature": data.schema_signature, "training_data_digest": data.content_digest,
        # Campaign snapshots place frozen program files outside submit_directory,
        # but both forms retain their hashes. Bind the complete source set so
        # standalone and campaign recovery agree without weakening cost identity.
        "priority_source_fingerprint": checkpoints.hash_json({
            "parameter_source": snapshot.source_hashes.get("job_template/parameters_constraints.py", ""),
            "submit_sources": {key: value for key, value in snapshot.source_hashes.items()
                               if key.startswith("submit/")},
        }),
        "settings": settings.semantic_parameters(), "backends": backend_versions(),
    }


def training_subset(data, row_ids):
    requested = tuple(row_ids)
    if requested == data.row_ids:
        return data
    if not requested or len(set(requested)) != len(requested):
        return None
    lookup = {row_id: index for index, row_id in enumerate(data.row_ids)}
    if any(row_id not in lookup for row_id in requested):
        return None
    indices = tuple(lookup[row_id] for row_id in requested)
    fields = ("normalized_variables", "raw_data", "evidence_ids", "statuses",
              "valid_mask", "lineage", "record_metadata")
    return SurrogateTrainingData(
        parameter_names=data.parameter_names, row_ids=requested, transform_id=data.transform_id,
        **{name: tuple(getattr(data, name)[index] for index in indices) for name in fields},
    )


def ordered_training_data(dataset, cost_table, *, row_ids=None, transform_id=None):
    from ..training import materialize_training_data

    data = materialize_training_data(dataset, cost_table, row_ids=row_ids, transform_id=transform_id)
    if row_ids is not None:
        return data  # Explicit caller order is part of the public training contract.
    indices = sorted(range(len(data.row_ids)), key=lambda i: (
        int(data.record_metadata[i].get("generation_index", -1)),
        int(data.record_metadata[i].get("population_index", -1)), data.row_ids[i]))
    if indices == list(range(len(indices))):
        return data
    return training_subset(data, tuple(data.row_ids[i] for i in indices)) if indices else data


def _require_data(data):
    if not isinstance(data, SurrogateTrainingData):
        raise TypeError("amplitude_gp requires explicit SurrogateTrainingData")
    if len(set(data.row_ids)) != len(data.row_ids):
        raise ValueError("amplitude_gp training row IDs must be unique")


def _template(data):
    if not data.selected_indices:
        raise ValueError("amplitude_gp has no valid training evidence")
    return RawDataSchemaTemplate.from_items(data.raw_data[data.selected_indices[0]].items)


def _provenance(data):
    def thaw(value):
        from collections.abc import Mapping
        if isinstance(value, Mapping):
            return {str(key): thaw(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [thaw(item) for item in value]
        return value
    return {name: thaw(getattr(data, name)) for name in (
        "row_ids", "evidence_ids", "statuses", "valid_mask", "lineage", "record_metadata", "transform_id")}


def _restore_formal_coordinates(snapshot, data, provenance, fitted_inputs):
    """Restore exact fitted X only after two exact physical-record proofs.

    A live session can retain the optimizer's normalized X while persisted
    evidence rematerializes normalize(physical X). No epsilon comparison is
    permitted: both values must describe the same unchanged committed record.
    """
    try:
        if not all(status == "committed:succeeded" for status in data.statuses):
            return None
        if not all(data.valid_mask) or any(data.lineage):
            return None
        for name in ("row_ids", "evidence_ids", "statuses", "valid_mask"):
            if tuple(getattr(data, name)) != tuple(provenance[name]):
                return None
        if len(fitted_inputs) != len(data.row_ids):
            return None
        workspace = snapshot.config.workspace
        for fitted, current, old_record, record in zip(
            fitted_inputs, data.normalized_variables, provenance["record_metadata"], data.record_metadata, strict=True
        ):
            old_raw, raw = dict(old_record["raw_variables"]), dict(record["raw_variables"])
            if checkpoints.hash_json(old_raw) != checkpoints.hash_json(raw):
                return None
            physical = tuple(float(raw[name]) for name in data.parameter_names)
            original_physical = job_template_api.denormalize_variables(workspace, fitted)
            if checkpoints.hash_json(list(original_physical)) != checkpoints.hash_json(list(physical)):
                return None
            canonical = job_template_api.normalize_variables(workspace, physical)
            if tuple(canonical) != tuple(current):
                return None
        return replace(data, normalized_variables=fitted_inputs)
    except (KeyError, TypeError, ValueError):
        return None


def train_with_snapshot(snapshot, data, *, generation_index, settings, cancel_event=None):
    from .model import check_cancelled, fit_amplitude_model

    _require_data(data)
    if data.sample_count < settings.minimum_training_samples:
        raise ValueError(f"amplitude_gp requires {settings.minimum_training_samples} valid training rows")
    if isinstance(generation_index, bool) or not isinstance(generation_index, Integral) or generation_index < 0:
        raise ValueError("amplitude_gp generation_index must be a nonnegative integer")
    generation = int(generation_index)
    started, started_at = monotonic_time(), now_text()
    check_cancelled(cancel_event)
    if tuple(snapshot.parameter_names) != data.parameter_names:
        raise ValueError("amplitude_gp training parameters do not match the task snapshot")
    identity = state_identity(snapshot, data, settings)
    ordering = data.selected_indices
    rows = tuple(data.normalized_variables[i] for i in ordering)
    samples = tuple(data.raw_data[i] for i in ordering)
    with task_rawdata_cost_projector(snapshot.config.workspace, _template(data)) as projector:
        projected = projector.project_draw("training-priority", samples, rows)
    costs = np.asarray(projected.cost_samples[0])
    if not np.all(projected.valid_mask[0]) or not np.all(np.isfinite(costs)):
        raise ValueError("amplitude_gp training priorities require valid current costs for every selected row")
    model = fit_amplitude_model(data, ordering, costs, settings=settings, cancel_event=cancel_event)
    check_cancelled(cancel_event)
    workspace = snapshot.config.workspace
    root = workspace.surrogate_checkpoint_dir
    alias, manifest, artifact, staging, _run, _component = checkpoints.publication_paths(
        root, generation, identity["strategy_signature"])
    history = {
        **model.diagnostics, "duration_sec": monotonic_time() - started,
        "priority_cost_digest": checkpoints.hash_json(costs.tolist()),
        "training_data_digest": data.content_digest, "training_provenance_digest": data.provenance_digest,
        "training_transform_id": data.transform_id, "posterior_capability": False,
        "interval_policy": "zero-width",
    }
    state = AmplitudeGPState(
        generation_index=generation, sample_count=data.sample_count,
        state_signature=checkpoints.hash_json(identity), training_data_digest=data.content_digest,
        training_provenance_digest=data.provenance_digest, identity=identity,
        training_row_ids=data.row_ids, training_normalized_variables=data.normalized_variables,
        training_provenance=_provenance(data), model=model,
        checkpoint_path=alias, namespace_manifest_path=manifest, artifact_dir=artifact,
        train_history=history,
    )
    checkpoints.write_checkpoint(state, root=root, staging_dir=staging, cancel_event=cancel_event)
    record_training_event(workspace, {
        "record_type": "surrogate_training", "status": "completed", "model": checkpoints.MODEL_NAME,
        "generation_index": generation, "sample_count": data.sample_count,
        "started_at": started_at, "ended_at": now_text(), "duration_sec": monotonic_time() - started,
        "strategy_signature": identity["strategy_signature"], "state_signature": state.state_signature,
        "training_data_digest": data.content_digest,
    })
    with _LOCK:
        key = workspace_state_key(workspace, settings)
        previous = _STATES.get(key)
        if previous is None or previous.generation_index <= generation:
            _STATES[key] = state
    return state


def start_fit(workspace, data, *, generation_index=0, settings=DEFAULT_AMPLITUDE_GP_SETTINGS,
              session=None, snapshot=None):
    _require_data(data)
    owned = create_generation_snapshot(load_config(workspace)) if snapshot is None else None
    selected = owned if snapshot is None else snapshot
    if not isinstance(selected, GenerationTaskSnapshot):
        raise TypeError("amplitude_gp fit requires a GenerationTaskSnapshot")
    if workspace_root(workspace) != selected.config.workspace.root.resolve():
        if owned is not None:
            owned.close()
        raise ValueError("amplitude_gp snapshot belongs to another workspace")
    try:
        return TrainingHandle(
            lambda cancel: train_with_snapshot(selected, data, generation_index=generation_index,
                                              settings=settings, cancel_event=cancel),
            session=session, snapshot=selected, owned_cleanup=None if owned is None else owned.close,
        ).start()
    except Exception:
        if owned is not None:
            owned.close()
        raise


def fit(workspace, data, **kwargs):
    handle = start_fit(workspace, data, **kwargs)
    try:
        return handle.wait()
    finally:
        handle.close()


def _recover(snapshot, data, settings, allow_lagged):
    if data.sample_count < settings.minimum_training_samples:
        return None
    workspace = snapshot.config.workspace
    key = workspace_state_key(workspace, settings)
    with _LOCK:
        state = _STATES.get(key)

    def matching_subset(row_ids, digest, provenance, fitted_inputs):
        if not allow_lagged and tuple(data.row_ids) != tuple(row_ids):
            return None
        subset = training_subset(data, row_ids)
        if subset is not None and subset.content_digest != digest:
            subset = _restore_formal_coordinates(snapshot, subset, provenance, fitted_inputs)
        return subset if subset is not None and subset.content_digest == digest else None

    if state is not None:
        subset = matching_subset(state.training_row_ids, state.training_data_digest,
                                 state.training_provenance, state.training_normalized_variables)
        if subset is not None and checkpoints.hash_json(state_identity(snapshot, subset, settings)) == state.state_signature:
            return state
    root = workspace.surrogate_checkpoint_dir
    directory = checkpoints.namespace(root, strategy_signature(workspace))
    if not directory.is_dir():
        return None
    for manifest in sorted(directory.glob("generation_*.json"), reverse=True):
        try:
            payload = checkpoints.validate_manifest(json.loads(manifest.read_text(encoding="utf-8")))
            fitted_inputs = checkpoints.load_training_inputs(root, payload)
            subset = matching_subset(tuple(payload["training_row_ids"]), payload["training_data_digest"],
                                     payload["training_provenance"], fitted_inputs)
            if subset is None:
                continue
            identity = state_identity(snapshot, subset, settings)
            if checkpoints.hash_json(identity) != payload["state_signature"]:
                continue
            if payload["sample_count"] != subset.sample_count:
                continue
            model = checkpoints.load_model(root, payload, template=_template(subset))
            state = AmplitudeGPState(
                generation_index=payload["generation_index"], sample_count=payload["sample_count"],
                state_signature=payload["state_signature"], training_data_digest=payload["training_data_digest"],
                training_provenance_digest=payload["training_provenance_digest"], identity=identity,
                training_row_ids=tuple(payload["training_row_ids"]),
                training_normalized_variables=fitted_inputs,
                training_provenance=dict(payload["training_provenance"]), model=model,
                checkpoint_path=root / f"generation_{payload['generation_index']:04d}.json",
                namespace_manifest_path=manifest, artifact_dir=checkpoints.resolve_artifact_dir(root, payload),
                train_history=dict(payload["train_history"]),
            )
            with _LOCK:
                _STATES[key] = state
            return state
        except checkpoints.RECOVERY_ERRORS:
            continue
    return None


def recover(workspace, data, *, settings=DEFAULT_AMPLITUDE_GP_SETTINGS, snapshot=None, allow_lagged=False):
    _require_data(data)
    owned = create_generation_snapshot(load_config(workspace)) if snapshot is None else None
    selected = owned if snapshot is None else snapshot
    try:
        if not isinstance(selected, GenerationTaskSnapshot):
            raise TypeError("amplitude_gp recovery requires a GenerationTaskSnapshot")
        if workspace_root(workspace) != selected.config.workspace.root.resolve():
            raise ValueError("amplitude_gp snapshot belongs to another workspace")
        return _recover(selected, data, settings, allow_lagged)
    finally:
        if owned is not None:
            owned.close()


def predict(state, population, *, snapshot):
    if not isinstance(state, AmplitudeGPState) or not isinstance(snapshot, GenerationTaskSnapshot):
        raise TypeError("amplitude_gp prediction requires AmplitudeGPState and GenerationTaskSnapshot")
    if list(snapshot.parameter_names) != state.identity["parameter_names"] or checkpoints.hash_json(
        job_template_api.get_parameter_definition_signature(snapshot.config.workspace)
    ) != checkpoints.hash_json(state.identity["parameter_definition_signature"]):
        raise ValueError("amplitude_gp prediction parameter definition differs from the fitted state")
    rows = tuple(tuple(float(v) for v in row) for row in population)
    width = len(state.identity["parameter_names"])
    if any(len(row) != width or any(not np.isfinite(v) or v < -1e-9 or v > 1 + 1e-9 for v in row)
           for row in rows):
        raise ValueError("amplitude_gp prediction requires finite normalized parameters in [0, 1]")
    rows = tuple(tuple(max(0.0, min(1.0, v)) for v in row) for row in rows)
    samples, collapsed = state.model.predict(np.asarray(rows)) if rows else ((), 0)
    if rows:
        with task_rawdata_cost_projector(snapshot.config.workspace, state.model.schema) as projector:
            projection = projector.project_draw("central-response", samples, rows)
        values = np.array(projection.cost_samples[0], dtype=float, copy=True)
        valid = tuple(bool(v) for v in projection.valid_mask[0])
        values[~np.asarray(valid)] = np.inf
        samples = tuple(sample if good else None for sample, good in zip(samples, valid, strict=True))
        costs = tuple(tuple(float(v) for v in row) for row in values)
        diagnostics = projection.diagnostics.as_dict()
    else:
        costs = valid = ()
        diagnostics = {}
    return SurrogatePrediction(
        state_signature=state.state_signature, training_data_digest=state.training_data_digest,
        normalized_variables=rows, raw_data=samples, costs=costs, valid_mask=valid,
        intervals=tuple(tuple((v, v) for v in row) for row in costs),
        interpretation_fingerprint=snapshot.interpretation_fingerprint,
        diagnostics={"component": checkpoints.COMPONENT_NAMESPACE, "posterior_capability": False,
                     "interval_policy": "zero-width", "candidate_count": len(rows),
                     "trained_generation": state.generation_index,
                     "collapsed_positive_span": collapsed, "cost_projection": diagnostics},
    )


def reset_workspace_state(workspace):
    root = str(workspace_root(workspace))
    with _LOCK:
        for key in tuple(_STATES):
            if key[0] == root:
                _STATES.pop(key, None)
