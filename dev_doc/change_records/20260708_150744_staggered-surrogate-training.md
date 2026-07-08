# 2026-07-08 15:07 - Staggered Surrogate Training

## Context
- The previous GPSAF flow trained the surrogate before candidate selection and again after real evaluation, which could leave distributed workers idle while the submit machine trained or predicted.
- The toDo requested a staggered flow: submit real jobs first using the latest completed surrogate model, then train the next model while the cluster is running those jobs.

## Change
- Added a surrogate scheduler that starts one background training task after real jobs are submitted and blocks only when the configured lag limit would be exceeded.
- Changed GPSAF to use only an already-trained surrogate state during candidate selection; prediction no longer implicitly trains.
- Added `after_jobs_submitted` callbacks to `evaluate_manager` and the HTCondor runner so submit-side training can begin after `condor_submit` succeeds and before polling waits for outputs.
- Split surrogate responsibilities into `types.py`, `checkpoints.py`, `metadata.py`, and `scheduler.py`, leaving `runtime.py` focused on training/prediction data flow.
- Added `recorded_data.api.record_surrogate_metadata()` and `list_surrogate_metadata()` for compact surrogate-training metadata rows under `optMeta/optMeta.jsonl`.
- Added file-level blueprints under `dev_doc/blueprints/20_files/` for the touched stable files.

## Rationale
- Using the newest completed model before training the next one keeps cluster resources busy and avoids the old double-train-per-generation behavior.
- A default maximum training lag of two generations preserves throughput while preventing indefinite use of stale surrogate states.
- Keeping surrogate training metadata in optimization metadata makes diagnostics visible without mixing derived training information into individual real-evaluation records.

## Impact
- `project.optimize` now passes a submit-side training callback to evaluation.
- `project.evaluate_manager` supports optional after-submit callbacks in local and distributed paths; distributed mode invokes the callback before polling jobs.
- `project.surrogate` has a wider internal file layout and a larger public API for scheduling/freshness status.
- `project.recorded_data` stores surrogate-training metadata rows in `optMeta/optMeta.jsonl`.
- Tests cover staggered GPSAF behavior, after-submit callback timing, and surrogate metadata recording.

## Follow-Up
- Future work may add process persistence for scheduler state if optimization is interrupted while background training is running.
