# Workspace Submit-Side Code And Optimization Strategy

## Status And Execution Order

- This is a manual, one-shot, project-wide workspace-contract change. Reading it
  does not authorize implementation.
- The prerequisite simplification is complete and archived at
  `../obsolete/20260819_144148_simplify-surrogate-real-only-training.md`. Strategy
  work starts from its final real-only, rawData-field-balanced conditional-INR
  behavior and atomic retained-state contract.
- This work and the coordinated modularization change package/component/workspace
  boundaries. Pre-refactor quantitative performance acceptance is not a prerequisite;
  any such acceptance must be redesigned and run against the final architecture.
- Then execute this toDo and
  `20260818_173629_modular-surrogate-optimize-methods.md` as coordinated but staged
  work. The latter owns the smallest package seams required by a workspace strategy;
  this document owns layout, loading, snapshots, state retention, migration, and
  initialization. Each stage must keep the accepted default runnable and testable.
- Archive both coordinated toDos only after their shared installed-wheel acceptance
  passes. Trust-region/local refinement is parked research and must not cause this
  task to create a refinement role, capability system, state API, SciPy dependency,
  or fake refinement.
- After both coordinated toDos, workspace migration, and documentation updates are
  complete—but before the final wheel build, installed acceptance, and archival—
  bump the single public yadof package version from `0.3.0` to `0.4.0`. Do not bump
  during a partial stage; update every current-version document, test, and artifact
  expectation at that point while leaving historical change records unchanged.

## Verified Current Facts And Corrections

- `job_template/calc_cost.py` is currently submit-side code. `prepare_job()`
  explicitly excludes it, and distributed workers never receive or import it. The
  user's recollection is correct.
- The canonical workspace `job_template/parameters_constraints.py` is loaded by the
  submit process, but it defines the worker parameter/constraint handoff and remains
  in the worker-facing `job_template/` tree by explicit workspace-contract decision.
  Job preparation does not copy that source verbatim: it generates a different,
  self-contained assigned `parameters_constraints.py` inside each job. The new
  submit-only directory must not move or duplicate the canonical source.
- `job_template/evaluation.py` is different. Fast mode runs it in isolated processes
  on the submit host, but the supported shared-kernel pattern also allows
  distributed `workflow.py` to import it on an execute node. It remains
  evaluate-side task payload under `job_template/`.
- The current default is not unconditionally NSGA-III. Single-objective problems use
  pymoo GA; multi-objective problems use pymoo NSGA-III. GPSAF optionally adds
  conditional-INR surrogate pressure around that baseline. The new starter must
  preserve this objective-count-dependent default.
- Current `yadof.optimize.api` directly calls the complete `gpsaf.run_one_generation`
  implementation, while `yadof.surrogate` directly exposes one concrete conditional
  INR runtime. Workspace-defined composition therefore requires a real package
  boundary change, not only a new script or directory move.
- The installed numerical baseline includes `pymoo 0.6.2` and `torch 2.10.0`.
  Pymoo already supplies GA, NSGA-III, and single-objective PSO, but not GPSAF.
  Reuse auditing in this task is therefore focused on the current GA/NSGA-III,
  conditional-INR, and irreducible GPSAF behavior. Installed SciPy does not justify
  adding a refinement abstraction or dependency while that work is parked.

## Goal

- Introduce a reserved workspace `submit/` directory for task-owned Python that is
  never copied into local/distributed prepared jobs and is never imported by an
  execute-side workflow.
- Move the current cost policy, and only other code that is exclusively submit-side,
  out of `job_template/` into `submit/`. Keep canonical
  `parameters_constraints.py` under `job_template/` and preserve its generated
  assigned-file handoff.
- Add mandatory `submit/optimization.py` as the authoritative definition of the
  active complete optimization strategy. There is no package-default fallback when
  this file is absent.
- Keep campaign/session ownership, generation boundaries, evaluation, failure
  isolation, recording, rawData-first interpretation, scheduler safety, checkpoint
  publication, and metadata mechanisms in yadof. The engine consumes one narrow
  strategy/callable boundary. GPSAF exposes only its current real search and
  rawData-surrogate seams; do not build a generic component graph, capability
  matrix, registry, lifecycle manager, or second package-owned complete default.
