from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from importlib import metadata
from types import MappingProxyType
from typing import Mapping

from .hierarchical_cae.schema import (
    normalize_axis_encodings,
    normalize_field_layouts,
    normalize_groups,
)
from .hierarchical_cae.types import CAETrainConfig, CoordinatePrediction
from .quality import (
    ApplicabilityPrediction,
    DiagnosticCondition,
    DiagnosticRegimeRule,
    RawDataQualityPolicy,
    ShapeQualityRule,
    quality_policy_from_mapping,
)

from .posterior import (
    MaterializedRawDataPosterior,
    RAWDATA_POSTERIOR_PROTOCOL,
    RAWDATA_POSTERIOR_PROTOCOL_VERSION,
    RawDataFunctionDraw,
    RawDataPosterior,
    RawDataPosteriorDiagnostics,
    RawDataPosteriorSampler,
    RawDataPosteriorSurrogate,
    SUPPORT_CONTINUOUS_OR_UNKNOWN,
    SUPPORT_FINITE,
    posterior_capability_identity,
    project_rawdata_sampler,
    require_rawdata_posterior_surrogate,
)


@dataclass(frozen=True, slots=True)
class ConditionalINRComponent:
    """Narrow rawData-first surrogate component consumed by GPSAF."""

    def validate(self, config, problem) -> None:
        del config, problem
        try:
            metadata.version("torch")
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "conditional_inr requires the yadof surrogate extra (torch)"
            ) from exc

    def semantic_identity(self, config, problem) -> Mapping[str, object]:
        del problem
        controlled_names = (
            "SURROGATE_CONSTANT_ATOL",
            "SURROGATE_TARGET_SCALE_FLOOR",
            "SURROGATE_TORCH_DEVICE",
            "SURROGATE_INR_EPOCHS",
            "SURROGATE_INR_ENSEMBLE_SIZE",
            "SURROGATE_INR_BATCH_SIZE",
            "SURROGATE_INR_LR",
            "SURROGATE_INR_WEIGHT_DECAY",
            "SURROGATE_INR_LOSS_BETA",
            "SURROGATE_MAX_NONFINITE_FRACTION",
            "SURROGATE_INR_X_LATENT_DIM",
            "SURROGATE_INR_FIELD_EMB_DIM",
            "SURROGATE_INR_COORD_FOURIER_FEATURES",
            "SURROGATE_INR_HIDDEN_DIM",
            "SURROGATE_INR_HIDDEN_LAYERS",
            "SURROGATE_INR_TRAIN_QUERY_CHUNK",
            "SURROGATE_INR_TRAIN_QUERY_SAMPLE_COUNT",
            "SURROGATE_INR_SAMPLE_BATCH_EVAL",
            "SURROGATE_INR_QUERY_BATCH_EVAL",
            "SURROGATE_INR_BOOTSTRAP_MEMBERS",
            "SURROGATE_INR_BOOTSTRAP_FRACTION",
        )
        return {
            "component": "conditional-inr",
            "component_version": 2,
            "backend_distribution": "torch",
            "backend_version": metadata.version("torch"),
            "training_policy": "real-field-balanced",
            "controlled_parameters": {
                name: config[name] for name in controlled_names
            },
        }

    def ensure_fresh_enough(self, context):
        from .conditional_inr import runtime, scheduler

        return scheduler.ensure_fresh_enough(
            context.config.workspace,
            context.generation_index,
            _config=context.config,
            _training_data=runtime.training_data_from_session(
                context.session,
                context.snapshot,
            ),
        )

    def has_trained_state(self, context) -> bool:
        from .conditional_inr import runtime

        return bool(runtime.has_trained_state(context.config.workspace))

    def start_training(self, context):
        from .conditional_inr import runtime, scheduler

        return scheduler.start_training(
            context.config.workspace,
            generation_index=context.generation_index,
            block=False,
            _config=context.config,
            _training_data=runtime.training_data_from_session(
                context.session,
                context.snapshot,
            ),
        )

    def predict_population(self, context, population):
        from .conditional_inr import runtime

        return runtime.predict_population(context.config.workspace, population)


