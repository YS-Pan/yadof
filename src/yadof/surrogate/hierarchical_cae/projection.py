"""Hierarchical CAE projection service."""
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

def _predict_members(state: HierarchicalState, population) -> tuple[tuple[np.ndarray, ...], np.ndarray, np.ndarray]:
    from .data_adapter import _x_matrix
    assert state.schema is not None and state.model is not None
    assert isinstance(state.device, torch.device)
    x = _x_matrix(population, len(state.parameter_names))
    return predict_hierarchical_members(model=state.model, parameters=x, device=state.device, batch_size=state.train_cfg.inference_batch_size)

def predict_raw_data(workspace: WorkspaceContext | str | Path, population, *, component) -> tuple[StructuredRawDataSample, ...]:
    from .data_adapter import _as_population
    from .state_repository import _require_state
    config = load_config(workspace)
    state = _require_state(config, component=component)
    rows = _as_population(population)
    if not rows:
        return ()
    fields, _applicability, _residual = _predict_members(state, rows)
    assert state.schema is not None
    means = tuple((np.mean(values, axis=0) for values in fields))
    return reconstruct_samples(state.schema, means)

def predict_population(workspace: WorkspaceContext | str | Path, population, *, component) -> tuple[tuple[tuple[float, ...], tuple[tuple[float, float], ...]], ...]:
    from .data_adapter import _as_population, _costs_from_samples
    from .state_repository import _require_state
    config = load_config(workspace)
    state = _require_state(config, component=component)
    rows = _as_population(population)
    if not rows:
        return ()
    fields, _applicability, _residual = _predict_members(state, rows)
    assert state.schema is not None
    mean_samples = reconstruct_samples(state.schema, tuple((np.mean(values, axis=0) for values in fields)))
    costs = _costs_from_samples(config.workspace, mean_samples, rows)
    member_costs = []
    for member_index in range(fields[0].shape[0]):
        try:
            samples = reconstruct_samples(state.schema, tuple((values[member_index] for values in fields)))
            member_costs.append(np.asarray(_costs_from_samples(config.workspace, samples, rows), dtype=np.float64))
        except Exception:
            continue
    if member_costs:
        matrix = np.stack(member_costs, axis=0)
        lower = np.min(matrix, axis=0)
        upper = np.max(matrix, axis=0)
    else:
        lower = upper = np.asarray(costs, dtype=np.float64)
    output = []
    for row_index, cost_row in enumerate(costs):
        intervals = tuple(((min(float(lower[row_index, index]), float(upper[row_index, index])), max(float(lower[row_index, index]), float(upper[row_index, index]))) for index in range(len(cost_row))))
        output.append((tuple(cost_row), intervals))
    return tuple(output)

def predict_applicability(workspace: WorkspaceContext | str | Path, population, *, component) -> ApplicabilityPrediction:
    from .data_adapter import _as_population
    from .state_repository import _require_state
    config = load_config(workspace)
    state = _require_state(config, component=component)
    rows = _as_population(population)
    if not rows:
        members = tuple((() for _ in range(state.train_cfg.predictor_members)))
        means: tuple[float, ...] = ()
    else:
        _fields, probabilities, _residual = _predict_members(state, rows)
        members = tuple((tuple((float(value) for value in row)) for row in probabilities))
        means = tuple((float(value) for value in np.mean(probabilities, axis=0)))
    policy_identity = {'enabled': False, 'default': 'uniform-smooth'} if state.quality_policy is None else state.quality_policy.as_dict()
    return ApplicabilityPrediction(population=rows, mean_smooth_probability=means, member_smooth_probabilities=members, policy_identity=policy_identity, state_signature=state.state_signature, strategy_signature=state.strategy_signature, calibrated=False)

def predict_field_at_coordinates(workspace: WorkspaceContext | str | Path, population, *, component, field_selector: tuple[str, str], axis_coordinates: Sequence[np.ndarray]) -> CoordinatePrediction:
    """Query the experimental viewer-only trunk without changing full-grid state."""
    from .data_adapter import _as_population, _x_matrix
    from .state_repository import _require_state
    config = load_config(workspace)
    state = _require_state(config, component=component)
    if not state.train_cfg.coordinate_readout:
        raise RuntimeError('the selected hierarchical CAE checkpoint has no coordinate readout')
    assert state.schema is not None and state.model is not None
    assert isinstance(state.device, torch.device)
    selector = (str(field_selector[0]), str(field_selector[1]))
    try:
        field_index = state.schema.field_selectors.index(selector)
    except ValueError as exc:
        raise KeyError(selector) from exc
    layout = state.schema.layouts[field_index]
    points, output_shape, axes = coordinate_grid(layout, axis_coordinates)
    rows = _as_population(population)
    if rows:
        x = _x_matrix(rows, len(state.parameter_names))
        standardized = predict_hierarchical_coordinate_members(model=state.model, parameters=x, field_index=field_index, coordinate_points=points, device=state.device, batch_size=state.train_cfg.inference_batch_size, query_batch_size=state.train_cfg.coordinate_query_batch_size)
    else:
        standardized = np.empty((state.train_cfg.predictor_members, 0, int(points.shape[0])), dtype=np.float32)
    scaler = state.schema.scalers[field_index]
    means = interpolate_stored_values(layout, scaler.mean, points)
    scales = interpolate_stored_values(layout, scaler.scale, points)
    physical = np.asarray(standardized, dtype=np.float64) * scales[None, None, :] + means[None, None, :]
    member_values = np.ascontiguousarray(physical.reshape((physical.shape[0], physical.shape[1], *output_shape)), dtype=np.float64)
    return CoordinatePrediction(field_selector=selector, axis_coordinates=tuple((values.copy() for values in axes)), member_values=member_values, state_signature=state.state_signature)
