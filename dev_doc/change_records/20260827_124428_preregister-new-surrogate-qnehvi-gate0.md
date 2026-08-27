# 2026-08-27 12:44 - Preregister New Surrogate and qNEHVI Gate 0

## Context

- The new hierarchical rawData surrogate, joint-posterior, and qNEHVI work must
  begin with a reviewable schema inventory and benchmark preregistration rather
  than implementation or result-driven thresholds.
- The editable SAW, Chrono, and synthetic-antenna baseline manifests each contain
  zero recorded rows and zero checkpoints. The selected timing-history policy is
  empty, and the historical README summaries do not have inspectable run specs in
  the configured run root, so no legal frozen 1000/2000-design dataset is present.
- Chrono uses the existing adapter's subprocess boundary. The outer environment
  points `YADOF_PYCHRONO_PYTHON` at an independent Conda interpreter; its package
  record identifies PyChrono 10.0.0 build `py313h418371c_0` without importing the
  native module or running a model.

## Change

- Added a tracked Gate 0 preregistration containing:
  - exact field selectors, main keys, shapes, axes and digests, float64
    representation, array bytes, parameter semantics, objective widths, task
    fingerprints, and relevant source hashes for all three representative cases;
  - a provenance audit that distinguishes source/schema evidence, zero-record
    templates, unavailable historical summaries, and future eligible recorded
    evidence;
  - a row-order-independent design identity and design-level split with 400 test,
    200 calibration, 200 validation, and 2,000 nested training-pool designs per
    case;
  - disjoint seed groups, offline/posterior/online comparison matrices, metrics,
    the registration resource block, gate inputs, and stop conditions;
  - an intentionally unsealed numeric-threshold template that freezes derivation
    rules and pass logic without inventing acceptance values; and
  - a no-simulation validator plus focused tests for source drift, artifact
    integrity, blocked readiness, and deterministic disjoint/nested splits.
- Recorded the independent PyChrono interpreter, interpreter hash, Conda record
  hash, version/build/channel, and package hash in the resource block. The formal
  run contract still requires adapter preflight and a run-local frozen environment.
- Updated benchmark architecture, blueprints, terminology, test coverage, and the
  operator README to define preregistration as an inert input contract rather than
  a runnable suite or evidence.
- Updated the root architecture, project blueprint, terminology, and active
  acceptance TODO with the completed Gate 0 status and the next-gate boundary. The
  overall TODO remains active because Gates 1--6 are not complete.

## Validation

- Gate 0 validator: passed with all three task fingerprints and schemas matching;
  `data_status=no-eligible-frozen-dataset`,
  `threshold_status=unsealed-template`,
  `pychrono_version_evidence=conda-record:10.0.0`,
  `formal_test_ready=false`, and `simulator_launched=false`.
- `pytest -q benchmark_automation/tests -p no:cacheprovider` with a fresh absolute
  basetemp: 62 passed in 2.46 seconds.
- No-write `plan --suite performance`: six cells, 12,000 planned attempted
  evaluations, three cases, two current arms, and one paired seed.
- No-simulation `preflight --suite structural-full`: 13/13 checks passed against
  installed yadof 0.4.1 from the outer workspace, including both external runtime
  paths and CUDA.
- No wheel was built or installed: package code, build configuration, resource
  mapping, and installed-package behavior are unchanged; benchmark automation and
  developer documentation are source-checkout-only for this change.

## Impact

- Gate 0 is reproducible and reviewable, but intentionally not formal-test-ready.
  A baseline template shape or zero-record manifest cannot be reported as a
  training dataset, and this change does not authorize a simulator campaign.
- The future formal optimization matrix is preregistered as five arms, five seeds,
  three cases, and 2,000 attempted evaluations per cell (150,000 total). It remains
  blocked until its gate-specific evidence and explicit campaign authority exist.
- Runtime APIs, current conditional-INR/GPSAF behavior, baseline contents, recorded
  data, checkpoints, and user-visible installed behavior are unchanged.

## Follow-Up

- The next execution unit is the lightweight joint rawData posterior contract:
  persistent function-sampler semantics, chunk/permutation invariance, structured
  fake rawData, and a thin current-`CostInterpreter` projector.
- It may start only from a committed tree whose Gate 0 validator passes. Schema or
  split changes require a new preregistration version. The next unit must not make
  1000/2000-design fitting, calibration, or optimization claims.
- Before Gate 4 or any formal test, select or generate an authorized immutable
  dataset with at least 2,800 compatible unique designs per case and seal its
  provenance manifest. Before viewing formal test results or launching the Gate 6
  matrix, seal numeric thresholds from the permitted validation/calibration/pilot
  evidence and obtain the applicable simulator-campaign authorization.
