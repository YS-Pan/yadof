# Config Split, Job Config Copy, And Path Cleanup

## Why
- `project/config.py` had grown into a mixed file containing key campaign settings, derived defaults, helper functions, and distributed-runtime details.
- HTCondor jobs needed the submit-side config snapshot copied into each prepared job folder so worker-side workflow defaults are reproducible.
- The old HTCondor environment example used semicolon-separated values inside a quoted environment string, which can prevent HFSS core overrides from reaching the worker.
- Several launch and pool helper scripts still assumed machine-specific install or scratch paths.

## What Changed
- Split config into short key config `project/config.py` and full grouped defaults `project/config_all.py`.
- Updated runtime modules to import `project.config_all` while keeping `project/config.py` free of helper functions.
- Added job preparation copying for both `config.py` and `config_all.py` into each prepared job folder.
- Updated `workflow.py` so HFSS defaults come from the copied job-local `config.py`, then can be overridden by job environment variables.
- Changed default HTCondor environment construction to quoted, whitespace-separated syntax and kept `HTCONDOR_REQUEST_CPUS` aligned with `HFSS_JOB_CPUCORE` by default.
- Removed fixed-drive defaults from launch, diagnostics, and HTCondor pool helper scripts; they now use PATH, existing environment-derived locations, Program Files discovery, or explicit user parameters.
- Updated user docs, blueprints, architecture notes, terminology, and the related HFSS multi-core diagnostic toDo.

## Notes
- Historical change records may still mention older machine-specific paths as history.
- The remaining HFSS 08 iterative-solver multi-core diagnosis is not complete; only the config/path/env parts related to this cleanup were implemented.
