# 2026-09-02 11:40 - Archive Expired Context Ledgers

## Context

- The user explicitly requested an expiry review of every item under
  `dev_doc/context/`.
- The review read every dated Markdown document and both linked screenshots, then
  compared their roles with current architecture, blueprints, active toDos,
  completed change records, and still-available runtime evidence.
- A recently fixed defect had allowed unindexed standalone smoke evidence to enter
  optimizer history. The 2026-09-01 formal benchmark was checked separately rather
  than assuming another benchmark investigation applied to it: all 18 run logs say
  `Smoke test: False (CLI override)`, and each cell has exactly one `opt_*`
  recording session with no smoke session.

## Change

- Moved the completed eight-stage explicit-optimization overall plan, unchanged,
  from `dev_doc/context/` to `dev_doc/obsolete/context/`.
- Moved the completed yadof-benchmark problem-closure ledger, unchanged, to the
  same source-partitioned archive.
- Retained the focused formal benchmark result, the CAE/PCA-SVD and posterior
  evidence, the Chrono/SAW screenshots and observation, and the filtered-target
  negative result in active context.

## Rationale

- Every stage in the explicit-optimization plan is complete and its toDo is already
  archived. Current architecture and the eight stage change records now own the
  implemented contracts, so the former cross-session execution plan is superseded.
- The benchmark ledger's B01-B07 and D01-D09 closure gates are all verified. Current
  benchmark behavior is owned by architecture and user documentation, the completed
  implementation is preserved by the benchmark closure change record, and the
  terminal measured outcome is preserved by the newer focused formal-results
  context. The broad execution-period ledger no longer has an active routing role.
- The retained documents still carry evidence that is either directly referenced
  by active scientific toDos or not superseded by a newer source. Completion or age
  alone was not treated as expiry.

## Impact

- Documentation lifecycle only. Archived files keep their original filenames and
  bytes; no code, package-resource mapping, runtime artifact, evidence, user
  instruction, architecture, or blueprint contract changed.
- The formal benchmark result remains valid with respect to the smoke-history
  defect because its trigger evidence was absent from every formal cell.

## Follow-Up

- Continue to assess context expiry only on explicit user request. Leave uncertain
  or uniquely informative experimental evidence active until specific superseding,
  invalidating, or irrelevance evidence exists.