- Preserve the present default numerical behavior after the preceding real-only
  cleanup while making alternative compositions expressible without copying
  campaign, history, evaluator, recorder, or checkpoint infrastructure.
- Allow sequential strategy changes in one workspace. Only one run is active at a
  time; recorded evidence and inactive persistent optimizer/surrogate state are
  retained rather than deleted.

## Workspace Standard

The new initialized layout is:

```text
workspace/
  .yadof/workspace.json
  config.py
  submit/
    calc_cost.py                 rawData -> current objective tuple
    optimization.py              complete optimization-strategy composition
    optional submit-only helpers
  job_template/
    parameters_constraints.py   canonical worker parameter/constraint definition
    workflow.py                  local/distributed execute entry
    evaluation.py                optional shared fast/evaluate-side kernel
    optional adapters, models, assets, and execute-side helpers
  jobs/                          generated local/distributed jobs
  recorded_data/                 generated evidence and events
```

The directory name is deliberately `submit`: it describes the execution boundary,
not one numerical method. Do not call it `optimizer/`, because cost interpretation
and future submit-only task helpers also belong there.

### Ownership rules

- `submit/` is user-owned task source, but every file in it is submit-side only. Job
  preparation, Condor input discovery, and worker execution must ignore the complete
  tree rather than maintain a filename-by-filename exclusion list.
- `job_template/` is the worker-facing source root. Subject to explicit runtime/cache
  and reserved generated-file rules, its evaluate-side task content is copied into
  local/distributed jobs. Canonical `parameters_constraints.py` is the deliberate
  exception: it stays in this root but is materialized rather than copied verbatim.
  A misplaced `calc_cost.py` or `optimization.py` must produce an actionable
  `check`/preparation error rather than be silently excluded.
- Job preparation loads the snapshotted
  `job_template/parameters_constraints.py` and materializes the existing
  self-contained job-local `parameters_constraints.py`. The generated file remains
  importable by `workflow.py` without yadof on execute nodes; the canonical source
  itself never enters the prepared job or transfer list.
- Root `config.py` remains in its established location. It is framework/campaign
  configuration, not a task module moved merely because it executes on the submit
  host.
- Fast `evaluation.py` remains below `job_template/` because it is evaluate-side
  task logic and may be shared by a distributed workflow. Fast still creates no
  prepared job and loads the generation snapshot's evaluate tree directly.
- Submit modules may use submit-local packages and stable installed yadof APIs.
  Execute modules may import job-local files, the standard library, and deliberately
  installed worker dependencies, but distributed execution still cannot import
  yadof or `submit/`.

## Optimization Definition Contract

`submit/optimization.py` defines exactly one callable:

```python
def build_optimization():
    ...
```

The callable returns one immutable strategy object or callable accepted by the
campaign engine. Importing the module and building the strategy must not train a
model, read history, create state/checkpoints, evaluate a candidate, open a GUI, or
mutate workspace data. `yadof check` loads it through the normal isolated workspace
loader and validates only the current concrete contract.

Conceptually the engine owns one boundary:

```text
OptimizationStrategy.run_generation(context) -> OptimizationResult
```

Exact spelling is settled from the current call sites. The engine owns sessions,
generation snapshots, real evaluation, history/recording, failure isolation,
progress, and metadata. A strategy proposes candidates and consumes real results
through those provided boundaries; it cannot write a parallel history or accept a
surrogate prediction as truth.

Illustrative, non-final spelling of the mandatory starter is:

```python
def build_optimization():
    search = by_objective_count(
        single=pymoo_ga(),
        multi=pymoo_nsga3(),
    )
    return gpsaf(
        search=search,
        surrogate=conditional_inr(),
    )
```

The first production compositions required by this work are:

1. the current GPSAF + (single-objective GA / multi-objective NSGA-III) +
   conditional-INR behavior;
2. a real multi-objective NSGA-III-only strategy with no GPSAF or surrogate.

