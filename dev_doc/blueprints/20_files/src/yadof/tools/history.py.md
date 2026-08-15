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
- Acquire a non-active campaign check before mutation.
- Clear job entries, remove the checkpoint tree and the framework-owned
  `segments/` and `metadata/` directories, and finally recreate an empty jobs
  directory. Other recorded-data entries remain untouched.

## I/O Format

- Input: a workspace-like value and explicit confirmation.
- Output: a dictionary containing the resolved workspace, count of deleted job
  entries, whether checkpoints were deleted, and exact removed record targets.
- The workspace marker, `config.py`, `job_template/`, and general tool-output files
  are not deletion targets.

## Non-Obvious Techniques

- Optional surrogate imports happen only during clearing; an unavailable optional
  surrogate stack does not prevent cleanup.
- Record cleanup recursively targets only the framework-owned segment and event
  directories after the exact workspace boundary and campaign-lock checks.

## Mutability Profile

- Confirmation, broad-path rejection, link/junction handling, and workspace
  isolation are non-negotiable safety contracts.
- Add a record target only when persistence owns that exact generated path.
