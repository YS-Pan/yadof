# Project-Specific Terminology

Only terms that need project context are listed here.

| Term | Meaning In This Project |
|---|---|
| `individual` | One optimizer candidate after it has been turned into a real evaluation job. In code this is usually represented by a job folder and later by one `indMeta.jsonl` row. |
| `individual_metadata.json` | A job-local JSON file written by `workflow.py`. It is the source of truth for an individual's `started_at`, `ended_at`, workflow status, and run/generation context that the workflow can see. |
| `indMeta.jsonl` | Append-only recorded-data stream with one compact row per individual. It stores raw variables once, archived rawData member names, compact rawData metadata, workflow timing, status, and run/generation identifiers. |
| `rawData.npz` | A zip-based archive despite the `.npz` suffix. Members are named `job_name/file.npz` and store the actual rawData files produced by jobs. |
| `rawdata_metadata` | Metadata extracted from each rawData `.npz` for quick inspection in `indMeta.jsonl`. It is scrubbed so repeated variable vectors do not appear once per rawData file. |
| `job_static_hash` | A hash of static files copied into a prepared job. It excludes runtime files and per-individual values, so it marks task-definition changes rather than candidate changes. |
| `run_id` | String identifier for one optimizer run created by `optimize.api.run_generations()` or direct single-generation calls. |
| `optimization_index` | Numeric ordinal for an optimization run. It is stored on each individual and in generation-level metadata. |
| `generation_index` | Numeric generation number inside an optimization run. It is stored on each individual and in generation-level metadata. |
| `population_index` | Zero-based position of an individual inside the evaluated population sent to `evaluate_manager`. |
