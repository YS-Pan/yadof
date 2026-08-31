from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from importlib import metadata
from types import MappingProxyType
from typing import Mapping

from .._component_settings import text

from .hierarchical_cae.schema import (
    normalize_axis_encodings,
    normalize_field_layouts,
    normalize_groups,
)
from .hierarchical_cae.types import CAETrainConfig, CoordinatePrediction
from .conditional_inr.settings import (
    ConditionalINRSettings,
    DEFAULT_CONDITIONAL_INR_SETTINGS,
    create_settings as create_conditional_inr_settings,
)
from .linear_subspace.settings import (
    DEFAULT_PCA_SVD_SETTINGS,
    PCASVDSettings,
)
from .hierarchical_cae.data_filtering import (
    DATA_FILTER_NONE,
    DATA_FILTER_FREQUENCY,
    ApplicabilityPrediction,
    DiagnosticCondition,
    DiagnosticRegimeRule,
    FrequencyFilter,
    FrequencyFilterRule,
    resolve_data_filter,
)
from .calibration import (
    APPLICABILITY_METHOD,
    CALIBRATED,
    EXPERIMENTAL_PERFORMANCE_STATUS,
    FIELD_SPREAD_METHOD,
    NOT_APPLICABLE,
    POSTERIOR_CALIBRATION_PROTOCOL,
    POSTERIOR_CALIBRATION_PROTOCOL_VERSION,
    UNCALIBRATED,
    ApplicabilityCalibration,
    CalibratedRawDataPosteriorSampler,
    FieldSpreadCalibration,
    PosteriorCalibrationArtifact,
    assess_spread_scale,
    calibrated_applicability_prediction,
    calibration_identity_signature,
    fit_monotone_applicability_calibration,
    select_conservative_spread_scale,
    transform_applicability_members,
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
from .exploitation import (
    APPLICABILITY_CALIBRATED,
    APPLICABILITY_NOT_APPLICABLE,
    APPLICABILITY_UNCALIBRATED,
    PERFORMANCE_ACCEPTED,
    PERFORMANCE_NOT_ACCEPTED,
    POSTERIOR_CALIBRATED,
    POSTERIOR_EXPLOITATION_PROTOCOL,
    POSTERIOR_EXPLOITATION_PROTOCOL_VERSION,
    POSTERIOR_UNCALIBRATED,
    PosteriorExploitationReadiness,
    PosteriorExploitationSurrogate,
    blocked_exploitation_identity,
    require_posterior_exploitation_surrogate,
)


DEFAULT_CAE_TRAIN_CONFIG = CAETrainConfig()


@dataclass(frozen=True, slots=True)
class PCASVDComponent:
    """Deterministic per-field PCA/SVD component consumed by GPSAF.

    The low-level methods deliberately keep oracle reconstruction separate from
    the deployable normalized-parameter predictor while sharing these settings.
    """

    settings: PCASVDSettings

    def validate(self, config, problem) -> None:
        del config, problem
        try:
            metadata.version("torch")
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "pca_svd requires the yadof surrogate extra (torch); "
                "install yadof[surrogate]"
            ) from exc

    def semantic_identity(self, config, problem) -> Mapping[str, object]:
        del config, problem
        return {
            "component": "pca-svd-rawdata-surrogate",
            "component_version": 2,
            "backend_distribution": "torch",
            "backend_version": metadata.version("torch"),
            "training_policy": "per-field-lowrank-ridge",
            "posterior_capability": False,
            "controlled_parameters": self.settings.semantic_parameters(),
        }

    def fit_codec(self, samples):
        from .linear_subspace.codec import fit_codec

        return fit_codec(_structured_samples(samples), settings=self.settings)

    def evaluate_oracle(self, codec, samples):
        from .linear_subspace.codec import evaluate_oracle

        return evaluate_oracle(codec, _structured_samples(samples))

    def fit_oracle(self, samples):
        """Fit and project the same samples for reconstruction diagnostics only."""

        selected = _structured_samples(samples)
        return self.evaluate_oracle(self.fit_codec(selected), selected)

    def fit_deployable(self, normalized_parameters, samples, *, parameter_names):
        from .linear_subspace.codec import fit_deployable

        return fit_deployable(
            normalized_parameters,
            _structured_samples(samples),
            parameter_names=parameter_names,
            settings=self.settings,
        )

    def predict_rawdata(self, model, normalized_parameters):
        from .linear_subspace.codec import predict_rawdata

        return predict_rawdata(model, normalized_parameters)

    def training_data(
        self,
        dataset,
        cost_table,
        *,
        row_ids=None,
        transform_id: str | None = None,
    ):
        from .training import materialize_training_data

        return materialize_training_data(
            dataset,
            cost_table,
            row_ids=row_ids,
            transform_id=transform_id,
        )

    def start_fit(
        self,
        workspace,
        training_data,
        *,
        generation_index: int = 0,
        session=None,
        snapshot=None,
    ):
        from .linear_subspace import runtime

        return runtime.start_fit(
            workspace,
            training_data,
            generation_index=generation_index,
            _settings=self.settings,
            _session=session,
            _snapshot=snapshot,
        )

    def fit(
        self,
        workspace,
        training_data,
        *,
        generation_index: int = 0,
        session=None,
        snapshot=None,
    ):
        from .linear_subspace import runtime

        return runtime.fit(
            workspace,
            training_data,
            generation_index=generation_index,
            _settings=self.settings,
            _session=session,
            _snapshot=snapshot,
        )

    def recover(self, workspace, training_data, *, snapshot=None):
        from .linear_subspace import runtime

        return runtime.recover_state(
            workspace,
            training_data,
            _settings=self.settings,
            _config=(None if snapshot is None else snapshot.config),
        )

    def predict(self, state, normalized_parameters, *, snapshot):
        from .linear_subspace import runtime

        return runtime.predict(state, normalized_parameters, snapshot=snapshot)

    def predict_for_selection(self, context, population, training_data=None):
        """Recover the exact fitted state and return the Stage 4 prediction DTO."""

        from .linear_subspace import runtime
        from .training import SurrogateTrainingData

        if not isinstance(training_data, SurrogateTrainingData):
            raise TypeError(
                "pca_svd selection prediction requires SurrogateTrainingData"
            )
        state = runtime.recover_state(
            context.config.workspace,
            training_data,
            _settings=self.settings,
            _config=context.snapshot.config,
        )
        if state is None:
            raise RuntimeError("pca_svd surrogate is not trained for this data")
        return runtime.predict(state, population, snapshot=context.snapshot)

    def ensure_fresh_enough(self, context, training_data):
        from .linear_subspace import scheduler

        return scheduler.ensure_fresh_enough(
            context.config.workspace,
            context.generation_index,
            _config=context.config,
            _settings=self.settings,
            _max_training_lag=int(context.config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG),
            _training_data=training_data,
            _session=context.session,
            _snapshot=context.snapshot,
        )

    def has_trained_state(self, context, training_data) -> bool:
        from .linear_subspace import runtime

        return runtime.has_trained_state(
            context.config.workspace,
            training_data,
            _settings=self.settings,
        )

    def start_training(self, context, training_data):
        from .linear_subspace import scheduler

        return scheduler.start_training(
            context.config.workspace,
            context.generation_index,
            block=False,
            _config=context.config,
            _settings=self.settings,
            _training_data=training_data,
            _session=context.session,
            _snapshot=context.snapshot,
        )

    def finish_training(self, context):
        from .linear_subspace import scheduler

        return scheduler.wait_for_pending_training(
            context.config.workspace,
            _settings=self.settings,
        )

    def predict_population(self, context, population, training_data):
        from .linear_subspace import runtime

        return runtime.predict_population(
            context.config.workspace,
            population,
            _training_data=training_data,
            _snapshot=context.snapshot,
            _settings=self.settings,
        )


