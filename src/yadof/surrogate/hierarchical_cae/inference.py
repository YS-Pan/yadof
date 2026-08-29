"""Hierarchical CAE inference."""
from __future__ import annotations
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import time
from typing import Iterable, Sequence
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from .coordinates import coordinate_feature_count, encode_coordinate_points, stored_coordinate_points
from .types import CAETrainConfig, FieldLayout, HierarchicalSchema

@torch.no_grad()
def predict_hierarchical_members(*, model: HierarchicalCAEModel, parameters: np.ndarray, device: torch.device, batch_size: int) -> tuple[tuple[np.ndarray, ...], np.ndarray, np.ndarray]:
    from .networks import HierarchicalCAEModel
    x = np.ascontiguousarray(parameters, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != model.input_dim:
        raise ValueError(f'expected normalized parameter matrix [N,{model.input_dim}]')
    per_field: list[list[np.ndarray]] = [list() for _ in model.schema.layouts]
    applicability_chunks: list[np.ndarray] = []
    residual_chunks: list[np.ndarray] = []
    model.eval()
    for start in range(0, len(x), max(1, int(batch_size))):
        batch = torch.as_tensor(x[start:start + max(1, int(batch_size))], dtype=torch.float32, device=device)
        member_outputs = [model.predict_member(member_index, batch) for member_index in range(len(model.predictors))]
        for field_index in range(len(per_field)):
            stacked = torch.stack([values[0][field_index] for values in member_outputs], dim=0)
            per_field[field_index].append(stacked.float().cpu().numpy())
        applicability_chunks.append(torch.stack([torch.sigmoid(values[1]) for values in member_outputs], dim=0).float().cpu().numpy())
        residual_chunks.append(torch.stack([torch.sigmoid(values[2]) for values in member_outputs], dim=0).float().cpu().numpy())
    return (tuple((np.ascontiguousarray(np.concatenate(chunks, axis=1), dtype=np.float32) for chunks in per_field)), np.ascontiguousarray(np.concatenate(applicability_chunks, axis=1), dtype=np.float32), np.ascontiguousarray(np.concatenate(residual_chunks, axis=1), dtype=np.float32))

@torch.no_grad()
def predict_hierarchical_coordinate_members(*, model: HierarchicalCAEModel, parameters: np.ndarray, field_index: int, coordinate_points: np.ndarray, device: torch.device, batch_size: int, query_batch_size: int) -> np.ndarray:
    """Evaluate one field readout while preserving predictor-member identity."""
    from .networks import HierarchicalCAEModel
    if not model.cfg.coordinate_readout:
        raise RuntimeError('coordinate queries require a coordinate-enabled hierarchical CAE checkpoint')
    index = int(field_index)
    if not 0 <= index < len(model.schema.layouts):
        raise IndexError(index)
    x = np.ascontiguousarray(parameters, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != model.input_dim:
        raise ValueError(f'expected normalized parameter matrix [N,{model.input_dim}]')
    encoded = encode_coordinate_points(model.schema.layouts[index], coordinate_points)
    member_count = len(model.predictors)
    result = np.empty((member_count, x.shape[0], encoded.shape[0]), dtype=np.float32)
    model.eval()
    sample_size = max(1, int(batch_size))
    query_size = max(1, int(query_batch_size))
    for sample_start in range(0, len(x), sample_size):
        sample_end = min(sample_start + sample_size, len(x))
        batch = torch.as_tensor(x[sample_start:sample_end], dtype=torch.float32, device=device)
        for member_index in range(member_count):
            latent, _applicability, residual_logits = model.predictor_output(member_index, batch)
            residual_gates = torch.sigmoid(residual_logits) if model.cfg.regime_head and model.cfg.gated_private_residual else torch.zeros_like(residual_logits)
            for query_start in range(0, encoded.shape[0], query_size):
                query_end = min(query_start + query_size, encoded.shape[0])
                coordinate_tensor = torch.as_tensor(encoded[query_start:query_end], dtype=torch.float32, device=device)
                values = model.decode_coordinates(latent, residual_gates, field_index=index, encoded_coordinates=coordinate_tensor)
                result[member_index, sample_start:sample_end, query_start:query_end] = values.float().cpu().numpy()
    return np.ascontiguousarray(result)

def save_model_bundle(path: Path, *, model: HierarchicalCAEModel, train_cfg: CAETrainConfig) -> None:
    from .networks import HierarchicalCAEModel, MODEL_NAME
    payload = {'model_name': MODEL_NAME, 'input_dim': model.input_dim, 'train_cfg': asdict(train_cfg), 'state_dict': model.state_dict()}
    torch.save(payload, Path(path))

def load_model_bundle(path: Path, *, schema: HierarchicalSchema, device: torch.device) -> tuple[HierarchicalCAEModel, CAETrainConfig]:
    from .networks import HierarchicalCAEModel, MODEL_NAME
    payload = torch.load(Path(path), map_location=device, weights_only=True)
    if not isinstance(payload, dict) or payload.get('model_name') != MODEL_NAME:
        raise ValueError('unsupported hierarchical CAE model bundle')
    cfg = CAETrainConfig(**dict(payload['train_cfg']))
    model = HierarchicalCAEModel(int(payload['input_dim']), schema, cfg).to(device)
    model.load_state_dict(payload['state_dict'], strict=True)
    model.eval()
    return (model, cfg)
