"""Hierarchical CAE objectives."""
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
from .data_filtering import DataFilterAssessment
from .coordinates import coordinate_feature_count, encode_coordinate_points, stored_coordinate_points
from .types import CAETrainConfig, FieldLayout, HierarchicalSchema

def design_field_losses(predictions: Sequence[torch.Tensor], targets: Sequence[torch.Tensor], *, beta: float=1.0) -> torch.Tensor:
    if len(predictions) != len(targets) or not predictions:
        raise ValueError('field-macro loss requires aligned non-empty field lists')
    losses = [F.smooth_l1_loss(prediction, target, beta=float(beta), reduction='none').reshape(prediction.shape[0], -1).mean(dim=1) for prediction, target in zip(predictions, targets)]
    return torch.stack(losses, dim=1)

def field_macro_loss(predictions: Sequence[torch.Tensor], targets: Sequence[torch.Tensor], *, field_weights: torch.Tensor | None=None, loss_cap: float | None=None, beta: float=1.0) -> torch.Tensor:
    """Robust design-by-field aggregation; grids never receive point-count weight."""
    losses = design_field_losses(predictions, targets, beta=beta)
    if loss_cap is not None:
        losses = torch.clamp(losses, max=float(loss_cap))
    if field_weights is None:
        return losses.mean()
    weights = field_weights.to(dtype=losses.dtype, device=losses.device)
    if weights.shape != losses.shape:
        raise ValueError('field weights must align with design-by-field losses')
    denominator = torch.clamp(weights.sum(), min=torch.finfo(losses.dtype).eps)
    return torch.sum(losses * weights) / denominator

def design_level_split(parameters: np.ndarray, *, validation_fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Row-order-independent split; duplicate designs never cross partitions."""
    matrix = np.ascontiguousarray(parameters, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError('design-level split expects X[N,D]')
    identities = [hashlib.sha256(row.tobytes(order='C')).digest() for row in matrix]
    unique: dict[bytes, int] = {}
    for index, identity in enumerate(identities):
        unique.setdefault(identity, index)
    if len(unique) < 2:
        raise ValueError('hierarchical CAE training requires at least two unique designs')
    seed_bytes = int(seed).to_bytes(8, 'big', signed=True)
    ordered = sorted(unique.items(), key=lambda item: hashlib.sha256(seed_bytes + item[0]).digest())
    validation_count = max(1, min(len(ordered) - 1, int(round(len(ordered) * float(validation_fraction)))))
    validation_ids = {identity for identity, _index in ordered[:validation_count]}
    train = [index for index, identity in enumerate(identities) if identity not in validation_ids]
    validation = [index for index, identity in enumerate(identities) if identity in validation_ids]
    return (np.asarray(train, dtype=np.int64), np.asarray(validation, dtype=np.int64))

def unique_design_indices(parameters: np.ndarray) -> np.ndarray:
    matrix = np.ascontiguousarray(parameters, dtype=np.float64)
    seen: set[bytes] = set()
    output = []
    for index, row in enumerate(matrix):
        digest = hashlib.sha256(row.tobytes(order='C')).digest()
        if digest in seen:
            continue
        seen.add(digest)
        output.append(index)
    return np.asarray(output, dtype=np.int64)

def _batch_indices(indices: np.ndarray, batch_size: int, rng=None) -> Iterable[np.ndarray]:
    ordered = np.asarray(indices, dtype=np.int64).copy()
    if rng is not None:
        rng.shuffle(ordered)
    for start in range(0, len(ordered), max(1, int(batch_size))):
        yield ordered[start:start + max(1, int(batch_size))]

def _field_batch(fields: Sequence[np.ndarray], indices: np.ndarray, device: torch.device) -> tuple[torch.Tensor, ...]:
    return tuple((torch.as_tensor(values[indices], dtype=torch.float32, device=device) for values in fields))

def _filter_batch(data_filter: DataFilterAssessment, indices: np.ndarray, device: torch.device, cfg: CAETrainConfig) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    rows = np.asarray(indices, dtype=np.int64)
    field_weights = data_filter.field_weights[rows] if cfg.filter_weighted_loss else np.ones_like(data_filter.field_weights[rows])
    shared_weights = data_filter.shared_weights[rows] if cfg.shared_filter_isolation else np.ones_like(data_filter.shared_weights[rows])
    residual_targets = data_filter.residual_targets[rows] if cfg.gated_private_residual else np.zeros_like(data_filter.residual_targets[rows])
    return (torch.as_tensor(field_weights, dtype=torch.float32, device=device), torch.as_tensor(shared_weights, dtype=torch.float32, device=device), torch.as_tensor(residual_targets, dtype=torch.float32, device=device), torch.as_tensor(data_filter.applicability_targets[rows], dtype=torch.float32, device=device))
