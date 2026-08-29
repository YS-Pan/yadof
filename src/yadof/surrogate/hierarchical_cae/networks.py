"""Hierarchical CAE networks."""
from __future__ import annotations
from typing import Sequence
import torch
from torch import nn
from torch.nn import functional as F
from .coordinates import coordinate_feature_count
from .types import CAETrainConfig, HierarchicalSchema
MODEL_NAME = 'hierarchical_cae_rawdata_predictor_ensemble'

def _activation() -> nn.Module:
    return nn.SiLU()

class _ScalarCodec(nn.Module):

    def __init__(self, token_dim: int, latent_dim: int, private_dim: int, width: int) -> None:
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(1, width), _activation(), nn.Linear(width, token_dim))
        self.decoder = nn.Sequential(nn.Linear(latent_dim, width), _activation(), nn.Linear(width, 1))
        self.residual_decoder = nn.Sequential(nn.Linear(private_dim, width), _activation(), nn.Linear(width, 1))

    def encode(self, values: torch.Tensor) -> torch.Tensor:
        return self.encoder(values.reshape(values.shape[0], 1))

    def decode(self, latent: torch.Tensor, private: torch.Tensor, residual_gate: torch.Tensor, gradient_weight: torch.Tensor | None=None) -> torch.Tensor:
        base = self.decoder(latent).reshape(latent.shape[0])
        if gradient_weight is not None:
            weight = gradient_weight.reshape(-1)
            base = base.detach() + weight * (base - base.detach())
        residual = self.residual_decoder(private).reshape(latent.shape[0])
        return base + residual_gate.reshape(-1) * residual

