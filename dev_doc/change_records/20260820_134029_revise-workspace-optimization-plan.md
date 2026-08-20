# 2026-08-20 13:40 - Revise Workspace Optimization Plan

## Context

- The preceding planning change moved canonical
  `job_template/parameters_constraints.py` into the proposed `submit/` directory and
  treated yadof-owned numerical components as the primary modularization target.
- The user clarified that the canonical parameter/constraint source must remain on
  the worker-facing side and that yadof should minimize its own surrogate/optimizer
  modules and numerical implementations in favor of mature packages.
- Local inspection used the installed project environment: `pymoo 0.6.2` provides
  GA, NSGA-III, and single-objective PSO but no GPSAF module; `scipy 1.18.0` provides
  mature scalar-objective local/global solvers; `torch 2.10.0` supplies the existing
  conditional-INR primitives.

## Change

- Revised the workspace composition toDo so canonical
  `job_template/parameters_constraints.py` remains in place. Submit-side preparation
  still loads the snapshotted source and generates the self-contained assigned file
  sent to each worker; the canonical source itself is not copied into a job.
- Narrowed the new `submit/` tree to `calc_cost.py`, `optimization.py`, and other code
  that is exclusively submit-side. Updated init, check, snapshot, fingerprint,
  tooling, migration, verification, and completion requirements accordingly.
- Added a library-first numerical policy: audit supported mature dependencies before
  implementing an algorithm, use thin lazy adapters, expose explicit effective
  defaults and backend identity/version, validate capabilities, and do not copy
  backend numerical loops into yadof. Any directly imported backend must be declared
  as a direct core/optional dependency rather than assumed from transitive installs.
- Revised the modular surrogate/optimize toDo to target fewer package files and less
  framework machinery. Pymoo remains responsible for GA/NSGA-III mechanics, PyTorch
  for compatible modeling/training primitives, and yadof for only its irreducible
  orchestration, rawData/task adaptation, real-validation, lifecycle, and provenance
  boundaries.
- Revised the real-only surrogate toDo to use mature primitives while retaining only
  yadof-specific field/slot and rawData behavior, without expanding that first phase
  into a backend migration.
- Revised the trust-region refinement toDo to require a dependency-reuse matrix and
  prefer thin SciPy/pymoo-backed solver adapters. It now distinguishes backend inner
  solver state from yadof's outer prediction-versus-real model-management loop.

## Rationale

- Canonical parameters define the generated worker handoff even though the submit
  process loads them, so retaining their worker-facing source ownership makes the
  workspace standard clearer without changing the safe self-contained transfer
  contract.
- Mature numerical libraries provide broader testing, maintenance, and known
  semantics than local copies. Yadof adds value at campaign, task, rawData,
  distributed-evaluation, and provenance boundaries rather than by duplicating
  general optimization or neural-network machinery.
- A named algorithm is not automatically interchangeable: the installed pymoo PSO
  is single-objective and cannot directly replace multi-objective NSGA-III, while no
  installed GPSAF implementation can currently replace yadof-specific GPSAF
  coordination. Explicit capability checks prevent misleading compositions.

## Impact

- Only active planning documents changed. No package code, runtime behavior,
  workspace template, dependency, public API, checkpoint, history, architecture,
  blueprint, or user documentation changed.
- Future implementation must begin with the recorded dependency/capability audit and
  justify every remaining yadof-owned numerical routine. It must not assume a
  dependency upgrade or claim that test-only replacement components are production
  algorithms.

## Follow-Up

- Execute the real-only toDo first. Then execute the workspace composition and
  modularization toDos together; only afterward implement trust-region refinement.
- During implementation, re-check supported dependency versions/licenses and run
  adapter default, capability, determinism, restart, provenance, installed-wheel,
  and full-suite tests before archiving the coordinated toDos.
