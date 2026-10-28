# 2026-09-30 12:35 - Ensure HTCondor batch.log exists

## Context
- HTCondor's explicit `transfer_output_files` list requires each named output to
  exist at job completion. The solver may not create `batch.log` on every path.
- The user chose to have the worker create an empty placeholder when the solver
  does not produce the file, avoiding a transfer hold while retaining real logs.

## Change
- The copied worker lifecycle now ensures `batch.log` exists after task cleanup,
  creating an empty file only when the simulator did not leave one.
- Updated terminology, architecture, source blueprints, user guidance, and
  administrator Condor contracts to describe the guarantee.

## Rationale
- Creating the placeholder after task cleanup leaves the path available for the
  simulator to create and write its own log during execution.
- On ordinary workflow success and task-error paths, the explicitly listed output
  exists for HTCondor transfer.

## Impact
- Jobs with a simulator-produced `batch.log` retain its contents.
- Jobs without one return an empty `batch.log` and do not fail output transfer for
  that missing file.
- Already prepared or submitted jobs keep their copied worker and submit snapshots;
  the change applies to jobs prepared with the updated package.

## Verification
- Built `yadof-0.6.0-py3-none-any.whl` and force-installed it into the canonical
  `D:\.venv`; import-origin verification resolved to `D:\.venv\Lib\site-packages\yadof`.
- Tests and a live HTCondor job were not run.
