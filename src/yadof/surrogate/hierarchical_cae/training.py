"""Hierarchical CAE training."""
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

def _autocast(device: torch.device, enabled: bool):
    if not enabled or device.type != 'cuda':
        return nullcontext()
    return torch.autocast(device_type='cuda', dtype=torch.float16)

def _make_grad_scaler(device: torch.device, enabled: bool):
    return torch.amp.GradScaler(device.type, enabled=bool(enabled and device.type == 'cuda'))

def _state_copy(module: nn.Module) -> dict[str, torch.Tensor]:
    return {name: value.detach().cpu().clone() for name, value in module.state_dict().items()}

def _mean_loss(values: list[float]) -> float:
    return float(np.mean(values, dtype=np.float64)) if values else math.inf

@torch.no_grad()
def _codec_validation_loss(model: HierarchicalCAEModel, fields: Sequence[np.ndarray], data_filter: DataFilterAssessment, indices: np.ndarray, device: torch.device, cfg: CAETrainConfig) -> float:
    from .networks import HierarchicalCAEModel
    from .objectives import _batch_indices, _field_batch, _filter_batch, field_macro_loss
    model.eval()
    losses = []
    for batch in _batch_indices(indices, cfg.batch_size):
        targets = _field_batch(fields, batch, device)
        field_weights, shared_weights, residual_targets, _applicability = _filter_batch(data_filter, batch, device, cfg)
        with _autocast(device, cfg.mixed_precision):
            loss = field_macro_loss(model.autoencode(targets, shared_weights=shared_weights, residual_targets=residual_targets), targets, field_weights=field_weights, loss_cap=cfg.robust_loss_cap)
        losses.append(float(loss.detach().cpu()))
    return _mean_loss(losses)

def _train_codecs(model: HierarchicalCAEModel, fields: Sequence[np.ndarray], data_filter: DataFilterAssessment, train_indices: np.ndarray, validation_indices: np.ndarray, device: torch.device, cfg: CAETrainConfig, seed: int) -> dict[str, object]:
    from .networks import HierarchicalCAEModel
    from .objectives import _batch_indices, _field_batch, _filter_batch, field_macro_loss
    parameters = [parameter for name, parameter in model.named_parameters() if not name.startswith('predictors.')]
    optimizer = torch.optim.AdamW(parameters, lr=cfg.learning_rate, weight_decay=cfg.weight_decay)
    scaler = _make_grad_scaler(device, cfg.mixed_precision)
    rng = np.random.default_rng(int(seed))
    best_loss = math.inf
    best_state = _state_copy(model)
    patience = 0
    history = []
    started = time.perf_counter()
    for epoch in range(cfg.codec_epochs):
        model.train()
        losses = []
        for batch in _batch_indices(train_indices, cfg.batch_size, rng):
            targets = _field_batch(fields, batch, device)
            field_weights, shared_weights, residual_targets, _applicability = _filter_batch(data_filter, batch, device, cfg)
            optimizer.zero_grad(set_to_none=True)
            with _autocast(device, cfg.mixed_precision):
                loss = field_macro_loss(model.autoencode(targets, shared_weights=shared_weights, residual_targets=residual_targets), targets, field_weights=field_weights, loss_cap=cfg.robust_loss_cap)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(parameters, cfg.gradient_clip_norm)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))
        validation = _codec_validation_loss(model, fields, data_filter, validation_indices, device, cfg)
        history.append({'epoch': epoch + 1, 'training_field_macro_loss': _mean_loss(losses), 'validation_field_macro_loss': validation})
        if not math.isfinite(best_loss) or validation < best_loss - max(1e-07, abs(best_loss) * 1e-05):
            best_loss = validation
            best_state = _state_copy(model)
            patience = 0
        else:
            patience += 1
            if patience >= cfg.early_stopping_patience:
                break
    model.load_state_dict(best_state)
    return {'epochs_completed': len(history), 'best_validation_field_macro_loss': best_loss, 'wall_sec': time.perf_counter() - started, 'history': history}

