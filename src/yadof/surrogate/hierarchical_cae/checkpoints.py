from __future__ import annotations
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping
import numpy as np
import torch
from ..quality import RawDataQualityPolicy
from .inference import save_model_bundle
from .networks import MODEL_NAME
from .types import CAETrainConfig, HierarchicalSchema, HierarchicalState
from .._shared.artifacts import atomic_write_json as _shared_atomic_write_json, new_publication_paths as _shared_new_publication_paths, run_namespace_for_signature as _shared_run_namespace_for_signature
SURROGATE_METHOD = 'hierarchical_cae'
TRAINING_POLICY = 'design_split_field_macro_hierarchical_latent'
COMPONENT_NAMESPACE = 'hierarchical-cae'

def _array_signature(values: np.ndarray) -> dict[str, object]:
    array = np.ascontiguousarray(values)
    return {'dtype': str(array.dtype), 'shape': list(array.shape), 'sha256': hashlib.sha256(array.tobytes(order='C')).hexdigest()}

def schema_payload(schema: HierarchicalSchema | None) -> dict[str, object]:
    if schema is None:
        return {'template_signature': '', 'rawdata_item_count': 0, 'flat_dim': 0, 'modeled_slots': [], 'layouts': [], 'groups': []}
    slots = []
    offset = 0
    for item_index, layout in enumerate(schema.layouts):
        start = offset
        offset += layout.point_count
        slots.append({'item_index': item_index, 'key': layout.selector[1], 'shape': list(layout.shape), 'dtype': layout.dtype, 'start': start, 'end': offset, 'field_id': item_index, 'selector': list(layout.selector)})
    return {'contract': 'yadof.hierarchical-cae-schema', 'contract_version': 1, 'template_signature': schema.template.signature, 'rawdata_item_count': len(schema.layouts), 'flat_dim': offset, 'modeled_slots': slots, 'layouts': [layout.as_dict() for layout in schema.layouts], 'groups': [[list(selector) for selector in group] for group in schema.groups]}

def semantic_state_signature(*, strategy_signature: str, parameter_names: tuple[str, ...], parameter_definition_signature: Mapping[str, object], schema: HierarchicalSchema | None, train_cfg: CAETrainConfig, quality_policy: RawDataQualityPolicy | None, torch_version: str | None=None) -> str:
    schema_identity = schema_payload(schema)
    payload = {'strategy_signature': str(strategy_signature), 'surrogate_method': SURROGATE_METHOD, 'training_policy': TRAINING_POLICY, 'parameter_names': list(parameter_names), 'parameter_definition_signature': dict(parameter_definition_signature), 'schema': schema_identity, 'axis_signatures': [] if schema is None else [[_array_signature(values) for values in layout.axis_values] for layout in schema.layouts], 'train_cfg': asdict(train_cfg), 'quality_policy': None if quality_policy is None else quality_policy.as_dict(), 'torch_version': str(torch.__version__) if torch_version is None else str(torch_version)}
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

def run_namespace_for_signature(strategy_signature: str) -> str:
    return _shared_run_namespace_for_signature(strategy_signature)

def new_publication_paths(checkpoint_dir: Path, *, generation_index: int, strategy_signature: str) -> tuple[Path, Path, Path, Path, str, str]:
    return _shared_new_publication_paths(checkpoint_dir, generation_index=generation_index, strategy_signature=strategy_signature, component_namespace=COMPONENT_NAMESPACE)

