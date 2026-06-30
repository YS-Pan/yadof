# 2026-05-29 01:15 - HFSS Distributed Diagnostics And Resources

## Context
- Distributed jobs reached PyAEDT/AEDT startup but generation evaluation still returned all `inf`.
- Some jobs exceeded the generation-level wait budget, while others terminated without rawData and lacked enough metadata to identify the workflow exception.
- The HTCondor request values were lower than the workflow's default HFSS core usage and too small for typical AEDT memory use.

## Change
- Added `EVALUATION_TIMEOUT_SEC = 12 * 60 * 60` to the project config.
- Changed distributed job requests to 3 CPUs and 8 GB memory, and passed matching `YADOT_HFSS_JOB_CPUCORE=3` through the HTCondor environment.
- Updated `workflow.py` to write catchable exception details into `individual_metadata.json` before re-raising.
- Guarded `solver_exit()` so a failed `solver_init()` does not hide the original startup error by trying to release a `None` HFSS object.
- Added Condor return-value parsing, Condor log tail capture, optional `batch.log` tail capture, and Windows-codepage fallback decoding for returned logs.
- Expanded the optimization launcher failure summary to print the new diagnostics.

## Consequences
- Timeout is treated as a full-generation budget; large populations may still need a higher value.
- Future no-rawData failures should report Python/AEDT exception details or Condor return value instead of only saying that no `.npz` files were found.
- Worker slot packing now matches the workflow's HFSS core count more closely.
