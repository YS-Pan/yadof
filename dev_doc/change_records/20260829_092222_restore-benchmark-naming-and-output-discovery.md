# 2026-08-29 09:22 - Restore benchmark naming and output discovery

## Context

- Historical benchmark tasks required human-visible date/time names, one
  discoverable run root, automatic cost plots, and uniformly invoked domain
  visualizations after every optimization.
- The code-first rewrite retained compact run-internal execution paths and a
  generic workflow postprocessor, but initialized workspaces and explicit run IDs
  were not timestamped, workspace output roots stayed empty, and cell execution
  did not invoke cost or baseline-domain visualization.

## Change

- Added one local `YYYYMMDD_HHMMSS` naming contract for initialized workspaces,
  runs, and workspace-level run indexes while retaining digest-named compact cell
  workspaces.
- Required every baseline to ship `workspace/postprocess.py`; each successful
  optimization now runs explicit-output `yadof view cost` and the snapshotted
  baseline script before the cell becomes collected.
- Grouped cost plots in one `visualizations/cost/` category and domain artifacts in
  one semantic directory per baseline, with cell/attempt filename prefixes.
- Added Markdown, CSV, and JSON cell-validity/final-HV reports plus timestamped
  workspace report/visualization indexes that point to the authoritative run root.
- Declared the yadof plotting extra as a benchmark dependency because cost and
  packaged domain plots are now required runtime output rather than optional use.
- Added fake three-baseline pipeline coverage and failure coverage for missing or
  empty required visualization output; synchronized package/root documentation and
  the active restoration TODO.

## Rationale

- Timestamping human-visible names makes runs sortable and recognizable without
  leaking that concern into yadof. Compact execution paths remain separate because
  their digest form exists for Windows simulator path safety rather than user UX.
- Treating visualization as required cell evidence prevents a run from reporting
  success while its promised outputs are absent. Workspace indexes provide
  discoverability without duplicating or flattening immutable run-local evidence.

## Impact

- `yadof-benchmark init` returns the resolved timestamped workspace path. An
  explicit unprefixed run ID becomes the timestamped semantic suffix.
- Third-party baseline collections must add the documented uniform
  `postprocess.py` interface.
- No simulator campaign was started; installed-wheel tests use fake command and
  public-result fixtures.

## Follow-Up

- CLI/progress, inspect/ETA, performance-scale guards, fairness/metrics, richer
  recovery semantics, and concurrency remain in sections 3--9 of the active
  benchmark restoration TODO.
