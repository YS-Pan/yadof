# Module blueprint: recorded_data

`yadof.recorded_data` stores workspace-local append-only individual metadata,
optimization/surrogate metadata, and zip-archived rawData under locks and atomic
publication. It stores raw variables once and scrubs duplicate variable payloads.
Public queries derive normalized variables, costs, and training bundles from current
task semantics. Invalid/legacy/corrupt rawData is skipped with diagnostics. No API
implicitly accesses another workspace.

`record_job_results()` is the population fast path. It validates a batch, copies the
existing archive once, appends all job members, and publishes the archive and JSONL
manifest atomically under the workspace lock. Single-job recording remains available
for direct callers and per-individual fallback.
