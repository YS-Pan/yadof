# 4+1 scenarios

## Create and run a study

A user or user-directed agent selects one writable workspace, follows the installed
user documentation, initializes or edits task-owned files, and validates the task.
Real execution proceeds only under the documented cost/risk authority. The package
assigns parameters, obtains rawData, calculates current cost, and records evidence
without requiring a repository checkout.

This scenario validates the package/workspace boundary, task/framework ownership,
and agent-not-runtime relationship.

## Evaluate through different backends

- A fast-compatible task returns memory-backed rawData from reusable isolated local
  workers.
- Local mode runs a prepared task workflow on the submit host.
- Distributed mode transfers the prepared workflow to an administrator-managed
  execute host and returns validated file-backed evidence.

All three paths produce ordered backend-neutral results, publish through the same
campaign recorder, and apply the same frozen current task cost policy only after
committed receipts. This scenario validates transport equivalence without requiring
identical intermediate files.

## Use an external simulator runtime

A task selects a packaged adapter and provides task-owned child/model code. An
administrator has provisioned the external runtime on the selected host. The
adapter launches the child inside isolated scratch and accepts only validated
artifacts; task mechanics remain outside the adapter.

This scenario validates process isolation, administrator/task/framework ownership,
and rejection of partial evidence.

## Change task interpretation between generations

The user edits task cost, supported parameter ranges/levels, configuration,
workflow/evaluator logic, or optimization composition between generations. The
next generation captures one new coherent snapshot and reinterprets mechanically
compatible history. The framework records provenance but does not decide whether
the earlier and later scientific problems should share evidence.

This scenario validates generation coherence and user authority over history.

## Resume and inspect

A later command opens the same explicit workspace, discovers durable evidence and
compatible component state, and continues or inspects it under current task
interpretation. Read-only tools do not train models, execute workflows, or rewrite
evidence.

This scenario validates workspace isolation, persistence, and current-view
interpretation.

## Filter, transform, and reinterpret evidence

A reader freezes one durable or live evidence dataset, filters or reorders it by
row identity, and calculates a cost table under one coherent task snapshot. Lazy
rawData decoding occurs only during interpretation and one row at a time. Repeated
physical designs retain distinct candidate identities even though they share a
design key, and cost joins remain correct when either view is reordered.

An explicit rawData transform may create transient derived rows with deterministic
parent/operation/parameter/ordinal/content lineage. Those rows can be interpreted
for analysis, but they do not enter the recorder or committed optimizer history.
This scenario validates identity-preserving manipulation without creating a second
source of truth.

## Use derived candidate selection

An explicitly composed surrogate-assisted strategy learns from recorded real
evidence and proposes candidates. If it uses posterior samples, those samples keep
their declared cross-candidate/field/objective identity and are converted through
the current cost policy. Missing readiness or derived-state failure follows the
strategy's fail-closed boundary. Selected candidates still receive real evaluation
and normal durable recording.

This scenario validates that predictions help selection without becoming truth.

## Run two workspaces

Two campaigns may run concurrently only when they use different workspaces. Each
workspace keeps independent configuration, task modules, jobs, locks, records,
component state, logs, and tools. A second campaign targeting the same workspace is
rejected.

This scenario validates state isolation and the single-writer domain.

## Handle failures

A candidate preparation, execution, timeout, transport, or rawData failure produces
an ordered diagnostic result and does not erase successful candidates. When valid
rawData commits but current-cost interpretation fails, the optimizer receives the
correct-width failure sentinel only at its adapter boundary while the cost table
retains a typed failure row and the completed evidence remains replayable. A
recorder publication failure stops the campaign because accepted evidence cannot be
lost. Corrupt historical entries are isolated during reads without rewriting good
evidence.

This scenario validates individual failure isolation, campaign-level durability,
and tolerant recovery.

## Build a clean artifact

A built distribution contains only declared package code and resources. It can be
installed outside the repository, used with read-only site-packages, and exercised
against explicit workspaces. Source-checkout administrator resources, examples,
benchmark inputs, and runtime evidence remain outside the artifact.

This scenario validates distribution and runtime ownership boundaries.
