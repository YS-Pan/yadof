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

from ..quality import QualityAssessmentBatch
from .coordinates import (
    coordinate_feature_count,
    encode_coordinate_points,
    stored_coordinate_points,
)
from .types import CAETrainConfig, FieldLayout, HierarchicalSchema


MODEL_NAME = "hierarchical_cae_rawdata_predictor_ensemble"


def _activation() -> nn.Module:
    return nn.SiLU()


class _ScalarCodec(nn.Module):
    def __init__(
        self, token_dim: int, latent_dim: int, private_dim: int, width: int
    ) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(1, width),
            _activation(),
            nn.Linear(width, token_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, width),
            _activation(),
            nn.Linear(width, 1),
        )
        self.residual_decoder = nn.Sequential(
            nn.Linear(private_dim, width),
            _activation(),
            nn.Linear(width, 1),
        )

    def encode(self, values: torch.Tensor) -> torch.Tensor:
        return self.encoder(values.reshape(values.shape[0], 1))

    def decode(
        self,
        latent: torch.Tensor,
        private: torch.Tensor,
        residual_gate: torch.Tensor,
        gradient_weight: torch.Tensor | None = None,
    ) -> torch.Tensor:
        base = self.decoder(latent).reshape(latent.shape[0])
        if gradient_weight is not None:
            weight = gradient_weight.reshape(-1)
            base = base.detach() + weight * (base - base.detach())
        residual = self.residual_decoder(private).reshape(latent.shape[0])
        return base + residual_gate.reshape(-1) * residual


