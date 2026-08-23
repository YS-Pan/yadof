from . import conditional_inr as _conditional_inr_package
from .api import (
    ConditionalINRComponent,
    conditional_inr,
    deactivate_workspace,
    ensure_fresh_enough,
    has_trained_state,
    latest_state_generation,
    predict_population,
    start_training,
    train,
    wait_for_pending_training,
)

# Load the private package before rebinding the same public factory name. This keeps
# ``yadof.surrogate.conditional_inr`` callable after private implementation imports.

__all__ = [
    "ConditionalINRComponent",
    "conditional_inr",
    "deactivate_workspace",
    "ensure_fresh_enough",
    "has_trained_state",
    "latest_state_generation",
    "predict_population",
    "start_training",
    "train",
    "wait_for_pending_training",
]
