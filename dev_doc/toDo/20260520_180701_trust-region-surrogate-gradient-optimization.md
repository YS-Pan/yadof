# Trust-Region RawData-Surrogate Local Refinement

## Status And Execution Dependencies

- This is a manual, long-term research and implementation direction. Reading it
  does not authorize execution.
- Before starting this work, complete and archive these active manual toDos in
  order:
  1. `20260819_144148_simplify-surrogate-real-only-training.md`;
  2. the coordinated
     `20260820_125457_workspace-submit-optimization-composition.md` and
     `20260818_173629_modular-surrogate-optimize-methods.md` work.
- Use their final real-only, field/slot-balanced conditional-INR training contract,
  component boundaries, component-namespaced checkpoint schema, snapshotted
  `submit/optimization.py`, and one immutable plan per workspace/campaign as the
  only baseline. Do not build this feature on the
  current mixup/importance/relative-loss paths, optimizer-facing training-fit error,
  ensemble-driven GPSAF noise, flat module layout, or legacy checkpoint behavior.
- Real out-of-sample benchmark evidence is an implementation prerequisite, not a
  later polish step. A production trust policy must not be enabled merely because
  local-refinement mechanics work on synthetic fixtures.

## Updated Context

- Yadof treats the real simulator or workflow as an expensive black box. It must
  never claim to obtain gradients of the real workflow.
- The durable prediction chain is `normalized variables -> predicted full rawData
  -> current workspace cost`. A selected proposal still receives real evaluation,
  and only real rawData is evidence/history source truth.
- The current concrete surrogate is a conditional-INR deep ensemble. Its Torch
  decoder is differentiable with respect to normalized variables, but the
  production prediction path converts tensors to NumPy, reconstructs task rawData,
  and calls arbitrary task-owned `calc_cost.py` (moved to `submit/calc_cost.py` by
  the prerequisite workspace change). Therefore the current objective is not
  generically differentiable end to end. “The surrogate is differentiable” is not
  sufficient evidence that a usable objective gradient exists.
- Yadof parameters may be continuous, discrete, or mixed piecewise ranges. A step
  in the normalized unit box can cross a discontinuous parameter segment, so a
  generic gradient method cannot silently treat every dimension as smooth.
- In the current pre-prerequisite selector, live alpha/beta survival uses mean
  predicted costs only. Interval/noise helpers have no live selection caller, and
  historical error is fetched and passed through an unused argument. The first
  prerequisite owns removal of these dead surfaces and tests that lock the existing
  selection invariance; this future task must not revive them accidentally.
- The post-simplification ensemble member min/max spread remains a diagnostic, not
  calibrated confidence. Training-row fit error is in-sample evidence. Neither may
  drive trust-region acceptance, candidate comparison, noise, or radius changes
  unless a later real benchmark establishes an explicit out-of-sample calibration.
- After the coordinated prerequisites, this feature is an appendable refinement
  component selected by the workspace optimization plan. It consumes a surrogate
  capability and package-owned real-evaluation handoff. It is not another GPSAF
  internal search component and not a package-owned complete optimizer: a trust-
  region stage owns local proposals and model-management feedback while the common
  engine owns real validation/session/recording.

## Goal

- After global evolutionary search identifies diverse promising real-evaluated
  anchors, propose a small number of local refinements around selected anchors.
- Optimize an explicit multi-objective scalarization or reference-direction goal
  only inside a bounded local region and only through a deliberately chosen
  proposal strategy.
- Treat every refined point as a proposal. Send selected points through yadof's
  normal real-evaluation/finalization path before accepting an improvement.
- Compare predictions captured before evaluation with the resulting real current
  costs, and use properly scoped out-of-sample residuals to update trust-region
  state.
- Preserve Pareto-front diversity and a deliberate global-exploration allocation;
  local refinement must not collapse a generation onto one scalar optimum.

The intended combination remains:

- evolutionary or other global search for exploration and diversity;
- local surrogate-based search for precision;
- real evaluation for truth and model-management feedback.

## Decisions Required Before Implementation