@torch.no_grad()
def _teacher_latents(model: HierarchicalCAEModel, fields: Sequence[np.ndarray], data_filter: DataFilterAssessment, device: torch.device, cfg: CAETrainConfig) -> np.ndarray:
    from .networks import HierarchicalCAEModel
    from .objectives import _batch_indices, _field_batch, _filter_batch
    model.eval()
    rows = []
    indices = np.arange(fields[0].shape[0], dtype=np.int64)
    for batch in _batch_indices(indices, cfg.batch_size):
        tensors = _field_batch(fields, batch, device)
        _field_weights, shared_weights, _residual, _applicability = _filter_batch(data_filter, batch, device, cfg)
        latent = model.teacher_latent(tensors, shared_weights)
        rows.append(latent.detach().float().cpu().numpy())
    return np.ascontiguousarray(np.concatenate(rows, axis=0), dtype=np.float32)

@torch.no_grad()
def _predictor_validation_loss(model: HierarchicalCAEModel, predictor: ParameterLatentPredictor, parameters: np.ndarray, latents: np.ndarray, data_filter: DataFilterAssessment, indices: np.ndarray, device: torch.device, cfg: CAETrainConfig) -> float:
    from .networks import HierarchicalCAEModel, ParameterLatentPredictor
    from .objectives import _batch_indices, _filter_batch
    predictor.eval()
    losses = []
    for batch in _batch_indices(indices, cfg.batch_size):
        x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
        target = torch.as_tensor(latents[batch], dtype=torch.float32, device=device)
        _field_weights, _shared_weights, residual_targets, applicability = _filter_batch(data_filter, batch, device, cfg)
        with _autocast(device, cfg.mixed_precision):
            predicted_latent, applicability_logit, residual_logits = model.split_predictor_output(predictor(x))
            loss = F.smooth_l1_loss(predicted_latent, target, beta=1.0)
            if cfg.regime_head:
                loss = loss + cfg.applicability_loss_weight * F.binary_cross_entropy_with_logits(applicability_logit, applicability)
                if cfg.gated_private_residual:
                    loss = loss + cfg.residual_gate_loss_weight * F.binary_cross_entropy_with_logits(residual_logits, residual_targets)
        losses.append(float(loss.detach().cpu()))
    return _mean_loss(losses)

def _train_predictors(model: HierarchicalCAEModel, parameters: np.ndarray, latents: np.ndarray, data_filter: DataFilterAssessment, train_indices: np.ndarray, validation_indices: np.ndarray, device: torch.device, cfg: CAETrainConfig, seed: int) -> dict[str, object]:
    from .networks import HierarchicalCAEModel
    from .objectives import _batch_indices, _filter_batch
    member_histories = []
    started = time.perf_counter()
    for member_index, predictor in enumerate(model.predictors):
        rng = np.random.default_rng(int(seed) + 104729 * (member_index + 1))
        bootstrap_count = max(2, int(math.ceil(len(train_indices) * cfg.bootstrap_fraction)))
        bootstrap = rng.choice(train_indices, size=bootstrap_count, replace=True)
        optimizer = torch.optim.AdamW(predictor.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay)
        scaler = _make_grad_scaler(device, cfg.mixed_precision)
        best_loss = math.inf
        best_state = _state_copy(predictor)
        patience = 0
        history = []
        for epoch in range(cfg.predictor_epochs):
            predictor.train()
            losses = []
            for batch in _batch_indices(bootstrap, cfg.batch_size, rng):
                x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
                target = torch.as_tensor(latents[batch], dtype=torch.float32, device=device)
                _field_weights, _shared_weights, residual_targets, applicability = _filter_batch(data_filter, batch, device, cfg)
                optimizer.zero_grad(set_to_none=True)
                with _autocast(device, cfg.mixed_precision):
                    predicted_latent, applicability_logit, residual_logits = model.split_predictor_output(predictor(x))
                    loss = F.smooth_l1_loss(predicted_latent, target, beta=1.0)
                    if cfg.regime_head:
                        loss = loss + cfg.applicability_loss_weight * F.binary_cross_entropy_with_logits(applicability_logit, applicability)
                        if cfg.gated_private_residual:
                            loss = loss + cfg.residual_gate_loss_weight * F.binary_cross_entropy_with_logits(residual_logits, residual_targets)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(predictor.parameters(), cfg.gradient_clip_norm)
                scaler.step(optimizer)
                scaler.update()
                losses.append(float(loss.detach().cpu()))
            validation = _predictor_validation_loss(model, predictor, parameters, latents, data_filter, validation_indices, device, cfg)
            history.append({'epoch': epoch + 1, 'training_latent_loss': _mean_loss(losses), 'validation_latent_loss': validation})
            if not math.isfinite(best_loss) or validation < best_loss - max(1e-07, abs(best_loss) * 1e-05):
                best_loss = validation
                best_state = _state_copy(predictor)
                patience = 0
            else:
                patience += 1
                if patience >= cfg.early_stopping_patience:
                    break
        predictor.load_state_dict(best_state)
        member_histories.append({'member_index': member_index, 'bootstrap_design_count': bootstrap_count, 'epochs_completed': len(history), 'best_validation_latent_loss': best_loss, 'history': history})
    return {'wall_sec': time.perf_counter() - started, 'members': member_histories}

