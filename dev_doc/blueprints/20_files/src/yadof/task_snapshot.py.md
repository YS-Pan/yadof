# File blueprint: src/yadof/task_snapshot.py

## Intent

- Freeze one generation's effective task inputs so all backends, cost
  interpretation, and asynchronous surrogate work use coherent code and data.

## Functionalities

- Copy the complete `job_template/` root plus classified `submit/` task sources into
  one temporary owned tree without an AST/import dependency tracker. For an
  explicit run, omit the already-frozen program entry and declared helpers.
- Rebase `WorkspaceContext.submit_dir`, `job_template_dir`, and the effective config
  onto those copies without changing real jobs/records/checkpoint paths.
- Capture stable parameter/objective names, a complete task snapshot ID, and
  interpretation/evaluation/optimization fingerprints and source hashes. Merge the
  frozen program hashes/fingerprint into provenance and the complete snapshot ID
  without treating them as generation-reloaded interpretation sources.
- Exclude recorder infrastructure config from semantic task fingerprints.

## Invariants

- A snapshot is immutable for its generation and explicitly closed by its owner.
- Classification is explicit: a program snapshot owns only the declared entry and
  helpers; the generation snapshot owns current cost, parameters, evaluation,
  workflow, and all other task sources.
- Cache artifacts are excluded from both trees; evaluate-side rawData and direct
  simulator result/lock artifacts are not copied.
- Fingerprints drive mechanical cache invalidation and provenance, never scientific
  equivalence decisions.