The remaining choices materially change public task contracts and must be made
explicitly rather than inferred while coding. Component ownership is already fixed
by the prerequisite workspace-composition contract below.

### 1. How local objective derivatives are obtained

Choose one primary proposal contract:

- **Task-opt-in differentiable objective:** define a narrow task-owned differentiable
  mapping from predicted rawData tensors to one scalarized objective. This permits
  true autograd but adds a new task API, restricts supported cost operations, and
  must be checked against the normal `submit/calc_cost.py` result.
- **Derivative-free local optimization of current predicted cost:** repeatedly use
  the normal rawData reconstruction/current-cost prediction inside a trust region.
  This preserves the existing task contract but is not surrogate-gradient
  optimization and should be named accordingly.
- **Separate proposal-only local cost model:** fit a differentiable local model from
  real current costs. This adds a derived `variables -> cost` proposal path and must
  be justified carefully against yadof's rawData-first architecture; it can never
  become authoritative truth.

Do not expose a fake gradient by differentiating only the rawData network while
ignoring a non-differentiable cost boundary. Do not make all surrogate methods
implement gradients unless the selected optimizer contract genuinely requires that
capability.

### Resolved: refinement ownership

- Implement refinement as a reusable package component appended by
  `submit/optimization.py` to a workspace plan, for example after the default GPSAF
  proposal stage.
- The component may own trust-region proposal/radius/model-management state, but the
  package campaign engine owns snapshot selection, common real evaluation,
  finalization, session history, recording, and generation metadata.
- It is neither a GPSAF global-search replacement nor another package-selected
  complete optimizer. Do not add a complete-method registry/config selector or
  copy GPSAF/campaign infrastructure into it.

### 2. Continuous, discrete, and mixed parameters

Choose and document one policy, for example:

- refine only continuous dimensions while freezing discrete/mixed segment choices;
- enumerate a bounded neighborhood of discrete choices and locally refine each
  continuous subspace; or
- use a mixed-variable local method with explicit discontinuity handling.

Projection to `[0, 1]` alone is not an adequate mixed-parameter policy. Task
constraints and duplicate/history keys must also remain valid after projection.

### 3. Trust calibration and benchmark gate

Select representative fast real-evaluation tasks, including sharply nonlinear
cases such as the deferred `20260807 saw` problem if it remains available, and
define acceptance metrics before enabling the method. The benchmark must capture a
prediction before its real outcome is known and measure at least local ranking or
improvement prediction, residual versus distance/radius, and failure behavior.
Decide what evidence is sufficient to use ensemble spread, data distance, or any
other diagnostic in a production trust rule. Synthetic training fixtures and
training-row reconstruction error are insufficient.

## Durable Design Constraints

- Run selection, local proposal generation, predicted-cost interpretation, and real
  validation under one immutable generation task snapshot. A task edit takes effect
  at the next generation boundary, not midway through a local-refinement batch.
- Treat interpretation/evaluation fingerprints as provenance and cache boundaries,
  not proof of scientific equivalence. Residuals produced under incompatible cost
  meanings must not be pooled mechanically.
- Select anchors only from completed real evaluations. Surrogate-predicted points
  cannot recursively become trusted anchors before real validation.
- Keep local steps inside explicit normalized-variable bounds and the chosen
  parameter/constraint policy. Deduplicate them against history and the current
  population using the optimizer's normal key semantics.
- Use an explicit scalarization or reference-direction goal. Weighted sums,
  achievement scalarizing functions, Tchebycheff-style goals, or direction-specific
  objectives remain possible, but the chosen rule must preserve coverage across
  the Pareto front. Current task objectives are already dimensionless minimization
  costs in `[0, 1]`; do not renormalize them against observed history.
- Route selected proposals through the common evaluation API and current-cost
  finalizer. The campaign session owns accepted current rows and best-effort durable
  recording; local-refinement code must not write a parallel history or treat
  recording loss as evaluation failure.
- Keep ensemble spread and any training-fit audit observable for diagnostics, but
  keep them out of decisions until the benchmark gate explicitly calibrates and
  approves their use. Prefer evaluation-before/after out-of-sample residuals for
  trust feedback.
