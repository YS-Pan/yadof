# 2026-09-30 12:08 - Return HTCondor batch.log

## Context
- Remote HFSS task failures need the execute-side `batch.log` for solver
  diagnostics. The generated submit file returned only `rawData.zip` and
  `individual_metadata.json`.
- The user explicitly requested that `batch.log` be added to Condor's output list.

## Change
- Added `batch.log` to the generated `transfer_output_files` list.
- Updated the submit-file regression assertion and the evaluate-manager blueprints.

## Rationale
- Returning the solver log makes it available beside each prepared job's other
  returned diagnostics on the submit side.

## Impact
- Newly generated Condor submit files request `rawData.zip`,
  `individual_metadata.json`, and `batch.log`.
- HTCondor requires every explicitly listed output to exist. A task that does not
  produce `batch.log` may be held during output transfer.
- Already submitted jobs retain their existing submit files.

## Verification
- Built and force-installed the wheel in the repository's `D:\.venv`; confirmed
  imports resolve from that environment.
- `tests/test_packaged_distributed_execution.py`: 16 passed.
- Full suite: 598 passed, 7 skipped, 6 failed. Five failures require the absent
  optional `botorch` distribution; one unrelated backpressure timing-counter
  assertion also failed when rerun alone.

## Follow-Up
- No live Condor job was run during generic package acceptance; the missing-file
  hold risk remains specific to execute environments that do not produce the log.
