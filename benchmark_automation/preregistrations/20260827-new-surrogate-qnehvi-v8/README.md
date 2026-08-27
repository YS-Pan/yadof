# Gate 0 v8 - 082609 experimental posterior calibration

This directory freezes the first calibration-locator access for the exact
development-only hierarchical-CAE checkpoints created from the committed v7 tree.
It does not alter the Gate 0 v5 failure, accept the current architecture, authorize
offline-test access, implement the complete qNEHVI strategy, or perform the final
same-budget optimization benchmark.

Before this registration was written, one development-only process trained and
published six durable yadof checkpoints (three cases at 1000/2000 designs) using
only development train rows and development-validation early stopping. The bundle
summary, every checkpoint/model/scaler hash, exact state/strategy/schema signature,
training design provenance, and policy/label/head/loss identity are bound by
`calibration_plan.json`. The bundle records that neither protected locator was
opened and no simulator was launched.

`calibration_access_seal.json` authorizes only the 600-row calibration locator.
`validate.py` is read-only with respect to protected data: it verifies the committed
source hashes, v5/v7 boundary, installed-wheel origin, six checkpoint chains, and
locator receipt without reading `calibration_locator.json` or
`offline-test_locator.json`. Its external receipt must exist before the calibration
runner starts.

The calibration runner then performs one design-level two-fold cross-fit. It fits
only conservative per-field spread multipliers, never changes the posterior mean,
and uses one monotone logit-affine mapping for every applicability member. Every
complete rawData member is projected through the current task `calc_cost.py`; the
bounded qLogNEHVI calculation is a decision proxy against calibration truth, not the
082611 strategy or 082612 formal benchmark. Failed gates produce explicit identity
or uncalibrated artifacts with no reusable coefficients.

The intended pre-access sequence is:

```powershell
& "..\.venv\Scripts\python.exe" `
  ".\benchmark_automation\preregistrations\20260827-new-surrogate-qnehvi-v8\validate.py" `
  --dataset-manifest ".\temp\hierarchical_cae_gate4_runs\hierarchical-cae-gate4-v2-20260827\dataset_seal\sealed_dataset_manifest.json" `
  --checkpoint-summary ".\temp\hierarchical_cae_gate4_runs\hierarchical-cae-gate4-v2-20260827\posterior_calibration_v8\development_checkpoints\development_checkpoint_summary.json" `
  --pre-access-commit "<full committed preregistration SHA>" `
  --output-receipt ".\temp\hierarchical_cae_gate4_runs\hierarchical-cae-gate4-v2-20260827\posterior_calibration_v8\pre_access_validation_receipt.json"
```

Only after that command exits zero may the hash-bound runner open calibration data.
Offline-test remains sealed for 082612.