@dataclass(frozen=True, slots=True)
class ConditionalINRPosteriorAdapter:
    """Explicit finite-ensemble posterior view over conditional INR.

    The wrapped component keeps its legacy GPSAF identity and tuple API. This
    adapter has a separate semantic identity so only strategies that opt into the
    joint posterior enter a new state namespace.
    """

    component: ConditionalINRComponent = ConditionalINRComponent()

    def validate(self, config, problem) -> None:
        self.component.validate(config, problem)

    def semantic_identity(self, config, problem) -> Mapping[str, object]:
        return {
            "component": "conditional-inr-posterior-adapter",
            "component_version": 1,
            "base_surrogate": self.component.semantic_identity(config, problem),
            "posterior": self.posterior_semantic_identity(config, problem),
        }

    def posterior_semantic_identity(self, config, problem) -> Mapping[str, object]:
        del problem
        return posterior_capability_identity(
            posterior_kind="empirical_ensemble",
            support_kind=SUPPORT_FINITE,
            backend_distribution="torch",
            backend_version=metadata.version("torch"),
            controlled_parameters={
                "configured_member_count": int(
                    config["SURROGATE_INR_ENSEMBLE_SIZE"]
                ),
                "member_selection": "seeded-permutation-cycles-v1",
                "candidate_evaluation": "fixed-member-full-grid-single-row-v1",
                "observation_noise_included": False,
                "calibrated": False,
            },
        )

    def ensure_fresh_enough(self, context):
        return self.component.ensure_fresh_enough(context)

    def has_trained_state(self, context) -> bool:
        return self.component.has_trained_state(context)

    def start_training(self, context):
        return self.component.start_training(context)

    def predict_population(self, context, population):
        return self.component.predict_population(context, population)

    def make_rawdata_sampler(self, context, *, draw_count: int, seed: int):
        from .conditional_inr.posterior_adapter import make_rawdata_sampler

        return make_rawdata_sampler(
            context,
            draw_count=draw_count,
            seed=seed,
        )


