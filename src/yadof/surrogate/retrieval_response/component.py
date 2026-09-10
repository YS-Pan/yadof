"""Public deterministic component; numerical backends load only on use."""

from dataclasses import dataclass

from .settings import RetrievalResponseSettings, DEFAULT_RETRIEVAL_RESPONSE_SETTINGS as _DEFAULT


@dataclass(frozen=True, slots=True)
class RetrievalResponseComponent:
    settings: RetrievalResponseSettings

    def validate(self, config, problem):
        from .runtime import backend_versions
        backend_versions()

    def semantic_identity(self, config, problem):
        from .runtime import backend_versions
        return {
            "component": "retrieval-response-rawdata-surrogate", "component_version": 1,
            "backends": backend_versions(), "controlled_parameters": self.settings.semantic_parameters(),
            "training_policy": "own-prior-field-balanced-joint-neighbor-response-correction",
            "prediction_statistic": "mean-latent-then-complete-response", "posterior_capability": False,
            "cost_policy": "snapshot-cost-of-predicted-full-rawdata",
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
            raise RuntimeError("retrieval_response has no compatible fitted state for this evidence and interpretation")
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


def retrieval_response(
    *,
    random_seed: int = _DEFAULT.random_seed,
    neighbors: int = _DEFAULT.neighbors,
    shape_rank: int = _DEFAULT.shape_rank,
    hidden_width: int = _DEFAULT.hidden_width,
    members: int = _DEFAULT.members,
    steps: int = _DEFAULT.steps,
    validation_steps: int = _DEFAULT.validation_steps,
    validation_fraction: float = _DEFAULT.validation_fraction,
    batch_size: int = _DEFAULT.batch_size,
    learning_rate: float = _DEFAULT.learning_rate,
    weight_decay: float = _DEFAULT.weight_decay,
    gradient_clip: float = _DEFAULT.gradient_clip,
    minimum_training_samples: int = _DEFAULT.minimum_training_samples,
    prediction_chunk: int = _DEFAULT.prediction_chunk,
    constant_tolerance: float = _DEFAULT.constant_tolerance,
    numerical_floor: float = _DEFAULT.numerical_floor,
    span_floor_relative: float = _DEFAULT.span_floor_relative,
) -> RetrievalResponseComponent:
    """Build the experimental CPU retrieval response surrogate."""
    return RetrievalResponseComponent(RetrievalResponseSettings(
        random_seed=random_seed,
        neighbors=neighbors,
        shape_rank=shape_rank,
        hidden_width=hidden_width,
        members=members,
        steps=steps,
        validation_steps=validation_steps,
        validation_fraction=validation_fraction,
        batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        gradient_clip=gradient_clip,
        minimum_training_samples=minimum_training_samples,
        prediction_chunk=prediction_chunk,
        constant_tolerance=constant_tolerance,
        numerical_floor=numerical_floor,
        span_floor_relative=span_floor_relative,
    ))
