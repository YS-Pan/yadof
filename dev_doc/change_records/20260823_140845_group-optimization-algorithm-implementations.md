# Group optimization algorithm implementations into subpackages

- Timestamp: 2026-08-23 14:08

## Context

The optimization and surrogate implementations had grown into flat packages even
though GPSAF, pymoo integration, and conditional-INR each consist of several
closely related implementation files. The public factories and workspace-facing
contracts still need to remain stable and lazily imported.

## Change

- Moved GPSAF implementation files under `yadof.optimize.gpsaf`.
- Moved the pymoo adapter under `yadof.optimize.pymoo`.
- Moved conditional-INR runtime, modeling, checkpoint, scheduling, metadata, and
  type modules under `yadof.surrogate.conditional_inr`.
- Kept `yadof.optimize.gpsaf()` and `yadof.surrogate.conditional_inr()` as the
  public callable factories while preloading private package markers to prevent
  later submodule imports from replacing those attributes.
- Updated the surrogate viewer's package-internal imports, tests, architecture,
  blueprints, and wheel-membership assertions.

## Rationale

Algorithm-specific implementation now has an explicit ownership boundary without
adding a method registry, selector layer, compatibility forwarding modules, or a
new public API. Parent packages retain common orchestration, state, and public
entry points.

## Impact

Public optimization and surrogate configuration/workspace behavior is unchanged.
Private flat implementation import paths are intentionally replaced by the new
subpackage paths. Optional pymoo and PyTorch-heavy implementation modules remain
lazy.

## Verification

Verification is recorded by the task's build, installed-package import-origin,
focused-test, and full-test results.
