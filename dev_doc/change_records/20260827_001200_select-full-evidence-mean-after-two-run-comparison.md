# 2026-08-27 00:12 - Select Full-Evidence Ensemble Mean After Two-Run Comparison

## Context

- The requested two complete, single-seed performance runs finished all six
  cells and retained all three paired comparisons:
  `20260826_1851-conditional-inr-full-evidence-mean` (Variant A) and
  `20260826_2138-conditional-inr-bootstrap-optimistic-members` (Variant B).
- Variant A trains every independently initialized member on all retained real
  rows and uses ensemble-mean rawData inference. Variant B retained bootstrap,
  evaluated every member through the current task cost function, and selected
  the per-objective minimum member costs.
- Both variants preserved the authoritative normalized variables to rawData to
  current task cost path. The benchmark evidence is descriptive for seed
  `104729`; it is not a statistical ranking across seeds.

## Evidence

- Variant A final cumulative hypervolume, GPSAF + conditional-INR versus
  NSGA-III, was `0.27241114` versus `0.38081006` on Chrono, `0.48370779`
  versus `0.45582636` on SAW, and `0.24739780` versus `0.22127482` on
  test-com. The paired differences were `-0.10839892`, `+0.02788143`, and
  `+0.02612297`.
- Variant B final cumulative hypervolume was `0.28476843` versus `0.46539845`
  on Chrono, `0.46855827` versus `0.43829185` on SAW, and `0.23997889`
  versus `0.25112401` on test-com. The paired differences were
  `-0.18063001`, `+0.03026642`, and `-0.01114512`.
- Relative to Variant A's within-run paired differences, Variant B changed the
  final difference by `-0.07223109` on Chrono, `+0.00238498` on SAW, and
  `-0.03726809` on test-com. Its mean paired difference across the three cases
  was `-0.05383624`, compared with `-0.01813150` for Variant A.
- Variant A tied the first checkpoint and then trailed NSGA-III at all 19
  remaining Chrono checkpoints; it led the final two SAW checkpoints and every
  test-com checkpoint after the first. Variant B led early on Chrono but
  trailed from checkpoint 9 onward, ending at its largest deficit. On test-com
  it led checkpoints 2--9, then trailed checkpoints 10--20. Variant B's only
  retained final win was SAW.
- Variant B completed 11,736 of 12,000 candidate evaluations. Its 264 failures
  were confined to Chrono (122 for NSGA-III and 142 for GPSAF); there were no
  timeouts, all-infinite generations, excluded pairs, or public-API issues.

## Decision

- Restore Variant A as the default implementation. It wins two of the three
  paired cases, while Variant B wins one, and the optimistic aggregation loses
  materially more on Chrono while reversing the test-com result from a win to a
  loss.
- Per-objective minima can assemble an internally inconsistent cost vector from
  different ensemble members. The two-run evidence indicates that this optimism
  can over-select surrogate artifacts even though every member individually
  follows the required rawData-to-current-cost path.
- Preserve both immutable benchmark run directories and the Variant B Git
  commit as evidence. No benchmark process or evidence is deleted or rewritten.

## Change

- Reverted the bootstrap-plus-optimistic-member-cost default and restored
  full-evidence training with ensemble-mean rawData inference.
- Restored the corresponding package defaults, tests, current user
  documentation, and development blueprints to the Variant A contract.
- No simulator, task cost function, normalized-variable mapping, recorded real
  evidence, or benchmark result was changed.

## Verification

- Built `yadof-0.4.1-py3-none-any.whl` and force-reinstalled it into the outer
  workspace `.venv`.
- Confirmed imports resolve below `.venv/Lib/site-packages/yadof`, the installed
  version is `0.4.1`, both bootstrap defaults are `False`, and installed
  `predict_population` uses ensemble-mean rawData before the current task cost.
- Focused installed-package policy tests: `12 passed in 2.40s`.
- Complete installed-package suite: `258 passed in 73.41s`.
- Standalone benchmark suite: `55 passed in 3.43s`.

## Follow-Up

- Stop the automated two-run loop after verification and commit. Additional
  algorithm changes need a new evidence-driven hypothesis; repeatedly tuning
  the same single seed would risk benchmark overfitting.
