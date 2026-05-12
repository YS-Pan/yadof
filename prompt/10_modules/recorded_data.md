# Module prompt: recorded_data

## Intent
- Store durable real-evaluation evidence while avoiding derived values that can become stale.
- Provide the optimizer and surrogate with current interpretations of history: normalized variables, rawData samples, and dynamically calculated costs.
- Make completed, failed, errored, and timed-out job records inspectable through one manifest schema.

## Functionalities
- `api.py` is the public entry point for recording jobs, listing records, querying raw variables, calculating normalized variables, loading rawData, calculating costs, and bundling surrogate training data.
- `records.py` writes one job record, copies `.npz` files into `rawData/<job_name>/`, sanitizes metadata, and rejects duplicate jobs unless `overwrite=True`.
- `query.py` reads raw variables, normalizes them through `job_template.api`, loads rawData, calculates costs through `job_template.api`, filters invalid rawData, and builds training bundles.
- `manifest_store.py` handles manifest schema metadata, file locking, atomic writes, and status normalization.
- `rawdata_store.py`, `paths.py`, and `utils.py` provide path configuration, `.npz` loading, metadata extraction, and JSON-safe serialization.

## I/O Format
- Stored record fields include `job_name`, `status`, `raw_variables`, `rawdata_files`, `rawdata_metadata`, `job_metadata`, and `recorded_at`.
- Valid record statuses are centralized in `paths.py`.
- Completed history for optimization is returned as `(job_name, normalized_variables, costs)`.
- Surrogate training data is returned as a dict with `parameter_names`, `normalized_variables`, and loaded `raw_data`.
- Cost and normalized variables are returned to callers but not saved as durable manifest source fields.

## Non-Obvious Techniques
- Metadata is scrubbed to avoid storing `cost`, `costs`, `objective_costs`, or normalized-variable fields.
- Manifest writes use a lock and temporary file replacement so concurrent recorders do not corrupt history.
- Default history queries use completed records; failed and timed-out records remain available for diagnostics.
- Invalid rawData can be skipped for optimization or surrogate training while still being diagnosable through `get_rawdata_diagnostics()`.
- Normalization and cost calculation intentionally use the current `job_template`, enabling reuse of old rawData after controlled task edits.

## Mutability Profile
- Manifest schema changes need explicit migration thinking.
- Query helper aliases may grow to support older or future callers, but `api.py` should remain the stable public face.
- Storage layout and locking behavior should change only with tests that cover duplicate, concurrent, failed, and invalid rawData cases.
