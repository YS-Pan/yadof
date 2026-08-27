# Integrated acceptance and fail-closed release framework

## Summary

TODO 082612 now has a versioned, machine-checkable integrated acceptance and
progressive-release framework. It preserves the frozen upstream failures, records
the complete formal matrix and its current gaps, validates the existing baseline
path with one bounded real structural run, and defines exact conditions for later
formal re-entry. It does not claim scientific acceptance.

The implementation is documentation, preregistration, validators, and focused
benchmark tests. No surrogate, posterior, acquisition, GPSAF, recorder, task, or
simulator model code changed.

## Frozen scientific state

The v10 plan is bound to clean `main` commit
`aebcde11798c70153fa9cda6bb59c2fcccbef6b0` and hashes the immutable v5, v7, v8,
and v9 result files.

- v5 still rejects representation, quality/regime, and the full-grid gate.
- v7 remains mechanism-only and keeps both performance flags false.
- v8 still has zero calibrated rawData cells, zero calibrated applicability cells,
  and six non-transferable artifacts.
- v9 still records two real fallback evaluations with no surrogate use and reason
  `typed-exploitation-capability-blocked`.

The current `performance` suite still contains only NSGA-III and GPSAF plus
conditional-INR. Five required entries are absent as formal runner arms:
hierarchical-CAE mean, hierarchical-CAE plus qNEHVI, conditional-INR adapter plus
qNEHVI, PCA/SVD reconstruction, and mandatory hierarchical-CAE plus GPSAF. Formal
posterior-decision, optimizer-quality, and total engineering-cost thresholds also
remain unsealed. The formal suite was not started.

## Release and fallback decision

The v10 plan separates three phases:

- Phase A accepts only experimental offline, checkpoint/viewer, and separately
  preregistered diagnostic-shadow mechanics. It cannot alter campaign selection,
  submit extra real evaluations, or retain predicted rawData as evidence; no shadow
  campaign is activated here.
- Phase B keeps the explicit public composition available, but every currently
  shipped posterior remains blocked by typed performance/calibration/transferability
  readiness and must use full-real search plus the common evaluator.
- Phase C remains blocked, not recommended, and makes no package-template change.

Static capability, missing real baseline/state, and bounded selection/backend
failures use visible full-real fallback. Configured support rejection, invalid
qNEHVI configuration, recorder/finalization failure, and any attempt to use an
experimental head as an exploitation shortcut are hard stops.

## Real structural evidence

The candidate installed wheel passed `structural-full` preflight 13/13. One runner
process then created
`20260827_192319-082612-v10-structural-release-5762ec48fe39` and completed all nine
cells. Public collection and reporting found:

- 99 attempted real evaluations, 96 completed records, and three explicit Chrono
  error records handled by the existing finite worst-cost contract;
- zero timeouts and zero all-infinite generations;
- 82/82 structural checks passed and `contract_satisfied=true`;
- all rawData shape, declared-input, objective-count, generation-sequence,
  checkpoint, surrogate summary/audit, initial-population pairing, and isolated
  workspace checks passed.

The three disposable smoke cells retain a known attempted-count alignment warning.
Evaluation-normalized HV AUC and checkpoint training cutoff remain explicit public
tool gaps. Neither affects this structural contract; neither may be hidden in a
future formal performance decision.

This run exercised only the existing NSGA-III/GPSAF baseline arms. It is not a
qNEHVI performance arm and has no optimizer-ranking interpretation.

## Formal re-entry

Formal acceptance can be reconsidered only through a new versioned candidate that
preserves v5-v9, passes 1000/2000-design representation/quality/coordinate/resource
gates, yields exact-state transferable rawData calibration and calibrated
applicability policy where needed, implements all seven frozen arms, seals every
remaining numeric threshold before test access, passes final installed-wheel and
fallback/viewer/checkpoint/recorder checks, and obtains campaign authority before
running every same-budget cell. Recommendation requires all representation,
posterior, optimization, and engineering decisions jointly; a default change still
requires a later explicit user decision.

## Validation and lifecycle

`acceptance_release_result_receipt.json` is the bounded source of exact final wheel,
source, test, structural artifact, and public fallback hashes/counts. Its result
validator re-runs the input gate against the installed wheel and rechecks the
structural report without reading the large metrics file wholesale.

TODOs 082608, 082609, 082611, and 082612 remain active. No upstream threshold or
failure receipt was changed, no model was tuned, no formal benchmark ran, no
experimental head selected an exploitation point, and the GPSAF plus
conditional-INR package default is unchanged.
