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
from ..quality import RawDataQualityPolicy


Population = tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class NamedTrainingData:
    """Design-level parameter/rawData rows with stable field filenames."""

    parameter_names: tuple[str, ...]
    normalized_variables: Population
    raw_data: tuple[StructuredRawDataSample, ...]
    record_metadata: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if len(self.normalized_variables) != len(self.raw_data):
            raise ValueError("parameter and rawData training rows must align")
        if self.record_metadata and len(self.record_metadata) != len(self.raw_data):
            raise ValueError("record metadata and rawData training rows must align")


@dataclass(frozen=True, slots=True)
class AxisEncoding:
    """Explicit physical-coordinate encoding for one rawData axis."""

    kind: str = "linear"
    period: float | None = None

    def __post_init__(self) -> None:
        kind = str(self.kind).strip().lower()
        if kind not in {"linear", "log", "periodic"}:
            raise ValueError(
                "axis encoding must be one of: linear, log, periodic"
            )
        period = None if self.period is None else float(self.period)
        if kind == "periodic" and (
            period is None or not np.isfinite(period) or period <= 0
        ):
            raise ValueError(
                "periodic axis encoding requires a positive finite period"
            )
        if kind != "periodic" and period is not None:
            raise ValueError("only periodic axis encodings accept a period")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "period", period)

    def as_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "period": self.period}


@dataclass(frozen=True, slots=True)
class FieldLayout:
    """Selector-keyed codec layout with an exact array-axis permutation."""

    selector: RawDataFieldSelector
    shape: tuple[int, ...]
    dtype: str
    axis_names: tuple[str, ...]
    codec_kind: str
    channel_axes: tuple[str, ...] = ()
    spatial_axes: tuple[str, ...] = ()
    model_permutation: tuple[int, ...] = ()
    inverse_permutation: tuple[int, ...] = ()
    model_channels: int = 1
    model_spatial_shape: tuple[int, ...] = ()
    axis_values: tuple[np.ndarray, ...] = field(default=(), repr=False)
    axis_encodings: tuple[AxisEncoding, ...] = ()

    @property
    def rank(self) -> int:
        return len(self.shape)

    @property
    def point_count(self) -> int:
        return int(np.prod(self.shape, dtype=np.int64)) if self.shape else 1

    def as_dict(self) -> dict[str, object]:
        return {
            "selector": list(self.selector),
            "shape": list(self.shape),
            "dtype": self.dtype,
            "axis_names": list(self.axis_names),
            "codec_kind": self.codec_kind,
            "channel_axes": list(self.channel_axes),
            "spatial_axes": list(self.spatial_axes),
            "model_permutation": list(self.model_permutation),
            "inverse_permutation": list(self.inverse_permutation),
            "model_channels": self.model_channels,
            "model_spatial_shape": list(self.model_spatial_shape),
            "axis_values": [
                {
                    "dtype": str(values.dtype),
                    "shape": list(values.shape),
                    "values": values.tolist(),
                }
                for values in self.axis_values
            ],
            "axis_encodings": [item.as_dict() for item in self.axis_encodings],
        }


