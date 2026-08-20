# Workspace Submit-Side Code And Optimization Composition

## Status And Execution Order

- This is a manual, one-shot, project-wide workspace-contract change. Reading it
  does not authorize implementation.
- First complete and archive
  `20260819_144148_simplify-surrogate-real-only-training.md` so the component work
  starts from the final real-only, field/slot-balanced conditional-INR behavior and
  fresh-only checkpoint format.
- Then execute this toDo and
  `20260818_173629_modular-surrogate-optimize-methods.md` as one coordinated change.
  The latter owns the detailed package-component extraction; this document owns the
  workspace layout, loading, composition, snapshot, provenance, migration, and
  initialization contracts. Neither may land as a temporary compatibility layer
  that leaves a complete algorithm selected inside yadof.
- Archive both coordinated toDos only after their shared installed-wheel acceptance
  passes. The trust-region refinement toDo remains a later consumer of the resulting
  composition boundary.

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
- The installed numerical baseline is `pymoo 0.6.2`, `scipy 1.18.0`, and
  `torch 2.10.0`. That pymoo version already supplies GA, NSGA-III, and
  single-objective PSO, but it does not expose a GPSAF implementation. SciPy supplies
  mature local/global scalar-objective solvers, not a drop-in multi-objective
  NSGA-III or GPSAF replacement. Reuse therefore needs a capability/semantics audit;
  package removal cannot be inferred from an algorithm name alone.

## Goal

- Introduce a reserved workspace `submit/` directory for task-owned Python that is
  never copied into local/distributed prepared jobs and is never imported by an
  execute-side workflow.
- Move the current cost policy, and only other code that is exclusively submit-side,
  out of `job_template/` into `submit/`. Keep canonical
  `parameters_constraints.py` under `job_template/` and preserve its generated
  assigned-file handoff.
- Add `submit/optimization.py` as the authoritative definition of the one complete
  optimization plan used by that workspace.
- Keep campaign/session ownership, generation boundaries, evaluation, failure
  isolation, recording, rawData-first interpretation, scheduler safety, checkpoint
  publication, and metadata mechanisms in yadof. Expose reusable search,
  surrogate-assistance, surrogate-model, and later refinement components that the
  workspace plan composes; do not keep a second package-owned complete default
  algorithm selected by config or a registry.
- Preserve the present default numerical behavior after the preceding real-only
  cleanup while making alternative compositions expressible without copying
  campaign, history, evaluator, recorder, or checkpoint infrastructure.

## Workspace Standard

The new initialized layout is:

```text
workspace/
  .yadof/workspace.json
  config.py
  submit/
    calc_cost.py                 rawData -> current objective tuple
    optimization.py              complete optimization-plan composition
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

The callable returns one validated immutable optimization-plan object assembled
from public yadof components. Importing the module and building the plan must not
train a model, read history, create a checkpoint, submit/evaluate a candidate, open
a GUI, or mutate workspace data. `yadof check` loads the module in the normal fresh,
isolated workspace namespace and validates the returned component graph without
executing a campaign.

Exact constructor names should be settled from the extracted call boundaries during
implementation, but the stable roles are mandatory:

- a campaign engine owns sessions, generation reload/snapshot, metadata, strict
  all-infinite behavior, and calls the workspace plan;
- a global-search component proposes/advances normalized candidates and consumes
  real objective rows;
- an optional surrogate-model component trains on real rawData, predicts compatible
  rawData, and leaves current-cost interpretation outside the model;
- an optional GPSAF assistance component combines a global-search component and a
  surrogate-model component while preserving exploration and real validation;
- zero or more refinement components may add bounded proposal/validation stages;
- the common real-evaluation handoff remains package-owned and is not replaceable by
  workspace code that writes history or returns predicted values as truth.

Illustrative, non-final spelling of the intended compositions is:

```python
def build_optimization():
    global_search = by_objective_count(
        single=genetic_algorithm(),
        multi=nsga3(),
    )
    return optimization_plan(
        gpsaf(
            search=global_search,
            surrogate=conditional_inr(),
        )
    )
