# 2026-08-27 11:27 - Refine Joint rawData Posterior Plan

## Context

- A fresh-context review correctly identified that the first plan bound posterior
  sampling too tightly to a fully materialized candidate set, duplicated part of
  the existing cost-interpreter responsibility, staged benchmarking too late, and
  combined too many model structures in the first CAE implementation.
- The user supplied the remaining product decisions: current benchmark baselines
  define the representative rawData shapes; repeated evaluations are nearly
  deterministic; coordinate readout should follow the full-grid model gate;
  explicit grouping belongs in the first MVP; `(NPZ basename, main array key)` is
  the stable field selector; finite task fallback cost `1.0` remains a valid worst
  cost; and the six detailed TODOs should remain separate rather than being merged.

## Change

- Revised the six existing future-work handoffs without changing their file
  structure or shortening their standalone context.
- Replaced whole-population posterior binding with a persistent function sampler
  whose draw identities remain fixed across candidate chunks and permutations.
- Defined cost projection as a thin streaming adapter over the existing frozen
  `CostInterpreter`; schema/call/width/finite success defines validity, while a
  finite task-level `error_cost=1.0` remains valid because its origin is not exposed
  by the current callback contract.
- Recorded the current benchmark baseline support matrix: SAW `[1201]` curves,
  Chrono scalar and `[513]` phase fields, and synthetic-antenna `[5]`,
  `[1,73,73]`, and `[5,73,73]` fields, all with fixed real-valued main arrays and
  fixed axes.
- Narrowed the first CAE vertical slice to per-field codecs, a shared parameter
  predictor with global/optional-group/private heads, explicit selector-based
  groups, and a predictor-only ensemble. The antenna frequency axis is handled by
  an explicit channel/spatial layout rather than inferred from its size; attention,
  native Conv3d, full-model ensembles, and variable/complex schemas are evidence-
  gated follow-ups. Coordinate readout remains required but follows the full-grid
  fitting gate.
- Moved schema inventory, benchmark preregistration, the conditional-INR adapter,
  and a qLogNEHVI backend spike ahead of the full CAE implementation. The first
  qNEHVI MVP uses a fixed real Pareto baseline with zero observation noise, defers
  pending points and outcome constraints, and does not add a generic public search-
  pool protocol.
- Made `new CAE + GPSAF` a required ablation so representation and acquisition
  effects can be separated.

## Rationale

- The persistent sampler preserves the joint-function semantics needed by Monte
  Carlo acquisition while allowing large candidate pools to be evaluated within a
  bounded memory budget.
- Reusing `CostInterpreter` keeps one task-snapshot/cost-callback contract and
  avoids a second source of task-loading and fallback behavior.
- The baseline-derived support matrix is broad enough to exercise scalar, long
  curve, and antenna field behavior without claiming unsupported arbitrary tensor
  schemas. Explicit axis roles preserve task meaning and avoid an unnecessary
  Conv3d requirement.
- Early vertical spikes can invalidate an interface or backend assumption before
  expensive model work. The simpler predictor-only ensemble and staged coordinate
  readout retain the approved final direction while requiring evidence before each
  major complexity increase.

## Impact

- This is a documentation-only planning refinement. Runtime APIs, current
  conditional-INR/GPSAF behavior, benchmark inputs, rawData persistence, optional
  dependencies, and installed package behavior are unchanged.
- Future implementation now has explicit first-MVP support and rejection boundaries
  for field identity, grouping, tensor layouts, posterior support, deterministic
  baselines, cost fallback, pending points, and outcome constraints.

## Follow-Up

- Begin future implementation with the benchmark/schema preregistration and the
  minimum sampler plus `CostInterpreter` adapter, then complete the conditional-INR
  and qLogNEHVI spike before building the new CAE.
- Re-audit the supported BoTorch API and recommended qLogNEHVI class at execution
  time; do not treat the planning-time class name as a permanent dependency
  contract.
- Generate or select the 1000/2000-design frozen evidence under the normal user
  cost/risk authority before making fitting or optimization performance claims;
  baseline template shape metadata is not a training dataset.
