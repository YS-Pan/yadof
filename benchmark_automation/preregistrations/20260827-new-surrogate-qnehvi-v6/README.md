# Gate 0 v6: experimental framework continuation

Gate 0 v6 records a user-authorized workflow exception after the immutable v5
development decision failed. The v5 thresholds, result, and prohibition on
scientific acceptance remain unchanged. What changes is narrower: coordinate
readout, its viewer adapter, and one fixed offline-test mechanism path may run as
`experimental / performance-not-accepted` framework work.

The sealed plan uses all three frozen cases, train sizes 1000 and 2000, and the
first already-frozen v4 model seed. It trains only on development train rows,
uses only development-validation rows for CAE early stopping, and evaluates all
400 offline-test designs per case. The paired conditional-INR and coordinate-CAE
results are descriptive. There are deliberately no numeric coordinate or
performance thresholds, so the outputs cannot pass Gate 4 or archive TODO
082608.

The coordinate trunk receives the same predictor-member global/group/private
latent as the full-grid decoder. Its high-frequency residual is field-private
and multiplied by the same regime gate. It supports every declared axis through
explicit linear/log/periodic encodings. It is a viewer/off-grid capability only:
full-grid rawData remains authoritative for cost, posterior draws, audit, and
optimization.

Run the validator before any access:

```powershell
& "..\.venv\Scripts\python.exe" `
  ".\benchmark_automation\preregistrations\20260827-new-surrogate-qnehvi-v6\validate.py" `
  --dataset-manifest ".\temp\hierarchical_cae_gate4_runs\hierarchical-cae-gate4-v2-20260827\dataset_seal\sealed_dataset_manifest.json" `
  --pretty
```

The validator is read-only and preserves `offline_test_locator_accessed=false`.
Only the hash-bound experimental runner may subsequently open that locator. Any
changed source, seed, split, setting, or metric requires a new preregistration
version and cannot alter v5.
