"""Hierarchical CAE state repository service."""
from __future__ import annotations
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import threading
from typing import Mapping, Sequence
import numpy as np
import psutil
import torch
from ...config import LoadedConfig, load_config
from ...job_template import api as job_template_api
from ...job_template.rawdata_contract import NamedRawDataItem
from ...job_template.rawdata_template import StructuredRawDataSample
from ...optimize.state import active_strategy_signature
from ...recorded_data import api as recorded_api
from ...recorded_data.session import CampaignSession
from ...task_snapshot import GenerationTaskSnapshot
from ...workspace import WorkspaceContext
from ..quality import ApplicabilityPrediction, assess_quality
from .._shared.training_events import monotonic_time, now_text, record_training_event
from .checkpoints import COMPONENT_NAMESPACE, new_publication_paths, resolve_artifact_dir, resolve_namespace_manifest_path, run_namespace_for_signature, schema_payload, semantic_state_signature, validate_manifest_identity, write_checkpoint
from .coordinates import coordinate_grid, interpolate_stored_values
from .inference import load_model_bundle, predict_hierarchical_coordinate_members, predict_hierarchical_members
from .networks import MODEL_NAME
from .objectives import unique_design_indices
from .training import fit_hierarchical_cae
from .schema import build_schema, field_matrices, fit_scalers, named_sample_from_payloads, reconstruct_samples, standardized_field_matrices
from .types import CoordinatePrediction, FieldScaler, HierarchicalSchema, HierarchicalState, NamedTrainingData, Population
StateKey = tuple[str, str, str, str, str, str]
_STATE_LOCK = threading.RLock()
_STATES: dict[StateKey, HierarchicalState] = {}
_STANDALONE_PREFIX = b'yadof:standalone-hierarchical-cae-state:v1:'
__all__ = ['StateKey', 'has_trained_state', 'latest_state_generation', 'predict_applicability', 'predict_field_at_coordinates', 'predict_population', 'predict_raw_data', 'reset_workspace_state', 'strategy_signature_for_workspace', 'train', 'training_data_from_session', 'train_with_config', 'workspace_state_key']

def _training_success_metadata(state: HierarchicalState, *, started_at: str, ended_at: str, duration_sec: float) -> dict[str, object]:
    history = dict(state.train_history or {})
    return {'record_type': 'surrogate_training', 'status': 'completed', 'generation_index': int(state.generation_index), 'started_at': str(started_at), 'ended_at': str(ended_at), 'duration_sec': float(duration_sec), 'model': MODEL_NAME, 'sample_count': int(state.sample_count), 'train_sample_count': int(history.get('train_design_count', 0)), 'validation_sample_count': int(history.get('validation_design_count', 0)), 'member_count': int(history.get('member_count', 0)), 'device': str(history.get('device', '')), 'skipped': bool(history.get('skipped', False)), 'skip_reason': str(history.get('skip_reason', '')), 'training_policy': str(history.get('training_policy', '')), 'strategy_signature': state.strategy_signature, 'state_signature': state.state_signature, 'run_namespace': state.run_namespace, 'component_namespace': state.component_namespace, 'checkpoint_path': str(state.checkpoint_path), 'namespace_manifest_path': str(state.namespace_manifest_path), 'artifact_dir': str(state.artifact_dir)}

def _component_payload(component) -> dict[str, object]:
    payload = component.configuration_payload()
    return json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False))

