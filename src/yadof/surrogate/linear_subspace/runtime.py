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
from ...job_template.rawdata_contract import NamedRawDataItem
from ...job_template.rawdata_template import RawDataSchemaTemplate, StructuredRawDataSample
from ...optimize.state import active_strategy_signature
from ...recorded_data import api as recorded_api
from ...recorded_data.session import CampaignSession
from ...task_snapshot import GenerationTaskSnapshot
from ...workspace import WorkspaceContext
from .._shared.training_events import monotonic_time, now_text, record_training_event
from . import checkpoints
from .model import fit_linear_subspace, predict_raw_data as predict_model_raw_data
from .settings import DEFAULT_LINEAR_SUBSPACE_SETTINGS, LinearSubspaceSettings
from .types import LinearSubspaceState, NamedTrainingData


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


def training_data_from_session(
    session: CampaignSession,
    snapshot: GenerationTaskSnapshot,
) -> NamedTrainingData:
    historical = session.historical_results(snapshot)
    job_names = tuple(name for name, _variables, _costs in historical)
    named = dict(session.named_rawdata_samples(job_names=job_names, status="completed"))
    metadata_rows = dict(session.record_metadata(job_names=job_names, status="completed"))
    variables = []
    samples = []
    selected_names = []
    metadata_output = []
    for job_name, normalized, _costs in historical:
        items = named.get(job_name)
        if items is None:
            continue
        selected_names.append(str(job_name))
        variables.append(tuple(float(value) for value in normalized))
        samples.append(StructuredRawDataSample.from_items(items))
        metadata_output.append(dict(metadata_rows.get(job_name, {})))
    return NamedTrainingData(
        parameter_names=tuple(snapshot.parameter_names),
        normalized_variables=tuple(variables),
        raw_data=tuple(samples),
        row_ids=tuple(selected_names),
        record_metadata=tuple(metadata_output),
    )


def _load_training_data(workspace: WorkspaceContext) -> NamedTrainingData:
    bundled = recorded_api.get_surrogate_training_data(workspace)
    names = tuple(str(value) for value in bundled.get("parameter_names", ()))
    variables = tuple(
        tuple(float(value) for value in row)
        for row in bundled.get("normalized_variables", ())
    )
    payload_rows = tuple(bundled.get("raw_data", ()))
    filename_rows = tuple(bundled.get("rawdata_filenames", ()))
    metadata_rows = tuple(bundled.get("record_metadata", ()))
    bundled_job_names = tuple(str(value) for value in bundled.get("job_names", ()))
    if len(payload_rows) != len(filename_rows):
        raise ValueError("recorded PCA/SVD training data is missing rawData filenames")
    samples = []
    row_ids = []
    for index, (filenames, payloads) in enumerate(zip(filename_rows, payload_rows)):
        if len(filenames) != len(payloads):
            raise ValueError("recorded rawData filenames and payloads must align")
        samples.append(
            StructuredRawDataSample.from_items(
                tuple(
                    NamedRawDataItem(str(filename), dict(payload))
                    for filename, payload in zip(filenames, payloads)
                )
            )
        )
        metadata_row = metadata_rows[index] if index < len(metadata_rows) else {}
        identity = bundled_job_names[index] if index < len(bundled_job_names) else None
        row_ids.append(str(identity or f"recorded-row-{index:08d}"))
    return NamedTrainingData(
        parameter_names=names,
        normalized_variables=variables,
        raw_data=tuple(samples),
        row_ids=tuple(row_ids),
        record_metadata=tuple(
            dict(value) if isinstance(value, Mapping) else {} for value in metadata_rows
        ),
    )