- Preserve an exploration quota and bound the number of local proposals and real
  validations per generation. A failed validation is normal model-management
  evidence, not a reason to hide the candidate or bypass failure isolation.
- Record compact method, anchor, scalarization, radius, predicted-improvement,
  actual-improvement, and acceptance diagnostics without storing predictions as
  source truth or duplicating rawData.
- Respect the workspace-plan provenance rule. Adding/removing this refinement or
  changing its search/surrogate component graph changes the optimization
  fingerprint and requires a new workspace or the documented explicit clear
  operation; it cannot hot-switch against retained plan state.

## Candidate Workflow

1. Start from one generation snapshot containing the exact `submit/` plan/cost and
   `job_template/` evaluation sources plus mechanically interpretable real history.
2. Select a diverse set of nondominated or otherwise promising real-evaluated
   anchors.
3. Assign scalarizations/reference directions and initialize bounded local regions
   in the valid continuous or mixed-variable subspaces.
4. Generate local proposals using the explicitly selected derivative or derivative-
   free strategy; retain prediction and provenance before real evaluation.
5. Filter proposals by parameter semantics, task constraints, bounds, duplicates,
   novelty, diversity, and the currently calibrated trust policy.
6. Keep a bounded exploration allocation and send selected candidates through the
   normal real evaluator.
7. Compare predicted and real current costs under the same interpretation snapshot;
   update radius/state using a documented model-management rule such as actual-
   versus-predicted improvement, including rejection and failure outcomes.
8. Make the real results available to the campaign session and later surrogate
   training through the existing evaluation/recording flow.

## Verification Plan

- Prove that no path labels a surrogate/rawData derivative as a real-workflow
  gradient and that no predicted cost/rawData becomes authoritative history.
- Test the selected differentiability contract end to end. If true autograd is
  chosen, compare it with finite differences for supported task costs and reject
  unsupported/non-differentiable task operations explicitly.
- Cover continuous, discrete, mixed-segment, boundary, constraint, and duplicate
  behavior under deterministic seeds.
- Test single- and multi-objective scalarization, reference-direction coverage,
  exploration quota, bounded evaluation budget, radius expansion/shrinkage, and
  failed validation.
- Prove that local candidates use the same generation snapshot and common real-
  evaluation/finalization path, and that recording loss cannot change a valid
  current cost.
- Build trust tests from held-out or online pre-evaluation predictions. Demonstrate
  that uncalibrated member spread or training-fit diagnostics cannot affect
  selection, then add any calibrated signal only with reliability/ranking evidence
  and an ablation test.
- Verify component sequencing, capability validation, plan fingerprint freeze, and
  workspace provenance through `submit/optimization.py`; do not couple the
  implementation to pre-modular flat files or a package complete-method selector.
- Update architecture, blueprints, terminology, user documentation, checkpoint/
  metadata contracts, and installed-wheel tests in proportion to the chosen design.

## Completion Rule

- All three prerequisite toDos are complete and archived, the three remaining
  decisions above are recorded with their rationale, and refinement ownership
  follows the resolved workspace-plan component boundary.
- The project has a documented and tested local-refinement workflow with explicit
  multi-objective goals, parameter-domain handling, trust-region limits, bounded
  real-evaluation validation, and feedback-driven model management.
- Any claimed objective gradient is genuinely defined through the selected
  end-to-end proposal contract. If the implementation is derivative-free, its name
  and documentation say so while preserving the conceptual link to trust-region
  surrogate-based or surrogate-assisted memetic optimization.
- Production trust decisions use benchmarked out-of-sample evidence; ensemble
  spread and training-fit error are not silently restored as GPSAF noise or
  confidence.
- Real validation uses yadof's rawData-first generation-snapshot/evaluation/session
  contracts, preserves Pareto diversity and exploration, and introduces no legacy
  checkpoint reader, parallel history, or unvalidated direct-cost truth path.
- A workspace can append the completed component to its default or another
  compatible plan without copying engine/GPSAF/evaluation code, while a plan that
  omits it remains unaffected.
