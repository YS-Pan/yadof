# 2026-08-20 12:54 - Plan Workspace-Defined Optimization

## Context

- The current workspace mixes submit-only canonical parameters and cost policy with
  execute-side workflow payload below `job_template/`, although job preparation
  explicitly excludes the submit-only sources.
- The complete GPSAF + pymoo GA/NSGA-III + conditional-INR combination is currently
  selected inside yadof. The existing modularization plan would have retained this
  ownership through package registries and config selectors.
- The user requested a new submit-side workspace directory, a workspace Python file
  that composes the optimization process from yadof modules, corresponding package
  component boundaries, initialization changes, and alignment of the three active
  manual surrogate/optimization toDos.

## Change

- Added a manual umbrella toDo defining the `submit/` workspace directory,
  `submit/optimization.py:build_optimization()`, two-root generation snapshots,
  separate interpretation/evaluation/optimization fingerprints, plan provenance,
  fresh-workspace migration, init/check changes, verification, and completion
  criteria.
- Recorded two implementation facts that affect the move: canonical
  `parameters_constraints.py` is submit-loaded and replaced by a generated assigned
  job file, while optional `evaluation.py` remains evaluate-side because a
  distributed workflow may share it.
- Corrected the current algorithm description to single-objective GA versus
  multi-objective NSGA-III under optional GPSAF/conditional-INR assistance.
- Rewrote the modularization toDo around composable campaign, search, GPSAF,
  surrogate, and refinement roles. Removed its planned complete-method registries
  and config selectors so the workspace plan is the sole complete-algorithm source.
- Updated the real-only surrogate toDo to remain the first current-layout phase and
  hand its simplified result to the coordinated workspace/component change without
  introducing dual paths.
- Updated the trust-region toDo so refinement is an appendable workspace-plan
  component rather than a GPSAF search backend or package-selected complete method;
  derivative, mixed-parameter, and benchmark decisions remain explicit.

## Rationale

- A directory boundary is safer and easier to explain than maintaining special
  exclusions for submit-only files inside an execute payload tree.
- Keeping invariant campaign/evaluation/persistence mechanisms in yadof while
  composing numerical components in the workspace makes task-level algorithm
  choices visible and editable without duplicating framework infrastructure.
- One authoritative workspace plan plus frozen fingerprint/component provenance
  avoids contradictory config/registry selection and unsafe mid-campaign state
  changes.
- Coordinating the new umbrella with the existing modularization work avoids a
  temporary refactor that would have to be immediately reversed.

## Impact

- No package code, runtime behavior, workspace file, checkpoint, history, public API,
  architecture, blueprint, terminology, or user workflow changed in this planning
  task.
- Future implementation order is now: real-only surrogate cleanup first; workspace
  submit/composition and package componentization together; trust-region refinement
  afterward.
- Pending work is described by the new umbrella and the three revised manual toDos.

## Follow-Up

- Execute the manual toDos only when explicitly requested and in their documented
  dependency order.
- During implementation, settle the smallest concrete component constructor names
  from current call sites, then update all current-view documentation and perform
  installed-wheel acceptance before archiving the coordinated toDos.
