# 2026-05-18 12:00 - HTCondor Distributed Evaluation

## Context
- The project specification requires `evaluate_manager` to support both local and distributed evaluation while keeping local mode usable without HTCondor.
- The old `reference/20260124 combined/batch_eval.py` and `reference/htcondor_windows_debug_reference.md` contain a previously validated Windows HTCondor submit pattern.
- The current workstation may have a stale or unhealthy HTCondor installation, so project code should capture failures without trying to repair that environment.

## Change
- Added an optional HTCondor backend in `project/evaluate_manager/condor_runner.py`.
- Wired `evaluate_population(mode="distributed")` to prepare all jobs, submit them through HTCondor, collect `JobResult` objects, and reuse the existing `recorded_data` finalization path.
- Added shared job-result metadata helpers so local and HTCondor backends use the same rawData discovery and metadata writing behavior.
- Added HTCondor settings to `project/config.py` and `project/evaluate_manager/config.py`.
- Added tests for submit-file generation, submit failure capture, and distributed-mode finalization without requiring a real HTCondor pool.

## Rationale
- Direct `workflow.py` submission with `transfer_executable = True` matches the most recent Windows debug reference and avoids the fragile absolute-interpreter submit pattern.
- Distributed jobs still produce rawData and `individual_metadata.json`; cost remains dynamically calculated after recording.
- HTCondor installation, daemon, credential, or topology problems are external environment issues. The project records them as evaluation failures instead of attempting environment repair.

## Impact
- `evaluate_manager` now supports `local` and `distributed` modes.
- Default config remains `EVALUATION_MODE = "local"`, so standard tests and first-run debugging do not depend on HTCondor.
- Architecture, prompt, reference map, and terminology docs were updated for the new backend.

## Follow-Up
- A real HTCondor smoke test can be run on a known-good pool, but it should remain separate from the default pytest suite.
