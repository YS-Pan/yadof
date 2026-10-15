# File blueprint: src/yadof/tools/history.py

## Intent

- Destructively clear generated campaign history for exactly one confirmed
  workspace while preserving its task definition, configuration, and unrelated
  tool output.

## Functionalities

- Require `confirm=True` and otherwise raise
  `HistoryClearConfirmationRequired`.
- Resolve jobs, recorded-data, and surrogate-checkpoint locations through effective
  workspace config and reject workspace-root or filesystem-anchor targets.
- Refuse to traverse directory symlinks or Windows junctions as real runtime
  directories.
- Deactivate the active strategy's surrogate component, waiting for pending work
  and releasing memory before deleting all retained derived checkpoint and active
  optimization-state namespaces.
- Acquire and hold the campaign OS lock through deactivation, deletion, and empty
  directory recreation; release it even on failure. An inactivity probe alone is
  insufficient because another campaign could start after the probe.
- Clear job entries, remove the checkpoint tree and the framework-owned
  `segments/` and `metadata/` directories, and finally recreate an empty jobs
  directory. Other recorded-data entries remain untouched by default.
- With explicit `all_recorded_data=True`, remove the entire configured record root
  and recreate it empty, including user-added entries in that root. Require every
  deletion target to stay inside the workspace; reject overlaps with configuration,
  task sources, marker or lock before any deletion. Nested symlinks/junctions are
  removed without traversing their destinations.

## I/O Format

- Input: a workspace-like value, explicit confirmation, and optional full
  recorded-data reset (default false).
- Output: a dictionary containing the resolved workspace, count of deleted job
  entries, whether checkpoints were deleted, and exact removed record targets.
- The workspace marker, `config.py`, `submit/`, `job_template/`, and general
  tool-output files are not deletion targets. Failures may leave partial cleanup;
  callers must not report success or a completed reset on exception.

## Non-Obvious Techniques

- Optional surrogate imports happen only during clearing; an unavailable optional
  surrogate stack does not prevent cleanup.
- Record cleanup recursively targets only the framework-owned segment and event
  directories after the exact workspace boundary and campaign-lock checks.

## Mutability Profile

- Confirmation, broad-path rejection, link/junction handling, and workspace
  isolation are non-negotiable safety contracts.
- Add a record target only when persistence owns that exact generated path.
