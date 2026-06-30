# 2026-05-27 15:30 - HTCondor Start Preflight

## Context
- Distributed optimization could appear stuck immediately after `starting optimization` because the launcher did not verify HTCondor visibility before entering the Python optimization loop.
- The submit-side `JOBS_DIR` had been confused with worker-side RAM-disk execution.

## Change
- Updated `project/config.py` so `JOBS_DIR` is the submit-side `project/jobs` staging directory again.
- Added an HTCondor requirement that matches workers advertising `YADOF_RAMDISK = True`.
- Updated `start_optimization_aedtopt.cmd` to use the `yadof` Conda environment, find HTCondor, set `CONDOR_CONFIG` when available, print pool status, and verify the queue before launching Python.
- Enabled opt-in progress logging from the launcher so generation start, distributed job preparation, HTCondor submission, and pending-job waits are visible during long runs.
- Enabled launcher-only strict validation that treats an all-`inf` generation as a failed real optimization run and prints recent job failure metadata.
- Clarified the worker RAM-disk docs and architecture notes.

## Rationale
- Worker R: execution should be controlled by HTCondor `EXECUTE`, while the submit machine keeps a durable staging directory for generated job folders and returned outputs.
- A launcher preflight makes missing Condor configuration, unreachable schedd/collector, or missing worker advertisements visible before a long optimization run starts.
- Progress output distinguishes slow job preparation, submission backlog, and worker-side execution waits without adding noisy library output to default API calls.
- All-`inf` costs are useful as library-level failure isolation, but a production CMD launcher should not call that a successful optimization campaign.

## Impact
- Launching optimization now fails early if the submit machine cannot reach HTCondor.
- Jobs are constrained to execute on workers that advertise the RAM-disk setup.

## Follow-Up
- If jobs remain idle after submission, inspect `condor_q -better-analyze <cluster>` and compare requested CPU/memory/disk resources with the slots printed by the launcher.
