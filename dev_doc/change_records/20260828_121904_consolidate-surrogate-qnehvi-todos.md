# Consolidate Surrogate And qNEHVI TODOs

## Summary

Consolidated the six 2026-08-27 surrogate/posterior/qNEHVI plans into one active,
standalone remaining-work handoff. The two completed plans were already under
`dev_doc/obsolete/`; the four long, partially completed plans were moved there by
explicit user request.

## Documentation decision

The new handoff is the only active execution entry for that six-document batch. It
records the implemented joint-posterior, conditional-INR adapter, hierarchical-CAE,
calibration, qNEHVI, fallback, validation, and structural-release mechanisms; it
also records the frozen representation/quality/calibration failures and the missing
formal benchmark arms.

The remaining route is ordered as successor architecture and PCA/SVD baselines,
independent exact-state calibration, real typed readiness, eligible qNEHVI
integration, the complete seven-arm same-budget benchmark, and a separate release
decision. Links to the six archived plans are supplemental historical provenance
and are not prerequisites for normal context gathering or execution.

## Impact

- Moved TODOs 082608, 082609, 082611, and 082612 from `dev_doc/toDo/` to
  `dev_doc/obsolete/`; 082607 and 082610 were already archived.
- Added one active consolidated TODO and updated active PCA/SVD and anti-noise
  handoffs to use it as the current state owner.
- Repaired historical cross-links affected by the moves.
- Updated the package artifact test to expect the archived qNEHVI plan and the new
  active consolidated plan.
- No package runtime, algorithm, scientific result, frozen preregistration, receipt,
  threshold, evidence, configuration, or user behavior changed.

## Validation

- Verify UTF-8 and all changed Markdown links.
- Verify the old six files exist below `obsolete/`, no longer exist below `toDo/`,
  and the new consolidated file is the only active handoff for the batch.
- Run whitespace checks, the focused artifact test, wheel build/force-reinstall,
  import-origin verification, and the full installed-package suite because the
  documented wheel-resource paths changed.
