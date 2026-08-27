# Gate 0 v7: experimental framework result

Gate 0 v7 freezes the one hash-bound v6 process. Session `33861` completed all
12 fixed cells with exit code 0 in 1466.907 seconds, opened all 1200 offline-test
designs, did not open calibration data, and did not launch a simulator. The first
attempt is separately recorded as an ACL failure before output-directory creation,
offline access, or training; it produced zero cells and did not duplicate work.

All six coordinate-CAE cells returned finite stored/off-grid queries and retained
identical before/after model-state digests. The run covered SAW rank-1 fields,
Chrono scalar plus rank-1 fields, and test-com rank-1/rank-2/rank-3 fields. The
largest sampled coordinate-vs-grid standardized RMSE was 0.638. This is descriptive
because v6 deliberately sealed no numeric coordinate threshold.

The single-seed offline field-macro MAE ratios versus conditional-INR were:

| case | train=1000 | train=2000 |
|---|---:|---:|
| SAW | 1.29201 | 1.14690 |
| Chrono | 1.20186 | 1.29294 |
| test-com | 1.15099 | 0.89248 |

These numbers do not reverse Gate 0 v5. They are not a performance gate and
cannot be used to tune or backfill thresholds after test access. The coordinate
framework, viewer adapter, and offline path are mechanically complete under the
explicit label `experimental / performance-not-accepted`; TODO 082608 remains
active and cannot be archived.

082609 may next build calibration plumbing against the typed experimental state
only after separately preregistering calibration access. Any result remains bound
to the exact state signature and cannot promote or transfer to a successor model.
082611 exploitation remains blocked until a performance-accepted architecture and
independently calibrated applicability capability exist.
