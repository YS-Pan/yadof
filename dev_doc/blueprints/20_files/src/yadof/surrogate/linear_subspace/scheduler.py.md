# Blueprint: `surrogate/linear_subspace/scheduler.py`

## Contract

Own a workspace/strategy/settings-keyed facade over one public `TrainingHandle`.
Every freshness/state/start call requires the exact explicit training value and
its content digest; no scheduler query scans history. Blocking and background
training share the same runtime fit path, expose bounded cached failure status,
lease the caller's exact generation snapshot, and are drained on strategy
deactivation. Releasing memory never deletes retained compatible checkpoint
artifacts.

The blocking `ensure_fresh_enough()` operation is an explicit component call for
direct users. GPSAF selection uses the read-only component freshness value, then
the workspace program calls background start/wait after real evaluation has
started.
