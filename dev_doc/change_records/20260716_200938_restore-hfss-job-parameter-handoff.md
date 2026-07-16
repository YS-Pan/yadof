# 2026-07-16 20:09 - Restore HFSS Job Parameter Handoff

## Context

- The launch smoke test prepared and submitted its Condor job successfully, but the
  worker exited before starting HFSS because active `workflow.py` imported the
  removed `worker_misc.load_variables` helper.
- Job preparation already materializes the current individual's finite assigned
  values in the job-local `parameters_constraints.py`, so the extra input path was
  both stale and redundant.

## Change

- Removed the active HFSS workflow's legacy `load_variables` import and its generated
  `parameters_values.py` compatibility file.
- The workflow now passes its assigned job-local `parameters_constraints.py`
  directly to `hfss_com.set_para()`.
- Clarified the same single-source parameter handoff in architecture, blueprint, and
  user workflow guidance.

## Rationale

- One assigned parameter snapshot avoids payload-internal API drift and guarantees
  that the values materialized by `evaluate_manager` are the values applied to HFSS.
- `hfss_com.set_para()` already reads `PARAMETERS` and validates finite assigned
  values, so a second generated file adds no useful boundary.

## Impact

- Distributed and local executions of the active HFSS workflow can import and reach
  simulator startup again.
- HTCondor submission, timeout, retry, and resource-calibration behavior is
  unchanged.

## Follow-Up

- Deploy the updated source to the campaign directory before retrying the launcher.
