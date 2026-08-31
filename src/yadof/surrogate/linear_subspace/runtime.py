"""Workspace lifecycle, recovery, and current-cost projection for PCA/SVD."""

from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import threading
from typing import Mapping, Sequence

import numpy as np

from ...config import LoadedConfig, load_config
from ...job_template import api as job_template_api
from ...job_template.rawdata_template import RawDataSchemaTemplate, StructuredRawDataSample
from ...optimize.state import active_strategy_signature
from ...task_snapshot import GenerationTaskSnapshot, create_generation_snapshot
from ...workspace import WorkspaceContext
from .._shared.training_events import monotonic_time, now_text, record_training_event
from ..training import (
    SurrogatePrediction,
    SurrogateTrainingData,
    TrainingCancelledError,
    TrainingHandle,
)
from . import checkpoints
from .model import fit_linear_subspace, predict_raw_data as predict_model_raw_data
from .settings import DEFAULT_LINEAR_SUBSPACE_SETTINGS, LinearSubspaceSettings
from .types import LinearSubspaceState


StateKey = tuple[str, str, str, str, str, str]
WorkspaceLike = WorkspaceContext | str | Path

_STANDALONE_STRATEGY_SIGNATURE = hashlib.sha256(
    b"yadof:standalone-pca-svd-state:v1"
).hexdigest()
_LOCK = threading.RLock()
_STATES: dict[StateKey, LinearSubspaceState] = {}


def strategy_signature_for_workspace(workspace: WorkspaceContext) -> str:
    return active_strategy_signature(workspace) or _STANDALONE_STRATEGY_SIGNATURE


def workspace_state_key(
    config: LoadedConfig,
    *,
    settings: LinearSubspaceSettings,
) -> StateKey:
    workspace = config.workspace
    settings_signature = _hash_json(settings.semantic_parameters())
    return (
        str(workspace.root),
        str(workspace.config_file),
        str(workspace.recorded_data_dir),
        str(workspace.surrogate_checkpoint_dir),
        strategy_signature_for_workspace(workspace),
        f"{checkpoints.COMPONENT_NAMESPACE}:{settings_signature}",
    )


