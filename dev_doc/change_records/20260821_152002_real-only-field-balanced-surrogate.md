# 2026-08-21 15:20 - Real-Only Field-Balanced Surrogate

## Context

- Conditional-INR training combined real rawData with synthetic mixup targets,
  task-owned positional importance, weighted sampling/loss, relative loss, and
  rank-forced queries. Those overlapping heuristics made poor real-task behavior
  difficult to attribute.
- GPSAF retained historical training-error/noise and interval handoff surfaces even
  though live alpha/beta survival selected only from mean predicted costs.
- Checkpoints lacked one explicit semantic identity and publication protocol able
  to isolate method/config/task changes while retaining real evidence and inactive
  artifacts.

## Change

- Reduced conditional-INR training to recorded real rows or seeded bootstrap draws,
  one pointwise Smooth L1 objective, seeded without-replacement query sampling, and
  per-field mean followed by equal field macro averaging. A too-short finite
  epoch/batch schedule now extends only enough to complete one rotation cycle in
  which every active field has the same number of appearances.
- Removed mixup, relative loss, task-owned rawData importance, query weights,
  forced-query ranking, their five workspace settings, job-template APIs/helpers,
  example hook, checkpoint/state fields, and active documentation. Remaining legacy
  task hooks fail validation instead of becoming silent no-ops.
- Removed historical training-error/noise/probabilistic GPSAF helpers and the public
  historical-error API. Surrogate member min/max spread remains an uncalibrated
  prediction/viewer diagnostic but no longer enters optimizer candidate records.
- Introduced versioned `conditional_inr` / `real_field_balanced` manifests and a
  SHA-256 semantic signature over parameter names and normalization ranges/levels,
  rawData query/schema identity, training configuration, and Torch version.
- Published complete artifact directories atomically, wrote a root convenience
  pointer, and used the unique semantic-namespace manifest as the final commit
  record. Runtime recovery scans only the expected semantic namespace, enabling a
  compatible A-to-B-to-A return without cross-loading or deleting either artifact.
- Updated viewer discovery to select the newest committed publication per generation,
  validate each artifact against its own persisted train config/runtime version,
  and filter parameter-normalization-incompatible checkpoints before an audit.
- Made non-trainable/skipped attempts metadata-only: they do not become active
  prediction state or make GPSAF consume all-infinite surrogate rows.

## Rationale

- Equal field macro loss prevents a large array or duplicated slot count from
  silently dominating a smaller rawData field, while real-only evidence keeps every
  target traceable to an evaluation.
- Parameter ranges and levels define normalized-input meaning; names alone cannot
  safely identify a recoverable model.
- An immutable namespaced commit record separates complete recovery evidence from a
  replaceable root pointer and preserves compatible historical strategies without
  accepting interrupted publication debris.
- Training-fit error and uncalibrated ensemble spread are not out-of-sample trust
  evidence and therefore must not steer GPSAF implicitly.

## Impact

- Workspaces using any removed setting now fail as unknown configuration. A task
  that still defines `rawdata_importance_weights()` fails `yadof check` with a
  deletion diagnostic.
- Existing real recorded data is untouched. Old-format or semantically incompatible
  checkpoint artifacts may remain on disk but are never recovered by the new reader.
- INR training may execute more epochs than configured only when required to finish
  one equal-appearance field rotation cycle; metadata records configured and
  effective epochs.
- Current `calc_cost.py` continues to interpret both real and predicted rawData, and
  ensemble mean/min-max public prediction remains available.

## Verification

- Built `yadof-0.3.0-py3-none-any.whl`, force-reinstalled it into the workspace
  virtual environment, and confirmed imports resolve below `.venv/Lib/site-packages`.
- Confirmed installed packaged user documentation contains the field-balanced policy.
- Passed 69 focused surrogate/job-template/config/viewer tests.
- Passed the complete installed-package suite: 258 tests, with 8 expected warnings
  from deliberate loss-tolerant-recording failure tests.
- Used an independent `gpt-5.6-sol` agent at maximum reasoning with no parent context
  to read the toDo and implementation; all seven actionable findings were assessed,
  accepted, fixed, and covered by regression tests.
- No real simulator or HTCondor execution was started.

## Follow-Up

- The manual toDo remains active and the implementation is not declared the
  production baseline until the user confirms the real benchmark suite, metrics,
  thresholds, and acceptable tradeoffs and that gate passes.
- Ensemble trust calibration remains separate future work; benchmark failure must
  be addressed within the real-only design and must not restore synthetic targets or
  task-specific importance.
