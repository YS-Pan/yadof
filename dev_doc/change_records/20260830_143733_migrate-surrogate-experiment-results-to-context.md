# 2026-08-30 14:37 - Migrate surrogate experiment results to context documents

## Context

The active Hierarchical CAE and posterior-assisted EHVI/qNEHVI TODOs had been
rewritten before `dev_doc/context/` existed. Each TODO therefore mixed future-work
instructions with completed benchmark matrices, artifact locations, frozen hashes,
measured results, and cross-session scientific interpretation.

After the context-document contract was added, the user explicitly requested that
the experimental results in those two TODOs move to `context/`. The TODOs still
needed enough decision-relevant evidence to remain standalone future-work handoffs,
but they no longer needed to be the primary store for detailed completed evidence.

## Change

- Added
  `context/20260830_143110_hierarchical-cae-pca-svd-measured-evidence.md` with the
  completed 24-cell base Hierarchical CAE benchmark, the 24-cell PCA/SVD
  oracle/deployable study, verified artifact locations, frozen hashes, numerical
  limitations, resource measurements, and the joint nonlinear-representation
  interpretation.
- Added
  `context/20260830_143110_posterior-calibration-qnehvi-structural-evidence.md` with
  the v8 exact-state calibration result, v9 blocked-readiness real canary, v10
  nine-cell structural run, existing tracked provenance, artifact-availability
  limits, and the explicit absence of formal qNEHVI optimization-quality evidence.
- Reduced both active TODOs to pending work, non-negotiable boundaries, concise
  decision-relevant evidence summaries, and links to the new context documents.
  The future scope, execution authority, non-goals, and completion rules remain
  active in the TODOs.
- Recorded that the old `benchmark_automation/preregistrations/20260828-*` paths
  referenced by historical v8/v9/v10 documents are absent from the current HEAD.
  The migration therefore uses append-only change records, archived handoffs,
  commits/signatures/hashes, and the still-present v10 evidence root rather than
  presenting retired paths as current artifacts.

## Rationale

Completed experimental evidence must survive across sessions but should not make a
future-work handoff double as an experiment archive. The new split preserves
filename-first discoverability and evidence provenance in `context/`, while each
TODO retains only the facts and interpretations that change how its remaining work
must be executed.

Two context documents were used because the evidence has two distinct routing
needs: representation/modeling work can find the CAE/PCA-SVD comparison by name,
while posterior/acquisition work can find calibration and structural qNEHVI
evidence without opening the representation document by default.

## Impact

This is a documentation-content and active-TODO organization change only. It does
not alter source code, tests, package-resource mapping, documentation discovery,
runtime behavior, checkpoint state, benchmark evidence, sealed historical results,
strategy defaults, or execution authority. No context document authorizes a new
simulator campaign, training run, eligible posterior path, formal benchmark, or
default migration.

The existing documentation architecture, documentation blueprint, terminology,
and user workflow already describe the context/TODO separation and therefore need
no current-view update for this use of the established contract.

## Validation

- Re-read the two active TODOs, their directly relevant tracked change records and
  archived handoffs, plus the still-accessible CAE, PCA/SVD, and v10 result summaries.
- Verified the new filenames follow the timestamped context naming contract and
  that `context/` now lists both evidence sets by descriptive names.
- Checked every changed local Markdown link, including links to ignored evidence
  that remains present at migration time, and verified UTF-8 text and heading
  separation.
- Reviewed the final Git diff and whitespace checks under the documentation-only
  validation exception. No wheel build, force reinstall, import-origin check,
  pytest, simulator launch, model training, or benchmark run was required.
