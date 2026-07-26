# 2026-07-26 11:25 - Enforce task/framework code boundary

## Context

- Execute-machine collection and other invariant lifecycle mechanics had been
  duplicated in the generic `workflow.py`.
- The HFSS reference workflow repeated lifecycle, metadata, archive, and error
  handling, while its cost module repeated reusable rawData/cost mechanisms.
- Task files must contain only behavior that changes with an optimization task.

## Change

- Added `WorkflowContext`, `run_workflow()`, and `rawdata_metadata()` to the
  package-owned `worker_misc.py` copied into prepared jobs.
- Centralized standard execute paths, sandbox setup/cleanup, runtime identity,
  execute-machine collection, rawData preparation/flat archive publication,
  lifecycle/error metadata, cleanup handling, and primary-error preservation.
- Added reusable defined-task cost, objective-name, worst-curve, axis-curve, and
  importance-weight helpers under `yadof.job_template`, plus generic rawData
  loading/result-width/failure handling for tasks that use custom cost callbacks.
- Reduced the generic and HFSS workflows/cost modules to task-variable callbacks,
  rawData interpretation, simulator operations, and objective policy.
- Adapted the Chengyang and `test_com` workspaces to the same boundary. Chengyang's
  specialized `(curve, data_range)` grouping remains task-local because it is not a
  sufficiently common package abstraction.
- Removed redundant task `get_objective_count()` functions because yadof derives
  the count from validated objective names.
- Corrected the HFSS reference's stale `rawData_outputs.zip` behavior to the fixed
  `rawData.zip` transport contract, and excluded current `_home`, `_appdata`, and
  `_localappdata` runtime directories during job preparation.
- Documented the task/framework variability rule in agent guidance, architecture,
  blueprints, terminology, and template documentation.

## Rationale

- Cross-task invariant code needs one tested implementation in yadof.
- Distributed execute nodes do not import the installed package, so invariant
  execute behavior must travel through the single copied worker-support file.
- Scientific simulator and objective policy must remain editable task code rather
  than becoming framework assumptions.
- Extractability alone does not justify a public helper: package code must be a
  stable contract or broadly useful across distinct optimization task families.

## Impact

- Task workflows call `worker_misc.run_workflow()` and no longer write lifecycle
  metadata or transport archives themselves.
- Task cost modules call `yadof.job_template` helpers and no longer duplicate
  reusable dispatch, constraint, failure, reduction, or counting behavior.
- Execute-machine provenance is worker-support-owned and cannot be overridden by
  task metadata or runtime extras.
- Generic tests cover the new worker lifecycle and reusable cost/rawData helpers.

## Follow-Up

- Other existing external workspaces are not rewritten automatically. Their task
  code should adopt the documented helper calls when intentionally updated.