GPSAF may accept a narrow search and rawData-surrogate interface so a later real PSO
or surrogate implementation can replace one seam without copying campaign code.
Do not stabilize a general third-party plugin API or use speculative PSO/surrogate/
refinement fakes as evidence that a future numerical method fits. Small test doubles
may verify the engine boundary and current dependency direction only.

## Library-First Numerical Policy

- Yadof owns orchestration and task-boundary semantics, not generic numerical
  algorithms. Audit only responsibilities touched by this change: GA, NSGA-III,
  current GPSAF coordination, and conditional INR. Audit PSO/local solvers only when
  a real implementation task starts.
- A package imported directly by yadof must be declared as a direct core or optional
  dependency with a supported version range; do not rely on it only because another
  dependency happens to install it transitively.
- A thin lazy adapter performs yadof/backend data translation, supported-argument
  validation, seed/state handoff, exception normalization, and compact provenance.
  It must not copy or subtly fork the backend's numerical loop.
- Pymoo continues to own GA/NSGA-III algorithms, populations, operators, and
  survival. PyTorch owns compatible tensor, layer, loss, optimizer, and serialization
  primitives.
- The installed pymoo has no GPSAF component. Preserve only the yadof-specific GPSAF
  assistance/orchestration that cannot be delegated, and re-audit mature packages
  before implementation in case a compatible maintained dependency can replace
  more of it. Adopting or upgrading a dependency requires focused equivalence and
  recovery tests; this toDo does not assume an upgrade.
- Expose only parameters yadof deliberately controls. Do not mirror full backend
  constructors or forward unrestricted `**kwargs`; record backend name/version and
  the effective yadof-controlled parameters.
- Do not add SciPy for parked refinement work. The installed planning baseline has
  no pymoo GPSAF, so retain only irreducible yadof GPSAF coordination and re-check
  supported dependencies during implementation.

## Package Boundary

### `yadof.optimize`

- Retain public workspace-explicit `run_one_generation()` and `run_generations()` as
  the package-owned campaign engine.
- Move `OptimizationResult` and common population/history/evaluation contracts out
  of the current complete GPSAF implementation.
- Load and validate the workspace strategy through one public/internal strategy boundary;
  the engine invokes it once per generation under the generation snapshot.
- Expose GPSAF pressure and objective-count dispatch as small composable yadof
  boundaries. Expose GA and NSGA-III through thin pymoo-backed factories with
  only the yadof-controlled parameters; do not extract or duplicate pymoo numerical
  mechanics into yadof. Pymoo types remain private to those adapters.
- Do not add `OPTIMIZE_METHOD`, `SURROGATE_METHOD`, or
  `OPTIMIZE_GPSAF_SEARCH_BACKEND` selectors. Those choices belong in
  `submit/optimization.py`, and a package selector would create a second source of
  truth.
- Do not keep a package registry entry representing the complete current algorithm.
  Strategy/backend/state-schema identities needed for provenance and recovery cannot
  select a complete strategy independently of the workspace script.

### `yadof.surrogate`

- Keep only the rawData training-data adaptation, conditional-INR scheduling/state,
  compact metadata, and atomic checkpoint behavior needed by the current production
  method. Do not build a generic surrogate framework before a second real method.
- Expose one narrow rawData-first conditional-INR seam required by GPSAF. It predicts
  complete rawData before current cost and never becomes an authoritative direct-cost
  model.
- Scheduler/checkpoint/viewer code may remain explicitly conditional-INR-specific,
  but GPSAF must call the narrow seam rather than import concrete runtime internals.
  A strategy with no surrogate produces no surrogate state and viewer discovery
  reports that fact cleanly.

The detailed source split, dependency direction, dependency-reuse audit, and
component tests are maintained in the coordinated modularization toDo. Avoid
symmetric empty files, generic `utils.py`, speculative third-party plugin APIs,
wrappers that only forward the old complete algorithm, and yadof-owned copies of
backend algorithms.

## Snapshot, Provenance, And Retained State

- A generation snapshot owns complete copies of both `submit/` and `job_template/`.
  It rebases both roots into one immutable temporary workspace while runtime output
  continues to target the real workspace.