@torch.no_grad()
def _predicted_grid_validation_loss(model: HierarchicalCAEModel, parameters: np.ndarray, fields: Sequence[np.ndarray], data_filter: DataFilterAssessment, indices: np.ndarray, device: torch.device, cfg: CAETrainConfig) -> float:
    from .networks import HierarchicalCAEModel
    from .objectives import _batch_indices, _field_batch, _filter_batch, field_macro_loss
    model.eval()
    losses = []
    for batch in _batch_indices(indices, cfg.batch_size):
        x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
        targets = _field_batch(fields, batch, device)
        field_weights, _shared_weights, _residual_targets, _applicability = _filter_batch(data_filter, batch, device, cfg)
        predictions_by_member = [model.predict_member(member_index, x)[0] for member_index in range(len(model.predictors))]
        means = tuple((torch.stack([member[field_index] for member in predictions_by_member], dim=0).mean(dim=0) for field_index in range(len(fields))))
        losses.append(float(field_macro_loss(means, targets, field_weights=field_weights, loss_cap=cfg.robust_loss_cap).detach().cpu()))
    return _mean_loss(losses)

def _fine_tune_gate(model: HierarchicalCAEModel, parameters: np.ndarray, fields: Sequence[np.ndarray], data_filter: DataFilterAssessment, train_indices: np.ndarray, validation_indices: np.ndarray, device: torch.device, cfg: CAETrainConfig, seed: int) -> dict[str, object]:
    from .networks import HierarchicalCAEModel
    from .objectives import _batch_indices, _field_batch, _filter_batch, field_macro_loss
    baseline = _predicted_grid_validation_loss(model, parameters, fields, data_filter, validation_indices, device, cfg)
    if cfg.fine_tune_epochs <= 0:
        return {'attempted': False, 'accepted': False, 'baseline_validation_field_macro_loss': baseline, 'candidate_validation_field_macro_loss': baseline, 'wall_sec': 0.0}
    original = _state_copy(model)
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    for codec in model.codecs:
        for parameter in codec.encoder_conv.parameters() if hasattr(codec, 'encoder_conv') else ():
            parameter.requires_grad_(False)
        for parameter in codec.encoder.parameters() if hasattr(codec, 'encoder') else ():
            parameter.requires_grad_(False)
    for module in [model.global_teacher, model.group_teachers, model.private_teachers]:
        for parameter in module.parameters():
            parameter.requires_grad_(False)
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=cfg.learning_rate * 0.2, weight_decay=cfg.weight_decay)
    scaler = _make_grad_scaler(device, cfg.mixed_precision)
    rng = np.random.default_rng(int(seed) + 99991)
    started = time.perf_counter()
    for _epoch in range(cfg.fine_tune_epochs):
        model.train()
        for batch in _batch_indices(train_indices, cfg.batch_size, rng):
            x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
            targets = _field_batch(fields, batch, device)
            field_weights, _shared_weights, residual_targets, applicability = _filter_batch(data_filter, batch, device, cfg)
            member_index = int(rng.integers(0, len(model.predictors)))
            optimizer.zero_grad(set_to_none=True)
            with _autocast(device, cfg.mixed_precision):
                predictions, applicability_logit, residual_logits = model.predict_member(member_index, x)
                loss = field_macro_loss(predictions, targets, field_weights=field_weights, loss_cap=cfg.robust_loss_cap)
                if cfg.regime_head:
                    loss = loss + cfg.applicability_loss_weight * F.binary_cross_entropy_with_logits(applicability_logit, applicability)
                    if cfg.gated_private_residual:
                        loss = loss + cfg.residual_gate_loss_weight * F.binary_cross_entropy_with_logits(residual_logits, residual_targets)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(trainable, cfg.gradient_clip_norm)
            scaler.step(optimizer)
            scaler.update()
    candidate = _predicted_grid_validation_loss(model, parameters, fields, data_filter, validation_indices, device, cfg)
    accepted = bool(candidate <= baseline * (1.0 - 0.001))
    if not accepted:
        model.load_state_dict(original)
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    return {'attempted': True, 'accepted': accepted, 'baseline_validation_field_macro_loss': baseline, 'candidate_validation_field_macro_loss': candidate, 'wall_sec': time.perf_counter() - started}

