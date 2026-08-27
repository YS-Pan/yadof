# 2026-08-27 14:00 - Add Joint rawData Posterior Contract

## Context

- The current conditional-INR/GPSAF boundary returns per-candidate mean costs and
  member min/max diagnostics. It cannot express the candidate-, field-, and
  objective-joint function draws required by a future posterior acquisition.
- The authoritative path remains normalized variables to complete rawData to the
  current generation's task cost callback. Posterior infrastructure must not fit
  cost directly, write predicted rawData as evidence, or change worker and history
  formats.
- Gate 0's preregistered schemas, splits, provenance audit, and unsealed threshold
  state remain unchanged. No eligible frozen 1000/2000-design dataset exists, and
  this implementation did not launch a simulator campaign.

## Change

- Added a backend-neutral, runtime-checkable joint posterior capability with:
  - persistent sampler and stable draw identities reusable across candidate
    chunks;
  - structured function draws and a small-population materialized convenience
    container;
  - honest finite-versus-continuous/unknown support diagnostics, reproducible seed,
    source identities, signatures, limitations, selectors, and bounded failures;
  - explicit capability validation and a JSON-safe semantic identity block that
    includes protocol, backend version, and controlled parameters; and
  - no Torch, BoTorch, pymoo algorithm, plotting, or GUI import at the parent
    package boundary.
- Added frozen rawData schema templates keyed only by exact
  `(direct .npz basename including .npz, resolved values/data main key)`. Main
  shape/dtype plus axes, units, metadata, and other non-main template values are
  signature-bound and reconstructed into complete current-schema samples.
- Added `RawDataCostProjector` as a narrow streaming adapter around one existing
  `CostInterpreter`. It reuses the interpreter's frozen task parameters, variable
  denormalization, callback, objective order, and typed width check. It retains only
  joint objective samples, a validity mask, and bounded diagnostics after each
  rawData draw/chunk is projected.
- Defined validity precisely: a finite callback row, including an
  indistinguishable finite `error_cost=1.0` fallback, is valid. Schema drift,
  normalized-variable failure, callback failure, wrong objective width, or
  non-finite cost is invalid and remains `NaN`/false rather than favorable
  uncertainty.
- Added a two-field, two-shape, two-objective sample-backed fake backend test. It
  covers seeded stable draws, repeated candidates, empty populations, reverse
  chunk order, chunk-size and candidate-permutation invariance, selector/schema
  rejection, streaming/materialized equivalence, bounded failures, semantic
  identity, lazy imports, and the absence of recorder writes.
- Kept `ConditionalINRComponent.predict_population()`, its component version,
  GPSAF selection, checkpoint state, worker transport, task rawData, and recorded
  evidence formats unchanged. A conditional-INR posterior adapter, CAE model,
  posterior calibration, qNEHVI strategy, and benchmark gates remain separate
  active work packages.

## Documentation

- Updated architecture views, C4 diagrams, project/module/file blueprints,
  terminology, checkpoint and optimization-state identity contracts, and the user
  optimization workflow.
- Archived the completed joint-posterior TODO and adjusted only the dependency
  links in its five successor TODOs so those work packages remain independently
  executable.

## Verification

- Built `yadof-0.4.1-py3-none-any.whl`, force-reinstalled it into the outer
  workspace `.venv`, and confirmed `yadof` resolves below
  `.venv/Lib/site-packages/yadof` rather than repository `src`.
- Complete pre-archive installed-package suite: `263 passed in 74.91s`.
- Complete final installed-package suite after TODO archival and packaged-document
  refresh: `263 passed`.
- Gate 0 no-simulation validator remained successful with
  `formal_test_ready=false`, `simulator_launched=false`, no eligible frozen
  dataset, and unsealed numeric performance thresholds.

## Impact

- Concrete backends can now expose coherent structured rawData functions without
  coupling the shared protocol or cost projection path to their numerical stack.
- Current users see no strategy-selection or checkpoint migration. The protocol is
  infrastructure only until a separately identified adapter/model and consuming
  acquisition strategy are selected.
- Gate 0 schema/split/provenance semantics and all durable simulator evidence
  remain untouched.

## Follow-Up

- The conditional-INR adapter must provide member-major, full named rawData draws,
  stable member source identities, and its own posterior semantic identity without
  cold-invalidating the existing GPSAF component.
- A qLogNEHVI/qNEHVI spike must consume only projected joint objective samples,
  define invalid-draw handling, preserve optional-backend lazy imports, and remain
  a separately selected strategy.
- CAE fitting, calibration, numerical performance gates, and formal benchmark
  claims still require the later TODOs. Dataset selection/generation and threshold
  sealing must follow the preregistration gates and obtain separate simulator
  campaign authority where applicable.