def _structured_samples(samples):
    from .linear_subspace.types import StructuredRawDataSample

    return tuple(
        sample
        if isinstance(sample, StructuredRawDataSample)
        else StructuredRawDataSample.from_items(sample)
        for sample in samples
    )


@dataclass(frozen=True, slots=True)
class ConditionalINRComponent:
    """Narrow rawData-first surrogate component consumed by GPSAF."""

    settings: ConditionalINRSettings

    def validate(self, config, problem) -> None:
        del config, problem
        try:
            metadata.version("torch")
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "conditional_inr requires the yadof surrogate extra (torch)"
            ) from exc

    def semantic_identity(self, config, problem) -> Mapping[str, object]:
        del config, problem
        return {
            "component": "conditional-inr",
            "component_version": 2,
            "backend_distribution": "torch",
            "backend_version": metadata.version("torch"),
            "training_policy": "real-field-balanced",
            "controlled_parameters": self.settings.semantic_parameters(),
        }

    def ensure_fresh_enough(self, context):
        from .conditional_inr import runtime, scheduler

        return scheduler.ensure_fresh_enough(
            context.config.workspace,
            context.generation_index,
            _config=context.config,
            _settings=self.settings,
            _max_training_lag=int(
                context.config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG
            ),
            _random_seed=int(context.config.OPTIMIZE_RANDOM_SEED),
            _training_data=runtime.training_data_from_session(
                context.session,
                context.snapshot,
            ),
        )

    def has_trained_state(self, context) -> bool:
        from .conditional_inr import runtime

        return bool(
            runtime.has_trained_state(
                context.config.workspace, _settings=self.settings
            )
        )

    def start_training(self, context):
        from .conditional_inr import runtime, scheduler

        return scheduler.start_training(
            context.config.workspace,
            generation_index=context.generation_index,
            block=False,
            _config=context.config,
            _settings=self.settings,
            _random_seed=int(context.config.OPTIMIZE_RANDOM_SEED),
            _training_data=runtime.training_data_from_session(
                context.session,
                context.snapshot,
            ),
        )

    def predict_population(self, context, population):
        from .conditional_inr import runtime

        return runtime.predict_population(
            context.config.workspace, population, _settings=self.settings
        )