def _coordinate_point_indices(layout: FieldLayout, limit: int, *, rng: np.random.Generator | None) -> np.ndarray:
    count = int(layout.point_count)
    selected = min(count, max(1, int(limit)))
    if selected == count:
        return np.arange(count, dtype=np.int64)
    if rng is not None:
        return np.sort(rng.choice(count, size=selected, replace=False)).astype(np.int64, copy=False)
    return np.unique(np.linspace(0, count - 1, num=selected, dtype=np.int64))

def _coordinate_tensors(layout: FieldLayout, point_indices: np.ndarray, device: torch.device) -> torch.Tensor:
    physical = stored_coordinate_points(layout)[point_indices]
    encoded = encode_coordinate_points(layout, physical)
    return torch.as_tensor(encoded, dtype=torch.float32, device=device)

@torch.no_grad()
def _coordinate_validation_loss(model: HierarchicalCAEModel, parameters: np.ndarray, fields: Sequence[np.ndarray], data_filter: DataFilterAssessment, indices: np.ndarray, device: torch.device, cfg: CAETrainConfig) -> dict[str, object]:
    from .networks import HierarchicalCAEModel
    from .objectives import _batch_indices, _field_batch, _filter_batch
    model.eval()
    point_indices = tuple((_coordinate_point_indices(layout, cfg.coordinate_validation_points_per_field, rng=None) for layout in model.schema.layouts))
    coordinate_tensors = tuple((_coordinate_tensors(layout, selected, device) for layout, selected in zip(model.schema.layouts, point_indices)))
    target_numerator = 0.0
    consistency_numerator = 0.0
    denominator = 0.0
    for batch in _batch_indices(indices, cfg.batch_size):
        x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
        targets = _field_batch(fields, batch, device)
        field_weights, _shared, _residual, _applicability = _filter_batch(data_filter, batch, device, cfg)
        for member_index in range(len(model.predictors)):
            latent, _applicability_logit, residual_logits = model.predictor_output(member_index, x)
            residual_gates = torch.sigmoid(residual_logits) if cfg.regime_head and cfg.gated_private_residual else torch.zeros_like(residual_logits)
            grids = model.decode_joint(latent, residual_gates)
            for field_index, selected in enumerate(point_indices):
                predicted = model.decode_coordinates(latent, residual_gates, field_index=field_index, encoded_coordinates=coordinate_tensors[field_index])
                target = targets[field_index].reshape(len(batch), -1)[:, selected]
                grid = grids[field_index].reshape(len(batch), -1)[:, selected]
                target_loss = F.smooth_l1_loss(predicted, target, beta=1.0, reduction='none').mean(dim=1)
                consistency_loss = F.smooth_l1_loss(predicted, grid, beta=1.0, reduction='none').mean(dim=1)
                weights = field_weights[:, field_index]
                target_numerator += float(torch.sum(target_loss * weights).cpu())
                consistency_numerator += float(torch.sum(consistency_loss * weights).cpu())
                denominator += float(torch.sum(weights).cpu())
    denominator = max(denominator, np.finfo(np.float64).eps)
    target_loss = target_numerator / denominator
    consistency_loss = consistency_numerator / denominator
    return {'target_field_macro_loss': float(target_loss), 'grid_consistency_field_macro_loss': float(consistency_loss), 'combined_loss': float(target_loss + cfg.coordinate_consistency_weight * consistency_loss), 'sampled_stored_points_per_field': [int(len(values)) for values in point_indices], 'member_count': len(model.predictors)}

