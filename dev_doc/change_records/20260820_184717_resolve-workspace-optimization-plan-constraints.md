# 2026-08-20 18:47 - Resolve Workspace Optimization Plan Constraints

## Context

- A fresh-context review identified risks in the proposed workspace-owned
  optimization design: an optional workspace strategy fallback, over-generalized
  component/plugin boundaries, synthetic surrogate targets, destructive state
  switching, field/slot weighting, unproven checkpoint publication, and premature
  local-refinement abstractions.
- The user resolved the material questions: training targets may only come from real
  evaluations; every workspace must own an explicit strategy whose default preserves
  current GPSAF behavior; numeric rawData fields are equally important; old algorithm
  state should remain on disk; production surrogate completion needs more real
  benchmarks; and local refinement is postponed until all other toDos are complete.

## Change

- Revised the workspace composition toDo around one mandatory
  `submit/optimization.py` strategy/callable, with no package fallback. The starter
  preserves GPSAF + conditional INR and dispatches pymoo GA for one objective or
  NSGA-III for multiple objectives; a real multi-objective NSGA-III-only strategy is
  the only additional production composition required now.
- Kept canonical `job_template/parameters_constraints.py` worker-facing while moving
  only submit-exclusive policy such as `calc_cost.py` into the new `submit/` root.
- Minimized package abstractions to the current engine boundary and GPSAF's actual
  search/rawData-surrogate seams. Removed plans for a generic component graph,
  capability registry, lifecycle framework, future-method fakes, and duplicated
  backend defaults; mature pymoo/PyTorch implementations remain authoritative.
- Made recorded variables/rawData durable evidence independent of source hashes.
  Strategy switches keep one active run, stop pending work, release in-memory
  pointers, and retain old namespaced optimizer/surrogate artifacts including neural
  weights. Compatible returns may resume; incompatible returns cold retrain from
  retained real evidence without cross-loading or deleting old state.
- Strengthened the surrogate plan so every target is traceable to a real evaluation.
  Each numeric rawData field receives equal total sampling and loss weight: values
  are averaged within a field and then macro-averaged across fields, so extra slots
  do not multiply field weight. Users are responsible for excluding objective-
  irrelevant numeric values from rawData.
- Replaced the bespoke per-slot cyclic proposal with equal field budgets and standard
  seeded, without-replacement sampling within each field, using deterministic
  shuffled rotation when a step cannot include every field.
- Added a user-approved production benchmark gate covering prediction quality,
  applicable ranking, resource cost, and fixed-real-evaluation-budget optimization
  efficiency. The final suite and thresholds remain intentionally open until the
  user's additional benchmarks are ready; failures may only be addressed within the
  real-only invariant.
- Parked the trust-region/local-refinement toDo as a non-binding research notebook.
  Current work must not reserve a refinement role/API/state/capability system, add a
  SciPy dependency, or create fake refinement tests.
- Left the exact atomic checkpoint mechanism open to Windows interruption/failure
  testing rather than assuming manifest-last publication is sufficient.

## Rationale

- Real evaluations are the only authoritative evidence, whereas source snapshots and
  model checkpoints are derived state with different compatibility and retention
  rules.
- A single strategy boundary gives workspace authors control without turning yadof
  into a plugin framework. Narrow seams can be expanded later only when a real
  algorithm consumer demonstrates the need.
- Field-level macro weighting matches the user's contract that all numeric rawData
  fields matter equally; treating every slot as a separate stratum would silently
  overweight fields with larger shapes.
- Retaining inactive state avoids needless data loss while explicit namespaces and
  semantic signatures prevent unsafe accidental recovery.
- Real benchmark gates prevent a structurally cleaner surrogate from being declared
  production-ready without evidence, while parking distant refinement work avoids
  constraining the architecture prematurely.

## Impact

- Only active planning documents and this append-only change record changed. No
  package code, workspace template, runtime behavior, dependency, checkpoint,
  history, public API, architecture, blueprint, or user documentation changed.
- No yadof reinstall or runtime test is required for this documentation-only change.
  Future implementation must still build and reinstall the package and pass the
  focused, benchmark, installed-wheel, and full-suite acceptance defined by the
  revised toDos.
