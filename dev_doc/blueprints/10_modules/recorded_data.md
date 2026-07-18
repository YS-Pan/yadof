# Module blueprint: recorded_data

## Intent
- Store durable real-evaluation evidence while avoiding derived values that can become stale.
- Provide the optimizer and surrogate with current interpretations of history: normalized variables, rawData samples, and dynamically calculated costs.
- Make completed, failed, errored, and timed-out job records inspectable through one append-only individual metadata stream.
- Keep every package-era manifest, lock, archive, and temporary file owned by one
  explicitly supplied workspace, with no installed-source fallback.

## Historical Lineage
- Durable individual history, rawData archiving, and plotting-facing history contracts descend from the fanyufei batch/recording lineage.
- Cumulative reusable archive ideas descend from the shorten archive lineage.
- Current storage differs from both by refusing to persist cost or normalized variables as source data.

## Functionalities
- `src/yadof/recorded_data/api.py` is the package public entry point. Every record,
  list, history, diagnostics, and optimization-metadata call takes a workspace/context
  first and resolves fresh storage/task state for that call.
- `records.py` writes one compact individual metadata row into workspace
  `indMeta.jsonl`, archives each source `.npz` into `rawData.npz` as
  `job_name/file.npz`, promotes workflow timing and run/generation identifiers,
  sanitizes metadata, and rejects duplicate jobs unless `overwrite=True`.
- `records.py` also records optimization-level rows in `optMeta/optMeta.jsonl`, including surrogate-training metadata rows written through `record_surrogate_metadata()`.
- `query.py` reads raw variables, normalizes them through workspace-explicit
  `yadof.job_template`, loads archive members, calculates current costs, filters
  invalid rawData, and builds training bundles without retaining task modules.
- `manifest_store.py` owns path-keyed process/file locking, atomic JSONL rewrites,
  logical append helpers, and status normalization. Empty-history reads do not create
  a directory or lock.
- Read-only manifest access remains standard-library-only; NumPy-aware JSON conversion is loaded lazily by manifest write operations.
- `rawdata_store.py`, `paths.py`, and `utils.py` provide atomic zip replacement,
  orphan-member recovery, immutable workspace path derivation, repeated-variable
  metadata scrubbing, metadata extraction, and JSON-safe serialization.
- `project/recorded_data` remains transitional for current source optimizer/
  surrogate/tools consumers; package code does not import it and no dual reader or
  repository-history migration exists.

## I/O Format
- Stored individual metadata fields include `job_name`, `status`, `raw_variables`, `rawdata_files`, `rawdata_metadata`, `started_at`, `ended_at` when provided by the workflow, `run_id`, `optimization_index`, `generation_index`, `population_index`, `job_metadata`, and `recorded_at`. HTCondor job metadata may include the effective request and observed ClassAd memory/disk/CPU fields used by the next generation's resource calibration.
- `rawdata_files` stores archive member names such as `job_name/summary.npz`.
- Valid record statuses are centralized in `paths.py`.
- Completed history for optimization is returned as `(job_name, normalized_variables, costs)`.
- Surrogate training data is returned as a dict with `parameter_names`, `normalized_variables`, and loaded `raw_data`.
- Cost and normalized variables are returned to callers but not saved as durable individual metadata source fields.
- Effective storage is `<WorkspaceContext.recorded_data_dir>/indMeta.jsonl`,
  `indMeta.jsonl.lock`, `rawData.npz`, and `optMeta/optMeta.jsonl`. An explicit
  configured absolute record path is allowed through the effective context; no
  storage path is based on `recorded_data.__file__`.

## Non-Obvious Techniques
- Metadata is scrubbed to avoid storing `cost`, `costs`, `objective_costs`, `created_at`, repeated variable payloads, or normalized-variable fields.
- rawData metadata in `indMeta.jsonl` is compacted by removing repeated `variables`, `raw_variables`, `unnormalized_variables`, `normalized_variables`, and `job_metadata` keys. The individual-level `raw_variables` field is the single durable variable source.
- Workflow-owned `started_at` and `ended_at` are promoted to top-level individual fields so tools do not need to inspect nested job metadata for lifecycle timing.
- JSONL metadata writes and rawData archive updates use a per-workspace process lock
  plus OS file lock. Unique temporary files live beside their targets and are
  atomically replaced. A retry of an unreferenced same-job archive member removes
  that orphan before writing new evidence.
- Default history queries use completed records; failed and timed-out records remain available for diagnostics.
- Invalid rawData can be skipped for optimization or surrogate training while still being diagnosable through `get_rawdata_diagnostics()`.
- Normalization and cost calculation intentionally use the current `job_template`, enabling reuse of old rawData after controlled task edits.

- Surrogate-training metadata is optimization-level metadata, not individual evidence. It records training status, generation index, timing, sample/query/member counts, checkpoint names, and error summaries without adding derived costs to `indMeta.jsonl`.

## Mutability Profile
- Individual metadata, optimization metadata, and rawData archive schema changes need explicit migration thinking.
- Query helpers may grow for current callers, but `api.py` should remain the stable public face; do not add old-version aliases by default.
- Storage layout and locking behavior should change only with tests that cover duplicate, concurrent, failed, archived, and invalid rawData cases.
- Same-named jobs in two workspaces, current-range/current-cost edits, existing JSONL
  recovery, and installed-wheel no-package/source-write behavior are required
  regression boundaries.