def _train_coordinate_readouts(model: HierarchicalCAEModel, parameters: np.ndarray, fields: Sequence[np.ndarray], data_filter: DataFilterAssessment, train_indices: np.ndarray, validation_indices: np.ndarray, device: torch.device, cfg: CAETrainConfig, seed: int) -> dict[str, object]:
    from .networks import HierarchicalCAEModel
    from .objectives import _batch_indices, _field_batch, _filter_batch
    if not cfg.coordinate_readout:
        return {'enabled': False, 'status': 'not-configured', 'wall_sec': 0.0}
    if not model.coordinate_readouts:
        raise RuntimeError('coordinate readout configuration/model mismatch')
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    coordinate_parameters = [parameter for module in model.coordinate_readouts for parameter in module.parameters()]
    for parameter in coordinate_parameters:
        parameter.requires_grad_(True)
    optimizer = torch.optim.AdamW(coordinate_parameters, lr=cfg.learning_rate, weight_decay=cfg.weight_decay)
    scaler = _make_grad_scaler(device, cfg.mixed_precision)
    rng = np.random.default_rng(int(seed) + 200003)
    best_loss = math.inf
    best_state = _state_copy(model.coordinate_readouts)
    patience = 0
    history = []
    started = time.perf_counter()
    for epoch in range(cfg.coordinate_epochs):
        model.train()
        epoch_losses = []
        for batch in _batch_indices(train_indices, cfg.batch_size, rng):
            x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
            targets = _field_batch(fields, batch, device)
            field_weights, _shared, _residual, _applicability = _filter_batch(data_filter, batch, device, cfg)
            member_index = int(rng.integers(0, len(model.predictors)))
            with torch.no_grad():
                latent, _applicability_logit, residual_logits = model.predictor_output(member_index, x)
                residual_gates = torch.sigmoid(residual_logits) if cfg.regime_head and cfg.gated_private_residual else torch.zeros_like(residual_logits)
                grids = model.decode_joint(latent, residual_gates)
            optimizer.zero_grad(set_to_none=True)
            target_numerator = torch.zeros((), dtype=torch.float32, device=device)
            consistency_numerator = torch.zeros((), dtype=torch.float32, device=device)
            denominator = torch.zeros((), dtype=torch.float32, device=device)
            with _autocast(device, cfg.mixed_precision):
                for field_index, layout in enumerate(model.schema.layouts):
                    selected = _coordinate_point_indices(layout, cfg.coordinate_points_per_field, rng=rng)
                    encoded = _coordinate_tensors(layout, selected, device)
                    predicted = model.decode_coordinates(latent, residual_gates, field_index=field_index, encoded_coordinates=encoded)
                    target = targets[field_index].reshape(len(batch), -1)[:, selected]
                    grid = grids[field_index].reshape(len(batch), -1)[:, selected]
                    target_loss = F.smooth_l1_loss(predicted, target, beta=1.0, reduction='none').mean(dim=1)
                    consistency_loss = F.smooth_l1_loss(predicted, grid, beta=1.0, reduction='none').mean(dim=1)
                    weights = field_weights[:, field_index]
                    target_numerator = target_numerator + torch.sum(target_loss * weights)
                    consistency_numerator = consistency_numerator + torch.sum(consistency_loss * weights)
                    denominator = denominator + torch.sum(weights)
                safe_denominator = torch.clamp(denominator, min=torch.finfo(torch.float32).eps)
                loss = (target_numerator + cfg.coordinate_consistency_weight * consistency_numerator) / safe_denominator
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(coordinate_parameters, cfg.gradient_clip_norm)
            scaler.step(optimizer)
            scaler.update()
            epoch_losses.append(float(loss.detach().cpu()))
        validation = _coordinate_validation_loss(model, parameters, fields, data_filter, validation_indices, device, cfg)
        history.append({'epoch': epoch + 1, 'training_combined_loss': _mean_loss(epoch_losses), 'validation': validation})
        candidate = float(validation['combined_loss'])
        if not math.isfinite(best_loss) or candidate < best_loss - max(1e-07, abs(best_loss) * 1e-05):
            best_loss = candidate
            best_state = _state_copy(model.coordinate_readouts)
            patience = 0
        else:
            patience += 1
            if patience >= cfg.early_stopping_patience:
                break
    model.coordinate_readouts.load_state_dict(best_state)
    final_validation = _coordinate_validation_loss(model, parameters, fields, data_filter, validation_indices, device, cfg)
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    return {'enabled': True, 'status': 'experimental-performance-not-accepted', 'epochs_completed': len(history), 'best_validation_combined_loss': float(best_loss), 'final_validation': final_validation, 'coordinate_parameter_count': int(sum((parameter.numel() for parameter in coordinate_parameters))), 'authority': 'viewer/off-grid-only; full-grid decoder remains authoritative', 'history': history, 'wall_sec': time.perf_counter() - started}