class _Conv1dCodec(nn.Module):

    def __init__(self, length: int, token_dim: int, latent_dim: int, private_dim: int, width: int) -> None:
        super().__init__()
        self.length = int(length)
        self.base_length = min(16, max(4, self.length))
        self.encoder_conv = nn.Sequential(nn.Conv1d(1, width, 7, stride=2, padding=3), nn.GroupNorm(1, width), _activation(), nn.Conv1d(width, width, 5, stride=2, padding=2), nn.GroupNorm(1, width), _activation(), nn.AdaptiveAvgPool1d(self.base_length))
        self.encoder_head = nn.Linear(width * self.base_length, token_dim)
        self.decoder_head = nn.Linear(latent_dim, width * self.base_length)
        self.decoder_conv = nn.Sequential(nn.Conv1d(width, width, 5, padding=2), nn.GroupNorm(1, width), _activation(), nn.Conv1d(width, max(8, width // 2), 5, padding=2), _activation(), nn.Conv1d(max(8, width // 2), 1, 5, padding=2))
        self.residual_head = nn.Linear(private_dim, width * self.base_length)
        self.residual_conv = nn.Sequential(nn.Conv1d(width, width, 5, padding=2), _activation(), nn.Conv1d(width, 1, 5, padding=2))

    def encode(self, values: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder_conv(values.reshape(values.shape[0], 1, self.length))
        return self.encoder_head(encoded.flatten(1))

    def decode(self, latent: torch.Tensor, private: torch.Tensor, residual_gate: torch.Tensor, gradient_weight: torch.Tensor | None=None) -> torch.Tensor:
        hidden = self.decoder_head(latent).reshape(latent.shape[0], -1, self.base_length)
        hidden = F.interpolate(hidden, size=self.length, mode='linear', align_corners=True)
        base = self.decoder_conv(hidden).reshape(latent.shape[0], self.length)
        if gradient_weight is not None:
            weight = gradient_weight.reshape(-1, 1)
            base = base.detach() + weight * (base - base.detach())
        residual = self.residual_head(private).reshape(latent.shape[0], -1, self.base_length)
        residual = F.interpolate(residual, size=self.length, mode='linear', align_corners=True)
        residual = self.residual_conv(residual).reshape(latent.shape[0], self.length)
        return base + residual_gate.reshape(-1, 1) * residual

class _Conv2dCodec(nn.Module):

    def __init__(self, channels: int, spatial_shape: tuple[int, int], token_dim: int, latent_dim: int, private_dim: int, width: int) -> None:
        super().__init__()
        self.channels = int(channels)
        self.spatial_shape = tuple((int(value) for value in spatial_shape))
        self.base_shape = tuple((min(8, max(3, int(value))) for value in self.spatial_shape))
        self.encoder_conv = nn.Sequential(nn.Conv2d(self.channels, width, 5, stride=2, padding=2), nn.GroupNorm(1, width), _activation(), nn.Conv2d(width, width, 3, stride=2, padding=1), nn.GroupNorm(1, width), _activation(), nn.AdaptiveAvgPool2d(self.base_shape))
        base_count = width * self.base_shape[0] * self.base_shape[1]
        self.encoder_head = nn.Linear(base_count, token_dim)
        self.decoder_head = nn.Linear(latent_dim, base_count)
        self.decoder_conv = nn.Sequential(nn.Conv2d(width, width, 3, padding=1), nn.GroupNorm(1, width), _activation(), nn.Conv2d(width, max(8, width // 2), 3, padding=1), _activation(), nn.Conv2d(max(8, width // 2), self.channels, 3, padding=1))
        self.residual_head = nn.Linear(private_dim, base_count)
        self.residual_conv = nn.Sequential(nn.Conv2d(width, width, 3, padding=1), _activation(), nn.Conv2d(width, self.channels, 3, padding=1))

    def encode(self, values: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder_conv(values)
        return self.encoder_head(encoded.flatten(1))

    def decode(self, latent: torch.Tensor, private: torch.Tensor, residual_gate: torch.Tensor, gradient_weight: torch.Tensor | None=None) -> torch.Tensor:
        hidden = self.decoder_head(latent).reshape(latent.shape[0], -1, self.base_shape[0], self.base_shape[1])
        hidden = F.interpolate(hidden, size=self.spatial_shape, mode='bilinear', align_corners=True)
        base = self.decoder_conv(hidden)
        if gradient_weight is not None:
            weight = gradient_weight.reshape(-1, 1, 1, 1)
            base = base.detach() + weight * (base - base.detach())
        residual = self.residual_head(private).reshape(latent.shape[0], -1, self.base_shape[0], self.base_shape[1])
        residual = F.interpolate(residual, size=self.spatial_shape, mode='bilinear', align_corners=True)
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

    def __init__(self, *, latent_dim: int, private_dim: int, coordinate_dim: int, width: int, layers: int) -> None:
        super().__init__()
        self.base = _mlp(latent_dim + coordinate_dim, 1, width, layers)
        self.private_residual = _mlp(private_dim + coordinate_dim, 1, width, layers)

    def forward(self, latent: torch.Tensor, private: torch.Tensor, encoded_coordinates: torch.Tensor, residual_gate: torch.Tensor) -> torch.Tensor:
        if encoded_coordinates.ndim != 2:
            raise ValueError('encoded coordinates must have shape [query, features]')
        batch_size = int(latent.shape[0])
        query_count = int(encoded_coordinates.shape[0])
        coordinates = encoded_coordinates.unsqueeze(0).expand(batch_size, query_count, -1)
        expanded_latent = latent.unsqueeze(1).expand(-1, query_count, -1)
        expanded_private = private.unsqueeze(1).expand(-1, query_count, -1)
        base = self.base(torch.cat((expanded_latent, coordinates), dim=2)).squeeze(2)
        residual = self.private_residual(torch.cat((expanded_private, coordinates), dim=2)).squeeze(2)
        return base + residual_gate.reshape(-1, 1) * residual

class ParameterLatentPredictor(nn.Module):
    """One independently initialized parameter-to-joint-latent function."""

    def __init__(self, input_dim: int, output_dim: int, cfg: CAETrainConfig) -> None:
        super().__init__()
        self.network = _mlp(input_dim, output_dim, cfg.predictor_width, cfg.predictor_layers)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return self.network(values - 0.5)

class HierarchicalCAEModel(nn.Module):
    """Shared field codecs plus global/group/private latent decomposition."""

    def __init__(self, input_dim: int, schema: HierarchicalSchema, cfg: CAETrainConfig) -> None:
        super().__init__()
        self.input_dim = int(input_dim)
        self.schema = schema
        self.cfg = cfg
        self.group_for_field = tuple((next((group_index for group_index, group in enumerate(schema.groups) if layout.selector in group), None) for layout in schema.layouts))
        if cfg.sharing == 'hierarchical':
            self.global_slice = slice(0, cfg.global_latent_dim)
            cursor = cfg.global_latent_dim
            self.group_slices = []
            for _group in schema.groups:
                self.group_slices.append(slice(cursor, cursor + cfg.group_latent_dim))
                cursor += cfg.group_latent_dim
        else:
            self.global_slice = slice(0, 0)
            self.group_slices = []
            cursor = 0
        self.private_slices = []
        for _layout in schema.layouts:
            self.private_slices.append(slice(cursor, cursor + cfg.private_latent_dim))
            cursor += cfg.private_latent_dim
        self.latent_dim = int(cursor)
        decoder_dims = [self.field_latent_dim(index) for index in range(len(schema.layouts))]
        codecs = []
        for layout, decoder_dim in zip(schema.layouts, decoder_dims):
            if layout.codec_kind == 'scalar-mlp':
                codecs.append(_ScalarCodec(cfg.token_dim, decoder_dim, cfg.private_latent_dim, max(16, cfg.codec_width)))
            elif layout.codec_kind == 'conv1d':
                codecs.append(_Conv1dCodec(layout.model_spatial_shape[0], cfg.token_dim, decoder_dim, cfg.private_latent_dim, cfg.codec_width))
            elif layout.codec_kind == 'conv2d':
                codecs.append(_Conv2dCodec(layout.model_channels, (int(layout.model_spatial_shape[0]), int(layout.model_spatial_shape[1])), cfg.token_dim, decoder_dim, cfg.private_latent_dim, cfg.codec_width))
            else:
                raise ValueError(f'unsupported field codec {layout.codec_kind!r}')
        self.codecs = nn.ModuleList(codecs)
        if cfg.sharing == 'hierarchical':
            token_width = len(schema.layouts) * cfg.token_dim + len(schema.layouts)
            self.global_teacher = _mlp(token_width, cfg.global_latent_dim, max(cfg.token_dim, cfg.global_latent_dim), 1)
            group_teachers = []
            for group in schema.groups:
                group_teachers.append(_mlp(len(group) * cfg.token_dim + len(group), cfg.group_latent_dim, max(cfg.token_dim, cfg.group_latent_dim), 1))
            self.group_teachers = nn.ModuleList(group_teachers)
        else:
            self.global_teacher = nn.Identity()
            self.group_teachers = nn.ModuleList()
        self.private_teachers = nn.ModuleList((nn.Linear(cfg.token_dim, cfg.private_latent_dim) for _layout in schema.layouts))
        self.predictor_output_dim = self.latent_dim + (1 + len(schema.layouts) if cfg.regime_head else 0)
        self.predictors = nn.ModuleList((ParameterLatentPredictor(input_dim, self.predictor_output_dim, cfg) for _ in range(cfg.predictor_members)))
        self.coordinate_readouts = nn.ModuleList((_CoordinateReadout(latent_dim=self.field_latent_dim(field_index), private_dim=cfg.private_latent_dim, coordinate_dim=coordinate_feature_count(layout), width=cfg.coordinate_width, layers=cfg.coordinate_layers) for field_index, layout in enumerate(schema.layouts))) if cfg.coordinate_readout else nn.ModuleList()

    def field_latent_dim(self, field_index: int) -> int:
        if self.cfg.sharing == 'independent':
            return self.cfg.private_latent_dim
        group_extra = self.cfg.group_latent_dim if self.group_for_field[field_index] is not None else 0
        return self.cfg.global_latent_dim + group_extra + self.cfg.private_latent_dim

    def _to_model_layout(self, field_index: int, values: torch.Tensor) -> torch.Tensor:
        layout = self.schema.layouts[field_index]
        if layout.codec_kind == 'scalar-mlp':
            return values.reshape(values.shape[0])
        if layout.codec_kind == 'conv1d':
            return values.reshape(values.shape[0], 1, layout.shape[0])
        rank = len(layout.shape)
        if rank == 2:
            return values.reshape(values.shape[0], 1, *layout.shape)
        permutation = (0,) + tuple((index + 1 for index in layout.model_permutation))
        ordered = values.permute(permutation)
        return ordered.reshape(values.shape[0], layout.model_channels, *layout.model_spatial_shape)

    def _from_model_layout(self, field_index: int, values: torch.Tensor) -> torch.Tensor:
        layout = self.schema.layouts[field_index]
        if layout.codec_kind == 'scalar-mlp':
            return values.reshape(values.shape[0])
        if layout.codec_kind == 'conv1d':
            return values.reshape(values.shape[0], *layout.shape)
        if len(layout.shape) == 2:
            return values.reshape(values.shape[0], *layout.shape)
        ordered_shape = tuple((layout.shape[index] for index in layout.model_permutation))
        ordered = values.reshape(values.shape[0], *ordered_shape)
        inverse = (0,) + tuple((index + 1 for index in layout.inverse_permutation))
        return ordered.permute(inverse).contiguous()

    def encode_fields(self, fields: Sequence[torch.Tensor]) -> tuple[torch.Tensor, ...]:
        if len(fields) != len(self.codecs):
            raise ValueError('one tensor is required per hierarchical CAE field')
        return tuple((codec.encode(self._to_model_layout(index, values)) for index, (codec, values) in enumerate(zip(self.codecs, fields))))

    def teacher_latent_from_tokens(self, tokens: Sequence[torch.Tensor], shared_weights: torch.Tensor | None=None) -> torch.Tensor:
        if shared_weights is None:
            shared_weights = torch.ones((tokens[0].shape[0], len(tokens)), dtype=tokens[0].dtype, device=tokens[0].device)
        if shared_weights.shape != (tokens[0].shape[0], len(tokens)):
            raise ValueError('shared field weights must have shape [batch, fields]')
        private = [teacher(token) for teacher, token in zip(self.private_teachers, tokens)]
        if self.cfg.sharing == 'independent':
            return torch.cat(private, dim=1)
        masked = [token * shared_weights[:, index:index + 1] for index, token in enumerate(tokens)]
        global_latent = self.global_teacher(torch.cat([*masked, shared_weights], dim=1))
        groups = []
        for teacher, group in zip(self.group_teachers, self.schema.groups):
            indices = [self.schema.field_selectors.index(selector) for selector in group]
            selected = [masked[index] for index in indices]
            group_weights = shared_weights[:, indices]
            groups.append(teacher(torch.cat([*selected, group_weights], dim=1)))
        return torch.cat([global_latent, *groups, *private], dim=1)

    def teacher_latent(self, fields: Sequence[torch.Tensor], shared_weights: torch.Tensor | None=None) -> torch.Tensor:
        return self.teacher_latent_from_tokens(self.encode_fields(fields), shared_weights)

    def field_latent(self, joint_latent: torch.Tensor, field_index: int) -> torch.Tensor:
        pieces = []
        if self.cfg.sharing == 'hierarchical':
            pieces.append(joint_latent[:, self.global_slice])
            group_index = self.group_for_field[field_index]
            if group_index is not None:
                pieces.append(joint_latent[:, self.group_slices[group_index]])
        pieces.append(joint_latent[:, self.private_slices[field_index]])
        return torch.cat(pieces, dim=1)

    def decode_joint(self, joint_latent: torch.Tensor, residual_gates: torch.Tensor | None=None, gradient_weights: torch.Tensor | None=None) -> tuple[torch.Tensor, ...]:
        batch_size = joint_latent.shape[0]
        field_count = len(self.codecs)
        if residual_gates is None:
            residual_gates = torch.zeros((batch_size, field_count), dtype=joint_latent.dtype, device=joint_latent.device)
        if residual_gates.shape != (batch_size, field_count):
            raise ValueError('residual gates must have shape [batch, fields]')
        if gradient_weights is not None and gradient_weights.shape != (batch_size, field_count):
            raise ValueError('gradient weights must have shape [batch, fields]')
        return tuple((self._from_model_layout(field_index, codec.decode(self.field_latent(joint_latent, field_index), joint_latent[:, self.private_slices[field_index]], residual_gates[:, field_index], None if gradient_weights is None else gradient_weights[:, field_index])) for field_index, codec in enumerate(self.codecs)))

    def autoencode(self, fields: Sequence[torch.Tensor], *, shared_weights: torch.Tensor | None=None, residual_targets: torch.Tensor | None=None) -> tuple[torch.Tensor, ...]:
        return self.decode_joint(self.teacher_latent(fields, shared_weights), residual_targets, shared_weights)

    def split_predictor_output(self, output: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        latent = output[:, :self.latent_dim]
        if not self.cfg.regime_head:
            applicability = torch.full((output.shape[0],), 20.0, dtype=output.dtype, device=output.device)
            residual_logits = torch.full((output.shape[0], len(self.codecs)), -20.0, dtype=output.dtype, device=output.device)
            return (latent, applicability, residual_logits)
        applicability = output[:, self.latent_dim]
        residual_logits = output[:, self.latent_dim + 1:]
        return (latent, applicability, residual_logits)

    def predictor_output(self, member_index: int, parameters: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.split_predictor_output(self.predictors[int(member_index)](parameters))

    def predict_member(self, member_index: int, parameters: torch.Tensor) -> tuple[tuple[torch.Tensor, ...], torch.Tensor, torch.Tensor]:
        latent, applicability_logit, residual_logits = self.predictor_output(member_index, parameters)
        residual_gates = torch.sigmoid(residual_logits) if self.cfg.regime_head and self.cfg.gated_private_residual else torch.zeros_like(residual_logits)
        return (self.decode_joint(latent, residual_gates), applicability_logit, residual_logits)

    def decode_coordinates(self, joint_latent: torch.Tensor, residual_gates: torch.Tensor, *, field_index: int, encoded_coordinates: torch.Tensor) -> torch.Tensor:
        if not self.cfg.coordinate_readout or not self.coordinate_readouts:
            raise RuntimeError('this hierarchical CAE checkpoint has no coordinate readout')
        index = int(field_index)
        if not 0 <= index < len(self.schema.layouts):
            raise IndexError(index)
        return self.coordinate_readouts[index](self.field_latent(joint_latent, index), joint_latent[:, self.private_slices[index]], encoded_coordinates, residual_gates[:, index])