```

The component contracts must also be able to express, in separate workspaces:

1. the current GPSAF + (single-objective GA / multi-objective NSGA-III) +
   conditional-INR behavior;
2. that same plan followed by a future trust-region surrogate local-refinement
   component;
3. a multi-objective NSGA-III-only plan with no GPSAF or surrogate training;
4. GPSAF with a future particle-swarm search component instead of the present
   evolutionary search component;
5. GPSAF with another rawData-first surrogate component instead of conditional INR.

This task does not implement production particle swarm, another surrogate, or the
trust-region algorithm. Focused test components must prove that each role can be
replaced or appended without duplicating campaign/evaluation/history code. Numerical
validity for a real added method remains its own implementation task.

## Library-First Numerical Policy

- Yadof should own orchestration and task-boundary semantics, not generic numerical
  algorithms. Before extracting or writing any search, local solver, loss, sampler,
  neural layer, or population operator, audit mature installed packages and their
  supported versions, licenses, state/restart behavior, objective/domain support,
  determinism, and serialization boundaries.
- A package imported directly by yadof must be declared as a direct core or optional
  dependency with a supported version range; do not rely on it only because another
  dependency happens to install it transitively. In particular, direct SciPy-backed
  code requires an explicit dependency decision during implementation.
- Where a compatible implementation exists, expose a thin lazy adapter/factory that
  constructs the library object with explicit keyword defaults. The few yadof-owned
  lines should make the effective default parameters inspectable for workspace
  composition and provenance, translate normalized arrays/results, and enforce
  yadof invariants. They must not copy or subtly fork the library's numerical loop.
- Prefer pymoo's GA, NSGA-III, and PSO implementations and SciPy's applicable
  scalar-objective local/global solvers instead of reimplementing them. A pymoo PSO
  is single-objective and therefore is not a semantic drop-in replacement for the
  current multi-objective NSGA-III path; plan validation must reject incompatible
  objective/constraint capabilities rather than silently scalarize or fall back.
- The installed pymoo has no GPSAF component. Preserve only the yadof-specific GPSAF
  assistance/orchestration that cannot be delegated, and re-audit mature packages
  before implementation in case a compatible maintained dependency can replace
  more of it. Adopting or upgrading a dependency requires focused equivalence and
  recovery tests; this toDo does not assume an upgrade.
- Conditional INR should use mature PyTorch primitives for modeling, optimization,
  losses, batching, and serialization wherever their semantics fit. Yadof retains
  only rawData schema/query reconstruction, task/campaign adaptation, component
  lifecycle, provenance, and checkpoint integration that are specific to its
  contract. If a maintained package can satisfy that complete capability later, it
  should be preferred behind the same component boundary.
- "Expose defaults" is an adapter concern, not permission to mirror an implementation.
  Each public numerical factory must document and pass explicit effective defaults,
  identify its backend/version for provenance, and leave unsupported backend options
  available only through a deliberately reviewed narrow escape hatch, if one is
  genuinely needed.

## Package Boundary

### `yadof.optimize`

- Retain public workspace-explicit `run_one_generation()` and `run_generations()` as
  the package-owned campaign engine.
- Move `OptimizationResult` and common population/history/evaluation contracts out
  of the current complete GPSAF implementation.
- Load and validate the workspace plan through one public/internal plan boundary;
  the engine invokes it once per generation under the generation snapshot.
- Expose GPSAF pressure and objective-count dispatch as small composable yadof
  boundaries. Expose GA and NSGA-III through thin pymoo-backed factories with
  explicit effective defaults; do not extract or duplicate pymoo numerical
  mechanics into yadof. Pymoo types remain private to those adapters.
- Do not add `OPTIMIZE_METHOD`, `SURROGATE_METHOD`, or
  `OPTIMIZE_GPSAF_SEARCH_BACKEND` selectors. Those choices belong in
  `submit/optimization.py`, and a package selector would create a second source of
  truth.
- Do not keep a package registry entry representing the complete current algorithm.
  Component-local IDs/factories needed for provenance, recovery, or viewer
  inspection are allowed, but they cannot select a complete plan independently of
  the workspace script.

### `yadof.surrogate`

- Keep only method-independent training-data/session adaptation, scheduling,
  lifecycle, compact metadata, and checkpoint publication that yadof actually needs;
  do not build generic surrogate-framework machinery already supplied by mature
  dependencies. Separate those boundaries from the conditional-INR
  model/data/artifact adapter.
- Expose the simplified conditional INR as a rawData-first surrogate component with
  explicit stable identity and capabilities. It must still reconstruct full rawData
  before current cost and must never become an authoritative direct-cost model.
- Scheduler and optimizer code depend on a selected component instance/contract,
  not directly on `surrogate.runtime` or a global default method.
- Viewer integration may use a component-specific inspection adapter or artifact
  identity, but it must not silently assume every plan uses conditional INR.

The detailed source split, dependency direction, dependency-reuse audit, and
component tests are maintained in the coordinated modularization toDo. Avoid
symmetric empty files, generic `utils.py`, speculative third-party plugin APIs,
wrappers that only forward the old complete algorithm, and yadof-owned copies of
backend algorithms.

## Snapshot, Identity, And Campaign Policy

- A generation snapshot owns both `submit/` and `job_template/`. It rebases both
  paths into one immutable temporary workspace and keeps jobs, history, checkpoints,
  logs, and tool output pointed at the real workspace.
- Interpretation fingerprints start from
  `job_template/parameters_constraints.py` and `submit/calc_cost.py`, following each
  root's dependency-aware local imports. Physical ownership does not remove the
  canonical parameter source from submit-side interpretation provenance.
- Evaluation fingerprints start from `job_template/workflow.py` and optional
  `job_template/evaluation.py` plus evaluate-side dependencies and semantic config.
- Add an optimization-definition fingerprint rooted at
  `submit/optimization.py` plus its submit-local dependencies. Record the complete
  task snapshot ID and the plan/component identities in generation and surrogate
  metadata.
- Cost/parameter/evaluator task corrections retain the documented generation-boundary
  behavior. A complete optimization-plan change is structural state change: after
  the first generation of a campaign, a changed optimization fingerprint or
  incompatible component identity fails before evaluation and instructs the user to
  use a new workspace or explicitly clear history/checkpoints.
- Numeric source edits that alter a stateful component cannot bypass this rule by
  reusing the same declared ID. Source fingerprint and declared component identity
  are separate provenance fields.
- Background surrogate work receives the same owned generation snapshot and exact
  plan/component selection. No thread may reopen the live `submit/optimization.py`
  while a generation is running.
- One workspace owns one plan and one set of component state/checkpoints. The design
  does not support switching plans against retained optimizer/surrogate state or
  keeping several active plans in one workspace.

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
  current cost, optimization plan, misplaced reserved files, backend requirements,
  and workflow syntax without importing/running the workflow or starting numerical
  work.
- Update generic smoke assessment to compare every starter source that affects its
  evaluation/cost contract. Merely relocating submit files must not make an edited
  real task look like the untouched starter.
- Keep packaged adapters/tools that locate canonical parameters on
  `job_template/parameters_constraints.py`; update only cost/optimization consumers
  to the new submit root. Adapters and models copied for execution still target
  `job_template/`.
- Migrate repository reference workspaces and tests to the new layout. Do not add a
  dual-path loader or silently accept legacy files in both locations.
- Existing user workspaces are never rewritten by `init`. Bump template provenance
  and document an explicit fresh-workspace/copy-task migration. `check` should
  diagnose the old layout and explain the move; it must not move files, edit the
  marker, clear history, or guess whether an active campaign is safe to migrate.
- Because plan identity and checkpoint layout are intentionally fresh-only in this
  series of tasks, acceptance uses a newly initialized workspace or an explicit
  user-authorized clear/new-workspace path. No legacy optimizer/checkpoint reader is
  added.

## Implementation Plan

### Phase 0 - Freeze The Post-Simplification Baseline

- [ ] Confirm the real-only surrogate toDo is archived and its final checkpoint and
  trust-signal removals are the only baseline.
- [ ] Characterize the current seeded default for single-objective GA,
  multi-objective NSGA-III, GPSAF warmup/fallback/alpha/beta/exploration, staggered
  conditional-INR training, current-cost conversion, and real validation.
- [ ] Inventory every loader/path/test/tool that consumes canonical parameters from
  `job_template/` or assumes `calc_cost.py` is beside them.
- [ ] Produce a library-reuse matrix for every numerical responsibility: installed
  backend/version, capabilities, explicit defaults, state/restart and determinism,
  yadof adapter duties, and evidence for any algorithm code that must remain in
  yadof. Confirm locally that pymoo GA/NSGA-III/PSO are available, installed pymoo
  GPSAF is not, and SciPy candidates are evaluated only for compatible scalar goals.

### Phase 1 - Establish The Two-Root Workspace

- [ ] Add the explicit submit path to workspace context/config validation and teach
  the fresh loader to isolate submit-local modules independently of execute modules.
- [ ] Move only cost and other exclusively submit-side sources in the template,
  examples, neutral test workspaces, tools, and task APIs; retain canonical
  parameters under `job_template/` without a duplicate submit copy.
- [ ] Make job preparation copy only evaluate-side task content and generate the
  assigned parameter handoff from the snapshotted canonical source. Replace the old
  cost exclusion with actionable misplaced-file validation while preserving the
  intentional canonical-parameter materialization exception.

### Phase 2 - Extend Generation Snapshots And Provenance

- [ ] Capture/rebase both roots atomically and split interpretation, evaluation, and
  optimization dependency fingerprints.
- [ ] Preserve per-generation hot task semantics for cost/evaluation while freezing
  the plan identity across a campaign.
- [ ] Record plan/component/source provenance and prove asynchronous training uses
  the owned snapshot.

### Phase 3 - Extract Composable Package Components

- [ ] Execute the coordinated modularization toDo: separate campaign/common
  contracts, irreducible GPSAF assistance, thin pymoo/SciPy adapters,
  conditional-INR-specific adaptation, scheduling, checkpoints, and inspection along
  actual call boundaries.
- [ ] Delete or avoid yadof numerical mechanics already supplied by an accepted
  mature dependency. Factories expose explicit effective defaults and backend
  identity; equivalence tests compare behavior through public yadof contracts rather
  than copying backend implementation details.
- [ ] Remove the package-owned complete-algorithm dispatch and any planned selector
  configs/registries that duplicate workspace composition.
- [ ] Preserve current behavior through the new component graph and keep optional
  dependencies lazy.

### Phase 4 - Load And Run The Workspace Plan

- [ ] Define and validate the minimal `build_optimization()` return contract and
  component identities/capabilities.
- [ ] Make the campaign engine invoke the snapshotted plan while retaining common
  real evaluation, session history, failure, progress, metadata, and recorder
  behavior.
- [ ] Add focused fake components proving a refinement step can be appended and a
  search or surrogate component can be replaced without infrastructure copies.
- [ ] Add a real NSGA-III-only neutral test plan; it performs no surrogate training
  and remains multi-objective-only.

### Phase 5 - Init, Check, Tools, And Documentation

- [ ] Publish the new default template and bump its provenance without adding
  automatic repair/upgrade.
- [ ] Update `check`, smoke assessment, parameter extraction, adapter copying/path
  guidance, history/cost/surrogate viewers, history clear, examples, and package
  artifact expectations.
- [ ] Update architecture, terminology, project/module/file blueprints, user docs,
  prompt examples, template README, and the nested surrogate-viewer documentation
  where component/plan discovery changes.

### Phase 6 - Installed Acceptance

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
  follow current rules; a plan change after campaign start fails before candidate
  evaluation until the workspace is new/cleared.
- Loader tests cover submit-local relative/absolute helper imports, same-named
  helpers across roots/workspaces, exception cleanup, and no lasting `sys.path` or
  `sys.modules` pollution.
- Default-plan tests cover single-objective GA and multi-objective NSGA-III, seeded
  GPSAF phases, real-only conditional INR, warm start, fallback, exploration,
  staggered training, rawData-first current cost, and real validation.
- Composition tests cover multi-objective NSGA-III without GPSAF/surrogate, an
  appended fake refinement, a replacement fake search component, and a replacement
  fake rawData-first surrogate. These prove contracts and dependency direction, not
  production quality of unimplemented methods.
- Lifecycle tests cover plan-aware checkpoint paths/metadata, history clear,
  workspace state isolation, viewer method handling, scheduler reset, recording-loss
  isolation, and absence of a second config/registry selection source.
- Static checks recursively reject old internal imports, duplicate complete
  algorithm implementations, backend numerical loops copied into yadof, task code
  copied into package fixtures, legacy workspace fallback paths, and package parent
  imports that eagerly load Torch, pymoo method implementations, SciPy solvers,
  Matplotlib, Tkinter, or viewer UI. Adapter tests assert explicit forwarded defaults,
  capability rejection, backend identity, and deterministic state/restart behavior.
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
  `build_optimization()` composition. Yadof owns reusable components and invariant
  campaign/evaluation/persistence mechanisms, with no competing complete-method
  config selector or registry.
- The starter reproduces GPSAF + objective-count-dependent GA/NSGA-III + simplified
  conditional INR. NSGA-III-only and fake append/swap plans prove the intended
  composition roles without claiming unimplemented numerical methods are ready.
- Yadof contains no copied implementation of an accepted backend algorithm. Mature
  package implementations are reached through thin lazy adapters whose explicit
  defaults and capabilities are inspectable; only yadof-specific orchestration,
  rawData/task adaptation, real-validation, and persistence glue remain, with a
  written justification wherever no compatible mature implementation exists.
- Plan/component/source provenance is durable, one generation is coherent, one
  campaign cannot silently change plans, and rawData-first plus real-validation
  invariants remain intact.
- Init/check/migration diagnostics, examples, architecture, blueprints, terminology,
  user docs, nested viewer docs, artifacts, and tests all describe the new standard;
  installed full pytest passes from the force-reinstalled wheel.
- This document and the coordinated modularization toDo are archived together. The
  later trust-region toDo can then add a real refinement component through the
  workspace plan rather than changing package-owned complete-algorithm dispatch.
