# 2026-07-31 10:54 - Surrogate Off-Grid rawData Query

## Context

- The viewer already exposed every rawData dimension but fixed-axis values were
  resolved only to stored checkpoint coordinates.
- An earlier assessment assumed arbitrary output-coordinate inference required a
  new training contract, checkpoint migration, and rawData schema change.
- Inspection showed that existing conditional-INR artifacts already contain the
  decoder, physical axis metadata, three-column coordinate table, field IDs, and
  per-query target scaler needed for a compatibility-preserving query path.

## Change

- Added a surrogate runtime query for one modeled rawData slot at arbitrary
  physical coordinates.
- Kept full-grid prediction, training, checkpoint serialization, reconstruction,
  optimizer screening, and historical audits on their existing path.
- Reused exact coordinate normalization and scaler entries at stored points.
  Between grid points, target mean/scale are linearly interpolated before inverse
  scaling; outside the stored range scaler values clamp to endpoints while the
  decoder coordinate remains an extrapolation.
- Added a checkpoint-grid dropdown and a free numeric entry for every unplotted
  viewer dimension.
- Routed only genuinely off-grid plot requests through the new runtime query.
  Stored-grid requests continue to use the reconstructed full sample.
- Suppressed recorded rawData overlays for off-grid coordinates and added a note
  that objective bars still use the checkpoint grid.
- Added regression coverage proving that stored-grid direct-query output is
  identical to the legacy decoder/scaler result and that an intermediate
  coordinate yields an additional prediction.

## Rationale

- This extension adds useful interpolation without perturbing existing optimizer
  or viewer behavior at checkpoint grid points.
- Keeping the old path intact is stronger compatibility evidence than routing all
  prediction through a generalized implementation.
- A real overlay at an unrecorded coordinate would imply evidence that does not
  exist, so it is omitted rather than interpolated for display.

## Impact

- Existing checkpoint files remain readable and need no migration or retraining.
- Grid-point rawData and cost predictions are unchanged.
- Off-grid rawData plots are model inferences; values outside the training axis
  range are extrapolations and should be interpreted cautiously.
- Current checkpoints encode only the first three rawData coordinate dimensions.
  Higher dimensions may remain on their full stored grid but require a future
  model-coordinate extension before they can be changed independently.

## Follow-Up

- If general callers beyond the viewer need partial rawData queries, design a
  higher-level public result contract around the runtime slot-query primitive.
- Any future increase beyond three encoded rawData coordinates requires an
  explicit model/checkpoint-version design and migration policy.
