from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import torch

from .modeling import INRTrainConfig


Population = tuple[tuple[float, ...], ...]
RawDataItem = Mapping[str, object] | str | Path
RawSample = tuple[RawDataItem, ...]


@dataclass(frozen=True)
class TrainingData:
    parameter_names: tuple[str, ...]
    normalized_variables: Population
    raw_data: tuple[RawSample, ...]


@dataclass(frozen=True)
class RawArraySlot:
    item_index: int
    key: str
    shape: tuple[int, ...]
    dtype: str
    start: int
    end: int
    field_id: int


@dataclass(frozen=True)
class RawDataSchema:
    templates: tuple[dict[str, object], ...]
    modeled_slots: tuple[RawArraySlot, ...]
    flat_dim: int
    coord_table: np.ndarray
    field_ids: np.ndarray

    @property
    def n_fields(self) -> int:
        return int(max((slot.field_id for slot in self.modeled_slots), default=-1) + 1)


@dataclass(frozen=True)
class TargetScaler:
    mean: np.ndarray
    scale: np.ndarray

    def transform(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray((values - self.mean) / self.scale, dtype=np.float32)

    def inverse(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(values * self.scale + self.mean, dtype=np.float64)

    def inverse_members(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(values * self.scale[None, None, :] + self.mean[None, None, :], dtype=np.float64)


@dataclass(frozen=True)
class SurrogateState:
    generation_index: int
    sample_count: int
    checkpoint_path: Path
    model_path: Path
    artifact_dir: Path
    model_name: str
    parameter_names: tuple[str, ...]
    normalized_variables: Population
    raw_data: tuple[RawSample, ...]
    schema: RawDataSchema | None
    scaler: TargetScaler | None
    model: object | None
    train_cfg: INRTrainConfig | None
    device: torch.device | None
    train_history: dict[str, object]
    training_flat_values: np.ndarray
    query_weights: np.ndarray
    mean_relative_error: float
    historical_relative_error_p50: tuple[float, ...]
    historical_relative_error_p90: tuple[float, ...]
    historical_relative_error_p95: tuple[float, ...]
    historical_absolute_error_p90: tuple[float, ...]
    historical_true_costs: tuple[tuple[float, ...], ...]
    historical_predicted_costs: tuple[tuple[float, ...], ...]
