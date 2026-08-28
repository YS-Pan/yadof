"""Pure data contracts for the PCA/SVD rawData component."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import numpy as np

from ...job_template.rawdata_template import (
    RawDataFieldSelector,
    RawDataSchemaTemplate,
    StructuredRawDataSample,
)
from .settings import LinearSubspaceSettings


Population = tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class NamedTrainingData:
    parameter_names: tuple[str, ...]
    normalized_variables: Population
    raw_data: tuple[StructuredRawDataSample, ...]
    row_ids: tuple[str, ...] = ()
    record_metadata: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        count = len(self.normalized_variables)
        if count != len(self.raw_data):
            raise ValueError("parameter and rawData training rows must align")
        if self.row_ids and len(self.row_ids) != count:
            raise ValueError("training row identities must align with design rows")
        if self.record_metadata and len(self.record_metadata) != count:
            raise ValueError("record metadata must align with design rows")


@dataclass(frozen=True, slots=True)
class FieldBasis:
    selector: RawDataFieldSelector
    shape: tuple[int, ...]
    dtype: str
    mean: np.ndarray
    basis: np.ndarray
    singular_values: np.ndarray
    requested_rank: int
    effective_rank: int
    rank_reason: str


@dataclass(frozen=True, slots=True)
class LinearSubspaceCodec:
    settings: LinearSubspaceSettings
    template: RawDataSchemaTemplate
    fields: tuple[FieldBasis, ...]
    coefficient_offsets: tuple[int, ...]

    @property
    def coefficient_count(self) -> int:
        return int(self.coefficient_offsets[-1])


@dataclass(frozen=True, slots=True)
class LinearSubspaceModel:
    settings: LinearSubspaceSettings
    parameter_names: tuple[str, ...]
    template: RawDataSchemaTemplate
    fields: tuple[FieldBasis, ...]
    coefficient_offsets: tuple[int, ...]
    ridge_weights: np.ndarray

    @property
    def coefficient_count(self) -> int:
        return int(self.coefficient_offsets[-1])


@dataclass(frozen=True, slots=True)
class OracleReconstruction:
    samples: tuple[StructuredRawDataSample, ...]
    requested_rank: int
    effective_ranks: Mapping[RawDataFieldSelector, int]
    diagnostic_only: bool = True
    validation_rawdata_encoded: bool = True


@dataclass(frozen=True, slots=True)
class LinearSubspaceState:
    generation_index: int
    sample_count: int
    strategy_signature: str
    state_signature: str
    training_design_signature: str
    parameter_definition_signature: Mapping[str, object]
    model: LinearSubspaceModel
    checkpoint_path: Path
    namespace_manifest_path: Path
    artifact_dir: Path
    artifact_path: Path
    run_namespace: str
    component_namespace: str
    training_row_ids: tuple[str, ...] = field(default=())
    train_history: Mapping[str, object] = field(default_factory=dict)


SurrogateState = LinearSubspaceState


__all__ = [
    "FieldBasis",
    "LinearSubspaceCodec",
    "LinearSubspaceModel",
    "LinearSubspaceState",
    "NamedTrainingData",
    "OracleReconstruction",
    "Population",
    "SurrogateState",
    "StructuredRawDataSample",
]