def train(
    workspace: WorkspaceLike,
    *,
    generation_index: int = 0,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> LinearSubspaceState:
    return train_with_config(
        load_config(workspace),
        generation_index=generation_index,
        settings=_settings,
    )


def train_with_config(
    config: LoadedConfig,
    *,
    generation_index: int = 0,
    training_data: NamedTrainingData | None = None,
    settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
    random_seed: int | None = None,
) -> LinearSubspaceState:
    del random_seed  # the component-owned settings snapshot is authoritative
    started_at = now_text()
    started = monotonic_time()
    data = training_data or _load_training_data(config.workspace)
    if not data.raw_data:
        raise ValueError("pca_svd training requires at least one completed rawData row")
    model = fit_linear_subspace(data, settings)
    strategy_signature = strategy_signature_for_workspace(config.workspace)
    parameter_definition_signature = (
        job_template_api.get_parameter_definition_signature(config.workspace)
    )
    provenance = checkpoints.training_design_signature(data)
    torch_version = metadata.version("torch")
    signature = checkpoints.state_signature(
        strategy_signature=strategy_signature,
        parameter_names=data.parameter_names,
        parameter_definition_signature=parameter_definition_signature,
        schema_signature=model.template.signature,
        training_design_signature=provenance,
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
        "sample_count": len(data.raw_data),
        "field_count": len(model.fields),
        "requested_rank": settings.rank,
        "effective_ranks": [field.effective_rank for field in model.fields],
        "rank_reasons": [field.rank_reason for field in model.fields],
        "torch_version": torch_version,
        "duration_sec": monotonic_time() - started,
        "deterministic_intervals": "zero-width",
        "posterior_capability": False,
    }
    state = LinearSubspaceState(
        generation_index=int(generation_index),
        sample_count=len(data.raw_data),
        strategy_signature=strategy_signature,
        state_signature=signature,
        training_design_signature=provenance,
        parameter_definition_signature=parameter_definition_signature,
        model=model,
        checkpoint_path=checkpoint_path,
        namespace_manifest_path=namespace_manifest_path,
        artifact_dir=artifact_dir,
        artifact_path=artifact_dir / "model.npz",
        run_namespace=run_namespace,
        component_namespace=component_namespace,
        training_row_ids=data.row_ids,
        train_history=history,
    )
    checkpoints.write_checkpoint(state, staging_dir=staging_dir)
    record_training_event(
        config.workspace,
        {
            "record_type": "surrogate_training",
            "status": "completed",
            "model": checkpoints.MODEL_NAME,
            "generation_index": int(generation_index),
            "sample_count": len(data.raw_data),
            "started_at": started_at,
            "ended_at": now_text(),
            "duration_sec": monotonic_time() - started,
            "strategy_signature": strategy_signature,
            "state_signature": signature,
        },
    )
    with _LOCK:
        _STATES[workspace_state_key(config, settings=settings)] = state
    return state


def _current_evidence(
    config: LoadedConfig,
) -> tuple[NamedTrainingData, RawDataSchemaTemplate, str]:
    data = _load_training_data(config.workspace)
    if not data.raw_data:
        raise ValueError("no PCA/SVD training evidence is available")
    template = RawDataSchemaTemplate.from_items(data.raw_data[0].items)
    for sample in data.raw_data:
        template.validate_sample(sample)
    return data, template, checkpoints.training_design_signature(data)


def _recover_latest_state(
    config: LoadedConfig,
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
        data, template, provenance = _current_evidence(config)
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
            if payload["training_design_signature"] != provenance:
                continue
            if payload["parameter_definition_signature"] != parameter_signature:
                continue
            if payload["settings"] != settings.semantic_parameters():
                continue
            model = checkpoints.load_model(
                root, payload, template=template
            )
            expected = checkpoints.state_signature(
                strategy_signature=strategy,
                parameter_names=data.parameter_names,
                parameter_definition_signature=parameter_signature,
                schema_signature=template.signature,
                training_design_signature=provenance,
                settings=settings,
                numpy_version=np.__version__,
                torch_version=metadata.version("torch"),
            )
            if payload["state_signature"] != expected:
                continue
            artifact_dir = checkpoints.resolve_artifact_dir(root, payload)
            return LinearSubspaceState(
                generation_index=int(payload["generation_index"]),
                sample_count=int(payload["sample_count"]),
                strategy_signature=strategy,
                state_signature=expected,
                training_design_signature=provenance,
                parameter_definition_signature=parameter_signature,
                model=model,
                checkpoint_path=root / f"generation_{int(payload['generation_index']):04d}.json",
                namespace_manifest_path=path,
                artifact_dir=artifact_dir,
                artifact_path=artifact_dir / str(payload["artifact_file"]),
                run_namespace=str(payload["run_namespace"]),
                component_namespace=str(payload["component_namespace"]),
                training_row_ids=data.row_ids,
                train_history=dict(payload.get("train_history", {})),
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _state_for_config(
    config: LoadedConfig,
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
        if current_parameter_signature != state.parameter_definition_signature:
            with _LOCK:
                _STATES.pop(key, None)
            state = None
    if state is not None:
        return state
    state = _recover_latest_state(config, settings=settings)
    if state is not None:
        with _LOCK:
            state = _STATES.setdefault(key, state)
    return state


def has_trained_state(
    workspace: WorkspaceLike,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> bool:
    return _state_for_config(load_config(workspace), settings=_settings) is not None


def latest_state_generation(
    workspace: WorkspaceLike,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> int | None:
    state = _state_for_config(load_config(workspace), settings=_settings)
    return None if state is None else state.generation_index


def _require_state(
    config: LoadedConfig,
    *,
    settings: LinearSubspaceSettings,
) -> LinearSubspaceState:
    state = _state_for_config(config, settings=settings)
    if state is None:
        raise RuntimeError("pca_svd surrogate is not trained")
    return state


def predict_raw_data(
    workspace: WorkspaceLike,
    population,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> tuple[StructuredRawDataSample, ...]:
    config = load_config(workspace)
    state = _require_state(config, settings=_settings)
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


def predict_population(
    workspace: WorkspaceLike,
    population,
    *,
    _settings: LinearSubspaceSettings = DEFAULT_LINEAR_SUBSPACE_SETTINGS,
) -> tuple[tuple[tuple[float, ...], tuple[tuple[float, float], ...]], ...]:
    rows = tuple(tuple(float(value) for value in row) for row in (population or ()))
    if not rows:
        return ()
    config = load_config(workspace)
    samples = predict_raw_data(config.workspace, rows, _settings=_settings)
    costs = _costs_from_samples(config.workspace, samples, rows)
    return tuple(
        (cost_row, tuple((value, value) for value in cost_row))
        for cost_row in costs
    )


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


__all__ = [
    "has_trained_state",
    "latest_state_generation",
    "predict_population",
    "predict_raw_data",
    "reset_workspace_state",
    "strategy_signature_for_workspace",
    "train",
    "training_data_from_session",
    "train_with_config",
    "workspace_state_key",
]
