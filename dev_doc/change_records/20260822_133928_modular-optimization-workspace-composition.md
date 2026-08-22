# 2026-08-22 13:39 - Modular Optimization And Workspace Composition

## Context

- The active manual work consisted of two coordinated toDos: one moved complete
  optimization composition into the workspace, and the other reduced package
  optimizer/surrogate ownership to the narrow components required by that
  composition.
- The previous workspace placed submit-side cost policy beside evaluate-side job
  sources and the package directly selected the complete GPSAF algorithm. That
  boundary could copy submit policy into prepared jobs and could not represent a
  workspace-owned alternative strategy without a second package selector.
- The archived real-only conditional-INR implementation remained the behavioral
  baseline. The parked trust-region research remained out of scope.

## Dependency Reuse Audit

- Retained pymoo 0.6.2 (Apache-2.0) as the supported GA/NSGA-III backend through
  the existing `pymoo>=0.6,<0.7` core range. Pymoo continues to own algorithms,
  populations, operators, reference directions, survival, and ask/tell mechanics.
- Retained PyTorch 2.10.0+cu128 (BSD-3-Clause) as the conditional-INR primitive
  backend and bounded the optional supported major range to `torch>=2.2,<3`.
- Confirmed pymoo does not provide GPSAF, so yadof retains only its task-specific
  rawData prediction, real-validation, generation, and component-coordination
  assistance. No SciPy, refinement role, plugin registry, PSO, or second surrogate
  implementation was added.

## Workspace And Snapshot Changes

- Established the fixed `submit/` root for `calc_cost.py`, submit-local helpers,
  and mandatory `optimization.py:build_optimization()`; retained canonical
  parameters, workflow, kernels, and evaluate assets under `job_template/`.
- Parameterized the isolated task loader by source root while preserving fresh
  compilation, relative and absolute sibling imports, same-named helper isolation,
  exception cleanup, and no persistent `sys.path` or `sys.modules` changes.
- Added legacy-layout, missing-file, misplaced-source, and pairwise path-overlap
  diagnostics. Init/check validate strategy construction without running training,
  prediction, evaluation, or the workspace workflow.
- Generation snapshots now copy and hash both complete roots beneath one immutable
  snapshot. Source fingerprints retain provenance, while semantic strategy/state
  signatures independently determine compatibility.
- Prepared local/distributed jobs continue to receive only evaluate-side assets and
  a generated assigned-parameter snapshot; submit cost, strategy, and helpers never
  enter a job or transfer list.

## Optimization Composition Changes

- Added common engine-owned generation context/result/history contracts and a
  loader for the single immutable strategy returned by snapshotted workspace code.
- Added thin lazy components for pymoo GA, pymoo NSGA-III, objective-count dispatch,
  real-only search, GPSAF assistance, and conditional-INR rawData prediction.
- The default template now composes GPSAF with GA for one objective, NSGA-III for
  multiple objectives, and conditional INR. A real multi-objective NSGA-III-only
  composition runs through the same campaign/evaluation/recording engine.
- NSGA-III-only validation fails clearly below two objectives. Backend version,
  selected algorithm, reference-direction controls, and the intentionally small
  yadof-controlled parameter set are exposed in semantic identity and diagnostics.
- Removed the package-owned complete `gpsaf.py` entry and renamed the retained
  assistance implementation so importing the submodule cannot overwrite the
  public `gpsaf()` composition factory.

## State, Tools, And Documentation

- Added an atomic `.yadof/optimization/active.json` pointer. Strategy switching
  waits for pending surrogate work, releases in-memory ownership, activates the new
  semantic namespace, and retains recorded evidence and all inactive artifacts.
- Conditional-INR checkpoint format 2 records strategy, state, run, and component
  identity. Recovery and viewer discovery are restricted to the compatible active
  `strategy-*/components/conditional-inr/` namespace.
- History clear now also removes generated optimization state explicitly; smoke,
  history, viewer, metadata, and example paths follow the two-root contract.
- Published default template version 2, migrated the maintained HFSS example, and
  updated user documentation, prompt guidance, root and nested architecture,
  terminology, project/module/file blueprints, and package artifact expectations.
- Bumped the single public package version and all current-version expectations
  from 0.3.0 to 0.4.0 after implementation and documentation were complete.
  Historical records were not rewritten.

## Verification

- Production source and tests compiled successfully with an isolated bytecode
  cache.
- Built `dist/yadof-0.4.0-py3-none-any.whl` and force-reinstalled it into the
  sibling `.venv`. Isolated import and CLI checks reported 0.4.0 from
  `.venv/Lib/site-packages/yadof`; importing `yadof.optimize` and
  `yadof.surrogate` loaded none of Torch, pymoo algorithm modules, Matplotlib, or
  Tkinter.
- Broad focused installed-package acceptance passed 124 tests; the final
  review-focused composition/state/distributed/tool subset passed another 41 tests.
  Together they cover loaders/config, init/check, optimizer/surrogate behavior,
  pending-work shutdown, viewer scope, recording-loss isolation, and
  local/distributed job preparation.
- Wheel/sdist membership and clean external virtual-environment installation passed
  all 6 package-foundation tests.
- Two separately initialized template-version-2 workspaces contained the same exact
  six files and both passed installed `yadof check` with zero warnings.
- The complete installed-package suite passed: 271 tests, with 8 expected warnings
  from tests that deliberately inject history-writer loss or interruption.
- No live simulator, surrogate benchmark campaign, or HTCondor execution was
  started.

## Outcome

- Complete algorithm ownership now exists only in snapshotted workspace
  `submit/optimization.py`; yadof owns the invariant campaign engine and minimal
  accepted-backend/task-adaptation seams.
- Source provenance, semantic state compatibility, and retained inactive evidence
  are distinct, auditable contracts. Both coordinated manual toDos are complete
  and may be archived together.
