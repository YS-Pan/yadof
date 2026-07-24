# 4+1 scenarios

## New generic study

Install wheel, `yadof init PATH`, edit workspace config/task, `check`, run one local
smoke, `run`, then inspect cost/time. No repository path is required.

The initialized generic workflow imports only its assigned parameter snapshot and
job-local `worker_misc.py`, writes one direct `.npz`, and creates flat
`rawData.zip`. Replacing it with a simulator workflow preserves the same evidence
and lifecycle contract.

## Agent-authored study

The user prefixes a request with the repository prompt starter. The agent reads the
installed `agent` documentation entry, follows its targeted reading order, runs
`init` when needed, edits only workspace-owned task inputs, and runs read-only
`check`. A real smoke or optimization remains an explicitly authorized execution
stage because it may launch expensive external software.

## Resume

`yadof run --workspace PATH --start-generation N --generations M` recovers current
history and workspace-local surrogate checkpoints, records the same campaign
generation context, and does not read another workspace.

History returns stored raw variables/rawData and recalculates normalization and
costs using the current workspace task. Checkpoint recovery requires compatible
parameter/rawData schema and reapplies current cost code.

## Real distributed campaign

The run command chooses smoke from workspace config unless explicit opposite CLI
flags override it. Smoke submits one unlimited midpoint individual. A finite result
permits generation zero; failure reports recent job metadata and submits no
generation. Skipped smoke activates configured synthetic calibration baselines.

For every candidate, the submit side copies the task, materializes self-contained
assigned parameters, and writes `job.sub` with `executable = workflow.py`. The
execute node runs as a slot user, creates direct `rawData/*.npz` and flat
`rawData.zip`, and returns only the zip plus individual metadata. The submit side
restores/validates evidence, records it, and calculates costs. Normal jobs retain
Condor's `allowed_execute_duration` and are independently watched from their local
`condor.log` execute events. At the per-job limit, yadof records timeout immediately,
attempts bounded `condor_rm` cleanup, and does not wait for queue removal.

## Change current cost policy

Edit only workspace `calc_cost.py`, run `check`, and query history again. Existing
compatible rawData stays unchanged while objective names/values are recalculated.
If the scientific meaning or schema of old evidence is no longer compatible, the
user explicitly clears or separates history.

## Two simultaneous workspaces

Every call passes a workspace. Config, task modules, jobs, records, locks, surrogate
state, checkpoints, logs, and tools remain path-keyed. Same-named task helpers are
fresh-loaded and removed so one workspace cannot contaminate the other.

## Failure

Prepare, workflow, timeout, submit, resource exhaustion, invalid/nested rawData,
missing or malformed `rawData.zip`, collection, and record errors are isolated per
individual. Strict CLI mode stops after an all-infinite generation and prints recent
diagnostic summaries. Pending unmatched Condor jobs receive one read-only match
analysis rather than being incorrectly marked failed. A missing, failed, or hung
`condor_rm` cannot keep a yadof-timed-out individual pending.

## Resource retry

A standard memory/disk hold is inspected, the old cluster is removed, only the
exhausted request is doubled within configured bounds, stale output is cleared, and
the same prepared job is submitted as a fresh cluster under the original generation
deadline. Workflow, timeout, and non-resource holds do not follow this path.

## Clean artifact

Build wheel/sdist, reject example/workspace/runtime/model members, install wheel
into a clean external environment, make site-packages read-only, and run help/version,
init/check/smoke/run/resume/view/history plus mocked distributed tests.
