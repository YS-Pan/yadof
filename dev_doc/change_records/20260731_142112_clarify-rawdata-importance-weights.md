# 2026-07-31 14:21 - Clarify RawData Importance Weights

## Context

- Task-authoring guidance could let “include all saved far-field rawData in the
  surrogate” be misread as “mark the entire far field important.”
- A one-axis frequency mask on multidimensional gain data broadcasts across every
  remaining angle and can give much more of the field elevated training attention
  than the cost function actually observes.

## Change

- Separated workflow rawData saving, surrogate training-bundle inclusion, and
  importance weighting in the user workflow and cost-authoring guides.
- Documented exact `floor`, `floor + boost`, full-query weighted-loss, and
  stochastic query-sampling semantics.
- Added an axis-order-independent gain example that marks the Cartesian intersection
  of frequency, `Phi`, and `Theta`, plus an explicit warning about single-axis
  broadcasting.
- Clarified the HFSS full-matrix export guidance and updated current architecture,
  blueprints, and terminology with the non-inclusion contract.

## Rationale

- Saving the complete far-field grid is what preserves it for surrogate modeling.
  Importance weights should mirror objective observation positions and should not
  be used as a proxy for data inclusion.

## Impact

- AI agents authoring HFSS and other multidimensional tasks receive an explicit,
  testable distinction between full-field coverage and objective-region emphasis.
- Runtime behavior and public APIs are unchanged.

## Follow-Up

- Existing workspaces may review broad one-axis masks against the selectors used by
  their current `calculate_cost()` implementation.
