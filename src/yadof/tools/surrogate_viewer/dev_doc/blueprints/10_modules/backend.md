# Module blueprint: backend

## Intent

Adapt the enclosing yadof package's workspace/checkpoint contracts into small,
read-only values and use-case methods suitable for a desktop viewer.

## Functionalities

- Discover valid saved checkpoints in generation order.
- Load effective workspace configuration, parameters, objectives, records, and one
  rawData template.
- Validate a checkpoint against current parameter names and rawData schema.
- Load conditional-INR artifacts onto the configured device.
- Predict reconstructed rawData, optional ensemble-member samples, and current
  costs.
- Load true samples/costs for recorded comparisons.
- Sample every optimization generation independently.
- Batch audit inference with CUDA-oriented sample batching and OOM fallback.
- Flatten true rawData through each checkpoint's modeled slots.
- Aggregate absolute and relative errors by cost and rawData item.
- Derive display matrices from small in-memory aggregate arrays.
- Describe every named or index-fallback dimension of generic rawData.
- Extract user-selected zero-, one-, or two-dimensional stored-grid slices.
- Query one rawData slot at arbitrary fixed physical coordinates and convert the
  resulting member grids into plot values.
- Derive pointwise finite minimum/maximum bounds from compatible ensemble-member
  slices for interactive display.

## I/O Format

Public inputs are a workspace path, checkpoint generation, normalized vector,
optional real job name, audit sample fraction, optional seed/cancel event, and
progress callback. Interactive slicing additionally accepts a rawData item index,
an ordered tuple of zero to two dimension indices, and fixed coordinate values for
the remaining dimensions. Grid coordinates retain the legacy full-sample result;
off-grid coordinates return immutable direct-query plot values whose rank equals
the number of selected dimensions.

Important output shapes:

```text
cost aggregates:
  [optimization_generation, checkpoint_generation, objective]

rawData aggregates:
  [optimization_generation, checkpoint_generation, rawData_item]

display matrix:
  [optimization_generation, checkpoint_generation]
```

Every aggregate has separate sums and counts for relative and absolute error.
Non-finite error elements add neither sum nor count.

## Non-Obvious Techniques

- Checkpoint JSON may exist for skipped/empty generations; discovery requires a
  usable flat schema and positive member count.
- True rawData is flattened separately for each distinct checkpoint schema and may
  be cached across identical schemas during one audit.
- rawData item aggregates use modeled-slot ranges, so multiple modeled fields in
  one item combine correctly and unmodeled metadata contributes nothing.
- Predicted costs are recalculated through the current workspace task instead of
  being frozen in checkpoint metadata.
- CUDA audit inference requests a larger sample batch than interactive prediction
  and halves it after out-of-memory until the checkpoint-configured baseline.
- Only one interactive predictor is cached; audit predictors are released after
  each checkpoint.
- Missing or non-finite stored axis coordinates fall back to dimension indices for
  display.
- The workspace detects stored fixed coordinates before querying. This preserves
  the old full-grid path exactly and suppresses recorded truth only for off-grid
  plots.
- Off-grid inverse scaling linearly interpolates checkpoint target mean/scale;
  checkpoint files and the optimizer/audit reconstruction path are not changed.

## Mutability Profile

Sampling controls, batching, metadata display, and supported matrix metrics may
evolve. Workspace read-only behavior, schema validation, array axis meaning,
current-cost interpretation, cancellation semantics, and no-partial-audit
publication should remain stable.

Package-internal yadof imports are an intentional adapter boundary. They may change
with the owning surrogate/rawData implementation, but must not leak into UI modules
or become an external viewer API.
