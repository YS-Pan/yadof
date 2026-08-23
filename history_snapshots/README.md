# History snapshots

No warm-start history snapshot is selected by the current benchmark. Every suite
uses the explicit `empty` cold-start policy.

If a future suite needs a warm start, create a new immutable
`<case>/<snapshot-id>/` directory with provenance, row count, and a content
fingerprint. Select that exact identity in `benchmark.toml` and copy it identically
into every paired arm. Never point an arm at mutable history in an original task
workspace.
