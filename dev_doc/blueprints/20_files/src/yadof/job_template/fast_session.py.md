# File blueprint: src/yadof/job_template/fast_session.py

## Intent

Own the versioned resident task interface without importing a concrete simulator.

## Functionalities

- Require literal `YADOF_FAST_API="yadof.fast.session/v1"` and callable
  `create_evaluation_session(context)`; declaration checks do not construct it.
- Load the task module under its isolated task context once, create the session,
  validate `evaluate_rawdata` and `close`, and close in `finally` before unloading.
- Validate optional `PHYSICAL_FAILURE_TYPES` as specific exception classes. Broad
  `Exception`/`BaseException` declarations cannot hide programming faults.
- Expose only the session methods and physical-failure types to the worker.

## Invariants

- No module-level legacy-kernel fallback, result cache, objective calculation,
  recorder bypass, process pool, or simulator ownership is hidden here.
- The owning worker determines lifetime; task sessions own their external handles.
- Declaration errors point to the installed resident-session migration guide.
