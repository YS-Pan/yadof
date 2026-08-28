# Blueprint: `surrogate/linear_subspace/scheduler.py`

## Contract

Own an independent one-worker, workspace/strategy/settings-keyed scheduler with
freshness checks, blocking and background training, bounded failure reporting,
generation-snapshot lifetime, and deactivation. Releasing memory never deletes
retained compatible checkpoint artifacts.
