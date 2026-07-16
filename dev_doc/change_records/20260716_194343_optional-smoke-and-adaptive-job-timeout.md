# 2026-07-16 19:43 - Optional Smoke And Adaptive Per-Job Timeout

## Context

- `start_optimization_aedtopt.cmd` reached `start_optimization_from_config.py` and began generation work without running the documented real smoke evaluation.
- Distributed evaluation had a submit-side whole-generation wait deadline but no scheduler-enforced limit for each individual job.
- Automatic memory/disk calibration already used smoke and preceding-generation measurements, so time calibration needed a parallel but time-specific policy.

## Change

- Added `OPTIMIZE_SMOKE_TEST_ENABLED` to key config. The launcher now optionally runs one midpoint individual through the configured backend with no timeout and aborts before optimization on an all-infinite result.
- Added `HTCONDOR_JOB_TIMEOUT_MODE` and the one-hour `HTCONDOR_JOB_TIMEOUT_SEC` baseline to key config. Advanced multiplier/top-trim defaults live in full config.
- Added `evaluate_manager.time_limits` to calculate fixed or automatic per-job limits from the newest smoke or preceding generation.
- Generated normal-job submit files now use HTCondor `allowed_execute_duration`; smoke submit files omit it. Hold codes 46/47 become terminal timeout records and are removed without retry.
- Recorded ClassAd diagnostics now include remote wall-clock and cumulative suspension time for future calibration.
- When smoke is disabled, configured memory, disk, and timeout baselines are treated as synthetic smoke measurements and receive the normal generation-zero multipliers.
- Added focused tests, current architecture/blueprints/terminology, user guidance, and a manual post-package CLI handoff.

## Rationale

- HTCondor's submit-side `allowed_execute_duration` is more precise and resilient than submit-process polling: the execute/scheduler path enforces execution time, excludes file transfer, and identifies the timeout with hold code 47.
- `periodic_remove` is more general but evaluated periodically and would require a custom ClassAd clock expression/reason contract. `max_job_retirement_time` concerns preemption grace and does not cap an otherwise uninterrupted job.
- Holding first lets yadof collect the standard reason and timing ClassAds; immediate submit-side removal then prevents retry and queue clutter.
- Official references: [condor_submit policy commands](https://htcondor.readthedocs.io/en/latest/man-pages/condor_submit.html), [job ClassAd attributes](https://htcondor.readthedocs.io/en/latest/classad-attributes/job-classad-attributes.html), [hold reason codes](https://htcondor.readthedocs.io/en/latest/codes-other-values/hold-reason-codes.html), and [Microsoft Windows behavior](https://htcondor.readthedocs.io/en/latest/platform-specific/microsoft-windows.html).

## Impact

- Launch behavior, generic config, evaluate-manager API, HTCondor submit files, recorded diagnostics, tests, user documentation, architecture, blueprints, and terminology changed.
- The existing generation timeout remains in place as a separate backend-wide safety budget.

## Follow-Up

- After package conversion, execute `dev_doc/toDo/20260716_194343_cli-run-with-optional-smoke-after-package.md` to move this launch behavior into the installed CLI.