@dataclass(frozen=True, slots=True)
class HierarchicalCAEComponent:
    """Full-grid hierarchical convolutional rawData surrogate component."""

    groups: tuple[tuple[tuple[str, str], ...], ...] = ()
    field_layouts: Mapping[tuple[str, str], Mapping[str, object]] = field(
        default_factory=dict
    )
    axis_encodings: Mapping[tuple[str, str], Mapping[str, object]] = field(
        default_factory=dict
    )
    quality_policy: RawDataQualityPolicy | None = None
    train_cfg: CAETrainConfig = CAETrainConfig()

    def __post_init__(self) -> None:
        groups = normalize_groups(self.groups)
        layouts = MappingProxyType(
            {
                selector: MappingProxyType(dict(layout))
                for selector, layout in normalize_field_layouts(
                    self.field_layouts
                ).items()
            }
        )
        encodings = MappingProxyType(
            {
                selector: MappingProxyType(dict(per_axis))
                for selector, per_axis in normalize_axis_encodings(
                    self.axis_encodings
                ).items()
            }
        )
        policy = quality_policy_from_mapping(self.quality_policy)
        train_cfg = self.train_cfg
        if policy is not None and not train_cfg.regime_head:
            train_cfg = replace(
                train_cfg,
                regime_head=True,
                robust_loss_cap=(
                    4.0
                    if train_cfg.robust_loss_cap is None
                    else train_cfg.robust_loss_cap
                ),
            )
        if policy is None and train_cfg.regime_head:
            raise ValueError(
                "hierarchical CAE regime_head requires a versioned quality_policy"
            )
        object.__setattr__(self, "groups", groups)
        object.__setattr__(self, "field_layouts", layouts)
        object.__setattr__(self, "axis_encodings", encodings)
        object.__setattr__(self, "quality_policy", policy)
        object.__setattr__(self, "train_cfg", train_cfg)

    def configuration_payload(self) -> dict[str, object]:
        return {
            "groups": [
                [list(selector) for selector in group] for group in self.groups
            ],
            "field_layouts": [
                {
                    "selector": list(selector),
                    "channel_axes": list(layout["channel_axes"]),
                    "spatial_axes": list(layout["spatial_axes"]),
                }
                for selector, layout in sorted(self.field_layouts.items())
            ],
            "axis_encodings": [
                {
                    "selector": list(selector),
                    "axes": {
                        axis: encoding.as_dict()
                        for axis, encoding in sorted(per_axis.items())
                    },
                }
                for selector, per_axis in sorted(self.axis_encodings.items())
            ],
            "quality_policy": (
                None
                if self.quality_policy is None
                else self.quality_policy.as_dict()
            ),
            "train_cfg": asdict(self.train_cfg),
        }

    def validate(self, config, problem) -> None:
        del config, problem
        try:
            metadata.version("torch")
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "hierarchical_cae requires the yadof surrogate extra (torch)"
            ) from exc

    def semantic_identity(self, config, problem) -> Mapping[str, object]:
        del problem
        return {
            "component": "hierarchical-cae",
            "component_version": (
                2 if self.train_cfg.coordinate_readout else 1
            ),
            "backend_distribution": "torch",
            "backend_version": metadata.version("torch"),
            "training_policy": "design-split-field-macro-hierarchical-latent",
            "configuration": self.configuration_payload(),
            "device": str(config["SURROGATE_TORCH_DEVICE"]),
            "posterior": self.posterior_semantic_identity(config, None),
            "applicability": {
                "capability": "yadof.rawdata-applicability",
                "capability_version": 1,
                "enabled": self.quality_policy is not None,
                "calibrated": False,
                "observation_noise": "zero",
            },
            "coordinate_readout": {
                "capability": "yadof.hierarchical-cae-coordinate-readout",
                "capability_version": 1,
                "enabled": self.train_cfg.coordinate_readout,
                "authority": "viewer/off-grid-only",
                "full_grid_decoder_remains_authoritative": True,
            },
        }

    def posterior_semantic_identity(self, config, problem) -> Mapping[str, object]:
        del config, problem
        return posterior_capability_identity(
            posterior_kind="empirical_predictor_ensemble",
            support_kind=SUPPORT_FINITE,
            backend_distribution="torch",
            backend_version=metadata.version("torch"),
            controlled_parameters={
                "configured_member_count": self.train_cfg.predictor_members,
                "member_selection": "seeded-permutation-cycles-v1",
                "shared_codecs": True,
                "regime_head": self.train_cfg.regime_head,
                "quality_policy": (
                    None
                    if self.quality_policy is None
                    else self.quality_policy.as_dict()
                ),
                "observation_noise_included": False,
                "calibrated": False,
            },
        )

    def ensure_fresh_enough(self, context):
        from .hierarchical_cae import runtime, scheduler

        return scheduler.ensure_fresh_enough(
            context.config.workspace,
            context.generation_index,
            _config=context.config,
            _component=self,
            _training_data=runtime.training_data_from_session(
                context.session, context.snapshot
            ),
        )

    def has_trained_state(self, context) -> bool:
        from .hierarchical_cae import runtime

        return bool(
            runtime.has_trained_state(context.config.workspace, component=self)
        )

    def start_training(self, context):
        from .hierarchical_cae import runtime, scheduler

        return scheduler.start_training(
            context.config.workspace,
            generation_index=context.generation_index,
            block=False,
            _config=context.config,
            _component=self,
            _training_data=runtime.training_data_from_session(
                context.session, context.snapshot
            ),
        )

    def predict_population(self, context, population):
        from .hierarchical_cae import runtime

        return runtime.predict_population(
            context.config.workspace, population, component=self
        )

    def make_rawdata_sampler(self, context, *, draw_count: int, seed: int):
        from .hierarchical_cae.posterior_adapter import make_rawdata_sampler

        return make_rawdata_sampler(
            context,
            component=self,
            draw_count=draw_count,
            seed=seed,
        )

    def predict_applicability(self, context, population) -> ApplicabilityPrediction:
        from .hierarchical_cae import runtime

        return runtime.predict_applicability(
            context.config.workspace, population, component=self
        )

    def predict_field_at_coordinates(
        self,
        context,
        population,
        *,
        field_selector: tuple[str, str],
        axis_coordinates,
    ) -> CoordinatePrediction:
        from .hierarchical_cae import runtime

        return runtime.predict_field_at_coordinates(
            context.config.workspace,
            population,
            component=self,
            field_selector=field_selector,
            axis_coordinates=axis_coordinates,
        )


