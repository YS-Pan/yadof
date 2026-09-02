# 2026-07-31 10:35 - Default Real Comparison And Seamless Heatmap

## Context

- The interactive viewer loaded with no real-result comparison even when completed
  generations were available.
- Cross-generation heatmap cells used contrasting borders that made the plot look
  like separated tiles.
- Arbitrary rawData-coordinate input was considered, but current checkpoints bind
  the query table, per-query target scaler, and reconstructed output schema to a
  fixed grid.

## Change

- Workspace loading now selects a random available optimization generation and a
  random real individual from that generation before the initial prediction.
- Initial selection reuses the same individual-list population path as subsequent
  generation changes.
- Heatmap cells now use zero line width and no edge color, so adjacent cells touch
  without visible grid lines or gaps.
- Documented that true off-grid rawData inference requires changes to core
  surrogate training/checkpoint/reconstruction contracts rather than a viewer-only
  control.

## Rationale

- A default real comparison makes the first interactive view immediately useful
  while preserving manual selection and clear-overlay behavior.
- Removing only mesh edges preserves discrete, non-interpolated cells and complete
  outer bounds.
- The viewer must not label display interpolation as direct surrogate inference.

## Impact

- Only read-only viewer selection and presentation behavior changes.
- Surrogate model training, checkpoint artifacts, rawData reconstruction,
  optimization, and workspace persistence are unchanged.

## Follow-Up

- Supporting direct arbitrary rawData coordinates would require a separately
  designed yadof surrogate API and checkpoint migration/compatibility plan.
