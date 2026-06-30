# 2026-05-27 20:19 - HTCondor Python Executable

## Context
- Windows HTCondor workers held jobs with `Bad exe type. err=193` because the submit file tried to execute `workflow.py` directly.
- The workers need to run the copied workflow through the Conda environment Python that contains the project's dependencies.

## Change
- Added `HTCONDOR_PYTHON_EXE` to `project/config.py` and the evaluate-manager config accessors.
- Changed generated `job.sub` files to use the configured worker Python executable with `arguments = workflow.py`.
- Changed `transfer_executable` to `False` in that mode and transfers `workflow.py` as an input file.
- Updated HTCondor tests and docs to describe the explicit Python execution path.

## Rationale
- Windows does not reliably treat `.py` files as directly executable HTCondor payloads.
- An explicit worker Python path makes the runtime environment deterministic and avoids dependence on file associations.

## Impact
- Every matching worker must have the configured Python executable at the same path.
- Existing held jobs submitted with the old direct-`.py` submit file must be removed before retrying.

## Follow-Up
- If worker Python is installed at different paths, either standardize the path on all workers or add a worker ClassAd/path-selection mechanism before submitting jobs.
