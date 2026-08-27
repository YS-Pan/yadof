# 2026-08-27 23:27 - Experimental Hierarchical CAE Coordinate/Offline Framework

## Context

- Gate 0 v5 froze a valid failure for the first hierarchical-CAE production
  candidate: representation and quality/regime requirements did not pass, and TODO
  082608 could not be archived.
- The user later made that performance failure non-blocking only for the remaining
  framework work. Thresholds, results, and scientific acceptance were not allowed to
  change; performance tuning and a successor architecture were explicitly deferred.
- Offline-test access therefore required a new pre-access registration that could
  prove mechanism execution but could not create an acceptance decision.

## Change

- Added architecture-version-2 field-local coordinate readouts to hierarchical CAE.
  They reuse each persistent predictor member's global/optional-group/private latent,
  use a smooth base plus the existing applicability-gated private residual, and are
  trained after the authoritative full-grid stages using development-only splits.
- Added explicit all-axis linear/log/periodic encoding, stored-grid consistency,
  in-domain validation, bounded query batching, typed mean/member results, and a
  read-only `predict_field_at_coordinates()` component API. Coordinate configuration,
  capability identity, training diagnostics, and state enter checkpoints.
- Added a hierarchical checkpoint adapter to the surrogate viewer. Generic discovery
  selects one compatible active conditional-INR or hierarchical-CAE namespace;
  method-specific readers never mix state. Full-grid rawData remains authoritative
  for cost, posterior, audit, and optimization.
- Added Gate 0 v6 pre-access plan/seal/validator/runner and Gate 0 v7 post-access
  assessment, immutable result/failure receipts, amendment, validator, tests, and
  documentation. Updated the 082608/082609/082611/082612 handoffs, root architecture
  and blueprints, viewer documentation, and user guidance.

## Evidence

- Pre-access implementation/plan commit:
  `df17efbff8e9b2f44c0a672b1fd0d59aeeb83ed9`.
- The only model/offline process was session `33861`: 12/12 fixed cells, exit 0,
  wall 1466.907 seconds, all 1200 offline-test designs, no calibration access, and no
  simulator launch. Test rows were not used for training or early stopping.
- Evidence root:
  `temp/hierarchical_cae_gate4_runs/hierarchical-cae-gate4-v2-20260827/experimental_offline_v6`.
  `offline_summary.json` SHA-256 is
  `84eed10dc6051374af871a84d5334c988268a029fdf2e18ed5f2bdec8cd93096`;
  `run_spec.json` SHA-256 is
  `599410e4e8fcce79709eef3f9da3568c2030cb76c03168b6d4553ef096311482`.
- All six coordinate cells produced finite stored/off-grid queries with unchanged
  query-state digests. The largest sampled coordinate-vs-grid standardized RMSE was
  0.63776. No numeric coordinate threshold existed, so this is descriptive only.
- Candidate/conditional field-macro MAE ratios for train=1000/2000 were Chrono
  1.20186/1.29294, SAW 1.29201/1.14690, and test-com 1.15099/0.89248. They cannot
  reverse v5 or be used to backfill thresholds.
- A first sandbox launch failed with mixed-ACL `PermissionError` before output
  directory creation, locator access, or training and produced zero cells. The exact
  directory was created with the required host identity, then the unchanged runner
  was run once. v7 preserves both receipts.
- Gate 0 v6 and v7 validators returned exit 0 after the result was frozen. Focused
  threshold/result-invariant tests passed 4/4.

## Decision

- Coordinate, viewer, and offline-test path mechanisms are complete under
  `experimental / performance-not-accepted`.
- Gate 0 v5 remains failed. v7 explicitly records
  `performance_accepted=false`, `coordinate_performance_accepted=false`, no
  post-access numeric thresholds, and `todo_082608_may_archive=false`.
- TODO 082608 remains active. No successor architecture, posterior calibration,
  qNEHVI exploitation policy, or performance tuning was implemented here.

## Follow-Up

- 082609 may begin calibration-framework work only from the committed and installed
  v7 tree, after creating a development-only durable experimental checkpoint/state
  signature and sealing a separate calibration-access preregistration. Calibration
  remains exact-signature-bound and cannot promote or transfer this model.
- 082611 may build typed capability plumbing, but the current head cannot gate
  exploitation. A performance-accepted architecture, independent calibration,
  frozen policy/threshold, and explicit real exploration quota remain prerequisites.
- 082612 retains null coordinate, posterior/calibration, acquisition, formal
  optimization, and total engineering-cost thresholds. Result-derived backfilling is
  prohibited.