- Hash both complete copied trees. Do not add a new AST/import dependency tracker for
  submit helpers: dynamic imports and data-file dependencies make that precision
  misleading. Interpretation/evaluation/optimization hashes are provenance and may
  invalidate derived caches, not scientific compatibility decisions.
- Record source hashes separately from a deterministic semantic state signature. The
  state signature contains strategy/backend identity, state schema, parameter and
  objective dimensions, backend versions, and effective yadof-controlled parameters
  required to decide whether derived state can be resumed.
- Source-hash inequality never rejects or deletes recorded variables/rawData. A
  compatible state signature may continue using active derived state; an incompatible
  signature activates a new optimization-run state namespace before evaluation.
- Each run owns component/method-specific persistent namespaces. On a plan change,
  yadof waits for or safely stops pending background work, releases in-memory state,
  marks the old run inactive, and activates a new compatible or empty namespace.
- Old optimizer and surrogate artifacts, including conditional-INR neural-network
  weights, remain on disk. Discovery is scoped to the active run/component/signature
  so a new surrogate cannot accidentally load them.
- Returning to an old strategy may resume retained state only when its strategy,
  backend, state schema, parameter/rawData schema, and training policy are supported
  and compatible. Otherwise it cold-starts from retained real evidence while still
  preserving the old files.
- Retention does not promise every future yadof version can read every old artifact;
  metadata must explain why recovery is accepted or refused. Automatic pruning is
  out of scope and any future prune operation must be explicit and confirmed.
- `history clear` remains a separate destructive user decision and is never required
  merely to switch strategy. Only one run may be active at a time, but one workspace
  may retain several inactive runs.
- Background surrogate work receives the same owned generation snapshot. No worker
  may reopen live `submit/optimization.py` while a generation is running.

## Initialization, Validation, And Migration

- Add `submit_dir` to `WorkspaceContext`, defaulting to the reserved workspace path
  `submit`. The constructor may accept an explicit internal/test rebase used by
  generation snapshots, but the first public workspace standard does not add a
  `SUBMIT_DIR` config setting: one fixed name keeps init, check, migration, and
  human inspection unambiguous. Validate configured framework paths so none can
  overlap `submit/` or make it overlap `job_template/`, jobs, recorded data,
  checkpoints, logs, tool output, or fast scratch.
- Update the bundled template manifest/version and `yadof init` staging validation
  to publish `submit/calc_cost.py`, `submit/optimization.py`, and the retained
  `job_template/parameters_constraints.py`; stop publishing only the old
  `job_template/calc_cost.py` source.
- The starter optimization file composes the current objective-count-dependent
  default. It contains composition only, not copied GPSAF, pymoo, surrogate,
  scheduler, evaluator, or campaign implementations.
- `yadof check` validates the marker, both source roots, canonical parameters,
  current cost, side-effect-free strategy construction, misplaced reserved files,
  objective/backend compatibility,
  and workflow syntax without importing/running the workflow or starting numerical
  work.
- Update generic smoke assessment to compare every starter source that affects its
  evaluation/cost contract. Merely relocating submit files must not make an edited
  real task look like the untouched starter.
- Keep packaged adapters/tools that locate canonical parameters on
  `job_template/parameters_constraints.py`; update only cost/optimization consumers
  to the new submit root. Adapters and models copied for execution still target
  `job_template/`.
- Parameterize and reuse the current isolated task-module loader for either source
  root; do not create a second import-isolation implementation.
- Migrate repository reference workspaces and tests to the new layout. Do not add a
  dual-path loader or silently accept legacy files in both locations.
- Existing user workspaces are never rewritten by `init`. Bump template provenance
  and document an explicit fresh-workspace/copy-task migration. `check` should
  diagnose the old layout and explain the move; it must not move files, edit the
  marker, clear history, or guess whether an active campaign is safe to migrate.
- Source-layout migration and strategy-internal refactoring are staged and tested
  separately, although final acceptance requires both. Incompatible old artifacts
  may remain retained and undiscoverable without adding a legacy reader; real
  evidence is not cleared merely because the new code cannot recover old state.

## Implementation Plan

### Phase 0 - Freeze The Post-Simplification Baseline

