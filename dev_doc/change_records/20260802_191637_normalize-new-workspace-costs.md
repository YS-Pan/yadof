# 2026-08-02 19:16 - Normalize New Workspace Costs

## Context

- A generated PLL workspace returned lock time in microseconds and frequency error
  in MHz directly as optimizer objectives, so objective magnitude depended on
  physical units rather than task preference.
- Existing yadof defined-cost helpers already used a tanh mapping, but the user
  workflow did not make normalized cost a mandatory authoring rule and the generic
  starter returned its raw scalar response unchanged.

## Change

- User guidance now requires every newly authored task objective to be an
  independent dimensionless minimization cost in `[0, 1]`, using fixed physical
  `goal`/`worst` thresholds and `error_cost=1.0`.
- The guidance explicitly rejects history-, population-, and batch-dependent
  min/max scaling, distinguishes task fallback `1.0` from framework execution
  failure `inf`, and shows `soft_cost()` use in custom rawData callbacks. It also
  defines `goal`/`worst` as `0.1`/`0.9` calibration anchors rather than hard
  `0`/`1` clipping bounds, preserving informative tanh tails when conservative
  thresholds are exceeded.
- The default workspace template now names its objective `cost_response`, maps the
  physical response through `soft_cost()`, and returns `1.0` for task calculation
  failure. The tracked HFSS reference uses the same task error bound.
- The `soft_cost()` docstring, architecture, terminology, blueprints, and tests now
  state and verify the normalized contract.

## Rationale

- Independently bounded objectives prevent units such as MHz or microseconds from
  changing optimizer balance merely through their numeric scale.
- Fixed scientific thresholds keep cost pure and repeatable: identical rawData has
  the same cost regardless of what other samples have been recorded.
- Reusing the existing tanh helper avoids a second normalization API and preserves
  the current defined-cost and curve-calculator path.

## Impact

- Future AI-authored and freshly initialized workspaces start from normalized cost
  policy. Existing workspaces remain unchanged until their task-owned
  `calc_cost.py` is intentionally edited.
- The generic starter smoke cost changes from raw `0.0` to normalized `0.1` at its
  configured goal under the default `edge_cost` behavior.

## Follow-Up

- None.
