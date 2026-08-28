"""Deterministic ridge prediction and diagnostic-only reconstruction oracle."""

from __future__ import annotations

from types import MappingProxyType
from typing import Sequence

import numpy as np

from ...job_template.rawdata_template import StructuredRawDataSample
from .codec import (
    _restore_dtype,
    decode_field,
    encode_field,
    field_matrices,
    fit_field_bases,
    validate_samples,
)
from .settings import LinearSubspaceSettings
from .types import LinearSubspaceModel, NamedTrainingData, OracleReconstruction


def normalized_parameter_matrix(values, *, width: int | None = None) -> np.ndarray:
    rows = tuple(values or ())
    if not rows:
        return np.zeros((0, 0 if width is None else width), dtype=np.float64)
    if not isinstance(rows[0], (tuple, list, np.ndarray)):
        rows = (rows,)
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("normalized surrogate parameters must be a two-dimensional sequence")
    if width is not None and matrix.shape[1] != width:
        raise ValueError(f"expected {width} normalized parameters, got {matrix.shape[1]}")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("normalized surrogate parameters must be finite")
    tolerance = 1e-9
    if np.any(matrix < -tolerance) or np.any(matrix > 1.0 + tolerance):
        raise ValueError("normalized surrogate parameters must stay in [0, 1]")
    return np.ascontiguousarray(np.clip(matrix, 0.0, 1.0))


def fit_linear_subspace(
    data: NamedTrainingData,
    settings: LinearSubspaceSettings,
) -> LinearSubspaceModel:
    x = normalized_parameter_matrix(
        data.normalized_variables,
        width=len(data.parameter_names),
    )
    if x.shape[0] != len(data.raw_data):
        raise ValueError("normalized parameter and rawData rows must align")
    template, samples = validate_samples(data.raw_data)
    matrices = field_matrices(template, samples)
    fields = fit_field_bases(template, matrices, settings)
    coefficient_rows = tuple(
        encode_field(matrix, field) for matrix, field in zip(matrices, fields)
    )
    offsets = [0]
    for field in fields:
        offsets.append(offsets[-1] + field.effective_rank)
    coefficients = (
        np.concatenate(coefficient_rows, axis=1)
        if offsets[-1]
        else np.zeros((x.shape[0], 0), dtype=np.float64)
    )
    weights = fit_multioutput_ridge(
        x,
        coefficients,
        alpha=settings.ridge_alpha,
        fit_intercept=settings.fit_intercept,
    )
    return LinearSubspaceModel(
        settings=settings,
        parameter_names=tuple(data.parameter_names),
        template=template,
        fields=fields,
        coefficient_offsets=tuple(offsets),
        ridge_weights=weights,
    )


def fit_multioutput_ridge(
    x: np.ndarray,
    targets: np.ndarray,
    *,
    alpha: float,
    fit_intercept: bool,
) -> np.ndarray:
    matrix = np.asarray(x, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    if matrix.ndim != 2 or y.ndim != 2 or matrix.shape[0] != y.shape[0]:
        raise ValueError("ridge inputs must be aligned two-dimensional matrices")
    design = (
        np.column_stack((np.ones(matrix.shape[0], dtype=np.float64), matrix))
        if fit_intercept
        else matrix
    )
    penalty = np.eye(design.shape[1], dtype=np.float64)
    if fit_intercept:
        penalty[0, 0] = 0.0
    augmented_x = np.vstack((design, np.sqrt(float(alpha)) * penalty))
    augmented_y = np.vstack((y, np.zeros((design.shape[1], y.shape[1]), dtype=np.float64)))
    weights, _residuals, _rank, _singular = np.linalg.lstsq(
        augmented_x, augmented_y, rcond=None
    )
    return np.ascontiguousarray(weights, dtype=np.float64)


def predict_coefficients(model: LinearSubspaceModel, population) -> np.ndarray:
    x = normalized_parameter_matrix(population, width=len(model.parameter_names))
    design = (
        np.column_stack((np.ones(x.shape[0], dtype=np.float64), x))
        if model.settings.fit_intercept
        else x
    )
    return np.ascontiguousarray(design @ model.ridge_weights, dtype=np.float64)


def reconstruct_from_coefficients(
    model: LinearSubspaceModel,
    coefficients: np.ndarray,
) -> tuple[StructuredRawDataSample, ...]:
    matrix = np.asarray(coefficients, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != model.coefficient_count:
        raise ValueError("coefficient matrix does not match the fitted field layout")
    decoded = []
    for index, field in enumerate(model.fields):
        start, end = model.coefficient_offsets[index : index + 2]
        decoded.append(decode_field(matrix[:, start:end], field))
    samples = []
    for row in range(matrix.shape[0]):
        arrays = {}
        for field, values in zip(model.fields, decoded):
            shaped = values[row].reshape(field.shape)
            arrays[field.selector] = _restore_dtype(shaped, np.dtype(field.dtype))
        samples.append(model.template.reconstruct(arrays))
    return tuple(samples)


def predict_raw_data(
    model: LinearSubspaceModel, population
) -> tuple[StructuredRawDataSample, ...]:
    return reconstruct_from_coefficients(model, predict_coefficients(model, population))


def reconstruction_oracle(
    model: LinearSubspaceModel,
    validation_samples: Sequence[StructuredRawDataSample],
) -> OracleReconstruction:
    samples = tuple(model.template.validate_sample(row) for row in validation_samples)
    matrices = field_matrices(model.template, samples)
    coefficients = tuple(
        encode_field(matrix, field) for matrix, field in zip(matrices, model.fields)
    )
    joined = (
        np.concatenate(coefficients, axis=1)
        if model.coefficient_count
        else np.zeros((len(samples), 0), dtype=np.float64)
    )
    return OracleReconstruction(
        samples=reconstruct_from_coefficients(model, joined),
        requested_rank=model.settings.rank,
        effective_ranks=MappingProxyType(
            {field.selector: field.effective_rank for field in model.fields}
        ),
    )


__all__ = [
    "fit_linear_subspace",
    "fit_multioutput_ridge",
    "normalized_parameter_matrix",
    "predict_coefficients",
    "predict_raw_data",
    "reconstruct_from_coefficients",
    "reconstruction_oracle",
]