def fit_hierarchical_cae(*, input_dim: int, schema: HierarchicalSchema, parameters: np.ndarray, standardized_fields: Sequence[np.ndarray], data_filter: DataFilterAssessment, device: torch.device, train_cfg: CAETrainConfig, seed: int, train_indices: np.ndarray | None=None, validation_indices: np.ndarray | None=None) -> tuple[HierarchicalCAEModel, dict[str, object]]:
    from .networks import HierarchicalCAEModel, MODEL_NAME
    from .objectives import design_level_split
    x = np.ascontiguousarray(parameters, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != int(input_dim):
        raise ValueError(f'expected parameter matrix [N,{int(input_dim)}]')
    if any((values.shape[0] != x.shape[0] for values in standardized_fields)):
        raise ValueError('every hierarchical CAE field must align with parameter rows')
    expected_filter_shape = (x.shape[0], len(schema.layouts))
    if data_filter.field_weights.shape != expected_filter_shape:
        raise ValueError('data-filter assessment does not align with design/field rows')
    if train_indices is None or validation_indices is None:
        train_indices, validation_indices = design_level_split(x, validation_fraction=train_cfg.validation_fraction, seed=int(seed))
    train_indices = np.asarray(train_indices, dtype=np.int64)
    validation_indices = np.asarray(validation_indices, dtype=np.int64)
    if set(train_indices.tolist()).intersection(validation_indices.tolist()):
        raise ValueError('training and validation design rows must be disjoint')
    if not len(train_indices) or not len(validation_indices):
        raise ValueError('training and validation partitions must both be non-empty')
    torch.manual_seed(int(seed))
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(int(seed))
        torch.cuda.reset_peak_memory_stats(device)
    model = HierarchicalCAEModel(input_dim, schema, train_cfg).to(device)
    started = time.perf_counter()
    codec = _train_codecs(model, standardized_fields, data_filter, train_indices, validation_indices, device, train_cfg, int(seed))
    latents = _teacher_latents(model, standardized_fields, data_filter, device, train_cfg)
    predictors = _train_predictors(model, x, latents, data_filter, train_indices, validation_indices, device, train_cfg, int(seed))
    fine_tune = _fine_tune_gate(model, x, standardized_fields, data_filter, train_indices, validation_indices, device, train_cfg, int(seed))
    coordinate = _train_coordinate_readouts(model, x, standardized_fields, data_filter, train_indices, validation_indices, device, train_cfg, int(seed))
    model.eval()
    parameter_count = sum((parameter.numel() for parameter in model.parameters()))
    group_parameter_count = sum((parameter.numel() for module in model.group_teachers for parameter in module.parameters()))
    history = {'model': MODEL_NAME, 'architecture_version': train_cfg.architecture_version, 'training_policy': 'design-split-field-macro-hierarchical-latent', 'member_count': len(model.predictors), 'train_design_count': int(len(train_indices)), 'validation_design_count': int(len(validation_indices)), 'field_count': len(schema.layouts), 'parameter_count': int(parameter_count), 'group_parameter_count': int(group_parameter_count), 'group_count': len(schema.groups), 'sharing': train_cfg.sharing, 'device': str(device), 'torch_version': str(torch.__version__), 'codec_stage': codec, 'predictor_stage': predictors, 'fine_tune_gate': fine_tune, 'coordinate_readout_stage': coordinate, 'data_filter_assessment': data_filter.diagnostics(), 'total_wall_sec': time.perf_counter() - started, 'peak_vram_bytes': int(torch.cuda.max_memory_allocated(device)) if device.type == 'cuda' else 0}
    return (model, history)