def conditional_inr() -> ConditionalINRComponent:
    return ConditionalINRComponent()


def conditional_inr_posterior() -> ConditionalINRPosteriorAdapter:
    return ConditionalINRPosteriorAdapter()


def hierarchical_cae(
    *,
    groups=(),
    field_layouts=None,
    axis_encodings=None,
    quality_policy: RawDataQualityPolicy | Mapping[str, object] | None = None,
    train_config: CAETrainConfig | None = None,
) -> HierarchicalCAEComponent:
    """Build the opt-in hierarchical CAE component from task-owned declarations."""

    return HierarchicalCAEComponent(
        groups=tuple(tuple(group) for group in groups),
        field_layouts={} if field_layouts is None else dict(field_layouts),
        axis_encodings={} if axis_encodings is None else dict(axis_encodings),
        quality_policy=quality_policy_from_mapping(quality_policy),
        train_cfg=CAETrainConfig() if train_config is None else train_config,
    )


def train(*args, **kwargs):
    from .conditional_inr.runtime import train as implementation

    return implementation(*args, **kwargs)


def predict_population(*args, **kwargs):
    from .conditional_inr.runtime import predict_population as implementation

    return implementation(*args, **kwargs)


def has_trained_state(*args, **kwargs):
    from .conditional_inr.runtime import has_trained_state as implementation

    return implementation(*args, **kwargs)


def latest_state_generation(*args, **kwargs):
    from .conditional_inr.runtime import latest_state_generation as implementation

    return implementation(*args, **kwargs)


def ensure_fresh_enough(*args, **kwargs):
    from .conditional_inr.scheduler import ensure_fresh_enough as implementation

    return implementation(*args, **kwargs)


def start_training(*args, **kwargs):
    from .conditional_inr.scheduler import start_training as implementation

    return implementation(*args, **kwargs)


def wait_for_pending_training(*args, **kwargs):
    from .conditional_inr.scheduler import wait_for_pending_training as implementation

    return implementation(*args, **kwargs)


def deactivate_workspace(*args, **kwargs):
    from .conditional_inr.scheduler import deactivate_workspace as conditional
    from .hierarchical_cae.scheduler import deactivate_workspace as hierarchical

    conditional_status = conditional(*args, **kwargs)
    hierarchical(*args, **kwargs)
    return conditional_status

__all__ = [
    "ConditionalINRComponent",
    "ConditionalINRPosteriorAdapter",
    "HierarchicalCAEComponent",
    "CAETrainConfig",
    "CoordinatePrediction",
    "DiagnosticCondition",
    "DiagnosticRegimeRule",
    "RawDataQualityPolicy",
    "ShapeQualityRule",
    "ApplicabilityPrediction",
    "MaterializedRawDataPosterior",
    "RAWDATA_POSTERIOR_PROTOCOL",
    "RAWDATA_POSTERIOR_PROTOCOL_VERSION",
    "RawDataFunctionDraw",
    "RawDataPosterior",
    "RawDataPosteriorDiagnostics",
    "RawDataPosteriorSampler",
    "RawDataPosteriorSurrogate",
    "SUPPORT_CONTINUOUS_OR_UNKNOWN",
    "SUPPORT_FINITE",
    "conditional_inr",
    "conditional_inr_posterior",
    "hierarchical_cae",
    "deactivate_workspace",
    "ensure_fresh_enough",
    "has_trained_state",
    "latest_state_generation",
    "predict_population",
    "posterior_capability_identity",
    "project_rawdata_sampler",
    "require_rawdata_posterior_surrogate",
    "start_training",
    "train",
    "wait_for_pending_training",
]