- [ ] Confirm the archived real-only handoff remains the active implementation
  baseline.
- [ ] Characterize the current seeded default for single-objective GA,
  multi-objective NSGA-III, GPSAF warmup/fallback/alpha/beta/exploration, staggered
  conditional-INR training, current-cost conversion, and real validation.
- [ ] Inventory every loader/path/test/tool that consumes canonical parameters from
  `job_template/` or assumes `calc_cost.py` is beside them.
- [ ] Audit only GA, NSGA-III, GPSAF, and conditional INR: backend/version,
  yadof-controlled parameters, state handoff, and the specific coordination code
  that cannot be delegated.

### Phase 1 - Establish The Two-Root Workspace

- [ ] Add the explicit submit path to workspace context/config validation and
  parameterize the existing isolated loader for either source root.
- [ ] Move only cost and other exclusively submit-side sources in the template,
  examples, neutral test workspaces, tools, and task APIs; retain canonical
  parameters under `job_template/` without a duplicate submit copy.
- [ ] Make job preparation copy only evaluate-side task content and generate the
  assigned parameter handoff from the snapshotted canonical source. Replace the old
  cost exclusion with actionable misplaced-file validation while preserving the
  intentional canonical-parameter materialization exception.

### Phase 2 - Extend Snapshots And Add One Strategy Boundary

- [ ] Capture/rebase and hash both complete roots without a new AST dependency
  tracker; preserve generation-boundary task semantics.
- [ ] Move common result/context types out of GPSAF and make the engine invoke one
  snapshotted strategy/callable.
- [ ] Publish the mandatory starter with single-objective GA versus multi-objective
  NSGA-III dispatch, plus a real multi-objective NSGA-III-only strategy.

### Phase 3 - Extract Composable Package Components

- [ ] Execute the coordinated modularization toDo: thin pymoo adapter, irreducible
  GPSAF coordination, one narrow conditional-INR rawData seam, and cohesion-based
  runtime splitting.
- [ ] Delete or avoid yadof numerical mechanics already supplied by an accepted
  mature dependency. Factories expose only yadof-controlled parameters plus backend
  identity/version; equivalence tests compare behavior through public yadof contracts
  rather than copying backend implementation details or full backend defaults.
- [ ] Remove the package-owned complete-algorithm dispatch and any planned selector
  configs/registries that duplicate workspace composition.
- [ ] Preserve current behavior through the narrow strategy/search/surrogate seams;
  add no refinement, generic plugin, capability, or lifecycle framework.

### Phase 4 - Retain And Isolate Strategy State

- [ ] Define the deterministic semantic state signature and per-run/component
  persistent namespaces separately from source hashes.
- [ ] Implement strategy switching that waits/stops pending work and resets in-memory
  ownership while preserving recorded evidence and all inactive persistent state.
- [ ] Scope discovery/recovery to compatible active state and prove switching away
  from and back to conditional INR never cross-loads another component's artifacts.
- [ ] Keep common real evaluation, session, failure, progress, metadata, and recorder
  behavior unchanged.

### Phase 5 - Init, Check, Tools, And Documentation

- [ ] Publish the new default template and bump its provenance without adding
  automatic repair/upgrade.
- [ ] Update `check`, smoke assessment, parameter extraction, adapter copying/path
  guidance, history/cost/surrogate viewers, state retention, explicit destructive
  history clear, examples, and package artifact expectations.
- [ ] Update architecture, terminology, project/module/file blueprints, user docs,
  prompt examples, template README, and the nested surrogate-viewer documentation
  where strategy/state discovery changes.

### Phase 6 - Installed Acceptance

- [ ] After both coordinated implementations and migration are complete, bump the
  single public package version from `0.3.0` to `0.4.0` and update every
  current-version assertion; do not bump during a partial stage.
- [ ] Build the wheel, force-reinstall it into the sibling `.venv`, verify imports
  come from site-packages with no `PYTHONPATH`, run focused tests, then full pytest.
- [ ] Inspect wheel/sdist members and two freshly initialized workspaces. Do not run
  a live simulator or HTCondor without separate explicit authorization.
- [ ] Add the completed change record and archive this toDo together with the
  coordinated modularization toDo only after every criterion passes.

