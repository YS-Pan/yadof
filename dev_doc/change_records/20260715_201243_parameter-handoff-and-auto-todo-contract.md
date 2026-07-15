# 2026-07-15 20:12 - Parameter Handoff And Automatic ToDo Contract

## Context
- A long-running optimizer kept the first imported parameter ranges while each new
  job copied the latest parameter file. The resulting job could contain new ranges
  but receive raw values calculated from old ranges through `job_input.json`.
- The direct HFSS parameter extractor could fail when an AEDT text file contained
  embedded non-UTF-8 bytes.
- Automatic toDo obsoletion included a subjective project-validity test, and current
  maintenance policy needed explicit reminders against old-version compatibility
  code and historical `v3` labels in current documentation.

## Change
- Made `Parameter` carry one current `normalized_value` and raw `value`, and added
  fresh isolated loading of `parameters_constraints.py` for all parameter queries.
- Added `job_template.api.materialize_job_parameters()`. Job preparation now
  materializes one assigned parameter snapshot from the requested template directory
  and uses the same returned raw values for `JobSpec` and recording.
- Removed the optimizer-variable `job_input.json`/`variables.json` path and
  `worker_misc.load_variables()`. The active HFSS workflow now calls `set_para()` on
  the job-local snapshot.
- Changed static hashing of the parameter snapshot to include only parameter name,
  ranges, unit, and constraints, excluding per-individual assigned values.
- Added parameter object, same-process range refresh, historical re-normalization,
  local/distributed handoff, static-hash, and HFSS adapter tests.
- Merged surrogate-escape decoding for AEDT files with embedded non-UTF-8 bytes into
  `specific/hfss/get_para_and_range_direct.py`. The existing single-project scan is
  covered by tests, and PyAEDT fallback now honors `--design` instead of a hard-coded
  design constant.
- Replaced automatic-toDo validity obsoletion with an optional, objective
  user-defined condition that is absent by default; time expiry remains seven days
  by default. Added automatic toDos for avoiding old-version compatibility design and
  removing historical `v3` labels from current documentation.
- Updated architecture, blueprints, terminology, and user documentation, then
  archived the completed parameter-handoff toDo.

## Rationale
- Fresh materialization makes the job-local parameter file the single definition and
  value input, preventing cached ranges, executed values, and recorded raw variables
  from diverging.
- A definition-only hash preserves task-change detection without making every
  individual appear to use a different task.
- Objective configured conditions make automatic document retirement reproducible;
  agents no longer infer obsoletion from a subjective assessment of project change.

## Impact
- Prepared jobs no longer contain or transfer an optimizer `job_input.json` or
  `variables.json`. Workflows must read assigned `parameter.value` fields.
- Canonical parameter files use the current `Parameter` class and may leave assignment
  fields as NaN; job-local snapshots must contain finite assignments.
- Default tests pass with `116 passed`. Simulator-specific tests that do not launch
  AEDT pass with `7 passed`.

## Follow-Up
- The two new automatic toDos remain active for incidental occurrences until their
  default obsolete rule archives them.
