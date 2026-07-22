# 2026-07-20 11:34 - Large-Scale `test_com` Profile

## Context

A task-level stress test needed a deterministic pure-Python evaluator with 30
optimization inputs and separate scalar, curve, surface, and volume rawData blocks.
The existing generic profile was intentionally small and the HFSS-like profile had
different fixed shapes.

## Change

- Added `profile="large_scale"` to the packaged `test_com.py` adapter, with `large`
  and `stress` aliases.
- Added two scalar blocks, two 20-point curves, one `100 x 100` surface, and one
  `5 x 100 x 100` volume, stored as deterministic `float32` arrays.
- Kept the new profile's 30-input latent mapping separate from the existing
  20-input profiles so their established responses do not change.
- Added an installed-resource test for names, shapes, dtypes, metadata, and
  deterministic alias behavior.
- Documented the profile and its package/workspace ownership boundary.

## Rationale

A reusable profile exercises rawData recording and conditional-INR surrogate
training without requiring simulator software. The adapter owns response shapes,
while each workspace continues to own objective windows and cost policy.

## Impact

Existing `hfss_like` and `generic` callers are unchanged. Workspaces can copy the
updated adapter and opt into `large_scale`; no new runtime dependency is required.

## Follow-Up

None.