def validate_manifest_identity(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError('surrogate checkpoint manifest must be a JSON object')
    if str(payload['surrogate_method']) != SURROGATE_METHOD:
        raise ValueError('unsupported hierarchical CAE checkpoint method')
    if str(payload['training_policy']) != TRAINING_POLICY:
        raise ValueError('unsupported hierarchical CAE training policy')
    signature = str(payload['state_signature'])
    if len(signature) != 64 or any((char not in '0123456789abcdef' for char in signature)):
        raise ValueError('surrogate state signature must be 64 lowercase hexadecimal characters')
    strategy_signature = str(payload['strategy_signature'])
    if str(payload['run_namespace']) != run_namespace_for_signature(strategy_signature):
        raise ValueError('checkpoint run namespace does not match its signature')
    if str(payload['component_namespace']) != COMPONENT_NAMESPACE:
        raise ValueError('unsupported checkpoint component namespace')
    if not isinstance(payload['parameter_definition_signature'], Mapping):
        raise ValueError('checkpoint parameter definition signature must be an object')
    if not isinstance(payload['schema'], Mapping):
        raise ValueError('checkpoint schema must be an object')
    if not isinstance(payload['train_cfg'], Mapping):
        raise ValueError('checkpoint train_cfg must be an object')
    if payload.get('quality_policy') is not None and (not isinstance(payload.get('quality_policy'), Mapping)):
        raise ValueError('checkpoint quality policy must be null or an object')
    publication_id = str(payload['publication_id'])
    if not publication_id or any((char not in '0123456789_abcdef' for char in publication_id)):
        raise ValueError('invalid surrogate checkpoint publication id')
    return payload

def resolve_artifact_dir(checkpoint_dir: Path, payload: object) -> Path:
    manifest = validate_manifest_identity(payload)
    root = Path(checkpoint_dir).resolve()
    relative = Path(str(manifest['artifact_dir']))
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('checkpoint artifact path must remain below its root')
    resolved = (root / relative).resolve()
    expected_parent = (root / 'runs' / str(manifest['run_namespace']) / 'components' / COMPONENT_NAMESPACE).resolve()
    expected_name = f"generation_{int(manifest['generation_index']):04d}_{manifest['publication_id']}"
    if resolved.parent != expected_parent or resolved.name != expected_name:
        raise ValueError('checkpoint artifact is outside its declared namespace')
    return resolved

def resolve_namespace_manifest_path(checkpoint_dir: Path, payload: object) -> Path:
    manifest = validate_manifest_identity(payload)
    root = Path(checkpoint_dir).resolve()
    relative = Path(str(manifest['namespace_manifest']))
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('namespace manifest path must remain below its root')
    resolved = (root / relative).resolve()
    expected_parent = (root / 'runs' / str(manifest['run_namespace']) / 'components' / COMPONENT_NAMESPACE).resolve()
    expected_name = f"generation_{int(manifest['generation_index']):04d}_{manifest['publication_id']}.json"
    if resolved.parent != expected_parent or resolved.name != expected_name:
        raise ValueError('namespace manifest is outside its declared namespace')
    return resolved

def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    _shared_atomic_write_json(path, payload)

def _checkpoint_payload(state: HierarchicalState, checkpoint_root: Path) -> dict[str, object]:
    prefix = f'generation_{int(state.generation_index):04d}_'
    manifest_stem = state.namespace_manifest_path.stem
    if not manifest_stem.startswith(prefix):
        raise ValueError('namespace manifest does not encode its generation')
    publication_id = manifest_stem[len(prefix):]
    member_count = int(state.train_history.get('member_count', 0))
    return {'surrogate_method': SURROGATE_METHOD, 'training_policy': TRAINING_POLICY, 'strategy_signature': state.strategy_signature, 'state_signature': state.state_signature, 'run_namespace': state.run_namespace, 'component_namespace': state.component_namespace, 'publication_id': publication_id, 'torch_version': str(torch.__version__), 'generation_index': int(state.generation_index), 'sample_count': int(state.sample_count), 'parameter_names': list(state.parameter_names), 'parameter_definition_signature': dict(state.parameter_definition_signature), 'model': MODEL_NAME, 'member_count': member_count, 'model_path': state.bundle_path.name, 'scaler_path': 'field_scalers.npz', 'artifact_dir': state.artifact_dir.relative_to(checkpoint_root).as_posix(), 'namespace_manifest': state.namespace_manifest_path.relative_to(checkpoint_root).as_posix(), 'schema': schema_payload(state.schema), 'train_cfg': asdict(state.train_cfg), 'quality_policy': None if state.quality_policy is None else state.quality_policy.as_dict(), 'train_history': state.train_history, 'coordinate_readout': bool(state.train_cfg.coordinate_readout), 'coordinate_capability': {'contract': 'yadof.hierarchical-cae-coordinate-readout-v1', 'enabled': bool(state.train_cfg.coordinate_readout), 'authority': 'viewer/off-grid-only', 'full_grid_decoder_remains_authoritative': True, 'acceptance_status': 'experimental-performance-not-accepted' if state.train_cfg.coordinate_readout else 'not-configured'}, 'note': 'Full-grid rawData is decoded by field-specific convolutional codecs from global/optional-group/private parameter-predicted latents. Predictor-member spread is finite and uncalibrated.'}

def write_checkpoint(state: HierarchicalState, *, staged_artifact_dir: Path) -> None:
    checkpoint_root = state.checkpoint_path.parent.resolve()
    staging = Path(staged_artifact_dir).resolve()
    artifact_dir = state.artifact_dir.resolve()
    if staging.parent != artifact_dir.parent:
        raise ValueError('checkpoint staging and artifact directories must share a parent')
    if artifact_dir.exists():
        raise FileExistsError(artifact_dir)
    if state.model is None or state.schema is None or (not state.schema.scalers):
        raise ValueError('a published hierarchical CAE checkpoint must be trainable')
    staging.mkdir(parents=True, exist_ok=True)
    save_model_bundle(staging / state.bundle_path.name, model=state.model, train_cfg=state.train_cfg)
    scaler_payload = {}
    for field_index, scaler in enumerate(state.schema.scalers):
        scaler_payload[f'field_{field_index:04d}_mean'] = scaler.mean
        scaler_payload[f'field_{field_index:04d}_scale'] = scaler.scale
    np.savez_compressed(staging / 'field_scalers.npz', **scaler_payload)
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, artifact_dir)
    payload = _checkpoint_payload(state, checkpoint_root)
    validate_manifest_identity(payload)
    _atomic_write_json(state.checkpoint_path, payload)
    _atomic_write_json(state.namespace_manifest_path, payload)
__all__ = ['COMPONENT_NAMESPACE', 'SURROGATE_METHOD', 'TRAINING_POLICY', 'new_publication_paths', 'resolve_artifact_dir', 'resolve_namespace_manifest_path', 'run_namespace_for_signature', 'schema_payload', 'semantic_state_signature', 'validate_manifest_identity', 'write_checkpoint']
