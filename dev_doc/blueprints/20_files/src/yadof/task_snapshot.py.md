# File blueprint: src/yadof/task_snapshot.py

## Intent

- Freeze one generation's effective task inputs so all backends, cost
  interpretation, and asynchronous surrogate work use coherent code and data.

## Functionalities

- Copy both complete task source roots into one temporary owned tree without an
  AST/import dependency tracker.
- Rebase `WorkspaceContext.submit_dir`, `job_template_dir`, and the effective config
  onto those copies without changing real jobs/records/checkpoint paths.
- Capture stable parameter/objective names, a complete task snapshot ID, and
  interpretation/evaluation/optimization fingerprints and source hashes.
- Exclude recorder infrastructure config from semantic task fingerprints.

## Invariants

- A snapshot is immutable for its generation and explicitly closed by its owner.
- Cache artifacts are excluded from both trees; evaluate-side rawData and direct
  simulator result/lock artifacts are not copied.
- Fingerprints drive mechanical cache invalidation and provenance, never scientific
  equivalence decisions.
