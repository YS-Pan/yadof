# 2026-08-21 16:12 - Use Slow-Tail Algebraic Soft Cost

## Context

- The canonical physical-result-to-cost mapping used a calibrated hyperbolic
  tangent. Although `goal` and `worst` mapped to `0.1` and `0.9`, values beyond
  those anchors approached the bounded endpoints quickly.
- The user requested the generalized algebraic sigmoid
  `a*x / (1 + abs(a*x)**p)**(1/p)` with `p=2`, preserving the anchor values while
  making the out-of-anchor tails slower and less prone to numerical saturation.

## Change

- `soft_cost()` now centers the normalized physical position at `0.5`, applies the
  fixed-`p=2` algebraic sigmoid, and uses the affine output transform
  `0.5 * (1 + sigmoid)` to obtain a cost in `[0, 1]`.
- The default scale is derived as
  `a = (1 - 2*edge_cost) / sqrt(edge_cost * (1 - edge_cost))`. Consequently the
  default `edge_cost=0.1` gives `a=8/3`, so `goal` and `worst` remain exactly the
  `0.1` and `0.9` calibration anchors.
- The implementation uses `hypot(1, a*x)` as the stable fixed-power denominator and
  handles an overflowed scaled position by its signed limiting value.
- The optional override is now named `algebraic_scale` instead of the obsolete
  curve-specific name `tanh_slope`. The maintained reference workspace, tests,
  user documentation, architecture, and blueprints use the current name and curve.

## Rationale

- The calibrated algebraic curve preserves the established normalized objective
  contract and cost direction while decaying polynomially outside the scientific
  anchors. Moderately out-of-range results therefore remain farther from exact
  `0`/`1` and more distinguishable to the optimizer than under the previous curve.
- Deriving `a` from `edge_cost` retains the existing configurable anchor contract;
  hard-coding `p=2` keeps the requested curve simple and avoids an unnecessary task
  parameter.

## Impact

- All scalar, curve, registered, and constraint costs that call `soft_cost()` use
  the new curve. Existing rawData and physical `goal`/`worst` thresholds are
  reinterpreted through it when current costs are calculated.
- Task-owned curve dictionaries that explicitly named `tanh_slope` must use
  `algebraic_scale` or omit the optional override.

## Follow-Up

- None.
