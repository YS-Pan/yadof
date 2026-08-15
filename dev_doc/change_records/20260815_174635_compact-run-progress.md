# 2026-08-15 17:46 - Compact run progress output

## Context

- A normal fast optimization printed a redundant fast worker-plan line for every
  generation, as well as generation `start` and `finished` lifecycle markers.
- The population progress bar already provides the useful per-generation status.

## Change

- Removed the recurring fast worker-plan progress message while preserving the plan
  in each evaluation's metadata.
- Removed generation lifecycle progress messages from the optimization loop.
- Added CLI and fast-evaluation regression tests for the compact output.
- Updated user and developer documentation to describe the retained progress and
  diagnostic behavior.

## Rationale

- Repeating static planning and lifecycle messages obscures the progress signal
  without adding runtime control or diagnostic value.

## Impact

- `yadof run` and fast evaluation retain outcome counts, backend diagnostics, and
  persisted fast worker-plan metadata, with fewer per-generation terminal lines.

## Follow-Up

- None.
