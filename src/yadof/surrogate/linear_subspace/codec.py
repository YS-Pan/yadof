"""Per-field centered PCA and uncentered truncated-SVD codecs."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from ...job_template.rawdata_template import (
    RawDataSchemaTemplate,
    StructuredRawDataSample,
)
from .settings import LinearSubspaceSettings
from .types import FieldBasis, LinearSubspaceCodec, NamedTrainingData, OracleReconstruction


def validate_samples(
    samples: Sequence[StructuredRawDataSample],
) -> tuple[RawDataSchemaTemplate, tuple[StructuredRawDataSample, ...]]:
    rows = tuple(samples)
    if not rows:
        raise ValueError("PCA/SVD fitting requires at least one rawData design row")
    template = RawDataSchemaTemplate.from_items(rows[0].items)
    validated = tuple(template.validate_sample(row) for row in rows)
    for field in template.fields:
        array = np.asarray(field.payload[field.main_key])
        if (
            array.dtype.hasobject
            or array.dtype.fields is not None
            or np.issubdtype(array.dtype, np.complexfloating)
            or not np.issubdtype(array.dtype, np.number)
        ):
            raise ValueError(f"rawData field {field.selector!r} must be real numeric")
    return template, validated


def field_matrices(
    template: RawDataSchemaTemplate,
    samples: Sequence[StructuredRawDataSample],
) -> tuple[np.ndarray, ...]:
    output: list[np.ndarray] = []
    for field in template.fields:
        rows = []
        for sample in samples:
            payload = sample.as_mapping()[field.filename]
            rows.append(np.asarray(payload[field.main_key]).reshape(-1))
        matrix = np.asarray(rows, dtype=np.float64)
        if not np.all(np.isfinite(matrix)):
            raise ValueError(f"rawData field {field.selector!r} contains non-finite fit input")
        output.append(np.ascontiguousarray(matrix))
    return tuple(output)


def fit_field_bases(
    template: RawDataSchemaTemplate,
    matrices: Sequence[np.ndarray],
    settings: LinearSubspaceSettings,
) -> tuple[FieldBasis, ...]:
    fields = []
    for index, (field, matrix) in enumerate(zip(template.fields, matrices)):
        rows, width = matrix.shape
        mean = (
            np.mean(matrix, axis=0, dtype=np.float64)
            if settings.decomposition == "pca"
            else np.zeros(width, dtype=np.float64)
        )
        centered = np.ascontiguousarray(matrix - mean, dtype=np.float64)
        maximum = min(width, rows - 1 if settings.decomposition == "pca" else rows)
        reason = "requested-rank"
        if settings.decomposition == "pca" and rows == 1:
            effective = 0
            reason = "single-row-pca-mean-only"
        elif settings.decomposition == "pca" and (
            centered.size == 0
            or float(np.max(np.abs(centered), initial=0.0)) <= settings.constant_atol
        ):
            effective = 0
            reason = "constant-or-near-constant-pca-mean-only"
        else:
            effective = min(settings.rank, maximum)
            if effective < settings.rank:
                reason = "clamped-to-field-and-sample-rank"
        if effective == 0:
            basis = np.zeros((width, 0), dtype=np.float64)
            singular = np.zeros((0,), dtype=np.float64)
        else:
            basis, singular = _torch_lowrank(
                centered,
                rank=effective,
                settings=settings,
                seed=settings.seed + index * 104729,
            )
            basis = canonicalize_basis_sign(basis)
        fields.append(
            FieldBasis(
                selector=field.selector,
                shape=field.main_shape,
                dtype=field.main_dtype,
                mean=np.ascontiguousarray(mean, dtype=np.float64),
                basis=np.ascontiguousarray(basis, dtype=np.float64),
                singular_values=np.ascontiguousarray(singular, dtype=np.float64),
                requested_rank=settings.rank,
                effective_rank=effective,
                rank_reason=reason,
            )
        )
    return tuple(fields)


def _torch_lowrank(
    matrix: np.ndarray,
    *,
    rank: int,
    settings: LinearSubspaceSettings,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - exercised in import isolation
        raise RuntimeError("pca_svd requires the yadof surrogate extra (torch)") from exc
    if settings.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("pca_svd requested CUDA but no CUDA device is available")
    device = "cuda" if settings.device == "auto" and torch.cuda.is_available() else settings.device
    if device == "auto":
        device = "cpu"
    torch_dtype = torch.float32 if settings.dtype == "float32" else torch.float64
    tensor = torch.as_tensor(matrix, dtype=torch_dtype, device=device)
    devices = [torch.cuda.current_device()] if str(device).startswith("cuda") else []
    with torch.random.fork_rng(devices=devices):
        torch.manual_seed(int(seed))
        if devices:
            torch.cuda.manual_seed_all(int(seed))
        _u, singular, vectors = torch.pca_lowrank(
            tensor,
            q=int(rank),
            center=False,
            niter=int(settings.power_iterations),
        )
    return (
        vectors.detach().cpu().numpy().astype(np.float64, copy=False),
        singular.detach().cpu().numpy().astype(np.float64, copy=False),
    )


def canonicalize_basis_sign(basis: np.ndarray) -> np.ndarray:
    output = np.asarray(basis, dtype=np.float64).copy()
    for column in range(output.shape[1]):
        vector = output[:, column]
        pivot = int(np.argmax(np.abs(vector)))
        if vector[pivot] < 0:
            output[:, column] *= -1.0
    return output


def encode_field(matrix: np.ndarray, field: FieldBasis) -> np.ndarray:
    values = np.asarray(matrix, dtype=np.float64)
    return np.ascontiguousarray((values - field.mean) @ field.basis)


def decode_field(coefficients: np.ndarray, field: FieldBasis) -> np.ndarray:
    values = np.asarray(coefficients, dtype=np.float64) @ field.basis.T + field.mean
    return np.ascontiguousarray(values, dtype=np.float64)


def fit_codec(
    samples: Sequence[StructuredRawDataSample],
    *,
    settings: LinearSubspaceSettings,
) -> LinearSubspaceCodec:
    template, validated = validate_samples(samples)
    matrices = field_matrices(template, validated)
    fields = fit_field_bases(template, matrices, settings)
    offsets = [0]
    for field in fields:
        offsets.append(offsets[-1] + field.effective_rank)
    return LinearSubspaceCodec(settings, template, fields, tuple(offsets))


def evaluate_oracle(
    codec: LinearSubspaceCodec,
    samples: Sequence[StructuredRawDataSample],
) -> OracleReconstruction:
    from types import MappingProxyType

    validated = tuple(codec.template.validate_sample(row) for row in samples)
    matrices = field_matrices(codec.template, validated)
    decoded = tuple(
        decode_field(encode_field(matrix, field), field)
        for matrix, field in zip(matrices, codec.fields)
    )
    reconstructed = []
    for row_index in range(len(validated)):
        arrays = {
            field.selector: _restore_dtype(
                values[row_index].reshape(field.shape), np.dtype(field.dtype)
            )
            for field, values in zip(codec.fields, decoded)
        }
        reconstructed.append(codec.template.reconstruct(arrays))
    return OracleReconstruction(
        samples=tuple(reconstructed),
        requested_rank=codec.settings.rank,
        effective_ranks=MappingProxyType(
            {field.selector: field.effective_rank for field in codec.fields}
        ),
    )


def fit_deployable(
    normalized_parameters,
    samples: Sequence[StructuredRawDataSample],
    *,
    parameter_names,
    settings: LinearSubspaceSettings,
):
    from .model import fit_linear_subspace

    return fit_linear_subspace(
        NamedTrainingData(
            parameter_names=tuple(str(value) for value in parameter_names),
            normalized_variables=tuple(
                tuple(float(value) for value in row) for row in normalized_parameters
            ),
            raw_data=tuple(samples),
        ),
        settings,
    )


def predict_rawdata(model, normalized_parameters):
    from .model import predict_raw_data

    return predict_raw_data(model, normalized_parameters)


def _restore_dtype(values: np.ndarray, dtype: np.dtype) -> np.ndarray:
    restored = np.asarray(values, dtype=np.float64)
    if np.issubdtype(dtype, np.integer):
        limits = np.iinfo(dtype)
        restored = np.clip(np.rint(restored), limits.min, limits.max)
    converted = restored.astype(dtype, copy=False)
    if converted.shape == ():
        return converted.copy()
    return np.ascontiguousarray(converted)


__all__ = [
    "canonicalize_basis_sign",
    "decode_field",
    "encode_field",
    "field_matrices",
    "evaluate_oracle",
    "fit_codec",
    "fit_deployable",
    "fit_field_bases",
    "validate_samples",
    "predict_rawdata",
]