def train(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    generation_index: int = 0,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> LinearSubspaceState:
    return train_with_config(
        load_config(workspace),
        generation_index=generation_index,
        training_data=training_data,
        settings=_settings,
    )


def train_with_config(
    config: LoadedConfig,
    *,
    generation_index: int = 0,
    training_data: SurrogateTrainingData,
    settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    random_seed: int | None = None,
    cancel_event: threading.Event | None = None,
) -> LinearSubspaceState:
    del random_seed  # the component-owned settings snapshot is authoritative
    started_at = now_text()
    started = monotonic_time()
    if not isinstance(training_data, SurrogateTrainingData):
        raise TypeError("pca_svd fit requires SurrogateTrainingData")
    data = training_data
    if data.sample_count < 1:
        raise ValueError("pca_svd training requires at least one completed rawData row")
    _check_cancelled(cancel_event)
    model = fit_linear_subspace(data, settings)
    _check_cancelled(cancel_event)
    strategy_signature = strategy_signature_for_workspace(config.workspace)
    parameter_definition_signature = (
        job_template_api.get_parameter_definition_signature(config.workspace)
    )
    torch_version = metadata.version("torch")
    signature = checkpoints.state_signature(
        strategy_signature=strategy_signature,
        parameter_names=data.parameter_names,
        parameter_definition_signature=parameter_definition_signature,
        schema_signature=model.template.signature,
        training_data_digest=data.content_digest,
        settings=settings,
        numpy_version=np.__version__,
        torch_version=torch_version,
    )
    (
        checkpoint_path,
        namespace_manifest_path,
        artifact_dir,
        staging_dir,
        run_namespace,
        component_namespace,
    ) = checkpoints.publication_paths(
        config.workspace.surrogate_checkpoint_dir,
        int(generation_index),
        strategy_signature,
    )
    history = {
        "model": checkpoints.MODEL_NAME,
        "sample_count": data.sample_count,
        "field_count": len(model.fields),
        "requested_rank": settings.rank,
        "effective_ranks": [field.effective_rank for field in model.fields],
        "rank_reasons": [field.rank_reason for field in model.fields],
        "torch_version": torch_version,
        "duration_sec": monotonic_time() - started,
        "deterministic_intervals": "zero-width",
        "posterior_capability": False,
        "training_data_digest": data.content_digest,
        "training_provenance_digest": data.provenance_digest,
        "training_transform_id": data.transform_id,
    }
    selected = data.selected_indices
    provenance = {
        "row_ids": [data.row_ids[index] for index in selected],
        "evidence_ids": [data.evidence_ids[index] for index in selected],
        "statuses": [data.statuses[index] for index in selected],
        "valid_mask": list(data.valid_mask),
        "lineage": [
            [_thaw_json(step) for step in data.lineage[index]]
            for index in selected
        ],
        "transform_id": data.transform_id,
    }
    state = LinearSubspaceState(
        generation_index=int(generation_index),
        sample_count=data.sample_count,
        strategy_signature=strategy_signature,
        state_signature=signature,
        training_data_digest=data.content_digest,
        training_provenance_digest=data.provenance_digest,
        parameter_definition_signature=parameter_definition_signature,
        model=model,
        checkpoint_path=checkpoint_path,
        namespace_manifest_path=namespace_manifest_path,
        artifact_dir=artifact_dir,
        artifact_path=artifact_dir / "model.npz",
        run_namespace=run_namespace,
        component_namespace=component_namespace,
        training_row_ids=tuple(data.row_ids[index] for index in selected),
        training_transform_id=data.transform_id,
        training_provenance=provenance,
        train_history=history,
    )
    _check_cancelled(cancel_event)
    checkpoints.write_checkpoint(state, staging_dir=staging_dir)
    record_training_event(
        config.workspace,
        {
            "record_type": "surrogate_training",
            "status": "completed",
            "model": checkpoints.MODEL_NAME,
            "generation_index": int(generation_index),
            "sample_count": data.sample_count,
            "started_at": started_at,
            "ended_at": now_text(),
            "duration_sec": monotonic_time() - started,
            "strategy_signature": strategy_signature,
            "state_signature": signature,
            "training_data_digest": data.content_digest,
        },
    )
    with _LOCK:
        _STATES[workspace_state_key(config, settings=settings)] = state
    return state


def _training_template(data: SurrogateTrainingData) -> RawDataSchemaTemplate:
    selected = data.selected_indices
    if not selected:
        raise ValueError("no PCA/SVD training evidence is available")
    template = RawDataSchemaTemplate.from_items(data.raw_data[selected[0]].items)
    for index in selected:
        template.validate_sample(data.raw_data[index])
    return template


def _training_subset(
    data: SurrogateTrainingData,
    row_ids: Sequence[str],
) -> SurrogateTrainingData | None:
    """Recreate an earlier owned training view from current explicit evidence."""

    requested = tuple(str(value) for value in row_ids)
    if not requested:
        return None
    lookup = {row_id: index for index, row_id in enumerate(data.row_ids)}
    if any(row_id not in lookup for row_id in requested):
        return None
    indices = tuple(lookup[row_id] for row_id in requested)
    return SurrogateTrainingData(
        parameter_names=data.parameter_names,
        normalized_variables=tuple(data.normalized_variables[index] for index in indices),
        raw_data=tuple(data.raw_data[index] for index in indices),
        row_ids=requested,
        evidence_ids=tuple(data.evidence_ids[index] for index in indices),
        statuses=tuple(data.statuses[index] for index in indices),
        valid_mask=tuple(data.valid_mask[index] for index in indices),
        lineage=tuple(data.lineage[index] for index in indices),
        record_metadata=tuple(data.record_metadata[index] for index in indices),
        transform_id=data.transform_id,
    )


def _matching_training_subset(
    data: SurrogateTrainingData,
    row_ids: Sequence[str],
    content_digest: str,
) -> SurrogateTrainingData | None:
    try:
        subset = _training_subset(data, row_ids)
    except (KeyError, TypeError, ValueError):
        return None
    if subset is None or subset.content_digest != str(content_digest):
        return None
    return subset


def _recover_latest_state(
    config: LoadedConfig,
    training_data: SurrogateTrainingData,
    *,
    settings: LinearSubspaceSettings,
) -> LinearSubspaceState | None:
    root = config.workspace.surrogate_checkpoint_dir
    strategy = strategy_signature_for_workspace(config.workspace)
    namespace = (
        root
        / "runs"
        / checkpoints.run_namespace_for_signature(strategy)
        / "components"
        / checkpoints.COMPONENT_NAMESPACE
    )
    if not namespace.is_dir():
        return None
    try:
        template = _training_template(training_data)
    except (OSError, ValueError):
        return None
    parameter_signature = job_template_api.get_parameter_definition_signature(
        config.workspace
    )
    candidates = sorted(namespace.glob("generation_*.json"), reverse=True)
    for path in candidates:
        try:
            payload = checkpoints.validate_manifest(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if payload["strategy_signature"] != strategy:
                continue
            if payload["training_data_digest"] != training_data.content_digest:
                continue
            if not _json_equivalent(
                payload["parameter_definition_signature"],
                parameter_signature,
            ):
                continue
            if not _json_equivalent(
                payload["settings"],
                settings.semantic_parameters(),
            ):
                continue
            model = checkpoints.load_model(
                root, payload, template=template
            )
            expected = checkpoints.state_signature(
                strategy_signature=strategy,
                parameter_names=training_data.parameter_names,
                parameter_definition_signature=parameter_signature,
                schema_signature=template.signature,
                training_data_digest=training_data.content_digest,
                settings=settings,
                numpy_version=np.__version__,
                torch_version=metadata.version("torch"),
            )
            if payload["state_signature"] != expected:
                continue
            artifact_dir = checkpoints.resolve_artifact_dir(root, payload)
            stored_provenance = payload.get("training_provenance", {})
            return LinearSubspaceState(
                generation_index=int(payload["generation_index"]),
                sample_count=int(payload["sample_count"]),
                strategy_signature=strategy,
                state_signature=expected,
                training_data_digest=str(payload["training_data_digest"]),
                training_provenance_digest=str(payload["training_provenance_digest"]),
                parameter_definition_signature=parameter_signature,
                model=model,
                checkpoint_path=root / f"generation_{int(payload['generation_index']):04d}.json",
                namespace_manifest_path=path,
                artifact_dir=artifact_dir,
                artifact_path=artifact_dir / str(payload["artifact_file"]),
                run_namespace=str(payload["run_namespace"]),
                component_namespace=str(payload["component_namespace"]),
                training_row_ids=tuple(str(value) for value in payload.get("training_row_ids", ())),
                training_transform_id=(
                    None
                    if payload.get("training_transform_id") is None
                    else str(payload["training_transform_id"])
                ),
                training_provenance=(
                    dict(stored_provenance)
                    if isinstance(stored_provenance, Mapping)
                    else {}
                ),
                train_history=dict(payload.get("train_history", {})),
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _recover_latest_compatible_state(
    config: LoadedConfig,
    training_data: SurrogateTrainingData,
    *,
    settings: LinearSubspaceSettings,
) -> LinearSubspaceState | None:
    """Recover the newest state whose exact old rows remain in current evidence."""

    root = config.workspace.surrogate_checkpoint_dir
    strategy = strategy_signature_for_workspace(config.workspace)
    namespace = (
        root
        / "runs"
        / checkpoints.run_namespace_for_signature(strategy)
        / "components"
        / checkpoints.COMPONENT_NAMESPACE
    )
    if not namespace.is_dir():
        return None
    parameter_signature = job_template_api.get_parameter_definition_signature(
        config.workspace
    )
    for path in sorted(namespace.glob("generation_*.json"), reverse=True):
        try:
            payload = checkpoints.validate_manifest(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if payload["strategy_signature"] != strategy:
                continue
            if not _json_equivalent(
                payload["parameter_definition_signature"],
                parameter_signature,
            ):
                continue
            if not _json_equivalent(
                payload["settings"],
                settings.semantic_parameters(),
            ):
                continue
            subset = _matching_training_subset(
                training_data,
                tuple(str(value) for value in payload.get("training_row_ids", ())),
                str(payload["training_data_digest"]),
            )
            if subset is None:
                continue
            state = _recover_latest_state(config, subset, settings=settings)
            if state is not None:
                return state
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _latest_compatible_state(
    config: LoadedConfig,
    training_data: SurrogateTrainingData,
    *,
    settings: LinearSubspaceSettings,
) -> LinearSubspaceState | None:
    key = workspace_state_key(config, settings=settings)
    with _LOCK:
        state = _STATES.get(key)
    if state is not None:
        parameter_signature = job_template_api.get_parameter_definition_signature(
            config.workspace
        )
        subset = _matching_training_subset(
            training_data,
            state.training_row_ids,
            state.training_data_digest,
        )
        if (
            parameter_signature != state.parameter_definition_signature
            or subset is None
            or state.model.template.signature != subset.schema_signature
        ):
            state = None
    if state is None:
        state = _recover_latest_compatible_state(
            config,
            training_data,
            settings=settings,
        )
        if state is not None:
            with _LOCK:
                _STATES[key] = state
    return state


def _state_for_config(
    config: LoadedConfig,
    training_data: SurrogateTrainingData,
    *,
    settings: LinearSubspaceSettings,
) -> LinearSubspaceState | None:
    key = workspace_state_key(config, settings=settings)
    with _LOCK:
        state = _STATES.get(key)
    if state is not None:
        current_parameter_signature = (
            job_template_api.get_parameter_definition_signature(config.workspace)
        )
        if (
            current_parameter_signature != state.parameter_definition_signature
            or state.training_data_digest != training_data.content_digest
            or state.model.template.signature != training_data.schema_signature
        ):
            state = None
    if state is not None:
        return state
    state = _recover_latest_state(config, training_data, settings=settings)
    if state is not None:
        with _LOCK:
            state = _STATES.setdefault(key, state)
    return state


def has_trained_state(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> bool:
    return _state_for_config(
        load_config(workspace), training_data, settings=_settings
    ) is not None


def latest_state_generation(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> int | None:
    state = _state_for_config(
        load_config(workspace), training_data, settings=_settings
    )
    return None if state is None else state.generation_index


def _require_state(
    config: LoadedConfig,
    training_data: SurrogateTrainingData,
    *,
    settings: LinearSubspaceSettings,
) -> LinearSubspaceState:
    state = _state_for_config(config, training_data, settings=settings)
    if state is None:
        raise RuntimeError("pca_svd surrogate is not trained")
    return state


def recover_state(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _config: LoadedConfig | None = None,
) -> LinearSubspaceState | None:
    config = load_config(workspace) if _config is None else _config
    return _state_for_config(config, training_data, settings=_settings)


def recover_latest_compatible_state(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _config: LoadedConfig | None = None,
) -> LinearSubspaceState | None:
    """Return a lagged state only when its exact training rows remain unchanged."""

    config = load_config(workspace) if _config is None else _config
    return _latest_compatible_state(config, training_data, settings=_settings)


def latest_compatible_state_generation(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _config: LoadedConfig | None = None,
) -> int | None:
    state = recover_latest_compatible_state(
        workspace,
        training_data,
        _settings=_settings,
        _config=_config,
    )
    return None if state is None else int(state.generation_index)


def start_fit(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    generation_index: int = 0,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _config: LoadedConfig | None = None,
    _session=None,
    _snapshot: GenerationTaskSnapshot | None = None,
) -> TrainingHandle:
    owned_snapshot = None
    if _snapshot is None:
        base_config = load_config(workspace) if _config is None else _config
        owned_snapshot = create_generation_snapshot(base_config)
        selected_snapshot = owned_snapshot
    else:
        selected_snapshot = _snapshot
    config = selected_snapshot.config
    try:
        handle = TrainingHandle(
            lambda cancel_event: train_with_config(
                config,
                generation_index=int(generation_index),
                training_data=training_data,
                settings=_settings,
                cancel_event=cancel_event,
            ),
            session=_session,
            snapshot=selected_snapshot,
            owned_cleanup=(None if owned_snapshot is None else owned_snapshot.close),
        )
    except Exception:
        if owned_snapshot is not None:
            owned_snapshot.close()
        raise
    return handle.start()


def fit(
    workspace: WorkspaceLike,
    training_data: SurrogateTrainingData,
    *,
    generation_index: int = 0,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    _config: LoadedConfig | None = None,
    _session=None,
    _snapshot: GenerationTaskSnapshot | None = None,
) -> LinearSubspaceState:
    handle = start_fit(
        workspace,
        training_data,
        generation_index=generation_index,
        _settings=_settings,
        _config=_config,
        _session=_session,
        _snapshot=_snapshot,
    )
    try:
        state = handle.wait()
        if not isinstance(state, LinearSubspaceState):
            raise TypeError("pca_svd fit returned an invalid state")
        return state
    finally:
        handle.close()


def predict_raw_data(
    state: LinearSubspaceState,
    population,
) -> tuple[StructuredRawDataSample, ...]:
    if not isinstance(state, LinearSubspaceState):
        raise TypeError("pca_svd prediction requires LinearSubspaceState")
    return predict_model_raw_data(state.model, population)


def _costs_from_samples(
    workspace: WorkspaceContext,
    samples: Sequence[StructuredRawDataSample],
    normalized_variables,
) -> tuple[tuple[float, ...], ...]:
    raw_variables = tuple(
        job_template_api.denormalize_variables(workspace, row)
        for row in normalized_variables
    )
    costs = job_template_api.calculate_costs_from_raw_data(
        workspace,
        tuple(sample.cost_items() for sample in samples),
        raw_variables=raw_variables,
    )
    return tuple(tuple(float(value) for value in row) for row in costs)


def predict(
    state: LinearSubspaceState,
    population,
    *,
    snapshot: GenerationTaskSnapshot,
) -> SurrogatePrediction:
    if not isinstance(state, LinearSubspaceState):
        raise TypeError("pca_svd prediction requires LinearSubspaceState")
    if not isinstance(snapshot, GenerationTaskSnapshot):
        raise TypeError("pca_svd prediction requires GenerationTaskSnapshot")
    rows = tuple(
        tuple(float(value) for value in row)
        for row in (() if population is None else population)
    )
    if not rows:
        samples = ()
        costs = ()
    else:
        samples = predict_raw_data(state, rows)
        costs = _costs_from_samples(snapshot.config.workspace, samples, rows)
    intervals = tuple(
        tuple((value, value) for value in cost_row)
        for cost_row in costs
    )
    return SurrogatePrediction(
        state_signature=state.state_signature,
        training_data_digest=state.training_data_digest,
        normalized_variables=rows,
        raw_data=samples,
        costs=costs,
        intervals=intervals,
        interpretation_fingerprint=snapshot.interpretation_fingerprint,
        diagnostics={
            "component": checkpoints.COMPONENT_NAMESPACE,
            "posterior_capability": False,
            "interval_policy": "zero-width",
            "candidate_count": len(rows),
        },
    )


def predict_population(
    workspace: WorkspaceLike,
    population,
    *,
    _training_data: SurrogateTrainingData,
    _snapshot: GenerationTaskSnapshot,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> tuple[tuple[tuple[float, ...], tuple[tuple[float, float], ...]], ...]:
    state = _require_state(
        _snapshot.config,
        _training_data,
        settings=_settings,
    )
    return predict(state, population, snapshot=_snapshot).as_gpsaf_rows()


def reset_workspace_state(workspace: WorkspaceLike) -> None:
    config = load_config(workspace)
    root = str(config.workspace.root)
    with _LOCK:
        for key in tuple(key for key in _STATES if key[0] == root):
            _STATES.pop(key, None)


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _check_cancelled(event: threading.Event | None) -> None:
    if event is not None and event.is_set():
        raise TrainingCancelledError("surrogate fit cancelled before checkpoint commit")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _json_equivalent(left: object, right: object) -> bool:
    def encoded(value: object) -> str:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    try:
        return encoded(left) == encoded(right)
    except (TypeError, ValueError):
        return False


__all__ = [
    "fit",
    "has_trained_state",
    "latest_state_generation",
    "latest_compatible_state_generation",
    "predict",
    "predict_population",
    "predict_raw_data",
    "recover_state",
    "recover_latest_compatible_state",
    "reset_workspace_state",
    "start_fit",
    "strategy_signature_for_workspace",
    "train",
    "train_with_config",
    "workspace_state_key",
]