@dataclass(frozen=True, slots=True)
class FieldScaler:
    mean: np.ndarray
    scale: np.ndarray

    def transform(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(
            (np.asarray(values, dtype=np.float64) - self.mean) / self.scale,
            dtype=np.float32,
        )

    def inverse(self, values: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(
            np.asarray(values, dtype=np.float64) * self.scale + self.mean,
            dtype=np.float64,
        )


@dataclass(frozen=True, slots=True)
class HierarchicalSchema:
    template: RawDataSchemaTemplate
    layouts: tuple[FieldLayout, ...]
    groups: tuple[tuple[RawDataFieldSelector, ...], ...]
    scalers: tuple[FieldScaler, ...] = ()

    def __post_init__(self) -> None:
        selectors = tuple(layout.selector for layout in self.layouts)
        if selectors != self.template.field_selectors:
            raise ValueError(
                "hierarchical layouts must follow canonical template order"
            )
        if self.scalers and len(self.scalers) != len(self.layouts):
            raise ValueError("one field scaler is required per layout")

    @property
    def field_selectors(self) -> tuple[RawDataFieldSelector, ...]:
        return self.template.field_selectors

    def layout_for(self, selector: RawDataFieldSelector) -> FieldLayout:
        try:
            return self.layouts[self.field_selectors.index(tuple(selector))]
        except ValueError as exc:
            raise KeyError(tuple(selector)) from exc

    def as_dict(self, *, include_axis_values: bool = True) -> dict[str, object]:
        layouts = []
        for layout in self.layouts:
            payload = layout.as_dict()
            if not include_axis_values:
                payload.pop("axis_values", None)
            layouts.append(payload)
        return {
            "contract": "yadof.hierarchical-cae-schema",
            "contract_version": 1,
            "template_signature": self.template.signature,
            "field_selectors": [list(value) for value in self.field_selectors],
            "layouts": layouts,
            "groups": [
                [list(selector) for selector in group] for group in self.groups
            ],
        }


@dataclass(frozen=True, slots=True)
class CAETrainConfig:
    architecture_version: int = 1
    token_dim: int = 24
    global_latent_dim: int = 24
    group_latent_dim: int = 12
    private_latent_dim: int = 16
    codec_width: int = 32
    predictor_width: int = 128
    predictor_layers: int = 3
    predictor_members: int = 5
    codec_epochs: int = 120
    predictor_epochs: int = 180
    fine_tune_epochs: int = 12
    batch_size: int = 32
    inference_batch_size: int = 64
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-5
    validation_fraction: float = 0.15
    early_stopping_patience: int = 20
    gradient_clip_norm: float = 5.0
    bootstrap_fraction: float = 1.0
    scale_floor: float = 1.0e-6
    minimum_samples: int = 32
    robust_loss_cap: float | None = None
    applicability_loss_weight: float = 0.25
    residual_gate_loss_weight: float = 0.25
    regime_head: bool = False
    quality_weighted_loss: bool = True
    shared_quality_isolation: bool = True
    gated_private_residual: bool = True
    coordinate_readout: bool = False
    coordinate_width: int = 64
    coordinate_layers: int = 2
    coordinate_epochs: int = 40
    coordinate_points_per_field: int = 128
    coordinate_validation_points_per_field: int = 512
    coordinate_query_batch_size: int = 4096
    coordinate_consistency_weight: float = 1.0
    mixed_precision: bool = True
    sharing: str = "hierarchical"

    def __post_init__(self) -> None:
        positive_ints = (
            "architecture_version",
            "token_dim",
            "global_latent_dim",
            "group_latent_dim",
            "private_latent_dim",
            "codec_width",
            "predictor_width",
            "predictor_layers",
            "predictor_members",
            "codec_epochs",
            "predictor_epochs",
            "batch_size",
            "inference_batch_size",
            "early_stopping_patience",
            "minimum_samples",
            "coordinate_width",
            "coordinate_layers",
            "coordinate_epochs",
            "coordinate_points_per_field",
            "coordinate_validation_points_per_field",
            "coordinate_query_batch_size",
        )
        for name in positive_ints:
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if int(self.fine_tune_epochs) < 0:
            raise ValueError("fine_tune_epochs must be non-negative")
        for name in (
            "learning_rate",
            "weight_decay",
            "gradient_clip_norm",
            "scale_floor",
            "applicability_loss_weight",
            "residual_gate_loss_weight",
            "coordinate_consistency_weight",
        ):
            value = float(getattr(self, name))
            if (
                not np.isfinite(value)
                or value < 0
                or (name != "weight_decay" and value == 0)
            ):
                raise ValueError(f"{name} must be finite and positive")
        if self.robust_loss_cap is not None:
            cap = float(self.robust_loss_cap)
            if not np.isfinite(cap) or cap <= 0:
                raise ValueError("robust_loss_cap must be finite and positive")
            object.__setattr__(self, "robust_loss_cap", cap)
        if not 0 < float(self.validation_fraction) < 0.5:
            raise ValueError("validation_fraction must be between zero and 0.5")
        if not 0 < float(self.bootstrap_fraction) <= 1:
            raise ValueError("bootstrap_fraction must be in (0, 1]")
        sharing = str(self.sharing).strip().lower()
        if sharing not in {"hierarchical", "independent"}:
            raise ValueError("sharing must be 'hierarchical' or 'independent'")
        object.__setattr__(self, "sharing", sharing)
        if self.coordinate_readout and int(self.architecture_version) < 2:
            raise ValueError(
                "coordinate_readout requires hierarchical CAE architecture_version >= 2"
            )
        for name in (
            "regime_head",
            "quality_weighted_loss",
            "shared_quality_isolation",
            "gated_private_residual",
            "coordinate_readout",
            "mixed_precision",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a bool")


@dataclass(frozen=True, slots=True)
class HierarchicalState:
    generation_index: int
    sample_count: int
    checkpoint_path: Path
    namespace_manifest_path: Path
    artifact_dir: Path
    bundle_path: Path
    strategy_signature: str
    state_signature: str
    run_namespace: str
    component_namespace: str
    parameter_names: tuple[str, ...]
    parameter_definition_signature: Mapping[str, object]
    schema: HierarchicalSchema | None
    quality_policy: RawDataQualityPolicy | None
    model: object | None
    train_cfg: CAETrainConfig
    device: object | None
    train_history: dict[str, object]


@dataclass(frozen=True, slots=True)
class CoordinatePrediction:
    """Typed, non-authoritative viewer/off-grid coordinate prediction."""

    field_selector: RawDataFieldSelector
    axis_coordinates: tuple[np.ndarray, ...]
    member_values: np.ndarray
    state_signature: str
    coordinate_contract: str = "yadof.hierarchical-cae-coordinate-readout-v1"
    authoritative_full_grid: bool = False
    calibrated: bool = False

    @property
    def mean_values(self) -> np.ndarray:
        return np.mean(self.member_values, axis=0, dtype=np.float64)


__all__ = [
    "AxisEncoding",
    "CAETrainConfig",
    "CoordinatePrediction",
    "FieldLayout",
    "FieldScaler",
    "HierarchicalSchema",
    "HierarchicalState",
    "NamedTrainingData",
    "Population",
]
