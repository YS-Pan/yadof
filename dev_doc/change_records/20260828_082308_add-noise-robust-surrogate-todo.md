# Add Noise-Robust Regime-Specialized Surrogate TODO

## Summary

Added a standalone manual TODO that records the previously session-only
quality/regime anti-noise requirement and separates its implemented engineering MVP
from the still-failed scientific acceptance work.

## Documentation decision

The handoff preserves the original interpretation of the Chrono evidence as
parameter-dependent chatter/failure regimes rather than independent measurement
noise. It forbids rawData smoothing, cost-based filtering, hidden task rules, and
uncalibrated exploitation while retaining design-by-field robust aggregation,
shared-token isolation, gated private residuals, applicability identity, and the
existing calibration/qNEHVI/release handoffs.

The TODO records the v5 clean-leakage, smooth-roughness, gated-ablation, and
worst-field failures plus the v8 19/181 calibration-label imbalance. It defines a
bounded, newly preregistered regime-specialized/Mixture-of-Experts successor path,
requires simple shared-isolation, PCA/SVD, and conditional-INR controls, and
requires new blind test and independently supported calibration evidence. Existing
frozen preregistrations and receipts remain immutable.

## Impact

- Added one active manual TODO under `dev_doc/toDo/`.
- No current architecture, blueprint, terminology, user workflow, source code,
  tests, benchmark preregistration, evidence, dependency, or runtime behavior
  changed.
- The existing hierarchical CAE and calibration TODOs remain active; this document
  gives the previously implicit anti-noise successor work an independent lifecycle.

## Validation

- Reused the current development/documentation contracts and architecture context,
  then rechecked the active hierarchical-CAE, calibration, integrated-validation,
  PCA/SVD, Gate 0 v2/v5, and Gate 4 result records directly relevant to this
  handoff.
- Verified that the recorded requirements distinguish completed mechanism work from
  failed scientific gates and preserve fail-closed downstream behavior.
