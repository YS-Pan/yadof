# 4+1 scenarios

## New generic study

Install an AI coding agent and the wheel, open the intended workspace in the agent,
give it the prompt starter and task, then let it follow installed user documents
through `yadof init PATH`, task editing, and read-only `check`. After explicit
authorization, run one local smoke, `run`, then inspect cost and integrated
time/failure/error history individually or with `view all`. A run without
`--generations` uses 50 generations. No repository path is required.

The initialized generic workflow contains only task-specific calculation/rawData
logic. It imports its assigned parameter snapshot and calls job-local
`worker_misc.run_workflow()`, which owns lifecycle metadata, execute identity,
standard paths, and flat `rawData.zip`. Replacing the task callback with a simulator
workflow preserves those package-owned contracts.

## Agent-authored study

The user prefixes a request with the repository prompt starter. The agent reads the
installed `user` documentation entry, follows its targeted reading order, runs
`init` when needed, edits only workspace-owned task inputs, and runs read-only
`check`. A real smoke or optimization remains an explicitly authorized execution
stage because it may launch expensive external software.

The standalone smoke CLI flushes the selected workspace, backend, jobs directory,
and no-timeout warning before blocking on the workflow, then reports success costs
or an actionable failure.

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

## Adaptive local campaign

The package default local cap is eight workers. A run smoke still evaluates one
midpoint individual and records process-tree CPU, peak-memory, and disk evidence.
Before generation zero, yadof applies the shared bootstrap calibration, samples the
host's current physical CPU/available memory/free disk, preserves the configured
system reserve, and starts only the minimum safe worker count. Later generations
recalculate from the preceding generation in the same run. `--progress` prints the
chosen count and each limiting capacity.

If local autodetection is disabled, the configured cap applies directly after the
population-size bound. The explicit cap is never exceeded, and a missing system or
history measurement falls back to the configured per-job resource hints rather than
blocking the campaign.

## Change current cost policy

Edit only workspace `calc_cost.py`, run `check`, and query history again. Existing
compatible rawData stays unchanged while objective names/values are recalculated.
If the scientific meaning or schema of old evidence is no longer compatible, the
user explicitly clears or separates history. The task file changes its rawData
interpretation and objective policy while continuing to call reusable
`yadof.job_template` cost/rawData helpers.

## Inspect saved surrogate checkpoints

Install the `viewer` extra and run
`yadof view surrogate --workspace PATH`. The optional desktop tool reads current
task definitions, recorded evidence, and compatible checkpoint artifacts. It
predicts rawData, reapplies current cost logic, compares selected real individuals,
and can calculate a cancellable in-memory cross-generation error audit. Closing or
stopping the viewer leaves configuration, history, rawData, and checkpoints
unchanged. `view all` remains the non-GUI cost/time pair and never opens this tool.

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
`condor_rm` cannot keep a yadof-timed-out individual pending. If timeout prevents
worker metadata transfer, the final active or allowed-duration-held execution
segment supplies source-labeled Condor machine/slot provenance; a queued job with no
execute event correctly remains `unknown`. Historical timeout records can obtain
the same display-only fallback from active-removal, `condor_rm`-eviction, or
terminal-before-collection evidence in their already recorded Condor log tail
without mutating durable evidence.

## Resource retry

A standard memory/disk hold is inspected, the old cluster is removed, only the
exhausted request is doubled within configured bounds, stale output is cleared, and
the same prepared job is submitted as a fresh cluster under the original generation
deadline. Workflow, timeout, and non-resource holds do not follow this path.

## Clean artifact

Build wheel/sdist, reject example/workspace/runtime/model members, install wheel
into a clean external environment, make site-packages read-only, and run help/version,
init/check/smoke/run/resume/view/history plus mocked distributed tests.
