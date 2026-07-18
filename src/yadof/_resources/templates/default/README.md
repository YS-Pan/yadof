# Default Workspace Template Resource

This bundled resource defines the software-neutral default workspace used by
`yadof init`. Its manifest lists the user-owned files published into a workspace;
framework APIs remain installed under `yadof` and are not copied.

The starter task evaluates a generic numeric input with pure Python/NumPy and writes
schema-valid rawData for a generic objective. It selects no simulator, vendor,
model/input filename, adapter, or physical result.

An unchanged initialized copy is the only task that `yadof smoke-test` runs without
`--real-task`. Prepared jobs receive package worker support separately; the
workspace template does not contain `worker_misc.py` or other framework runtime
implementations.
