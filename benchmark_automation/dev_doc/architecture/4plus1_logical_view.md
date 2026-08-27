# 4+1 Logical View

## Core concepts

- A baseline is an editable semantic task template. A run-local baseline snapshot
  is its immutable execution input.
- A suite declares purpose, cases, arms, seeds, budgets, and fail-fast policy.
- A cell is one case/arm/seed experiment or disposable smoke unit.
- An attempt is one immutable execution workspace for a cell. Replacement attempts
  link to interrupted predecessors without modifying them.
- A command record is a started/finished metadata pair, separate stdout/stderr
  logs, and one append-only timestamped lifecycle/progress event stream.
- A timing-history snapshot is a bounded immutable operational sample of completed
  matched cells from earlier immediate run directories. It does not enter run
  identity or scientific results.
- A benchmark preregistration is a tracked, reviewable input contract that freezes
  schema, provenance, design splits, metrics, comparison cells, resource blocks,
  threshold-sealing rules, and stop conditions before evidence is inspected. It is
  neither a runnable suite nor benchmark evidence; missing data or threshold seals
  keep formal execution blocked.
- Run state is the atomically replaced index of cell/attempt status. It is not the
  scientific result.
- Collection and reports are derived public-yadof interpretations that may be
  regenerated without changing measured workspaces.
- Benchmark ETA is a transient inspection estimate derived from the frozen timing
  sample, current-run wall time, and live phase progress. The estimate is not
  stored evidence or a deadline.

## Identity rules

Run ID names the directory, while `spec_sha256` proves resolved content identity.
Semantic baseline IDs do not contain fingerprints. Resume verifies the frozen spec,
package, runner, strategies, task snapshots, and scientific history rather than
trusting the name. The operational timing snapshot is fixed at creation but is not
an execution-identity input.

## State rules

Cells move from pending to running and then one terminal status. A running attempt
may contain a started command that has not yet published finished metadata. A
failed cell is terminal for the current foreground run; resume decides whether a
replacement is permitted.

## Interpretation rules

Structural suites prove declared wiring. Performance suites retain equal-budget
paired observations and descriptive differences only. Failures, duration, ETA,
resource facts, and warnings are validity/operations data, not algorithm quality.
