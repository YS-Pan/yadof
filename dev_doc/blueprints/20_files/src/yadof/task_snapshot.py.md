# File blueprint: src/yadof/task_snapshot.py

## Intent

- Freeze one generation's effective task inputs so all backends, cost
  interpretation, and asynchronous surrogate work use coherent code and data.

## Functionalities

- Copy task files into a temporary owned tree.
- Rebase `WorkspaceContext.job_template_dir` and the effective config onto that
  tree without changing the real workspace's jobs/records/checkpoint paths.
- Capture stable parameter/objective names, a complete task snapshot ID, and
  dependency-aware interpretation/evaluation fingerprints.
- Exclude recorder infrastructure config from semantic task fingerprints.

## Invariants

- A snapshot is immutable for its generation and explicitly closed by its owner.
- Task cache/runtime artifacts and direct simulator result/lock artifacts are not
  copied.
- Fingerprints drive mechanical cache invalidation and provenance, never scientific
  equivalence decisions.
