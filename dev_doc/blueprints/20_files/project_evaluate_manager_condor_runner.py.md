# File blueprint: project/evaluate_manager/condor_runner.py

## Intent
- Submit prepared jobs to HTCondor, then collect job-local outputs using the shared evaluation result contract.

## Functionalities
- Submit one `job.sub` per prepared `JobSpec`.
- Invoke an optional `after_jobs_submitted` callback after successful submissions and before polling outputs.
- Poll terminal job state, collect rawData and metadata, and turn failures/timeouts into `JobResult` rows.

## I/O Format
- Input is prepared job specs.
- Output is ordered `JobResult` rows.
- Callback has no arguments and its return value is ignored.

## Non-Obvious Techniques
- The after-submit callback is designed for submit-side surrogate training. Callback failure is logged but must not cancel already-submitted HTCondor jobs.

## Mutability Profile
- HTCondor submit details may change, but the callback location must remain after submission and before waiting if staggered training is to keep the cluster busy.