@dataclass(frozen=True, slots=True)
class ConditionalINRPosteriorAdapter:
    """Explicit finite-ensemble posterior view over conditional INR.

    The wrapped component keeps its legacy GPSAF identity and tuple API. This
    adapter has a separate semantic identity so only strategies that opt into the
    joint posterior enter a new state namespace.
    """

    component: ConditionalINRComponent

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
                "configured_member_count": self.component.settings.ensemble_size,
                "member_selection": "seeded-permutation-cycles-v1",
                "candidate_evaluation": "fixed-member-full-grid-single-row-v1",
                "observation_noise_included": False,
                "calibrated": False,
            },
        )

    def exploitation_semantic_identity(self, config, problem) -> Mapping[str, object]:
        del config, problem
        return blocked_exploitation_identity(
            applicability_status=APPLICABILITY_NOT_APPLICABLE
        )

    def assess_posterior_exploitation(
        self, context, population
    ) -> PosteriorExploitationReadiness:
        del context
        return PosteriorExploitationReadiness.blocked(
            population,
            applicability_status=APPLICABILITY_NOT_APPLICABLE,
            failure_reasons=(
                "conditional-INR posterior architecture has no independent "
                "performance acceptance",
                "conditional-INR function draws are uncalibrated and non-transferable",
            ),
            diagnostics={"evidence_status": "compatibility-path-only"},
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
            component=self.component,
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
    data_filter_mode: str = DATA_FILTER_NONE
    frequency_filter: FrequencyFilter | None = None
    train_cfg: CAETrainConfig = DEFAULT_CAE_TRAIN_CONFIG
    device: str = "auto"

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
        data_filter_mode, frequency_filter = resolve_data_filter(
            mode=self.data_filter_mode,
            frequency_filter=self.frequency_filter,
        )
        train_cfg = self.train_cfg
        if (
            data_filter_mode == DATA_FILTER_FREQUENCY
            and not train_cfg.regime_head
        ):
            train_cfg = replace(
                train_cfg,
                regime_head=True,
                robust_loss_cap=(
                    4.0
                    if train_cfg.robust_loss_cap is None
                    else train_cfg.robust_loss_cap
                ),
            )
        if data_filter_mode == DATA_FILTER_NONE and train_cfg.regime_head:
            raise ValueError(
                "hierarchical CAE regime_head requires "
                "data_filter_mode='frequency'"
            )
        object.__setattr__(self, "groups", groups)
        object.__setattr__(self, "field_layouts", layouts)
        object.__setattr__(self, "axis_encodings", encodings)
        object.__setattr__(self, "data_filter_mode", data_filter_mode)
        object.__setattr__(self, "frequency_filter", frequency_filter)
        object.__setattr__(self, "train_cfg", train_cfg)
        object.__setattr__(
            self, "device", text("hierarchical_cae", "device", self.device)
        )

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
            "data_filter": {
                "mode": self.data_filter_mode,
                "frequency_filter": (
                    None
                    if self.frequency_filter is None
                    else self.frequency_filter.as_dict()
                ),
            },
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
            "device": self.device,
            "posterior": self.posterior_semantic_identity(config, None),
            "applicability": {
                "capability": "yadof.rawdata-applicability",
                "capability_version": 1,
                "enabled": self.data_filter_mode != DATA_FILTER_NONE,
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
                "data_filter": self.configuration_payload()["data_filter"],
                "observation_noise_included": False,
                "calibrated": False,
            },
        )

    def exploitation_semantic_identity(self, config, problem) -> Mapping[str, object]:
        del config, problem
        return blocked_exploitation_identity(
            applicability_status=(
                APPLICABILITY_UNCALIBRATED
                if self.data_filter_mode != DATA_FILTER_NONE
                else APPLICABILITY_NOT_APPLICABLE
            )
        )

    def assess_posterior_exploitation(
        self, context, population
    ) -> PosteriorExploitationReadiness:
        del context
        reasons = [
            "082608 hierarchical CAE remains experimental-performance-not-accepted",
            "082609 posterior calibration is uncalibrated and non-transferable",
        ]
        applicability_status = APPLICABILITY_NOT_APPLICABLE
        if self.data_filter_mode != DATA_FILTER_NONE:
            applicability_status = APPLICABILITY_UNCALIBRATED
            reasons.append(
                "082609 applicability calibration exposes no transferable probabilities"
            )
        return PosteriorExploitationReadiness.blocked(
            population,
            applicability_status=applicability_status,
            failure_reasons=reasons,
            diagnostics={
                "architecture_gate": "082608-active",
                "calibration_gate": "082609-active",
            },
        )

    def ensure_fresh_enough(self, context):
        from .hierarchical_cae import runtime, scheduler

        return scheduler.ensure_fresh_enough(
            context.config.workspace,
            context.generation_index,
            _config=context.config,
            _component=self,
            _max_training_lag=int(
                context.config.OPTIMIZE_SURROGATE_MAX_TRAINING_LAG
            ),
            _random_seed=int(context.config.OPTIMIZE_RANDOM_SEED),
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
            _random_seed=int(context.config.OPTIMIZE_RANDOM_SEED),
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


def pca_svd(
    *,
    decomposition: str = DEFAULT_PCA_SVD_SETTINGS.decomposition,
    rank: int = DEFAULT_PCA_SVD_SETTINGS.rank,
    predictor: str = DEFAULT_PCA_SVD_SETTINGS.predictor,
    ridge_alpha: float = DEFAULT_PCA_SVD_SETTINGS.ridge_alpha,
    field_mode: str = DEFAULT_PCA_SVD_SETTINGS.field_mode,
    rank_policy: str = DEFAULT_PCA_SVD_SETTINGS.rank_policy,
    solver: str = DEFAULT_PCA_SVD_SETTINGS.solver,
    dtype: str = DEFAULT_PCA_SVD_SETTINGS.dtype,
    device: str = DEFAULT_PCA_SVD_SETTINGS.device,
    power_iterations: int = DEFAULT_PCA_SVD_SETTINGS.power_iterations,
    seed: int = DEFAULT_PCA_SVD_SETTINGS.seed,
    fit_intercept: bool = DEFAULT_PCA_SVD_SETTINGS.fit_intercept,
    constant_atol: float = DEFAULT_PCA_SVD_SETTINGS.constant_atol,
) -> PCASVDComponent:
    """Build the opt-in deterministic PCA/SVD rawData surrogate."""

    return PCASVDComponent(
        PCASVDSettings(
            decomposition=decomposition,
            rank=rank,
            predictor=predictor,
            ridge_alpha=ridge_alpha,
            field_mode=field_mode,
            rank_policy=rank_policy,
            solver=solver,
            dtype=dtype,
            device=device,
            power_iterations=power_iterations,
            seed=seed,
            fit_intercept=fit_intercept,
            constant_atol=constant_atol,
        )
    )


def conditional_inr(
    *,
    constant_atol: float = DEFAULT_CONDITIONAL_INR_SETTINGS.constant_atol,
    target_scale_floor: float = DEFAULT_CONDITIONAL_INR_SETTINGS.target_scale_floor,
    device: str = DEFAULT_CONDITIONAL_INR_SETTINGS.device,
    epochs: int = DEFAULT_CONDITIONAL_INR_SETTINGS.epochs,
    ensemble_size: int = DEFAULT_CONDITIONAL_INR_SETTINGS.ensemble_size,
    batch_size: int = DEFAULT_CONDITIONAL_INR_SETTINGS.batch_size,
    learning_rate: float = DEFAULT_CONDITIONAL_INR_SETTINGS.learning_rate,
    weight_decay: float = DEFAULT_CONDITIONAL_INR_SETTINGS.weight_decay,
    loss_beta: float = DEFAULT_CONDITIONAL_INR_SETTINGS.loss_beta,
    max_nonfinite_fraction: float = DEFAULT_CONDITIONAL_INR_SETTINGS.max_nonfinite_fraction,
    x_latent_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.x_latent_dim,
    field_embedding_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.field_embedding_dim,
    coordinate_fourier_features: int = DEFAULT_CONDITIONAL_INR_SETTINGS.coordinate_fourier_features,
    hidden_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.hidden_dim,
    hidden_layers: int = DEFAULT_CONDITIONAL_INR_SETTINGS.hidden_layers,
    train_query_chunk: int = DEFAULT_CONDITIONAL_INR_SETTINGS.train_query_chunk,
    train_query_sample_count: int = DEFAULT_CONDITIONAL_INR_SETTINGS.train_query_sample_count,
    sample_batch_eval: int = DEFAULT_CONDITIONAL_INR_SETTINGS.sample_batch_eval,
    query_batch_eval: int = DEFAULT_CONDITIONAL_INR_SETTINGS.query_batch_eval,
    bootstrap_members: bool = DEFAULT_CONDITIONAL_INR_SETTINGS.bootstrap_members,
    bootstrap_fraction: float = DEFAULT_CONDITIONAL_INR_SETTINGS.bootstrap_fraction,
) -> ConditionalINRComponent:
    return ConditionalINRComponent(
        create_conditional_inr_settings(
            "conditional_inr",
            constant_atol=constant_atol,
            target_scale_floor=target_scale_floor,
            device=device,
            epochs=epochs,
            ensemble_size=ensemble_size,
            batch_size=batch_size,
            learning_rate=learning_rate,
            weight_decay=weight_decay,
            loss_beta=loss_beta,
            max_nonfinite_fraction=max_nonfinite_fraction,
            x_latent_dim=x_latent_dim,
            field_embedding_dim=field_embedding_dim,
            coordinate_fourier_features=coordinate_fourier_features,
            hidden_dim=hidden_dim,
            hidden_layers=hidden_layers,
            train_query_chunk=train_query_chunk,
            train_query_sample_count=train_query_sample_count,
            sample_batch_eval=sample_batch_eval,
            query_batch_eval=query_batch_eval,
            bootstrap_members=bootstrap_members,
            bootstrap_fraction=bootstrap_fraction,
        )
    )


def conditional_inr_posterior(
    *,
    constant_atol: float = DEFAULT_CONDITIONAL_INR_SETTINGS.constant_atol,
    target_scale_floor: float = DEFAULT_CONDITIONAL_INR_SETTINGS.target_scale_floor,
    device: str = DEFAULT_CONDITIONAL_INR_SETTINGS.device,
    epochs: int = DEFAULT_CONDITIONAL_INR_SETTINGS.epochs,
    ensemble_size: int = DEFAULT_CONDITIONAL_INR_SETTINGS.ensemble_size,
    batch_size: int = DEFAULT_CONDITIONAL_INR_SETTINGS.batch_size,
    learning_rate: float = DEFAULT_CONDITIONAL_INR_SETTINGS.learning_rate,
    weight_decay: float = DEFAULT_CONDITIONAL_INR_SETTINGS.weight_decay,
    loss_beta: float = DEFAULT_CONDITIONAL_INR_SETTINGS.loss_beta,
    max_nonfinite_fraction: float = DEFAULT_CONDITIONAL_INR_SETTINGS.max_nonfinite_fraction,
    x_latent_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.x_latent_dim,
    field_embedding_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.field_embedding_dim,
    coordinate_fourier_features: int = DEFAULT_CONDITIONAL_INR_SETTINGS.coordinate_fourier_features,
    hidden_dim: int = DEFAULT_CONDITIONAL_INR_SETTINGS.hidden_dim,
    hidden_layers: int = DEFAULT_CONDITIONAL_INR_SETTINGS.hidden_layers,
    train_query_chunk: int = DEFAULT_CONDITIONAL_INR_SETTINGS.train_query_chunk,
    train_query_sample_count: int = DEFAULT_CONDITIONAL_INR_SETTINGS.train_query_sample_count,
    sample_batch_eval: int = DEFAULT_CONDITIONAL_INR_SETTINGS.sample_batch_eval,
    query_batch_eval: int = DEFAULT_CONDITIONAL_INR_SETTINGS.query_batch_eval,
    bootstrap_members: bool = DEFAULT_CONDITIONAL_INR_SETTINGS.bootstrap_members,
    bootstrap_fraction: float = DEFAULT_CONDITIONAL_INR_SETTINGS.bootstrap_fraction,
) -> ConditionalINRPosteriorAdapter:
    return ConditionalINRPosteriorAdapter(
        conditional_inr(
            constant_atol=constant_atol,
            target_scale_floor=target_scale_floor,
            device=device,
            epochs=epochs,
            ensemble_size=ensemble_size,
            batch_size=batch_size,
            learning_rate=learning_rate,
            weight_decay=weight_decay,
            loss_beta=loss_beta,
            max_nonfinite_fraction=max_nonfinite_fraction,
            x_latent_dim=x_latent_dim,
            field_embedding_dim=field_embedding_dim,
            coordinate_fourier_features=coordinate_fourier_features,
            hidden_dim=hidden_dim,
            hidden_layers=hidden_layers,
            train_query_chunk=train_query_chunk,
            train_query_sample_count=train_query_sample_count,
            sample_batch_eval=sample_batch_eval,
            query_batch_eval=query_batch_eval,
            bootstrap_members=bootstrap_members,
            bootstrap_fraction=bootstrap_fraction,
        )
    )


def hierarchical_cae(
    *,
    groups=(),
    field_layouts=None,
    axis_encodings=None,
    data_filter_mode: str = DATA_FILTER_NONE,
    frequency_filter: FrequencyFilter | Mapping[str, object] | None = None,
    device: str = "auto",
    architecture_version: int = DEFAULT_CAE_TRAIN_CONFIG.architecture_version,
    token_dim: int = DEFAULT_CAE_TRAIN_CONFIG.token_dim,
    global_latent_dim: int = DEFAULT_CAE_TRAIN_CONFIG.global_latent_dim,
    group_latent_dim: int = DEFAULT_CAE_TRAIN_CONFIG.group_latent_dim,
    private_latent_dim: int = DEFAULT_CAE_TRAIN_CONFIG.private_latent_dim,
    codec_width: int = DEFAULT_CAE_TRAIN_CONFIG.codec_width,
    predictor_width: int = DEFAULT_CAE_TRAIN_CONFIG.predictor_width,
    predictor_layers: int = DEFAULT_CAE_TRAIN_CONFIG.predictor_layers,
    predictor_members: int = DEFAULT_CAE_TRAIN_CONFIG.predictor_members,
    codec_epochs: int = DEFAULT_CAE_TRAIN_CONFIG.codec_epochs,
    predictor_epochs: int = DEFAULT_CAE_TRAIN_CONFIG.predictor_epochs,
    fine_tune_epochs: int = DEFAULT_CAE_TRAIN_CONFIG.fine_tune_epochs,
    batch_size: int = DEFAULT_CAE_TRAIN_CONFIG.batch_size,
    inference_batch_size: int = DEFAULT_CAE_TRAIN_CONFIG.inference_batch_size,
    learning_rate: float = DEFAULT_CAE_TRAIN_CONFIG.learning_rate,
    weight_decay: float = DEFAULT_CAE_TRAIN_CONFIG.weight_decay,
    validation_fraction: float = DEFAULT_CAE_TRAIN_CONFIG.validation_fraction,
    early_stopping_patience: int = DEFAULT_CAE_TRAIN_CONFIG.early_stopping_patience,
    gradient_clip_norm: float = DEFAULT_CAE_TRAIN_CONFIG.gradient_clip_norm,
    bootstrap_fraction: float = DEFAULT_CAE_TRAIN_CONFIG.bootstrap_fraction,
    scale_floor: float = DEFAULT_CAE_TRAIN_CONFIG.scale_floor,
    minimum_samples: int = DEFAULT_CAE_TRAIN_CONFIG.minimum_samples,
    robust_loss_cap: float | None = DEFAULT_CAE_TRAIN_CONFIG.robust_loss_cap,
    applicability_loss_weight: float = DEFAULT_CAE_TRAIN_CONFIG.applicability_loss_weight,
    residual_gate_loss_weight: float = DEFAULT_CAE_TRAIN_CONFIG.residual_gate_loss_weight,
    regime_head: bool = DEFAULT_CAE_TRAIN_CONFIG.regime_head,
    filter_weighted_loss: bool = DEFAULT_CAE_TRAIN_CONFIG.filter_weighted_loss,
    shared_filter_isolation: bool = DEFAULT_CAE_TRAIN_CONFIG.shared_filter_isolation,
    gated_private_residual: bool = DEFAULT_CAE_TRAIN_CONFIG.gated_private_residual,
    coordinate_readout: bool = DEFAULT_CAE_TRAIN_CONFIG.coordinate_readout,
    coordinate_width: int = DEFAULT_CAE_TRAIN_CONFIG.coordinate_width,
    coordinate_layers: int = DEFAULT_CAE_TRAIN_CONFIG.coordinate_layers,
    coordinate_epochs: int = DEFAULT_CAE_TRAIN_CONFIG.coordinate_epochs,
    coordinate_points_per_field: int = DEFAULT_CAE_TRAIN_CONFIG.coordinate_points_per_field,
    coordinate_validation_points_per_field: int = DEFAULT_CAE_TRAIN_CONFIG.coordinate_validation_points_per_field,
    coordinate_query_batch_size: int = DEFAULT_CAE_TRAIN_CONFIG.coordinate_query_batch_size,
    coordinate_consistency_weight: float = DEFAULT_CAE_TRAIN_CONFIG.coordinate_consistency_weight,
    mixed_precision: bool = DEFAULT_CAE_TRAIN_CONFIG.mixed_precision,
    sharing: str = DEFAULT_CAE_TRAIN_CONFIG.sharing,
) -> HierarchicalCAEComponent:
    """Build the opt-in hierarchical CAE component from task-owned declarations."""

    return HierarchicalCAEComponent(
        groups=tuple(tuple(group) for group in groups),
        field_layouts={} if field_layouts is None else dict(field_layouts),
        axis_encodings={} if axis_encodings is None else dict(axis_encodings),
        data_filter_mode=data_filter_mode,
        frequency_filter=frequency_filter,
        train_cfg=CAETrainConfig(
            architecture_version=architecture_version,
            token_dim=token_dim,
            global_latent_dim=global_latent_dim,
            group_latent_dim=group_latent_dim,
            private_latent_dim=private_latent_dim,
            codec_width=codec_width,
            predictor_width=predictor_width,
            predictor_layers=predictor_layers,
            predictor_members=predictor_members,
            codec_epochs=codec_epochs,
            predictor_epochs=predictor_epochs,
            fine_tune_epochs=fine_tune_epochs,
            batch_size=batch_size,
            inference_batch_size=inference_batch_size,
            learning_rate=learning_rate,
            weight_decay=weight_decay,
            validation_fraction=validation_fraction,
            early_stopping_patience=early_stopping_patience,
            gradient_clip_norm=gradient_clip_norm,
            bootstrap_fraction=bootstrap_fraction,
            scale_floor=scale_floor,
            minimum_samples=minimum_samples,
            robust_loss_cap=robust_loss_cap,
            applicability_loss_weight=applicability_loss_weight,
            residual_gate_loss_weight=residual_gate_loss_weight,
            regime_head=regime_head,
            filter_weighted_loss=filter_weighted_loss,
            shared_filter_isolation=shared_filter_isolation,
            gated_private_residual=gated_private_residual,
            coordinate_readout=coordinate_readout,
            coordinate_width=coordinate_width,
            coordinate_layers=coordinate_layers,
            coordinate_epochs=coordinate_epochs,
            coordinate_points_per_field=coordinate_points_per_field,
            coordinate_validation_points_per_field=coordinate_validation_points_per_field,
            coordinate_query_batch_size=coordinate_query_batch_size,
            coordinate_consistency_weight=coordinate_consistency_weight,
            mixed_precision=mixed_precision,
            sharing=sharing,
        ),
        device=device,
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
    from .linear_subspace.scheduler import deactivate_workspace as linear_subspace

    conditional_status = conditional(*args, **kwargs)
    hierarchical(*args, **kwargs)
    linear_subspace(*args, **kwargs)
    return conditional_status

__all__ = [
    "APPLICABILITY_CALIBRATED",
    "APPLICABILITY_NOT_APPLICABLE",
    "APPLICABILITY_UNCALIBRATED",
    "APPLICABILITY_METHOD",
    "CALIBRATED",
    "ConditionalINRComponent",
    "ConditionalINRPosteriorAdapter",
    "EXPERIMENTAL_PERFORMANCE_STATUS",
    "FIELD_SPREAD_METHOD",
    "HierarchicalCAEComponent",
    "PCASVDComponent",
    "PCASVDSettings",
    "NOT_APPLICABLE",
    "POSTERIOR_CALIBRATION_PROTOCOL",
    "POSTERIOR_CALIBRATION_PROTOCOL_VERSION",
    "POSTERIOR_EXPLOITATION_PROTOCOL",
    "POSTERIOR_EXPLOITATION_PROTOCOL_VERSION",
    "POSTERIOR_CALIBRATED",
    "POSTERIOR_UNCALIBRATED",
    "PERFORMANCE_ACCEPTED",
    "PERFORMANCE_NOT_ACCEPTED",
    "UNCALIBRATED",
    "ApplicabilityCalibration",
    "CalibratedRawDataPosteriorSampler",
    "CAETrainConfig",
    "CoordinatePrediction",
    "DiagnosticCondition",
    "DiagnosticRegimeRule",
    "FieldSpreadCalibration",
    "FrequencyFilter",
    "PosteriorCalibrationArtifact",
    "PosteriorExploitationReadiness",
    "PosteriorExploitationSurrogate",
    "FrequencyFilterRule",
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
    "pca_svd",
    "deactivate_workspace",
    "ensure_fresh_enough",
    "assess_spread_scale",
    "calibrated_applicability_prediction",
    "calibration_identity_signature",
    "fit_monotone_applicability_calibration",
    "has_trained_state",
    "latest_state_generation",
    "predict_population",
    "posterior_capability_identity",
    "project_rawdata_sampler",
    "require_rawdata_posterior_surrogate",
    "require_posterior_exploitation_surrogate",
    "start_training",
    "select_conservative_spread_scale",
    "train",
    "transform_applicability_members",
    "wait_for_pending_training",
]
