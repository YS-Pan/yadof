# 2026-08-23 19:30 - Expand Benchmark Performance Budget

## Context

- The formal source-checkout benchmark used only three generations with 12 or 24
  individuals per generation. That scale was useful for cost discovery but too
  small to assess the real-search and GPSAF plus conditional-INR strategies on the
  deliberately difficult frozen optimization tasks.
- The earlier 24-individual `test-com` cells also exposed recorder admission loss
  because the package default allowed only 32 unpublished candidates.

## Change

- Set every formal `performance` cell to 100 individuals for 20 generations while
  retaining three paired seeds, three cases, and two arms. The matrix now plans
  36,000 attempted real evaluations.
- Added runner-owned measured-cell config overrides and froze them in each run
  specification. The formal configuration uses 100 candidates per history segment
  and 128 unpublished-candidate credits so one complete generation fits without
  editing an immutable baseline.
- Kept `performance-pilot` at its separate three-generation cost-discovery scale.
- Updated focused tests, operator documentation, and benchmark architecture.

## Rationale

- Equal 100-by-20 budgets provide a materially longer evolutionary trajectory and
  enough population diversity for each difficult problem while preserving paired
  attempted-evaluation equality between arms.
- Recorder headroom is experiment infrastructure rather than task science, so it
  belongs in benchmark-owned measured-cell overrides instead of frozen baseline
  workspaces or duplicated arm settings.

## Impact

- A full performance run now has an estimated task-evaluation lower bound of
  13,650 seconds and about 8.4 GiB of record storage before optimizer and surrogate
  training overhead.
- Unit validation reports 33 passing benchmark tests. The no-write performance
  plan reports 18 cells and 36,000 evaluations; performance preflight passes all
  13 checks against the installed yadof 0.4.0 environment.

## Follow-Up

- The user-authorized long run is launched separately and remains runtime evidence;
  collection, reporting, and scientific interpretation occur only after the user
  reports that it has completed.
