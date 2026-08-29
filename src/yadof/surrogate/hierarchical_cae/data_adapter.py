"""Hierarchical CAE data adapter service."""
from __future__ import annotations
from typing import Mapping, Sequence
import numpy as np
from ...job_template import api as job_template_api
from ...job_template.rawdata_template import StructuredRawDataSample
from ...recorded_data import api as recorded_api
from ...recorded_data.session import CampaignSession
from ...task_snapshot import GenerationTaskSnapshot
from ...workspace import WorkspaceContext
from .objectives import unique_design_indices
from .schema import build_schema, named_sample_from_payloads
from .types import HierarchicalSchema, NamedTrainingData, Population

def _as_population(values) -> Population:
    if values is None:
        return ()
    rows = tuple(values)
    if not rows:
        return ()
    if not isinstance(rows[0], (list, tuple, np.ndarray)):
        rows = (rows,)
    return tuple((tuple((float(value) for value in row)) for row in rows))

def _x_matrix(population, input_dim: int | None=None) -> np.ndarray:
    rows = _as_population(population)
    if not rows:
        width = 0 if input_dim is None else int(input_dim)
        return np.zeros((0, width), dtype=np.float32)
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError('population must be a two-dimensional sequence')
    if input_dim is not None and matrix.shape[1] != int(input_dim):
        raise ValueError(f'expected population width {int(input_dim)}, got {matrix.shape[1]}')
    if not np.all(np.isfinite(matrix)):
        raise ValueError('normalized surrogate parameters must be finite')
    if np.any(matrix < -1e-09) or np.any(matrix > 1.0 + 1e-09):
        raise ValueError('normalized surrogate parameters must stay in [0, 1]')
    return np.ascontiguousarray(np.clip(matrix, 0.0, 1.0), dtype=np.float32)

def _load_training_data(workspace: WorkspaceContext) -> NamedTrainingData:
    bundled = recorded_api.get_surrogate_training_data(workspace)
    names = tuple((str(value) for value in bundled.get('parameter_names', ())))
    variables = _as_population(bundled.get('normalized_variables', ()))
    payload_rows = tuple(bundled.get('raw_data', ()))
    filename_rows = tuple(bundled.get('rawdata_filenames', ()))
    metadata_rows = tuple(bundled.get('record_metadata', ()))
    if len(payload_rows) != len(filename_rows):
        raise ValueError('recorded hierarchical CAE training data is missing rawData filenames')
    samples = tuple((named_sample_from_payloads(filenames, payloads) for filenames, payloads in zip(filename_rows, payload_rows)))
    return NamedTrainingData(parameter_names=names, normalized_variables=variables, raw_data=samples, record_metadata=tuple((dict(value) if isinstance(value, Mapping) else {} for value in metadata_rows)))

def training_data_from_session(session: CampaignSession, snapshot: GenerationTaskSnapshot) -> NamedTrainingData:
    historical = session.historical_results(snapshot)
    job_names = tuple((name for name, _variables, _costs in historical))
    named = dict(session.named_rawdata_samples(job_names=job_names, status='completed'))
    metadata = dict(session.record_metadata(job_names=job_names, status='completed'))
    variables = []
    samples = []
    metadata_rows = []
    for job_name, normalized, _costs in historical:
        items = named.get(job_name)
        if items is None:
            continue
        variables.append(tuple((float(value) for value in normalized)))
        samples.append(StructuredRawDataSample.from_items(items))
        metadata_rows.append(dict(metadata.get(job_name, {})))
    return NamedTrainingData(parameter_names=tuple(snapshot.parameter_names), normalized_variables=tuple(variables), raw_data=tuple(samples), record_metadata=tuple(metadata_rows))

def _unique_training_data(data: NamedTrainingData) -> tuple[NamedTrainingData, int]:
    matrix = _x_matrix(data.normalized_variables)
    indices = unique_design_indices(matrix)
    dropped = len(data.normalized_variables) - len(indices)
    metadata = data.record_metadata if data.record_metadata else tuple(({} for _sample in data.raw_data))
    return (NamedTrainingData(parameter_names=data.parameter_names, normalized_variables=tuple((data.normalized_variables[int(index)] for index in indices)), raw_data=tuple((data.raw_data[int(index)] for index in indices)), record_metadata=tuple((metadata[int(index)] for index in indices))), int(dropped))

def _costs_from_samples(workspace: WorkspaceContext, samples: Sequence[StructuredRawDataSample], normalized_variables: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    raw_variables = tuple((job_template_api.denormalize_variables(workspace, row) for row in normalized_variables))
    costs = job_template_api.calculate_costs_from_raw_data(workspace, tuple((sample.cost_items() for sample in samples)), raw_variables=raw_variables)
    return tuple((tuple((float(value) for value in row)) for row in costs))

def _build_current_schema(data: NamedTrainingData, component) -> HierarchicalSchema:
    if not data.raw_data:
        raise ValueError('hierarchical CAE requires rawData design rows')
    return build_schema(data.raw_data[0], groups=component.groups, field_layouts=component.field_layouts, axis_encodings=component.axis_encodings)