class _Conv1dCodec(nn.Module):
    def __init__(
        self,
        length: int,
        token_dim: int,
        latent_dim: int,
        private_dim: int,
        width: int,
    ) -> None:
        super().__init__()
        self.length = int(length)
        self.base_length = min(16, max(4, self.length))
        self.encoder_conv = nn.Sequential(
            nn.Conv1d(1, width, 7, stride=2, padding=3),
            nn.GroupNorm(1, width),
            _activation(),
            nn.Conv1d(width, width, 5, stride=2, padding=2),
            nn.GroupNorm(1, width),
            _activation(),
            nn.AdaptiveAvgPool1d(self.base_length),
        )
        self.encoder_head = nn.Linear(width * self.base_length, token_dim)
        self.decoder_head = nn.Linear(latent_dim, width * self.base_length)
        self.decoder_conv = nn.Sequential(
            nn.Conv1d(width, width, 5, padding=2),
            nn.GroupNorm(1, width),
            _activation(),
            nn.Conv1d(width, max(8, width // 2), 5, padding=2),
            _activation(),
            nn.Conv1d(max(8, width // 2), 1, 5, padding=2),
        )
        self.residual_head = nn.Linear(private_dim, width * self.base_length)
        self.residual_conv = nn.Sequential(
            nn.Conv1d(width, width, 5, padding=2),
            _activation(),
            nn.Conv1d(width, 1, 5, padding=2),
        )

    def encode(self, values: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder_conv(values.reshape(values.shape[0], 1, self.length))
        return self.encoder_head(encoded.flatten(1))

    def decode(
        self,
        latent: torch.Tensor,
        private: torch.Tensor,
        residual_gate: torch.Tensor,
        gradient_weight: torch.Tensor | None = None,
    ) -> torch.Tensor:
        hidden = self.decoder_head(latent).reshape(
            latent.shape[0], -1, self.base_length
        )
        hidden = F.interpolate(
            hidden, size=self.length, mode="linear", align_corners=True
        )
        base = self.decoder_conv(hidden).reshape(latent.shape[0], self.length)
        if gradient_weight is not None:
            weight = gradient_weight.reshape(-1, 1)
            base = base.detach() + weight * (base - base.detach())
        residual = self.residual_head(private).reshape(
            latent.shape[0], -1, self.base_length
        )
        residual = F.interpolate(
            residual, size=self.length, mode="linear", align_corners=True
        )
        residual = self.residual_conv(residual).reshape(
            latent.shape[0], self.length
        )
        return base + residual_gate.reshape(-1, 1) * residual


class _Conv2dCodec(nn.Module):
    def __init__(
        self,
        channels: int,
        spatial_shape: tuple[int, int],
        token_dim: int,
        latent_dim: int,
        private_dim: int,
        width: int,
    ) -> None:
        super().__init__()
        self.channels = int(channels)
        self.spatial_shape = tuple(int(value) for value in spatial_shape)
        self.base_shape = tuple(
            min(8, max(3, int(value))) for value in self.spatial_shape
        )
        self.encoder_conv = nn.Sequential(
            nn.Conv2d(self.channels, width, 5, stride=2, padding=2),
            nn.GroupNorm(1, width),
            _activation(),
            nn.Conv2d(width, width, 3, stride=2, padding=1),
            nn.GroupNorm(1, width),
            _activation(),
            nn.AdaptiveAvgPool2d(self.base_shape),
        )
        base_count = width * self.base_shape[0] * self.base_shape[1]
        self.encoder_head = nn.Linear(base_count, token_dim)
        self.decoder_head = nn.Linear(latent_dim, base_count)
        self.decoder_conv = nn.Sequential(
            nn.Conv2d(width, width, 3, padding=1),
            nn.GroupNorm(1, width),
            _activation(),
            nn.Conv2d(width, max(8, width // 2), 3, padding=1),
            _activation(),
            nn.Conv2d(max(8, width // 2), self.channels, 3, padding=1),
        )
        self.residual_head = nn.Linear(private_dim, base_count)
        self.residual_conv = nn.Sequential(
            nn.Conv2d(width, width, 3, padding=1),
            _activation(),
            nn.Conv2d(width, self.channels, 3, padding=1),
        )

    def encode(self, values: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder_conv(values)
        return self.encoder_head(encoded.flatten(1))

    def decode(
        self,
        latent: torch.Tensor,
        private: torch.Tensor,
        residual_gate: torch.Tensor,
        gradient_weight: torch.Tensor | None = None,
    ) -> torch.Tensor:
        hidden = self.decoder_head(latent).reshape(
            latent.shape[0], -1, self.base_shape[0], self.base_shape[1]
        )
        hidden = F.interpolate(
            hidden,
            size=self.spatial_shape,
            mode="bilinear",
            align_corners=True,
        )
        base = self.decoder_conv(hidden)
        if gradient_weight is not None:
            weight = gradient_weight.reshape(-1, 1, 1, 1)
            base = base.detach() + weight * (base - base.detach())
        residual = self.residual_head(private).reshape(
            latent.shape[0], -1, self.base_shape[0], self.base_shape[1]
        )
        residual = F.interpolate(
            residual,
            size=self.spatial_shape,
            mode="bilinear",
            align_corners=True,
        )
        residual = self.residual_conv(residual)
        return base + residual_gate.reshape(-1, 1, 1, 1) * residual


def _mlp(input_dim: int, output_dim: int, width: int, layers: int) -> nn.Module:
    modules: list[nn.Module] = []
    current = int(input_dim)
    for _ in range(max(1, int(layers))):
        modules.extend((nn.Linear(current, width), _activation()))
        current = int(width)
    modules.append(nn.Linear(current, output_dim))
    return nn.Sequential(*modules)


class _CoordinateReadout(nn.Module):
    """Field-local coordinate trunk with a gated private residual path."""

    def __init__(
        self,
        *,
        latent_dim: int,
        private_dim: int,
        coordinate_dim: int,
        width: int,
        layers: int,
    ) -> None:
        super().__init__()
        self.base = _mlp(
            latent_dim + coordinate_dim,
            1,
            width,
            layers,
        )
        self.private_residual = _mlp(
            private_dim + coordinate_dim,
            1,
            width,
            layers,
        )

    def forward(
        self,
        latent: torch.Tensor,
        private: torch.Tensor,
        encoded_coordinates: torch.Tensor,
        residual_gate: torch.Tensor,
    ) -> torch.Tensor:
        if encoded_coordinates.ndim != 2:
            raise ValueError("encoded coordinates must have shape [query, features]")
        batch_size = int(latent.shape[0])
        query_count = int(encoded_coordinates.shape[0])
        coordinates = encoded_coordinates.unsqueeze(0).expand(
            batch_size, query_count, -1
        )
        expanded_latent = latent.unsqueeze(1).expand(-1, query_count, -1)
        expanded_private = private.unsqueeze(1).expand(-1, query_count, -1)
        base = self.base(
            torch.cat((expanded_latent, coordinates), dim=2)
        ).squeeze(2)
        residual = self.private_residual(
            torch.cat((expanded_private, coordinates), dim=2)
        ).squeeze(2)
        return base + residual_gate.reshape(-1, 1) * residual


class ParameterLatentPredictor(nn.Module):
    """One independently initialized parameter-to-joint-latent function."""

    def __init__(self, input_dim: int, output_dim: int, cfg: CAETrainConfig) -> None:
        super().__init__()
        self.network = _mlp(
            input_dim,
            output_dim,
            cfg.predictor_width,
            cfg.predictor_layers,
        )

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return self.network(values - 0.5)


class HierarchicalCAEModel(nn.Module):
    """Shared field codecs plus global/group/private latent decomposition."""

    def __init__(
        self,
        input_dim: int,
        schema: HierarchicalSchema,
        cfg: CAETrainConfig,
    ) -> None:
        super().__init__()
        self.input_dim = int(input_dim)
        self.schema = schema
        self.cfg = cfg
        self.group_for_field = tuple(
            next(
                (
                    group_index
                    for group_index, group in enumerate(schema.groups)
                    if layout.selector in group
                ),
                None,
            )
            for layout in schema.layouts
        )
        if cfg.sharing == "hierarchical":
            self.global_slice = slice(0, cfg.global_latent_dim)
            cursor = cfg.global_latent_dim
            self.group_slices = []
            for _group in schema.groups:
                self.group_slices.append(
                    slice(cursor, cursor + cfg.group_latent_dim)
                )
                cursor += cfg.group_latent_dim
        else:
            self.global_slice = slice(0, 0)
            self.group_slices = []
            cursor = 0
        self.private_slices = []
        for _layout in schema.layouts:
            self.private_slices.append(
                slice(cursor, cursor + cfg.private_latent_dim)
            )
            cursor += cfg.private_latent_dim
        self.latent_dim = int(cursor)

        decoder_dims = [
            self.field_latent_dim(index) for index in range(len(schema.layouts))
        ]
        codecs = []
        for layout, decoder_dim in zip(schema.layouts, decoder_dims):
            if layout.codec_kind == "scalar-mlp":
                codecs.append(
                    _ScalarCodec(
                        cfg.token_dim,
                        decoder_dim,
                        cfg.private_latent_dim,
                        max(16, cfg.codec_width),
                    )
                )
            elif layout.codec_kind == "conv1d":
                codecs.append(
                    _Conv1dCodec(
                        layout.model_spatial_shape[0],
                        cfg.token_dim,
                        decoder_dim,
                        cfg.private_latent_dim,
                        cfg.codec_width,
                    )
                )
            elif layout.codec_kind == "conv2d":
                codecs.append(
                    _Conv2dCodec(
                        layout.model_channels,
                        (
                            int(layout.model_spatial_shape[0]),
                            int(layout.model_spatial_shape[1]),
                        ),
                        cfg.token_dim,
                        decoder_dim,
                        cfg.private_latent_dim,
                        cfg.codec_width,
                    )
                )
            else:
                raise ValueError(f"unsupported field codec {layout.codec_kind!r}")
        self.codecs = nn.ModuleList(codecs)

        if cfg.sharing == "hierarchical":
            token_width = len(schema.layouts) * cfg.token_dim + len(schema.layouts)
            self.global_teacher = _mlp(
                token_width,
                cfg.global_latent_dim,
                max(cfg.token_dim, cfg.global_latent_dim),
                1,
            )
            group_teachers = []
            for group in schema.groups:
                group_teachers.append(
                    _mlp(
                        len(group) * cfg.token_dim + len(group),
                        cfg.group_latent_dim,
                        max(cfg.token_dim, cfg.group_latent_dim),
                        1,
                    )
                )
            self.group_teachers = nn.ModuleList(group_teachers)
        else:
            self.global_teacher = nn.Identity()
            self.group_teachers = nn.ModuleList()
        self.private_teachers = nn.ModuleList(
            nn.Linear(cfg.token_dim, cfg.private_latent_dim)
            for _layout in schema.layouts
        )
        self.predictor_output_dim = self.latent_dim + (
            1 + len(schema.layouts) if cfg.regime_head else 0
        )
        self.predictors = nn.ModuleList(
            ParameterLatentPredictor(input_dim, self.predictor_output_dim, cfg)
            for _ in range(cfg.predictor_members)
        )
        self.coordinate_readouts = nn.ModuleList(
            _CoordinateReadout(
                latent_dim=self.field_latent_dim(field_index),
                private_dim=cfg.private_latent_dim,
                coordinate_dim=coordinate_feature_count(layout),
                width=cfg.coordinate_width,
                layers=cfg.coordinate_layers,
            )
            for field_index, layout in enumerate(schema.layouts)
        ) if cfg.coordinate_readout else nn.ModuleList()

    def field_latent_dim(self, field_index: int) -> int:
        if self.cfg.sharing == "independent":
            return self.cfg.private_latent_dim
        group_extra = (
            self.cfg.group_latent_dim
            if self.group_for_field[field_index] is not None
            else 0
        )
        return (
            self.cfg.global_latent_dim
            + group_extra
            + self.cfg.private_latent_dim
        )

    def _to_model_layout(
        self, field_index: int, values: torch.Tensor
    ) -> torch.Tensor:
        layout = self.schema.layouts[field_index]
        if layout.codec_kind == "scalar-mlp":
            return values.reshape(values.shape[0])
        if layout.codec_kind == "conv1d":
            return values.reshape(values.shape[0], 1, layout.shape[0])
        rank = len(layout.shape)
        if rank == 2:
            return values.reshape(values.shape[0], 1, *layout.shape)
        permutation = (0,) + tuple(index + 1 for index in layout.model_permutation)
        ordered = values.permute(permutation)
        return ordered.reshape(
            values.shape[0], layout.model_channels, *layout.model_spatial_shape
        )

    def _from_model_layout(
        self, field_index: int, values: torch.Tensor
    ) -> torch.Tensor:
        layout = self.schema.layouts[field_index]
        if layout.codec_kind == "scalar-mlp":
            return values.reshape(values.shape[0])
        if layout.codec_kind == "conv1d":
            return values.reshape(values.shape[0], *layout.shape)
        if len(layout.shape) == 2:
            return values.reshape(values.shape[0], *layout.shape)
        ordered_shape = tuple(
            layout.shape[index] for index in layout.model_permutation
        )
        ordered = values.reshape(values.shape[0], *ordered_shape)
        inverse = (0,) + tuple(
            index + 1 for index in layout.inverse_permutation
        )
        return ordered.permute(inverse).contiguous()

    def encode_fields(self, fields: Sequence[torch.Tensor]) -> tuple[torch.Tensor, ...]:
        if len(fields) != len(self.codecs):
            raise ValueError("one tensor is required per hierarchical CAE field")
        return tuple(
            codec.encode(self._to_model_layout(index, values))
            for index, (codec, values) in enumerate(zip(self.codecs, fields))
        )

    def teacher_latent_from_tokens(
        self,
        tokens: Sequence[torch.Tensor],
        shared_weights: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if shared_weights is None:
            shared_weights = torch.ones(
                (tokens[0].shape[0], len(tokens)),
                dtype=tokens[0].dtype,
                device=tokens[0].device,
            )
        if shared_weights.shape != (tokens[0].shape[0], len(tokens)):
            raise ValueError("shared field weights must have shape [batch, fields]")
        private = [
            teacher(token)
            for teacher, token in zip(self.private_teachers, tokens)
        ]
        if self.cfg.sharing == "independent":
            return torch.cat(private, dim=1)
        masked = [
            token * shared_weights[:, index : index + 1]
            for index, token in enumerate(tokens)
        ]
        global_latent = self.global_teacher(
            torch.cat([*masked, shared_weights], dim=1)
        )
        groups = []
        for teacher, group in zip(self.group_teachers, self.schema.groups):
            indices = [
                self.schema.field_selectors.index(selector) for selector in group
            ]
            selected = [masked[index] for index in indices]
            group_weights = shared_weights[:, indices]
            groups.append(teacher(torch.cat([*selected, group_weights], dim=1)))
        return torch.cat([global_latent, *groups, *private], dim=1)

    def teacher_latent(
        self,
        fields: Sequence[torch.Tensor],
        shared_weights: torch.Tensor | None = None,
    ) -> torch.Tensor:
        return self.teacher_latent_from_tokens(
            self.encode_fields(fields), shared_weights
        )

    def field_latent(
        self, joint_latent: torch.Tensor, field_index: int
    ) -> torch.Tensor:
        pieces = []
        if self.cfg.sharing == "hierarchical":
            pieces.append(joint_latent[:, self.global_slice])
            group_index = self.group_for_field[field_index]
            if group_index is not None:
                pieces.append(joint_latent[:, self.group_slices[group_index]])
        pieces.append(joint_latent[:, self.private_slices[field_index]])
        return torch.cat(pieces, dim=1)

    def decode_joint(
        self,
        joint_latent: torch.Tensor,
        residual_gates: torch.Tensor | None = None,
        gradient_weights: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, ...]:
        batch_size = joint_latent.shape[0]
        field_count = len(self.codecs)
        if residual_gates is None:
            residual_gates = torch.zeros(
                (batch_size, field_count),
                dtype=joint_latent.dtype,
                device=joint_latent.device,
            )
        if residual_gates.shape != (batch_size, field_count):
            raise ValueError("residual gates must have shape [batch, fields]")
        if gradient_weights is not None and gradient_weights.shape != (
            batch_size,
            field_count,
        ):
            raise ValueError("gradient weights must have shape [batch, fields]")
        return tuple(
            self._from_model_layout(
                field_index,
                codec.decode(
                    self.field_latent(joint_latent, field_index),
                    joint_latent[:, self.private_slices[field_index]],
                    residual_gates[:, field_index],
                    (
                        None
                        if gradient_weights is None
                        else gradient_weights[:, field_index]
                    ),
                ),
            )
            for field_index, codec in enumerate(self.codecs)
        )

    def autoencode(
        self,
        fields: Sequence[torch.Tensor],
        *,
        shared_weights: torch.Tensor | None = None,
        residual_targets: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, ...]:
        return self.decode_joint(
            self.teacher_latent(fields, shared_weights),
            residual_targets,
            shared_weights,
        )

    def split_predictor_output(
        self, output: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        latent = output[:, : self.latent_dim]
        if not self.cfg.regime_head:
            applicability = torch.full(
                (output.shape[0],),
                20.0,
                dtype=output.dtype,
                device=output.device,
            )
            residual_logits = torch.full(
                (output.shape[0], len(self.codecs)),
                -20.0,
                dtype=output.dtype,
                device=output.device,
            )
            return latent, applicability, residual_logits
        applicability = output[:, self.latent_dim]
        residual_logits = output[:, self.latent_dim + 1 :]
        return latent, applicability, residual_logits

    def predictor_output(
        self, member_index: int, parameters: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.split_predictor_output(
            self.predictors[int(member_index)](parameters)
        )

    def predict_member(
        self, member_index: int, parameters: torch.Tensor
    ) -> tuple[tuple[torch.Tensor, ...], torch.Tensor, torch.Tensor]:
        latent, applicability_logit, residual_logits = self.predictor_output(
            member_index, parameters
        )
        residual_gates = (
            torch.sigmoid(residual_logits)
            if self.cfg.regime_head and self.cfg.gated_private_residual
            else torch.zeros_like(residual_logits)
        )
        return (
            self.decode_joint(latent, residual_gates),
            applicability_logit,
            residual_logits,
        )

    def decode_coordinates(
        self,
        joint_latent: torch.Tensor,
        residual_gates: torch.Tensor,
        *,
        field_index: int,
        encoded_coordinates: torch.Tensor,
    ) -> torch.Tensor:
        if not self.cfg.coordinate_readout or not self.coordinate_readouts:
            raise RuntimeError(
                "this hierarchical CAE checkpoint has no coordinate readout"
            )
        index = int(field_index)
        if not 0 <= index < len(self.schema.layouts):
            raise IndexError(index)
        return self.coordinate_readouts[index](
            self.field_latent(joint_latent, index),
            joint_latent[:, self.private_slices[index]],
            encoded_coordinates,
            residual_gates[:, index],
        )


def design_field_losses(
    predictions: Sequence[torch.Tensor],
    targets: Sequence[torch.Tensor],
    *,
    beta: float = 1.0,
) -> torch.Tensor:
    if len(predictions) != len(targets) or not predictions:
        raise ValueError("field-macro loss requires aligned non-empty field lists")
    losses = [
        F.smooth_l1_loss(
            prediction, target, beta=float(beta), reduction="none"
        )
        .reshape(prediction.shape[0], -1)
        .mean(dim=1)
        for prediction, target in zip(predictions, targets)
    ]
    return torch.stack(losses, dim=1)


def field_macro_loss(
    predictions: Sequence[torch.Tensor],
    targets: Sequence[torch.Tensor],
    *,
    field_weights: torch.Tensor | None = None,
    loss_cap: float | None = None,
    beta: float = 1.0,
) -> torch.Tensor:
    """Robust design-by-field aggregation; grids never receive point-count weight."""

    losses = design_field_losses(predictions, targets, beta=beta)
    if loss_cap is not None:
        losses = torch.clamp(losses, max=float(loss_cap))
    if field_weights is None:
        return losses.mean()
    weights = field_weights.to(dtype=losses.dtype, device=losses.device)
    if weights.shape != losses.shape:
        raise ValueError("field weights must align with design-by-field losses")
    denominator = torch.clamp(weights.sum(), min=torch.finfo(losses.dtype).eps)
    return torch.sum(losses * weights) / denominator


def design_level_split(
    parameters: np.ndarray,
    *,
    validation_fraction: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Row-order-independent split; duplicate designs never cross partitions."""

    matrix = np.ascontiguousarray(parameters, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("design-level split expects X[N,D]")
    identities = [hashlib.sha256(row.tobytes(order="C")).digest() for row in matrix]
    unique: dict[bytes, int] = {}
    for index, identity in enumerate(identities):
        unique.setdefault(identity, index)
    if len(unique) < 2:
        raise ValueError("hierarchical CAE training requires at least two unique designs")
    seed_bytes = int(seed).to_bytes(8, "big", signed=True)
    ordered = sorted(
        unique.items(), key=lambda item: hashlib.sha256(seed_bytes + item[0]).digest()
    )
    validation_count = max(
        1,
        min(
            len(ordered) - 1,
            int(round(len(ordered) * float(validation_fraction))),
        ),
    )
    validation_ids = {identity for identity, _index in ordered[:validation_count]}
    train = [index for index, identity in enumerate(identities) if identity not in validation_ids]
    validation = [index for index, identity in enumerate(identities) if identity in validation_ids]
    return np.asarray(train, dtype=np.int64), np.asarray(validation, dtype=np.int64)


def unique_design_indices(parameters: np.ndarray) -> np.ndarray:
    matrix = np.ascontiguousarray(parameters, dtype=np.float64)
    seen: set[bytes] = set()
    output = []
    for index, row in enumerate(matrix):
        digest = hashlib.sha256(row.tobytes(order="C")).digest()
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
        yield ordered[start : start + max(1, int(batch_size))]


def _field_batch(
    fields: Sequence[np.ndarray], indices: np.ndarray, device: torch.device
) -> tuple[torch.Tensor, ...]:
    return tuple(
        torch.as_tensor(values[indices], dtype=torch.float32, device=device)
        for values in fields
    )


def _quality_batch(
    quality: QualityAssessmentBatch,
    indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    rows = np.asarray(indices, dtype=np.int64)
    field_weights = (
        quality.field_weights[rows]
        if cfg.quality_weighted_loss
        else np.ones_like(quality.field_weights[rows])
    )
    shared_weights = (
        quality.shared_weights[rows]
        if cfg.shared_quality_isolation
        else np.ones_like(quality.shared_weights[rows])
    )
    residual_targets = (
        quality.residual_targets[rows]
        if cfg.gated_private_residual
        else np.zeros_like(quality.residual_targets[rows])
    )
    return (
        torch.as_tensor(
            field_weights, dtype=torch.float32, device=device
        ),
        torch.as_tensor(
            shared_weights, dtype=torch.float32, device=device
        ),
        torch.as_tensor(
            residual_targets, dtype=torch.float32, device=device
        ),
        torch.as_tensor(
            quality.applicability_targets[rows],
            dtype=torch.float32,
            device=device,
        ),
    )


def _autocast(device: torch.device, enabled: bool):
    if not enabled or device.type != "cuda":
        return nullcontext()
    return torch.autocast(device_type="cuda", dtype=torch.float16)


def _make_grad_scaler(device: torch.device, enabled: bool):
    return torch.amp.GradScaler(
        device.type,
        enabled=bool(enabled and device.type == "cuda"),
    )


def _state_copy(module: nn.Module) -> dict[str, torch.Tensor]:
    return {
        name: value.detach().cpu().clone()
        for name, value in module.state_dict().items()
    }


def _mean_loss(values: list[float]) -> float:
    return float(np.mean(values, dtype=np.float64)) if values else math.inf


@torch.no_grad()
def _codec_validation_loss(
    model: HierarchicalCAEModel,
    fields: Sequence[np.ndarray],
    quality: QualityAssessmentBatch,
    indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
) -> float:
    model.eval()
    losses = []
    for batch in _batch_indices(indices, cfg.batch_size):
        targets = _field_batch(fields, batch, device)
        field_weights, shared_weights, residual_targets, _applicability = (
            _quality_batch(quality, batch, device, cfg)
        )
        with _autocast(device, cfg.mixed_precision):
            loss = field_macro_loss(
                model.autoencode(
                    targets,
                    shared_weights=shared_weights,
                    residual_targets=residual_targets,
                ),
                targets,
                field_weights=field_weights,
                loss_cap=cfg.robust_loss_cap,
            )
        losses.append(float(loss.detach().cpu()))
    return _mean_loss(losses)


def _train_codecs(
    model: HierarchicalCAEModel,
    fields: Sequence[np.ndarray],
    quality: QualityAssessmentBatch,
    train_indices: np.ndarray,
    validation_indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
    seed: int,
) -> dict[str, object]:
    parameters = [
        parameter
        for name, parameter in model.named_parameters()
        if not name.startswith("predictors.")
    ]
    optimizer = torch.optim.AdamW(
        parameters, lr=cfg.learning_rate, weight_decay=cfg.weight_decay
    )
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
            field_weights, shared_weights, residual_targets, _applicability = (
                _quality_batch(quality, batch, device, cfg)
            )
            optimizer.zero_grad(set_to_none=True)
            with _autocast(device, cfg.mixed_precision):
                loss = field_macro_loss(
                    model.autoencode(
                        targets,
                        shared_weights=shared_weights,
                        residual_targets=residual_targets,
                    ),
                    targets,
                    field_weights=field_weights,
                    loss_cap=cfg.robust_loss_cap,
                )
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(parameters, cfg.gradient_clip_norm)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))
        validation = _codec_validation_loss(
            model, fields, quality, validation_indices, device, cfg
        )
        history.append(
            {
                "epoch": epoch + 1,
                "training_field_macro_loss": _mean_loss(losses),
                "validation_field_macro_loss": validation,
            }
        )
        if not math.isfinite(best_loss) or validation < best_loss - max(
            1.0e-7, abs(best_loss) * 1.0e-5
        ):
            best_loss = validation
            best_state = _state_copy(model)
            patience = 0
        else:
            patience += 1
            if patience >= cfg.early_stopping_patience:
                break
    model.load_state_dict(best_state)
    return {
        "epochs_completed": len(history),
        "best_validation_field_macro_loss": best_loss,
        "wall_sec": time.perf_counter() - started,
        "history": history,
    }


@torch.no_grad()
def _teacher_latents(
    model: HierarchicalCAEModel,
    fields: Sequence[np.ndarray],
    quality: QualityAssessmentBatch,
    device: torch.device,
    cfg: CAETrainConfig,
) -> np.ndarray:
    model.eval()
    rows = []
    indices = np.arange(fields[0].shape[0], dtype=np.int64)
    for batch in _batch_indices(indices, cfg.batch_size):
        tensors = _field_batch(fields, batch, device)
        _field_weights, shared_weights, _residual, _applicability = (
            _quality_batch(quality, batch, device, cfg)
        )
        latent = model.teacher_latent(tensors, shared_weights)
        rows.append(latent.detach().float().cpu().numpy())
    return np.ascontiguousarray(np.concatenate(rows, axis=0), dtype=np.float32)


@torch.no_grad()
def _predictor_validation_loss(
    model: HierarchicalCAEModel,
    predictor: ParameterLatentPredictor,
    parameters: np.ndarray,
    latents: np.ndarray,
    quality: QualityAssessmentBatch,
    indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
) -> float:
    predictor.eval()
    losses = []
    for batch in _batch_indices(indices, cfg.batch_size):
        x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
        target = torch.as_tensor(latents[batch], dtype=torch.float32, device=device)
        _field_weights, _shared_weights, residual_targets, applicability = (
            _quality_batch(quality, batch, device, cfg)
        )
        with _autocast(device, cfg.mixed_precision):
            predicted_latent, applicability_logit, residual_logits = (
                model.split_predictor_output(predictor(x))
            )
            loss = F.smooth_l1_loss(predicted_latent, target, beta=1.0)
            if cfg.regime_head:
                loss = loss + cfg.applicability_loss_weight * F.binary_cross_entropy_with_logits(
                    applicability_logit, applicability
                )
                if cfg.gated_private_residual:
                    loss = loss + cfg.residual_gate_loss_weight * F.binary_cross_entropy_with_logits(
                        residual_logits, residual_targets
                    )
        losses.append(float(loss.detach().cpu()))
    return _mean_loss(losses)


def _train_predictors(
    model: HierarchicalCAEModel,
    parameters: np.ndarray,
    latents: np.ndarray,
    quality: QualityAssessmentBatch,
    train_indices: np.ndarray,
    validation_indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
    seed: int,
) -> dict[str, object]:
    member_histories = []
    started = time.perf_counter()
    for member_index, predictor in enumerate(model.predictors):
        rng = np.random.default_rng(int(seed) + 104729 * (member_index + 1))
        bootstrap_count = max(
            2, int(math.ceil(len(train_indices) * cfg.bootstrap_fraction))
        )
        bootstrap = rng.choice(
            train_indices,
            size=bootstrap_count,
            replace=True,
        )
        optimizer = torch.optim.AdamW(
            predictor.parameters(),
            lr=cfg.learning_rate,
            weight_decay=cfg.weight_decay,
        )
        scaler = _make_grad_scaler(device, cfg.mixed_precision)
        best_loss = math.inf
        best_state = _state_copy(predictor)
        patience = 0
        history = []
        for epoch in range(cfg.predictor_epochs):
            predictor.train()
            losses = []
            for batch in _batch_indices(bootstrap, cfg.batch_size, rng):
                x = torch.as_tensor(
                    parameters[batch], dtype=torch.float32, device=device
                )
                target = torch.as_tensor(
                    latents[batch], dtype=torch.float32, device=device
                )
                _field_weights, _shared_weights, residual_targets, applicability = (
                    _quality_batch(quality, batch, device, cfg)
                )
                optimizer.zero_grad(set_to_none=True)
                with _autocast(device, cfg.mixed_precision):
                    predicted_latent, applicability_logit, residual_logits = (
                        model.split_predictor_output(predictor(x))
                    )
                    loss = F.smooth_l1_loss(
                        predicted_latent, target, beta=1.0
                    )
                    if cfg.regime_head:
                        loss = loss + cfg.applicability_loss_weight * F.binary_cross_entropy_with_logits(
                            applicability_logit, applicability
                        )
                        if cfg.gated_private_residual:
                            loss = loss + cfg.residual_gate_loss_weight * F.binary_cross_entropy_with_logits(
                                residual_logits, residual_targets
                            )
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(
                    predictor.parameters(), cfg.gradient_clip_norm
                )
                scaler.step(optimizer)
                scaler.update()
                losses.append(float(loss.detach().cpu()))
            validation = _predictor_validation_loss(
                model,
                predictor,
                parameters,
                latents,
                quality,
                validation_indices,
                device,
                cfg,
            )
            history.append(
                {
                    "epoch": epoch + 1,
                    "training_latent_loss": _mean_loss(losses),
                    "validation_latent_loss": validation,
                }
            )
            if not math.isfinite(best_loss) or validation < best_loss - max(
                1.0e-7, abs(best_loss) * 1.0e-5
            ):
                best_loss = validation
                best_state = _state_copy(predictor)
                patience = 0
            else:
                patience += 1
                if patience >= cfg.early_stopping_patience:
                    break
        predictor.load_state_dict(best_state)
        member_histories.append(
            {
                "member_index": member_index,
                "bootstrap_design_count": bootstrap_count,
                "epochs_completed": len(history),
                "best_validation_latent_loss": best_loss,
                "history": history,
            }
        )
    return {
        "wall_sec": time.perf_counter() - started,
        "members": member_histories,
    }


@torch.no_grad()
def _predicted_grid_validation_loss(
    model: HierarchicalCAEModel,
    parameters: np.ndarray,
    fields: Sequence[np.ndarray],
    quality: QualityAssessmentBatch,
    indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
) -> float:
    model.eval()
    losses = []
    for batch in _batch_indices(indices, cfg.batch_size):
        x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
        targets = _field_batch(fields, batch, device)
        field_weights, _shared_weights, _residual_targets, _applicability = (
            _quality_batch(quality, batch, device, cfg)
        )
        predictions_by_member = [
            model.predict_member(member_index, x)[0]
            for member_index in range(len(model.predictors))
        ]
        means = tuple(
            torch.stack(
                [member[field_index] for member in predictions_by_member], dim=0
            ).mean(dim=0)
            for field_index in range(len(fields))
        )
        losses.append(
            float(
                field_macro_loss(
                    means,
                    targets,
                    field_weights=field_weights,
                    loss_cap=cfg.robust_loss_cap,
                )
                .detach()
                .cpu()
            )
        )
    return _mean_loss(losses)


def _fine_tune_gate(
    model: HierarchicalCAEModel,
    parameters: np.ndarray,
    fields: Sequence[np.ndarray],
    quality: QualityAssessmentBatch,
    train_indices: np.ndarray,
    validation_indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
    seed: int,
) -> dict[str, object]:
    baseline = _predicted_grid_validation_loss(
        model, parameters, fields, quality, validation_indices, device, cfg
    )
    if cfg.fine_tune_epochs <= 0:
        return {
            "attempted": False,
            "accepted": False,
            "baseline_validation_field_macro_loss": baseline,
            "candidate_validation_field_macro_loss": baseline,
            "wall_sec": 0.0,
        }
    original = _state_copy(model)
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    for codec in model.codecs:
        for parameter in codec.encoder_conv.parameters() if hasattr(codec, "encoder_conv") else ():
            parameter.requires_grad_(False)
        for parameter in codec.encoder.parameters() if hasattr(codec, "encoder") else ():
            parameter.requires_grad_(False)
    for module in [model.global_teacher, model.group_teachers, model.private_teachers]:
        for parameter in module.parameters():
            parameter.requires_grad_(False)
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(
        trainable,
        lr=cfg.learning_rate * 0.2,
        weight_decay=cfg.weight_decay,
    )
    scaler = _make_grad_scaler(device, cfg.mixed_precision)
    rng = np.random.default_rng(int(seed) + 99991)
    started = time.perf_counter()
    for _epoch in range(cfg.fine_tune_epochs):
        model.train()
        for batch in _batch_indices(train_indices, cfg.batch_size, rng):
            x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
            targets = _field_batch(fields, batch, device)
            field_weights, _shared_weights, residual_targets, applicability = (
                _quality_batch(quality, batch, device, cfg)
            )
            member_index = int(rng.integers(0, len(model.predictors)))
            optimizer.zero_grad(set_to_none=True)
            with _autocast(device, cfg.mixed_precision):
                predictions, applicability_logit, residual_logits = (
                    model.predict_member(member_index, x)
                )
                loss = field_macro_loss(
                    predictions,
                    targets,
                    field_weights=field_weights,
                    loss_cap=cfg.robust_loss_cap,
                )
                if cfg.regime_head:
                    loss = loss + cfg.applicability_loss_weight * F.binary_cross_entropy_with_logits(
                        applicability_logit, applicability
                    )
                    if cfg.gated_private_residual:
                        loss = loss + cfg.residual_gate_loss_weight * F.binary_cross_entropy_with_logits(
                            residual_logits, residual_targets
                        )
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(trainable, cfg.gradient_clip_norm)
            scaler.step(optimizer)
            scaler.update()
    candidate = _predicted_grid_validation_loss(
        model, parameters, fields, quality, validation_indices, device, cfg
    )
    accepted = bool(candidate <= baseline * (1.0 - 1.0e-3))
    if not accepted:
        model.load_state_dict(original)
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    return {
        "attempted": True,
        "accepted": accepted,
        "baseline_validation_field_macro_loss": baseline,
        "candidate_validation_field_macro_loss": candidate,
        "wall_sec": time.perf_counter() - started,
    }


def _coordinate_point_indices(
    layout: FieldLayout,
    limit: int,
    *,
    rng: np.random.Generator | None,
) -> np.ndarray:
    count = int(layout.point_count)
    selected = min(count, max(1, int(limit)))
    if selected == count:
        return np.arange(count, dtype=np.int64)
    if rng is not None:
        return np.sort(rng.choice(count, size=selected, replace=False)).astype(
            np.int64,
            copy=False,
        )
    return np.unique(
        np.linspace(0, count - 1, num=selected, dtype=np.int64)
    )


def _coordinate_tensors(
    layout: FieldLayout,
    point_indices: np.ndarray,
    device: torch.device,
) -> torch.Tensor:
    physical = stored_coordinate_points(layout)[point_indices]
    encoded = encode_coordinate_points(layout, physical)
    return torch.as_tensor(encoded, dtype=torch.float32, device=device)


@torch.no_grad()
def _coordinate_validation_loss(
    model: HierarchicalCAEModel,
    parameters: np.ndarray,
    fields: Sequence[np.ndarray],
    quality: QualityAssessmentBatch,
    indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
) -> dict[str, object]:
    model.eval()
    point_indices = tuple(
        _coordinate_point_indices(
            layout,
            cfg.coordinate_validation_points_per_field,
            rng=None,
        )
        for layout in model.schema.layouts
    )
    coordinate_tensors = tuple(
        _coordinate_tensors(layout, selected, device)
        for layout, selected in zip(model.schema.layouts, point_indices)
    )
    target_numerator = 0.0
    consistency_numerator = 0.0
    denominator = 0.0
    for batch in _batch_indices(indices, cfg.batch_size):
        x = torch.as_tensor(parameters[batch], dtype=torch.float32, device=device)
        targets = _field_batch(fields, batch, device)
        field_weights, _shared, _residual, _applicability = _quality_batch(
            quality, batch, device, cfg
        )
        for member_index in range(len(model.predictors)):
            latent, _applicability_logit, residual_logits = model.predictor_output(
                member_index, x
            )
            residual_gates = (
                torch.sigmoid(residual_logits)
                if cfg.regime_head and cfg.gated_private_residual
                else torch.zeros_like(residual_logits)
            )
            grids = model.decode_joint(latent, residual_gates)
            for field_index, selected in enumerate(point_indices):
                predicted = model.decode_coordinates(
                    latent,
                    residual_gates,
                    field_index=field_index,
                    encoded_coordinates=coordinate_tensors[field_index],
                )
                target = targets[field_index].reshape(len(batch), -1)[:, selected]
                grid = grids[field_index].reshape(len(batch), -1)[:, selected]
                target_loss = F.smooth_l1_loss(
                    predicted, target, beta=1.0, reduction="none"
                ).mean(dim=1)
                consistency_loss = F.smooth_l1_loss(
                    predicted, grid, beta=1.0, reduction="none"
                ).mean(dim=1)
                weights = field_weights[:, field_index]
                target_numerator += float(torch.sum(target_loss * weights).cpu())
                consistency_numerator += float(
                    torch.sum(consistency_loss * weights).cpu()
                )
                denominator += float(torch.sum(weights).cpu())
    denominator = max(denominator, np.finfo(np.float64).eps)
    target_loss = target_numerator / denominator
    consistency_loss = consistency_numerator / denominator
    return {
        "target_field_macro_loss": float(target_loss),
        "grid_consistency_field_macro_loss": float(consistency_loss),
        "combined_loss": float(
            target_loss + cfg.coordinate_consistency_weight * consistency_loss
        ),
        "sampled_stored_points_per_field": [
            int(len(values)) for values in point_indices
        ],
        "member_count": len(model.predictors),
    }


def _train_coordinate_readouts(
    model: HierarchicalCAEModel,
    parameters: np.ndarray,
    fields: Sequence[np.ndarray],
    quality: QualityAssessmentBatch,
    train_indices: np.ndarray,
    validation_indices: np.ndarray,
    device: torch.device,
    cfg: CAETrainConfig,
    seed: int,
) -> dict[str, object]:
    if not cfg.coordinate_readout:
        return {
            "enabled": False,
            "status": "not-configured",
            "wall_sec": 0.0,
        }
    if not model.coordinate_readouts:
        raise RuntimeError("coordinate readout configuration/model mismatch")
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    coordinate_parameters = [
        parameter
        for module in model.coordinate_readouts
        for parameter in module.parameters()
    ]
    for parameter in coordinate_parameters:
        parameter.requires_grad_(True)
    optimizer = torch.optim.AdamW(
        coordinate_parameters,
        lr=cfg.learning_rate,
        weight_decay=cfg.weight_decay,
    )
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
            x = torch.as_tensor(
                parameters[batch], dtype=torch.float32, device=device
            )
            targets = _field_batch(fields, batch, device)
            field_weights, _shared, _residual, _applicability = _quality_batch(
                quality, batch, device, cfg
            )
            member_index = int(rng.integers(0, len(model.predictors)))
            with torch.no_grad():
                latent, _applicability_logit, residual_logits = (
                    model.predictor_output(member_index, x)
                )
                residual_gates = (
                    torch.sigmoid(residual_logits)
                    if cfg.regime_head and cfg.gated_private_residual
                    else torch.zeros_like(residual_logits)
                )
                grids = model.decode_joint(latent, residual_gates)
            optimizer.zero_grad(set_to_none=True)
            target_numerator = torch.zeros((), dtype=torch.float32, device=device)
            consistency_numerator = torch.zeros(
                (), dtype=torch.float32, device=device
            )
            denominator = torch.zeros((), dtype=torch.float32, device=device)
            with _autocast(device, cfg.mixed_precision):
                for field_index, layout in enumerate(model.schema.layouts):
                    selected = _coordinate_point_indices(
                        layout,
                        cfg.coordinate_points_per_field,
                        rng=rng,
                    )
                    encoded = _coordinate_tensors(layout, selected, device)
                    predicted = model.decode_coordinates(
                        latent,
                        residual_gates,
                        field_index=field_index,
                        encoded_coordinates=encoded,
                    )
                    target = targets[field_index].reshape(len(batch), -1)[
                        :, selected
                    ]
                    grid = grids[field_index].reshape(len(batch), -1)[:, selected]
                    target_loss = F.smooth_l1_loss(
                        predicted, target, beta=1.0, reduction="none"
                    ).mean(dim=1)
                    consistency_loss = F.smooth_l1_loss(
                        predicted, grid, beta=1.0, reduction="none"
                    ).mean(dim=1)
                    weights = field_weights[:, field_index]
                    target_numerator = target_numerator + torch.sum(
                        target_loss * weights
                    )
                    consistency_numerator = consistency_numerator + torch.sum(
                        consistency_loss * weights
                    )
                    denominator = denominator + torch.sum(weights)
                safe_denominator = torch.clamp(
                    denominator, min=torch.finfo(torch.float32).eps
                )
                loss = (
                    target_numerator
                    + cfg.coordinate_consistency_weight * consistency_numerator
                ) / safe_denominator
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(
                coordinate_parameters, cfg.gradient_clip_norm
            )
            scaler.step(optimizer)
            scaler.update()
            epoch_losses.append(float(loss.detach().cpu()))
        validation = _coordinate_validation_loss(
            model,
            parameters,
            fields,
            quality,
            validation_indices,
            device,
            cfg,
        )
        history.append(
            {
                "epoch": epoch + 1,
                "training_combined_loss": _mean_loss(epoch_losses),
                "validation": validation,
            }
        )
        candidate = float(validation["combined_loss"])
        if not math.isfinite(best_loss) or candidate < best_loss - max(
            1.0e-7, abs(best_loss) * 1.0e-5
        ):
            best_loss = candidate
            best_state = _state_copy(model.coordinate_readouts)
            patience = 0
        else:
            patience += 1
            if patience >= cfg.early_stopping_patience:
                break
    model.coordinate_readouts.load_state_dict(best_state)
    final_validation = _coordinate_validation_loss(
        model,
        parameters,
        fields,
        quality,
        validation_indices,
        device,
        cfg,
    )
    for parameter in model.parameters():
        parameter.requires_grad_(True)
    return {
        "enabled": True,
        "status": "experimental-performance-not-accepted",
        "epochs_completed": len(history),
        "best_validation_combined_loss": float(best_loss),
        "final_validation": final_validation,
        "coordinate_parameter_count": int(
            sum(parameter.numel() for parameter in coordinate_parameters)
        ),
        "authority": "viewer/off-grid-only; full-grid decoder remains authoritative",
        "history": history,
        "wall_sec": time.perf_counter() - started,
    }


def fit_hierarchical_cae(
    *,
    input_dim: int,
    schema: HierarchicalSchema,
    parameters: np.ndarray,
    standardized_fields: Sequence[np.ndarray],
    quality: QualityAssessmentBatch,
    device: torch.device,
    train_cfg: CAETrainConfig,
    seed: int,
    train_indices: np.ndarray | None = None,
    validation_indices: np.ndarray | None = None,
) -> tuple[HierarchicalCAEModel, dict[str, object]]:
    x = np.ascontiguousarray(parameters, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != int(input_dim):
        raise ValueError(f"expected parameter matrix [N,{int(input_dim)}]")
    if any(values.shape[0] != x.shape[0] for values in standardized_fields):
        raise ValueError("every hierarchical CAE field must align with parameter rows")
    expected_quality_shape = (x.shape[0], len(schema.layouts))
    if quality.field_weights.shape != expected_quality_shape:
        raise ValueError("quality assessment does not align with design/field rows")
    if train_indices is None or validation_indices is None:
        train_indices, validation_indices = design_level_split(
            x,
            validation_fraction=train_cfg.validation_fraction,
            seed=int(seed),
        )
    train_indices = np.asarray(train_indices, dtype=np.int64)
    validation_indices = np.asarray(validation_indices, dtype=np.int64)
    if set(train_indices.tolist()).intersection(validation_indices.tolist()):
        raise ValueError("training and validation design rows must be disjoint")
    if not len(train_indices) or not len(validation_indices):
        raise ValueError("training and validation partitions must both be non-empty")

    torch.manual_seed(int(seed))
    if device.type == "cuda":
        torch.cuda.manual_seed_all(int(seed))
        torch.cuda.reset_peak_memory_stats(device)
    model = HierarchicalCAEModel(input_dim, schema, train_cfg).to(device)
    started = time.perf_counter()
    codec = _train_codecs(
        model,
        standardized_fields,
        quality,
        train_indices,
        validation_indices,
        device,
        train_cfg,
        int(seed),
    )
    latents = _teacher_latents(
        model, standardized_fields, quality, device, train_cfg
    )
    predictors = _train_predictors(
        model,
        x,
        latents,
        quality,
        train_indices,
        validation_indices,
        device,
        train_cfg,
        int(seed),
    )
    fine_tune = _fine_tune_gate(
        model,
        x,
        standardized_fields,
        quality,
        train_indices,
        validation_indices,
        device,
        train_cfg,
        int(seed),
    )
    coordinate = _train_coordinate_readouts(
        model,
        x,
        standardized_fields,
        quality,
        train_indices,
        validation_indices,
        device,
        train_cfg,
        int(seed),
    )
    model.eval()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    group_parameter_count = sum(
        parameter.numel() for module in model.group_teachers for parameter in module.parameters()
    )
    history = {
        "model": MODEL_NAME,
        "architecture_version": train_cfg.architecture_version,
        "training_policy": "design-split-field-macro-hierarchical-latent",
        "member_count": len(model.predictors),
        "train_design_count": int(len(train_indices)),
        "validation_design_count": int(len(validation_indices)),
        "field_count": len(schema.layouts),
        "parameter_count": int(parameter_count),
        "group_parameter_count": int(group_parameter_count),
        "group_count": len(schema.groups),
        "sharing": train_cfg.sharing,
        "device": str(device),
        "torch_version": str(torch.__version__),
        "codec_stage": codec,
        "predictor_stage": predictors,
        "fine_tune_gate": fine_tune,
        "coordinate_readout_stage": coordinate,
        "quality_assessment": quality.diagnostics(),
        "total_wall_sec": time.perf_counter() - started,
        "peak_vram_bytes": (
            int(torch.cuda.max_memory_allocated(device))
            if device.type == "cuda"
            else 0
        ),
    }
    return model, history


@torch.no_grad()
def predict_hierarchical_members(
    *,
    model: HierarchicalCAEModel,
    parameters: np.ndarray,
    device: torch.device,
    batch_size: int,
) -> tuple[tuple[np.ndarray, ...], np.ndarray, np.ndarray]:
    x = np.ascontiguousarray(parameters, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != model.input_dim:
        raise ValueError(
            f"expected normalized parameter matrix [N,{model.input_dim}]"
        )
    per_field: list[list[np.ndarray]] = [list() for _ in model.schema.layouts]
    applicability_chunks: list[np.ndarray] = []
    residual_chunks: list[np.ndarray] = []
    model.eval()
    for start in range(0, len(x), max(1, int(batch_size))):
        batch = torch.as_tensor(
            x[start : start + max(1, int(batch_size))],
            dtype=torch.float32,
            device=device,
        )
        member_outputs = [
            model.predict_member(member_index, batch)
            for member_index in range(len(model.predictors))
        ]
        for field_index in range(len(per_field)):
            stacked = torch.stack(
                [values[0][field_index] for values in member_outputs], dim=0
            )
            per_field[field_index].append(stacked.float().cpu().numpy())
        applicability_chunks.append(
            torch.stack(
                [torch.sigmoid(values[1]) for values in member_outputs], dim=0
            )
            .float()
            .cpu()
            .numpy()
        )
        residual_chunks.append(
            torch.stack(
                [torch.sigmoid(values[2]) for values in member_outputs], dim=0
            )
            .float()
            .cpu()
            .numpy()
        )
    return (
        tuple(
            np.ascontiguousarray(np.concatenate(chunks, axis=1), dtype=np.float32)
            for chunks in per_field
        ),
        np.ascontiguousarray(
            np.concatenate(applicability_chunks, axis=1), dtype=np.float32
        ),
        np.ascontiguousarray(
            np.concatenate(residual_chunks, axis=1), dtype=np.float32
        ),
    )


@torch.no_grad()
def predict_hierarchical_coordinate_members(
    *,
    model: HierarchicalCAEModel,
    parameters: np.ndarray,
    field_index: int,
    coordinate_points: np.ndarray,
    device: torch.device,
    batch_size: int,
    query_batch_size: int,
) -> np.ndarray:
    """Evaluate one field readout while preserving predictor-member identity."""

    if not model.cfg.coordinate_readout:
        raise RuntimeError(
            "coordinate queries require a coordinate-enabled hierarchical CAE checkpoint"
        )
    index = int(field_index)
    if not 0 <= index < len(model.schema.layouts):
        raise IndexError(index)
    x = np.ascontiguousarray(parameters, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != model.input_dim:
        raise ValueError(
            f"expected normalized parameter matrix [N,{model.input_dim}]"
        )
    encoded = encode_coordinate_points(
        model.schema.layouts[index], coordinate_points
    )
    member_count = len(model.predictors)
    result = np.empty(
        (member_count, x.shape[0], encoded.shape[0]), dtype=np.float32
    )
    model.eval()
    sample_size = max(1, int(batch_size))
    query_size = max(1, int(query_batch_size))
    for sample_start in range(0, len(x), sample_size):
        sample_end = min(sample_start + sample_size, len(x))
        batch = torch.as_tensor(
            x[sample_start:sample_end], dtype=torch.float32, device=device
        )
        for member_index in range(member_count):
            latent, _applicability, residual_logits = model.predictor_output(
                member_index, batch
            )
            residual_gates = (
                torch.sigmoid(residual_logits)
                if model.cfg.regime_head and model.cfg.gated_private_residual
                else torch.zeros_like(residual_logits)
            )
            for query_start in range(0, encoded.shape[0], query_size):
                query_end = min(query_start + query_size, encoded.shape[0])
                coordinate_tensor = torch.as_tensor(
                    encoded[query_start:query_end],
                    dtype=torch.float32,
                    device=device,
                )
                values = model.decode_coordinates(
                    latent,
                    residual_gates,
                    field_index=index,
                    encoded_coordinates=coordinate_tensor,
                )
                result[
                    member_index,
                    sample_start:sample_end,
                    query_start:query_end,
                ] = values.float().cpu().numpy()
    return np.ascontiguousarray(result)


def save_model_bundle(
    path: Path,
    *,
    model: HierarchicalCAEModel,
    train_cfg: CAETrainConfig,
) -> None:
    payload = {
        "model_name": MODEL_NAME,
        "input_dim": model.input_dim,
        "train_cfg": asdict(train_cfg),
        "state_dict": model.state_dict(),
    }
    torch.save(payload, Path(path))


def load_model_bundle(
    path: Path,
    *,
    schema: HierarchicalSchema,
    device: torch.device,
) -> tuple[HierarchicalCAEModel, CAETrainConfig]:
    payload = torch.load(Path(path), map_location=device, weights_only=True)
    if not isinstance(payload, dict) or payload.get("model_name") != MODEL_NAME:
        raise ValueError("unsupported hierarchical CAE model bundle")
    cfg = CAETrainConfig(**dict(payload["train_cfg"]))
    model = HierarchicalCAEModel(int(payload["input_dim"]), schema, cfg).to(device)
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()
    return model, cfg


__all__ = [
    "HierarchicalCAEModel",
    "MODEL_NAME",
    "ParameterLatentPredictor",
    "design_level_split",
    "field_macro_loss",
    "fit_hierarchical_cae",
    "load_model_bundle",
    "predict_hierarchical_coordinate_members",
    "predict_hierarchical_members",
    "save_model_bundle",
    "unique_design_indices",
]