def strategy_signature_for_workspace(workspace: WorkspaceContext, *, component) -> str:
    active = active_strategy_signature(workspace)
    if active:
        return active
    encoded = json.dumps(_component_payload(component), sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(_STANDALONE_PREFIX + encoded).hexdigest()

def workspace_state_key(config: LoadedConfig, *, component) -> StateKey:
    workspace = config.workspace
    return (str(workspace.root), str(workspace.config_file), str(workspace.recorded_data_dir), str(workspace.surrogate_checkpoint_dir), strategy_signature_for_workspace(workspace, component=component), COMPONENT_NAMESPACE)

def _select_device(requested: str) -> torch.device:
    requested = str(requested).strip().lower()
    if requested != 'auto':
        device = torch.device(requested)
        if device.type == 'cuda' and (not torch.cuda.is_available()):
            raise RuntimeError(f'hierarchical_cae(): device={requested!r} requests unavailable CUDA')
        return device
    if torch.cuda.is_available():
        return torch.device('cuda')
    if hasattr(torch, 'xpu') and torch.xpu.is_available():
        return torch.device('xpu')
    return torch.device('cpu')

def train(workspace: WorkspaceContext | str | Path, *, generation_index: int=0, component) -> HierarchicalState:
    return train_with_config(load_config(workspace), generation_index=int(generation_index), component=component)

def train_with_config(config: LoadedConfig, *, generation_index: int, component, started_at: str | None=None, training_data: NamedTrainingData | None=None, random_seed: int | None=None) -> HierarchicalState:
    from .data_adapter import _build_current_schema, _load_training_data, _unique_training_data, _x_matrix
    training_started_at = now_text() if started_at is None else str(started_at)
    started_monotonic = monotonic_time()
    raw_data = _load_training_data(config.workspace) if training_data is None else training_data
    if len(raw_data.normalized_variables) != len(raw_data.raw_data):
        raise ValueError('hierarchical CAE parameter/rawData rows do not align')
    data, duplicate_count = _unique_training_data(raw_data)
    x = _x_matrix(data.normalized_variables)
    strategy_signature = strategy_signature_for_workspace(config.workspace, component=component)
    checkpoint_path, namespace_manifest_path, artifact_dir, staging_dir, run_namespace, component_namespace = new_publication_paths(config.workspace.surrogate_checkpoint_dir, generation_index=int(generation_index), strategy_signature=strategy_signature)
    parameter_definition_signature = job_template_api.get_parameter_definition_signature(config.workspace)
    if len(data.raw_data) < int(component.train_cfg.minimum_samples):
        state = HierarchicalState(generation_index=int(generation_index), sample_count=len(data.raw_data), checkpoint_path=checkpoint_path, namespace_manifest_path=namespace_manifest_path, artifact_dir=artifact_dir, bundle_path=artifact_dir / 'model.pt', strategy_signature=strategy_signature, state_signature='0' * 64, run_namespace=run_namespace, component_namespace=component_namespace, parameter_names=data.parameter_names, parameter_definition_signature=parameter_definition_signature, schema=None, quality_policy=component.quality_policy, model=None, train_cfg=component.train_cfg, device=None, train_history={'model': MODEL_NAME, 'member_count': 0, 'skipped': True, 'skip_reason': 'fewer than configured minimum unique compatible designs', 'unique_design_count': len(data.raw_data), 'dropped_duplicate_designs': duplicate_count})
        return state
    schema = _build_current_schema(data, component)
    matrices = field_matrices(schema, data.raw_data)
    scalers = fit_scalers(matrices, scale_floor=component.train_cfg.scale_floor)
    schema = replace(schema, scalers=scalers)
    standardized = standardized_field_matrices(schema, matrices)
    quality = assess_quality(policy=component.quality_policy, samples=data.raw_data, record_metadata=data.record_metadata)
    state_signature = semantic_state_signature(strategy_signature=strategy_signature, parameter_names=data.parameter_names, parameter_definition_signature=parameter_definition_signature, schema=schema, train_cfg=component.train_cfg, quality_policy=component.quality_policy)
    device = _select_device(component.device)
    seed = int(config.OPTIMIZE_RANDOM_SEED if random_seed is None else random_seed) + int(generation_index) * 1009
    host_rss_before = int(psutil.Process().memory_info().rss)
    model, history = fit_hierarchical_cae(input_dim=x.shape[1], schema=schema, parameters=x, standardized_fields=standardized, quality=quality, device=device, train_cfg=component.train_cfg, seed=seed)
    history.update({'skipped': False, 'sample_count_before_deduplication': len(raw_data.normalized_variables), 'unique_design_count': len(data.raw_data), 'dropped_duplicate_designs': duplicate_count, 'quality_policy': None if component.quality_policy is None else component.quality_policy.as_dict(), 'host_rss_before_bytes': host_rss_before, 'host_rss_after_bytes': int(psutil.Process().memory_info().rss)})
    state = HierarchicalState(generation_index=int(generation_index), sample_count=len(data.raw_data), checkpoint_path=checkpoint_path, namespace_manifest_path=namespace_manifest_path, artifact_dir=artifact_dir, bundle_path=artifact_dir / 'model.pt', strategy_signature=strategy_signature, state_signature=state_signature, run_namespace=run_namespace, component_namespace=component_namespace, parameter_names=data.parameter_names, parameter_definition_signature=parameter_definition_signature, schema=schema, quality_policy=component.quality_policy, model=model, train_cfg=component.train_cfg, device=device, train_history=history)
    write_checkpoint(state, staged_artifact_dir=staging_dir)
    record_training_event(config.workspace, _training_success_metadata(state, started_at=training_started_at, ended_at=now_text(), duration_sec=monotonic_time() - started_monotonic))
    with _STATE_LOCK:
        _STATES[workspace_state_key(config, component=component)] = state
    return state

def _is_usable_state(state: HierarchicalState | None) -> bool:
    return bool(state is not None and state.model is not None and (state.schema is not None) and state.schema.scalers and (state.device is not None) and (not state.train_history.get('skipped', False)))

def has_trained_state(workspace: WorkspaceContext | str | Path, *, component) -> bool:
    config = load_config(workspace)
    return _is_usable_state(_state_for_config(config, component=component, recover=True))

def latest_state_generation(workspace: WorkspaceContext | str | Path, *, component) -> int | None:
    config = load_config(workspace)
    state = _state_for_config(config, component=component, recover=True)
    return int(state.generation_index) if _is_usable_state(state) else None

def reset_workspace_state(workspace: WorkspaceContext | str | Path, *, component=None) -> None:
    config = load_config(workspace)
    with _STATE_LOCK:
        if component is not None:
            _STATES.pop(workspace_state_key(config, component=component), None)
            return
        prefix = str(config.workspace.root)
        for key in tuple(_STATES):
            if key[0] == prefix:
                _STATES.pop(key, None)

def _state_for_config(config: LoadedConfig, *, component, recover: bool) -> HierarchicalState | None:
    key = workspace_state_key(config, component=component)
    with _STATE_LOCK:
        state = _STATES.get(key)
    if state is not None:
        expected_parameter_signature = job_template_api.get_parameter_definition_signature(config.workspace)
        expected = semantic_state_signature(strategy_signature=strategy_signature_for_workspace(config.workspace, component=component), parameter_names=state.parameter_names, parameter_definition_signature=expected_parameter_signature, schema=state.schema, train_cfg=component.train_cfg, quality_policy=component.quality_policy)
        if expected != state.state_signature:
            with _STATE_LOCK:
                _STATES.pop(key, None)
            state = None
    if state is not None or not recover:
        return state
    recovered = _recover_latest_state(config, component=component)
    if recovered is None:
        return None
    with _STATE_LOCK:
        return _STATES.setdefault(key, recovered)

def _recover_latest_state(config: LoadedConfig, *, component) -> HierarchicalState | None:
    from .data_adapter import _build_current_schema, _load_training_data
    checkpoint_root = config.workspace.surrogate_checkpoint_dir
    if not checkpoint_root.is_dir():
        return None
    data = _load_training_data(config.workspace)
    if not data.raw_data:
        return None
    schema = _build_current_schema(data, component)
    parameter_signature = job_template_api.get_parameter_definition_signature(config.workspace)
    strategy_signature = strategy_signature_for_workspace(config.workspace, component=component)
    expected_signature = semantic_state_signature(strategy_signature=strategy_signature, parameter_names=data.parameter_names, parameter_definition_signature=parameter_signature, schema=schema, train_cfg=component.train_cfg, quality_policy=component.quality_policy)
    namespace_dir = checkpoint_root / 'runs' / run_namespace_for_signature(strategy_signature) / 'components' / COMPONENT_NAMESPACE
    for path in sorted(namespace_dir.glob('generation_*.json'), reverse=True):
        try:
            return _recover_state_from_checkpoint(config, path, component=component, data=data, schema=schema, parameter_signature=parameter_signature, expected_signature=expected_signature)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return None

def _recover_state_from_checkpoint(config: LoadedConfig, checkpoint_path: Path, *, component, data: NamedTrainingData, schema: HierarchicalSchema, parameter_signature: Mapping[str, object], expected_signature: str) -> HierarchicalState:
    payload = validate_manifest_identity(json.loads(checkpoint_path.read_text(encoding='utf-8')))
    if str(payload['state_signature']) != expected_signature:
        raise ValueError('hierarchical CAE checkpoint is not current')
    strategy_signature = strategy_signature_for_workspace(config.workspace, component=component)
    if str(payload['strategy_signature']) != strategy_signature:
        raise ValueError('checkpoint belongs to a different strategy namespace')
    if tuple((str(value) for value in payload['parameter_names'])) != data.parameter_names:
        raise ValueError('checkpoint parameter names do not match the task')
    if dict(payload['schema']) != schema_payload(schema):
        raise ValueError('checkpoint rawData schema/layout/group identity changed')
    if dict(payload['train_cfg']) != asdict(component.train_cfg):
        raise ValueError('checkpoint training configuration changed')
    expected_policy = None if component.quality_policy is None else component.quality_policy.as_dict()
    if payload.get('quality_policy') != expected_policy:
        raise ValueError('checkpoint quality policy changed')
    manifest_signature = semantic_state_signature(strategy_signature=strategy_signature, parameter_names=data.parameter_names, parameter_definition_signature=dict(payload['parameter_definition_signature']), schema=schema, train_cfg=component.train_cfg, quality_policy=component.quality_policy, torch_version=str(payload['torch_version']))
    if manifest_signature != str(payload['state_signature']):
        raise ValueError('checkpoint semantic signature is inconsistent')
    checkpoint_root = config.workspace.surrogate_checkpoint_dir
    namespace_manifest = resolve_namespace_manifest_path(checkpoint_root, payload)
    if namespace_manifest.resolve() != checkpoint_path.resolve():
        raise ValueError('recovery candidate is not its namespace manifest')
    artifact_dir = resolve_artifact_dir(checkpoint_root, payload)
    scaler_path = artifact_dir / Path(str(payload['scaler_path'])).name
    if not scaler_path.is_file():
        raise FileNotFoundError(scaler_path)
    scalers = []
    with np.load(scaler_path, allow_pickle=False) as stored:
        for field_index, layout in enumerate(schema.layouts):
            mean = np.asarray(stored[f'field_{field_index:04d}_mean'], dtype=np.float64)
            scale = np.asarray(stored[f'field_{field_index:04d}_scale'], dtype=np.float64)
            if mean.size != layout.point_count or scale.size != layout.point_count:
                raise ValueError('checkpoint field scaler does not match schema')
            if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(scale)) or np.any(scale <= 0):
                raise ValueError('checkpoint field scaler is invalid')
            scalers.append(FieldScaler(np.ascontiguousarray(mean), np.ascontiguousarray(scale)))
    schema = replace(schema, scalers=tuple(scalers))
    device = _select_device(component.device)
    bundle_path = artifact_dir / Path(str(payload['model_path'])).name
    model, loaded_cfg = load_model_bundle(bundle_path, schema=schema, device=device)
    if loaded_cfg != component.train_cfg:
        raise ValueError('model bundle training configuration changed')
    generation = int(payload['generation_index'])
    active_path = checkpoint_root / f'generation_{generation:04d}.json'
    source_path = namespace_manifest
    try:
        active = validate_manifest_identity(json.loads(active_path.read_text(encoding='utf-8')))
        if active == payload:
            source_path = active_path
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        pass
    return HierarchicalState(generation_index=generation, sample_count=int(payload['sample_count']), checkpoint_path=source_path, namespace_manifest_path=namespace_manifest, artifact_dir=artifact_dir, bundle_path=bundle_path, strategy_signature=strategy_signature, state_signature=expected_signature, run_namespace=str(payload['run_namespace']), component_namespace=str(payload['component_namespace']), parameter_names=data.parameter_names, parameter_definition_signature=parameter_signature, schema=schema, quality_policy=component.quality_policy, model=model, train_cfg=component.train_cfg, device=device, train_history=dict(payload.get('train_history', {})))

def _require_state(config: LoadedConfig, *, component) -> HierarchicalState:
    state = _state_for_config(config, component=component, recover=True)
    if not _is_usable_state(state):
        raise RuntimeError('hierarchical CAE model is not trained')
    assert state is not None
    return state
