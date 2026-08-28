# Gate 0 v5: 082608 development-validation decision

Gate 0 v5 freezes the completed 116-cell Gate 0 v4 development validation,
seals only the numeric representation and quality/regime limits supported by
that legal partition, and records the resulting stop decision. It does not
open the calibration or offline-test locators.

The full-grid gate fails. The production candidates violate the paired
field-macro MAE and single-field guards in multiple case/train-size cells. The
gated residual arm also leaves material clean-target high-frequency leakage,
exceeds the smooth roughness limit, and does not improve leakage over the
shared-latent-isolation arm. Consequently coordinate readout remains blocked,
the offline test remains untouched, and TODO 082608 remains active.

This outcome does not erase the implemented experimental component or the
successful structural, checkpoint, posterior-identity, and anti-noise protocol
work. A later evidence-triggered architecture gate may compare a more explicit
regime decomposition such as a bounded mixture-of-experts, but v5 does not
implement it or relax thresholds to make the current model pass.

Run `validate.py --dataset-manifest <sealed_dataset_manifest.json>` to verify
the full v1--v5 chain and external evidence hashes. The validator is read-only
and does not start a simulator or load the offline-test locator.
# Historical preregistration

This directory is retained as historical plan/evidence only. Its executable
validator was retired on 2026-08-28 because current source, wheel, and artifact
digests are provenance—not gates on historical conclusions. Commands below
describe the former workflow and are no longer available at current HEAD.
