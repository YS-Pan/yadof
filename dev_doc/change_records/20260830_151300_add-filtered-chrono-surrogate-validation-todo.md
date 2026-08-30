# 2026-08-30 15:13 - Add Offline Filtered Chrono Surrogate Validation TODO

## Context

- The user requested an initial experiment outside the current yadof integration:
  filter the completed Chrono benchmark data, train CAE and INR surrogates, and
  inspect the results with the surrogate viewer before attempting a framework-level
  filter.
- Existing evidence shows narrow Chrono stress peaks and prediction chatter, but it
  does not establish their physical cause or prove that smoothing is scientifically
  valid.

## Change

- Added a standalone manual TODO defining a read-only, derived-data experiment with
  four paired raw/filtered x CAE/INR arms.
- Bound the experiment to the completed benchmark's exact cells, partitions, model
  settings, source receipts, and viewer workspaces.
- Defined an initial phase-domain low-pass selection procedure, provenance and
  current-cost guards, quantitative/visual comparisons, interpretation branches,
  non-goals, and completion rules.

## Rationale

- A disposable offline harness can test whether target high-frequency structure is
  a common surrogate difficulty without first adding a package transform contract
  or changing recorded physical evidence.
- Keeping the cost-bearing peak-utilization field unfiltered separates the first
  fitting experiment from a task-objective change and makes raw/filtered current
  cost equality an explicit guard.

## Impact

- Documentation only. No package code, benchmark source, user documentation,
  architecture, blueprint, terminology, simulator evidence, checkpoint, or viewer
  behavior changed.
- The parked regime-specialized anti-noise TODO remains inactive and independent.

## Follow-Up

- Execute the new TODO only when explicitly requested. Any later framework
  integration, real simulator run, broader filtering scope, or default-policy
  change requires a separate decision and proportional maintenance.
