"""Public deterministic component; numerical backends load only on use."""

from dataclasses import dataclass

from .settings import AmplitudeGPSettings, DEFAULT_AMPLITUDE_GP_SETTINGS as _DEFAULT


@dataclass(frozen=True, slots=True)
class AmplitudeGPComponent:
    settings: AmplitudeGPSettings

    def validate(self, config, problem):
        from .runtime import backend_versions
        backend_versions()

    def semantic_identity(self, config, problem):
        from .runtime import backend_versions
        return {
            "component": "amplitude-shape-gp-rawdata-surrogate", "component_version": 2,
            "backends": backend_versions(), "controlled_parameters": self.settings.semantic_parameters(),
            "training_policy": "field-minimum-asinh-span-log-shape-pca-matern-ard",
            "gp_row_policy": "stable-cost-elite-and-farthest-coverage",
            "prediction_statistic": "central-transformed-response", "posterior_capability": False,
            "cost_policy": "snapshot-cost-of-predicted-full-rawdata",
            "input_recovery_policy": "exact-committed-physical-roundtrip",
        }

    def training_data(self, dataset, cost_table, *, row_ids=None, transform_id=None):
        from .runtime import ordered_training_data
        return ordered_training_data(dataset, cost_table, row_ids=row_ids, transform_id=transform_id)

    def start_fit(self, workspace, training_data, *, generation_index=0, session=None, snapshot=None):
        from .runtime import start_fit
        return start_fit(workspace, training_data, generation_index=generation_index, settings=self.settings,
                         session=session, snapshot=snapshot)

    def fit(self, workspace, training_data, *, generation_index=0, session=None, snapshot=None):
        from .runtime import fit
        return fit(workspace, training_data, generation_index=generation_index, settings=self.settings,
                   session=session, snapshot=snapshot)

    def recover(self, workspace, training_data, *, snapshot=None):
        from .runtime import recover
        return recover(workspace, training_data, settings=self.settings, snapshot=snapshot)

    def predict(self, state, normalized_parameters, *, snapshot):
        from .runtime import predict
        return predict(state, normalized_parameters, snapshot=snapshot)

    def _compatible_state(self, context, training_data):
        from .runtime import recover
        return recover(context.config.workspace, training_data, settings=self.settings,
                       snapshot=context.snapshot, allow_lagged=True)

    def predict_for_selection(self, context, population, training_data=None):
        state = self._compatible_state(context, training_data)
        if state is None:
            raise RuntimeError("amplitude_gp has no compatible fitted state for this evidence and interpretation")
        return self.predict(state, population, snapshot=context.snapshot)

    def has_trained_state(self, context, training_data):
        return self._compatible_state(context, training_data) is not None

    def latest_trained_generation(self, context, training_data):
        state = self._compatible_state(context, training_data)
        return None if state is None else state.generation_index

    def ensure_fresh_enough(self, context, training_data):
        from .scheduler import ensure_fresh_enough
        return ensure_fresh_enough(context, training_data, self.settings)

    def start_training(self, context, training_data):
        from .scheduler import start
        return start(context, training_data, self.settings)

    def finish_training(self, context):
        from .scheduler import finish
        return finish(context.config.workspace, self.settings)


def amplitude_gp(
    *, shape_rank: int = _DEFAULT.shape_rank, gp_max_rows: int = _DEFAULT.gp_max_rows,
    elite_fraction: float = _DEFAULT.elite_fraction,
    minimum_training_samples: int = _DEFAULT.minimum_training_samples,
    random_seed: int = _DEFAULT.random_seed, optimizer_iterations: int = _DEFAULT.optimizer_iterations,
    optimizer_factr: float = _DEFAULT.optimizer_factr, kernel_amplitude: float = _DEFAULT.kernel_amplitude,
    kernel_amplitude_bounds: tuple[float, float] = _DEFAULT.kernel_amplitude_bounds,
    length_scale: float = _DEFAULT.length_scale,
    length_scale_bounds: tuple[float, float] = _DEFAULT.length_scale_bounds,
    matern_nu: float = _DEFAULT.matern_nu, noise_level: float = _DEFAULT.noise_level,
    noise_level_bounds: tuple[float, float] = _DEFAULT.noise_level_bounds,
    alpha: float = _DEFAULT.alpha, constant_tolerance: float = _DEFAULT.constant_tolerance,
    numerical_floor: float = _DEFAULT.numerical_floor,
    span_floor_relative: float = _DEFAULT.span_floor_relative,
    minimum_scale_quantile: float = _DEFAULT.minimum_scale_quantile,
    minimum_scale_std_fraction: float = _DEFAULT.minimum_scale_std_fraction,
) -> AmplitudeGPComponent:
    """Build the opt-in amplitude/shape GP with explicit scientific parameters."""
    return AmplitudeGPComponent(AmplitudeGPSettings(
        shape_rank=shape_rank, gp_max_rows=gp_max_rows, elite_fraction=elite_fraction,
        minimum_training_samples=minimum_training_samples, random_seed=random_seed,
        optimizer_iterations=optimizer_iterations, optimizer_factr=optimizer_factr,
        kernel_amplitude=kernel_amplitude, kernel_amplitude_bounds=kernel_amplitude_bounds,
        length_scale=length_scale, length_scale_bounds=length_scale_bounds, matern_nu=matern_nu,
        noise_level=noise_level, noise_level_bounds=noise_level_bounds, alpha=alpha,
        constant_tolerance=constant_tolerance, numerical_floor=numerical_floor,
        span_floor_relative=span_floor_relative, minimum_scale_quantile=minimum_scale_quantile,
        minimum_scale_std_fraction=minimum_scale_std_fraction,
    ))
