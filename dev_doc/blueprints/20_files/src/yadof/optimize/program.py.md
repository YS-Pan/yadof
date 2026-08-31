# File blueprint: src/yadof/optimize/program.py

## Intent

- Make one workspace-owned ordinary-Python optimization program explicit while
  retaining framework-owned locking, recording, evaluation, cleanup, commit, and
  generation-boundary recovery.
- Freeze program control flow for one command without freezing the task inputs that
  are intentionally reloaded between generations.

## Functionalities

- Statically parse the exact literal `YADOF_OPTIMIZATION_PROGRAM` v1 declaration,
  validate a synchronous entry and canonical declared `.py` helpers, and reject
  executable top-level statements without importing workspace code.
- Copy the entry plus exact helpers into an owned immutable temporary source root,
  record per-file SHA-256 hashes/source fingerprint, and isolated-load the entry
  once from that root.
- Build a semantic program signature from declared identity/capabilities and the
  stable parameter/objective shape while keeping source provenance separate.
- Expose one-use `OptimizationProgramContext`, `OptimizationRunScope`, and
  `ProgramGenerationScope` over the existing `CampaignSession`; provide explicit
  data views, preparation, result construction, and one-shot commit.
- Keep program evaluation preparation callback-free: the program starts an
  evaluation handle and independently starts any training against its already
  materialized evidence.
- Enforce ordered bounded generation entry, normal completion of registered
  training handles, closure of cancel-policy evaluation handles, durable recording,
  metadata publication, result collection, and atomic completion-pointer advance.
- Resume only at the next compatible complete generation and close snapshots,
  session owners, source modules, and temporary files on every normal or exceptional
  exit.

## Invariants

- Static checking and source freezing never execute a program body, factory, or
  declared helper top level.
- The program snapshot is run-scoped; interpretation/evaluation task sources remain
  generation-scoped and are classified separately by `task_snapshot.py`.
- The program may choose ordinary Python/NumPy control flow but cannot create a
  second run scope, skip/repeat generations, exceed the caller range, publish a
  result for the wrong generation/shape, or commit twice.
- `ProgramGenerationScope.prepare_evaluation()` cannot accept an
  `after_jobs_submitted` callback or otherwise hide program lifecycle ordering.
- The completion pointer contains no candidate, prediction, rawData, pymoo, or
  arbitrary user payload. Incomplete work resumes from durable evidence and the
  last published boundary.
- Program source changes are provenance; declared semantic identity changes select
  a distinct compatibility namespace.