## Verification Plan

- Initialization/check tests assert the exact new files, no old submit-only files
  under `job_template/` except the retained canonical parameter contract, no
  duplicate canonical source under `submit/`, no overwrite/repair, two-workspace
  isolation, and clear legacy-layout diagnostics.
- Prepared-job and distributed-submit tests prove the complete `submit/` tree,
  canonical parameter source, cost policy, optimization definition, and submit
  helpers never enter a job or transfer list; the generated assigned parameter file
  and evaluate-side assets still do.
- Snapshot tests edit cost, workflow/evaluation, and optimization sources at
  controlled boundaries. One generation remains coherent; cost/evaluation changes
  follow current rules; source hashes record provenance without rejecting evidence;
  incompatible strategy state activates an isolated new run.
- Loader tests cover submit-local relative/absolute helper imports, same-named
  helpers across roots/workspaces, exception cleanup, and no lasting `sys.path` or
  `sys.modules` pollution.
- Starter-default tests cover single-objective GA and multi-objective NSGA-III, seeded
  GPSAF phases, real-only conditional INR, warm start, fallback, exploration,
  staggered training, rawData-first current cost, and real validation.
- Strategy tests cover real multi-objective NSGA-III without GPSAF/surrogate and
  small engine/current-seam doubles only; there is no fake refinement or claim about
  unimplemented production methods.
- State tests cover pending-training shutdown, active/inactive run isolation,
  retained conditional-INR weights, no cross-component discovery, compatible
  resume, incompatible cold start from retained evidence, viewer handling,
  recording-loss isolation, and absence of a second selection source.
- Static checks recursively reject old internal imports, duplicate complete
  algorithm implementations, backend numerical loops copied into yadof, task code
  copied into package fixtures, legacy workspace fallback paths, and package parent
  imports that eagerly load Torch, pymoo method implementations, Matplotlib, Tkinter,
  or viewer UI. Adapter tests assert controlled parameters, backend identity, and
  deterministic state handoff without mirroring full backend APIs.
- Finish with `git diff --check`, UTF-8/link/path validation, installed-wheel focused
  tests, and the complete installed-package pytest suite.

## Completion Rule

- New workspaces have the exact two-root source boundary: submit-only cost and
  optimization composition under `submit/`; canonical worker parameter/constraint
  source plus evaluate-side workflow/kernel/assets under `job_template/`.
- Prepared local/distributed jobs contain no submit source and receive only the
  generated assigned parameter snapshot—not the canonical source—plus evaluate-side
  payload and package worker support.
- The complete algorithm exists only as the workspace's snapshotted
  `build_optimization()` composition. Yadof owns the minimal current seams and
  invariant campaign/evaluation/persistence mechanisms, with no competing complete-
  method config selector, registry, or generic component framework.
- The starter reproduces GPSAF + objective-count-dependent GA/NSGA-III + simplified
  conditional INR. A real multi-objective NSGA-III-only strategy verifies the engine
  boundary without speculative refinement or future-method APIs.
- Yadof contains no copied implementation of an accepted backend algorithm. Mature
  package implementations are reached through thin lazy adapters; yadof-controlled
  parameters, backend version, and current objective compatibility are inspectable.
  Only yadof-specific orchestration, rawData/task adaptation, real-validation, and
  persistence glue remain, with a written justification wherever no compatible
  mature implementation exists.
- Source provenance and semantic state compatibility are separate. One generation
  is coherent; a strategy change activates isolated state while retaining old
  optimizer/surrogate artifacts and recorded rawData. RawData-first and real-
  validation invariants remain intact.
- Init/check/migration diagnostics, examples, architecture, blueprints, terminology,
  user docs, nested viewer docs, artifacts, and tests all describe the new standard;
  installed full pytest passes from the force-reinstalled wheel.
- Final source, CLI, installed package, and wheel all report `0.4.0`; every
  current-version acceptance expectation is synchronized, and historical change
  records remain unchanged.
- This document and the coordinated modularization toDo are archived together.
  Parked trust-region research is reconsidered only after all other active work and
  does not constrain this completed strategy boundary.
