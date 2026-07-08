# Module blueprint: recorded_data

## Intent
- Store durable real-evaluation evidence while avoiding derived values that can become stale.
- Provide the optimizer and surrogate with current interpretations of history: normalized variables, rawData samples, and dynamically calculated costs.
- Make completed, failed, errored, and timed-out job records inspectable through one append-only individual metadata stream.

## Functionalities
- `api.py` is the public entry point for recording jobs, listing records, querying raw variables, calculating normalized variables, loading rawData, calculating costs, and bundling surrogate training data.
- `records.py` writes one compact individual metadata row into `indMeta.jsonl`, archives each source `.npz` into `rawData.npz` as `job_name/file.npz`, promotes workflow timing and run/generation identifiers, sanitizes metadata, and rejects duplicate jobs unless `overwrite=True`.
- `records.py` also records optimization-level rows in `optMeta/optMeta.jsonl`, including surrogate-training metadata rows written through `record_surrogate_metadata()`.
- `query.py` reads raw variables, normalizes them through `job_template.api`, loads rawData members from the archive, calculates costs through `job_template.api`, filters invalid rawData, and builds training bundles.
- `manifest_store.py` now owns JSONL file locking, atomic rewrites, append helpers, and status normalization.
- `rawdata_store.py`, `paths.py`, and `utils.py` provide path configuration, zip-based rawData archive loading, repeated-variable metadata scrubbing, metadata extraction, and JSON-safe serialization.

## I/O Format
- Stored individual metadata fields include `job_name`, `status`, `raw_variables`, `rawdata_files`, `rawdata_metadata`, `started_at`, `ended_at` when provided by the workflow, `run_id`, `optimization_index`, `generation_index`, `population_index`, `job_metadata`, and `recorded_at`.
- `rawdata_files` stores archive member names such as `job_name/summary.npz`.
- Valid record statuses are centralized in `paths.py`.
- Completed history for optimization is returned as `(job_name, normalized_variables, costs)`.
- Surrogate training data is returned as a dict with `parameter_names`, `normalized_variables`, and loaded `raw_data`.
- Cost and normalized variables are returned to callers but not saved as durable individual metadata source fields.

## Non-Obvious Techniques
- Metadata is scrubbed to avoid storing `cost`, `costs`, `objective_costs`, `created_at`, repeated variable payloads, or normalized-variable fields.
- rawData metadata in `indMeta.jsonl` is compacted by removing repeated `variables`, `raw_variables`, `unnormalized_variables`, `normalized_variables`, and `job_metadata` keys. The individual-level `raw_variables` field is the single durable variable source.
- Workflow-owned `started_at` and `ended_at` are promoted to top-level individual fields so tools do not need to inspect nested job metadata for lifecycle timing.
- JSONL metadata writes and rawData archive updates use a shared lock so concurrent recorders do not corrupt history.
- Default history queries use completed records; failed and timed-out records remain available for diagnostics.
- Invalid rawData can be skipped for optimization or surrogate training while still being diagnosable through `get_rawdata_diagnostics()`.
- Normalization and cost calculation intentionally use the current `job_template`, enabling reuse of old rawData after controlled task edits.

- Surrogate-training metadata is optimization-level metadata, not individual evidence. It records training status, generation index, timing, sample/query/member counts, checkpoint names, and error summaries without adding derived costs to `indMeta.jsonl`.

## Mutability Profile
- Individual metadata, optimization metadata, and rawData archive schema changes need explicit migration thinking.
- Query helper aliases may grow to support older or future callers, but `api.py` should remain the stable public face.
- Storage layout and locking behavior should change only with tests that cover duplicate, concurrent, failed, archived, and invalid rawData cases.
