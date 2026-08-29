# 2026-08-29 21:39 - Make Anti-Noise an Independent Extension

## Context

- The parked anti-noise Hierarchical CAE toDo was previously removed from the
  immediate execution sequence, but the control toDo still treated recovery of
  that route, or approval of a replacement successor, as necessary to remove the
  base Hierarchical CAE performance blocker.
- The user clarified that anti-noise behavior is an extensibility concern, not one
  of the metrics used to accept Hierarchical CAE and not a blocker for posterior,
  qNEHVI, the seven-arm study, or release.

## Change

- Reclassified the parked anti-noise work as an independently accepted extension
  rather than a required Hierarchical CAE successor.
- Removed clean leakage, smooth roughness, quality/regime classification,
  applicability class balance, and MoE/router diagnostics from the base
  Hierarchical CAE acceptance and completion gates.
- Defined the base acceptance chain in terms of rawData representation and
  prediction, current-cost prediction and ranking, field-macro and worst-field
  behavior, all-axis coordinates, resources, independent posterior calibration,
  and typed qNEHVI readiness.
- Made extension-specific calibration and qNEHVI handoff conditional on a future
  reactivation scope that explicitly asks to use the anti-noise variant for those
  capabilities. An optional future anti-noise benchmark arm is additional to, not
  part of, the required seven-arm matrix.
- Updated the PCA/SVD and Acquisition Capability Protocol toDos to preserve their
  independence from both the base acceptance chain and the parked extension.

## Rationale

- A specialized robustness feature should not prevent evaluation or release of a
  base component whose intended contract does not promise that feature.
- Keeping separate preregistrations and conclusions prevents a failed extension
  metric from being mistaken for a failed base model, while also preventing an
  extension pass from substituting for base representation, prediction,
  calibration, or optimization evidence.

## Impact

- No package code, public API, frozen evidence, receipt, calibration artifact, or
  current readiness value changed.
- Base `HierarchicalCAEComponent` remains experimental today because its own
  evidence has not passed; it can now progress without reactivating anti-noise
  work.
- The anti-noise extension remains `PARKED`. Its pause, failure, completion, or
  cancellation has no effect on the base Hierarchical CAE/qNEHVI completion rule.

## Follow-Up

- The next base Hierarchical CAE preregistration must freeze only the base metrics
  listed by the control toDo and must not silently reintroduce anti-noise gates.
- Reactivating the anti-noise extension still requires explicit user direction and
  a separate preregistration for its own evidence and, if requested, its own
  posterior/qNEHVI integration.
