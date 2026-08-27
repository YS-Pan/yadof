# Gate 0 v4: validation metric-adapter repair

The first Gate 0 v3 validation process stopped in its first conditional-INR
cell before publishing any metric or cell result. Conditional-INR correctly
adds surrogate provenance to prediction metadata; the new strict hierarchical
metric path incorrectly compared that enriched prediction metadata directly to
the frozen real-record template.

Gate 0 v4 preserves the failed runner, plan, output hashes, and exit code. The
v2 plan changes only the adapter: it takes the predicted numeric main arrays
and rebuilds axes, dtype, and metadata through the frozen task schema before
metric and current-cost evaluation. Model configurations, seeds, design rows,
metrics, thresholds, and all four anti-noise arms are unchanged.

No calibration or offline-test locator was opened. Run the v4 validator before
continuing the development/validation matrix.
