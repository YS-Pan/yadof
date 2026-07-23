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
- Wait for pending workspace-local surrogate training, then reset only that
  workspace's scheduler and in-memory surrogate state.
- Clear job entries, remove the checkpoint tree, remove the known record archive,
  lock, legacy aggregate, optimization metadata, and temporary targets, and finally
  recreate an empty jobs directory.

## I/O Format

- Input: a workspace-like value and explicit confirmation.
- Output: a dictionary containing the resolved workspace, count of deleted job
  entries, whether checkpoints were deleted, and exact removed record targets.
- The workspace marker, `config.py`, `job_template/`, and general tool-output files
  are not deletion targets.

## Non-Obvious Techniques

- Optional surrogate imports happen only during clearing; an unavailable optional
  surrogate stack does not prevent cleanup.
- Record cleanup targets the framework-owned mutable files rather than recursively
  deleting the entire configured recorded-data directory.

## Mutability Profile

- Confirmation, broad-path rejection, link/junction handling, and workspace
  isolation are non-negotiable safety contracts.
- Add a record target only when persistence owns that exact generated path.
