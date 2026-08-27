# Blueprint: integrated surrogate checkpoint viewer

## Intent

Provide an optional yadof GUI and terminal tool for understanding saved surrogate
checkpoints. It must let a user explore one prediction, compare it with recorded
real evidence, obtain bounded metadata as text/JSON, and audit checkpoint accuracy
across generations without mutating the selected workspace. CLI/parser imports
remain lightweight until the user explicitly selects a viewer mode.

## Main Contracts

Interactive prediction:

```text
selected checkpoint + normalized parameter vector
  -> predicted rawData + ensemble members
  -> current workspace cost calculation
  -> rawData curve and objective plots
```

Cross-generation audit:

```text
same per-generation sampled real individuals
  × every valid checkpoint
  -> predicted costs and modeled rawData scalars
  -> relative/absolute sum-count aggregates
  -> instantly selectable 2-D error matrix
```

Terminal reporting:

```text
workspace/checkpoint/task metadata
  -> bounded summary payload
  -> human text or schema-versioned JSON

one complete cross-generation audit
  + exact metric/quantity selection
  -> stdout matrix report
```

## End-To-End Responsibilities

1. Load one explicit compatible yadof workspace.
2. Resolve the workspace's active strategy pointer, select one compatible declared
   `conditional-inr` or experimental `hierarchical-cae` component namespace, and
   discover usable generations only within that scope while excluding broken/skipped
   placeholders. Never mix methods in one view.
3. Present normalized parameter controls while displaying denormalized physical
   values.
4. List every dimension of the selected rawData output; accept zero to two plot
   dimensions and a stored-grid or arbitrary finite fixed coordinate for every
   remaining dimension.
5. Predict rawData and current costs in a background worker.
6. Reuse the method's full-grid slice or query its supported off-grid path
   (conditional decoder/scaler or hierarchical all-axis in-domain readout), then
   display a scalar, curve, or filled two-dimensional color contour.
7. Optionally load one recorded individual for true/predicted comparison.
8. Sample each historical generation independently for an audit.
9. Use every checkpoint to predict the same selected rows.
10. Aggregate cost and per-rawData errors without retaining large prediction
   histories.
11. Render a discrete generation-by-generation heatmap.
12. Support cooperative stop and visible failure reporting.
13. Print summary metadata without model loading or a window.
14. Print selected audit matrices as text/JSON, keeping progress off stdout.

## Boundaries

- Viewer subtree: GUI, plots, terminal reporting, read-only adapter, aggregate
  contracts, and nested developer documentation below `yadof.tools`.
- Enclosing yadof package: CLI routing, workspace/task/record/checkpoint/rawData
  mechanisms, model implementation, packaging, and maintained tests.
- Selected workspace: external immutable inputs and evidence for the viewer.
- Simulator/optimizer/trainer: explicitly out of scope.

## Data Ownership

Real records/rawData and checkpoints remain owned by the workspace. Predicted
rawData, member spread, predicted costs, and audit aggregates are derived
session-local data. Nothing in the viewer becomes authoritative optimization
history.

The aggregate cache stores only finite error sums and counts. It intentionally
trades support for distribution metrics such as median/P90 for low memory and
instant switching among pre-aggregated means.

## Concurrency, Failure, And Recovery

A single executor worker performs model operations. Worker callbacks enter a queue
drained by the Tk main thread. Serials invalidate stale prediction/audit results,
and an event cooperatively stops audits at batch boundaries.

Failures are visible and preserve previously complete display state. There is no
retry that silently switches checkpoints, no repair of incompatible evidence, and
no persistence recovery because the viewer writes no audit cache.

## Invariants

- All workspace access is explicit and read-only.
- Reports identify the active strategy/run/component scope and never mix retained
  inactive namespaces.
- Relative error uses
  `abs(prediction - truth) / max(abs(truth), configured epsilon)`.
- Cost errors aggregate by objective; rawData errors aggregate by named rawData
  item and may also be combined across all modeled scalars.
- Heatmap x is checkpoint generation; y is optimization generation.
- Heatmap blocks are discrete, tick-centered, edge-complete, non-interpolated, and
  not forced square. Neighboring blocks have no drawn borders or gaps.
- Interactive rawData selection accepts at most two plot dimensions; every other
  dimension has a grid dropdown and free numeric entry.
- Stored coordinates retain legacy full-grid values; off-grid coordinates never
  fabricate recorded truth or modify the checkpoint.
- Metric/quantity switching after a complete audit performs no model inference.
- Cancellation never promotes partial aggregate state.
- Terminal JSON replaces non-finite matrix cells with `null`; optional progress
  goes only to stderr and reports are never persisted.

## Verification Boundary

Unit tests cover checkpoint discovery, curve extraction, aggregate selection,
sampling, cancellation, deterministic text/JSON reporting, and Tcl-popup ancestry
handling. Compile/import/CLI smoke checks cover the installed nested module, lazy
GUI/summary/audit registration, and artifact membership. Real-workspace checks
cover yadof checkpoint compatibility and error-array shapes. Hidden Tk checks cover
focus handlers and plot layout without launching a simulator.
