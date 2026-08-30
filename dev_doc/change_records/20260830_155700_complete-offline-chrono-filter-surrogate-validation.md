# 2026-08-30 15:57 - Complete Offline Chrono Filtered-Surrogate Validation

## Context

- The user explicitly requested execution of the manual offline filtered-target
  surrogate validation TODO.
- Existing context showed Chrono stress peaks and CAE-like prediction chatter, but
  did not establish whether target high-frequency content caused the fitting
  problem or whether smoothing was physically valid.

## Change

- Executed a disposable experiment under
  `temp/20260830_152530-chrono-filter-surrogate-validation` without changing the
  package, benchmark source, recorded history, optimizer, costs, or simulator.
- Froze a train/validation-only zero-phase Butterworth filter plan before test
  access, derived externally mapped stress arrays, and completed the four paired
  raw/filtered x CAE/INR arms for `c0003`.
- Preserved the first superseded pre-test plan/receipt after correcting a
  disposable INR harness attribute error; the correction and final plan were
  completed before any test rawData access.
- Captured source/filter receipts, derived-data mapping, paired metrics, resource
  measurements, same-scale overlays, four viewer workspaces, CLI validation, and
  GUI observations.
- Added a measured context document with the artifact identities, evidence,
  limitations, and stop decision, then moved the completed TODO to the obsolete
  archive.

## Rationale

- The selected filter removed most measured roughness and high-frequency energy,
  and substantially reduced unmatched narrow predictions, but filtered-target
  standardized RMSE improved by less than one percent for both architectures.
- Neither architecture met the preregistered joint fit-and-chatter interpretation.
  The evidence therefore does not justify a package-level filter or a `c0004`
  replicate and instead points back to model, scaling, checkpoint, or viewer
  adaptation questions.

## Validation

- The final filter identity is
  `9ba990995922b550bd4301b3e21c692754adb42b9c8d8356e870163c2b9981c4`;
  train/validation/test completed counts are `1479/148/295`.
- Reserved calibration access remained false, simulator launch remained false,
  and raw/filtered current costs were exactly equal for all opened rows.
- All four arms completed without failure. All four viewer workspaces passed
  `summary` and the frozen 1% `all-costs` audit, and all four GUIs loaded the same
  fixed generation-12/individual-156 test design.
- Fixed same-scale overlays for both target stress fields agreed with the paired
  quantitative result: filtered CAE was less noisy but still missed major peaks;
  raw and filtered INR were smooth and also underfit those peaks.

## Impact

- Repository impact is documentation only: one measured context, this change
  record, and archival of the completed TODO.
- No user documentation, architecture, blueprint, terminology, package code,
  installed package, simulator evidence, optimization state, or default behavior
  changed.

## Follow-Up

- Stop the filtering route for now and investigate model/scaling/checkpoint/viewer
  adaptation only under a separately authorized task.
- Any production integration, simulator rerun, physical event analysis, cost-truth
  change, wider field transform, `c0004` replication, or extended training requires
  new authorization and proportional documentation.
