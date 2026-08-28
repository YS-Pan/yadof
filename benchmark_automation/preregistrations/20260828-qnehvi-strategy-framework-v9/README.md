# Gate 0 v9 - 082611 posterior-assisted strategy framework

This registration freezes the structural and fail-closed validation for the
independent `qnehvi()` acquisition component and `posterior_assisted()` strategy.
It does not change or reinterpret the v5 architecture failure or the v8
calibration result. In particular, all six v8 artifacts remain uncalibrated and
non-transferable, so no current hierarchical-CAE or conditional-INR posterior may
control exploitation.

`framework_plan.json` and `canary_inputs/` were sealed before running the
installed-wheel tests or the bounded real-evaluation canary. The canary is exactly one two-objective generation
with population two and a typed, deliberately blocked posterior component. Its
only purpose is to prove that the explicit strategy composition falls back to
normal pymoo proposal, common real evaluation/finalization/recording, and bounded
generation metadata. It is structural evidence, not an optimizer comparison.

`validate.py` is read-only. It checks the installed-wheel origin, public factories,
typed current-component blockers, source presence, and the committed v8 scientific
boundary. It neither starts a simulator nor reads protected calibration/offline
locators.

The v9 acceptance sequence is:

1. build and force-install one wheel containing the sealed implementation;
2. run `validate.py` and the focused/full installed-package test suites;
3. run the one-generation real canary once and inspect it through public yadof
   surfaces;
4. record a bounded result receipt with hashes and exact counts;
5. leave 082611 active and leave the 082612 performance suite unstarted.

The formal 100-by-20, six-cell, 12,000-evaluation benchmark remains blocked until
an architecture is independently performance-accepted and a signature-bound
posterior/applicability capability is calibrated, transferable, and frozen with
its threshold and real-exploration policy. That future work belongs to 082612.

## Frozen result

`framework_result_receipt.json` records the final wheel/source hashes, exact test
counts, the two-record public canary result, and the no-write 12,000-attempt
benchmark boundary. `validate_result.py` rechecks the final wheel plus public
record/optimization metadata. Its terminal status is
`valid-complete-framework-mechanism-performance-not-accepted`; no qNEHVI
performance arm ran and TODO 082611 remains active.
# Historical preregistration

This directory is retained as historical plan/evidence only. Its executable
validators were retired on 2026-08-28 because current source, wheel, and artifact
digests are provenance—not gates on historical conclusions. Commands below
describe the former workflow and are no longer available at current HEAD.
