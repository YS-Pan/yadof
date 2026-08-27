from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Mapping

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


def conditional_inr() -> ConditionalINRComponent:
    return ConditionalINRComponent()


def conditional_inr_posterior() -> ConditionalINRPosteriorAdapter:
    return ConditionalINRPosteriorAdapter()


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
    from .conditional_inr.scheduler import deactivate_workspace as implementation

    return implementation(*args, **kwargs)

__all__ = [
    "ConditionalINRComponent",
    "ConditionalINRPosteriorAdapter",
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
