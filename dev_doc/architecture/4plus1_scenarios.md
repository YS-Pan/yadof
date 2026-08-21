# 4+1 scenarios

## New generic study

Install an AI coding agent and the wheel, open the intended workspace in the agent,
give it the prompt starter and task, then let it follow installed user documents
through `yadof init PATH`, task editing, and read-only `check`. Apply the documented
execution-risk policy and obtain explicit authorization when the estimated run
requires it; then run one local smoke, `run`, and inspect cost and integrated
time/failure/error history individually or with `view all`. A run without
`--generations` uses 50 generations. No repository path is required.

The initialized generic workflow contains only task-specific calculation/rawData
logic. It imports its assigned parameter snapshot and calls job-local
`worker_misc.run_workflow()`, which owns lifecycle metadata, execute identity,
standard paths, and flat `rawData.zip`. Replacing the task callback with a simulator
workflow preserves those package-owned contracts. Its starter `calc_cost.py`
demonstrates fixed-threshold algebraic-sigmoid normalization into a dimensionless
`[0, 1]` objective instead of returning the raw response value.

## Agent-authored study

The user prefixes a request with the repository prompt starter. The agent reads the
installed `user` documentation entry, follows its targeted reading order, runs
`init` when needed, edits only workspace-owned task inputs, and runs read-only
`check`. Before a real smoke or optimization, the agent classifies the concrete
runtime and external effects. It may autonomously run understood, bounded,
low-cost work; long, unknown-cost, shared-resource, or otherwise consequential work
requires explicit user authorization. An explicitly requested long run is detached
from the agent task and is not polled unless the user later asks.

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
restores/validates evidence, calculates current cost in the common finalizer, and
offers owned evidence to the campaign recorder. Normal jobs retain
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

## Fast local campaign

Select `EVALUATION_MODE = "fast"` only after adding a task-owned
`job_template/evaluation.py` kernel. The kernel receives a read-only named-value
mapping plus an evaluation context, returns direct `.npz` basenames mapped to
schema-valid memory payloads and optional JSON diagnostics, and never returns cost.
It may call a quick external simulator using the provided isolated scratch and
environment. Reusable workers run concurrently within the fast-specific resource
plan; a timeout or process exit replaces one worker. History receives the same
rawData/current-cost meaning as local mode, but `jobs/` gains no candidate folder.

## Change current cost policy

Edit workspace `calc_cost.py`, run `check`, and query history again. Existing
mechanically compatible rawData stays unchanged while objective names/values are
recalculated. During a campaign, make the edit between generations; the next
generation uses the new policy coherently. The full task tree was captured before
that generation's first candidate, so an edit during execution cannot split its
population; it becomes visible at the following boundary.

The same supported boundary applies when correcting parameter definitions,
configuration, workflow/evaluation code, or task helpers. The new generation may
use different parameter ranges/levels, objective meanings or thresholds, and is
intentionally allowed to be a scientifically different optimization problem.
Parameter identity/count and objective count remain stable for this supported
in-campaign path; structural dimension changes are future work. Yadof trusts the
user to decide whether retaining pre-edit evidence is scientifically reasonable.
It does not infer scientific equivalence from source signatures. If current code
cannot normalize or calculate a particular old record, that record is isolated; if
the user does not want old evidence considered at all, the user explicitly clears
history or uses another workspace. Task files continue to call reusable
`yadof.job_template` helpers rather than copying framework mechanisms.

## Inspect saved surrogate checkpoints

Install the `viewer` extra and run
`yadof view surrogate --workspace PATH`. The optional desktop tool reads current
task definitions, recorded evidence, and compatible checkpoint artifacts. It
predicts rawData, lets the user select zero to two plotted dimensions and fixed
coordinates for every remaining dimension through a checkpoint-grid dropdown or
arbitrary finite-value entry, reapplies current cost logic, compares selected real
individuals where recorded coordinates exist, and can calculate a cancellable
in-memory cross-generation error audit. Stored-grid selections keep legacy
prediction behavior; off-grid selections directly query the existing conditional
INR and interpolate its target scaler without changing checkpoint artifacts. The
resulting rawData view is a scalar, curve, or filled two-dimensional color contour.
Closing or stopping the viewer leaves configuration, history, rawData, and
checkpoints unchanged. `view all` remains the non-GUI cost/time pair and never
opens this tool.

For terminal or AI-agent inspection, run
`yadof view surrogate summary --workspace PATH --format json` to obtain checkpoint,
history, parameter, objective, and rawData-dimension metadata without loading a
model. Run `yadof view surrogate audit --workspace PATH --sample-percent 10
--random-seed 0 --metric both --quantity all-costs --format json` to calculate the
same cross-generation aggregate audit without opening a window. Audit progress, if
requested, goes to stderr; the schema-versioned report remains on stdout. Neither
mode writes a plot or workspace cache.

## Two simultaneous workspaces

Every call passes a workspace. Config, task modules, jobs, records, locks, surrogate
state, checkpoints, logs, and tools remain path-keyed. Same-named task helpers are
fresh-loaded and removed so one workspace cannot contaminate the other.

Concurrent optimization campaigns use different workspaces. One workspace is one
active campaign/write domain; an OS-backed non-blocking lock rejects the second
optimizer before evaluation. Destructive history clearing checks the same lock.

## Failure

Prepare, workflow, timeout, submit, resource exhaustion, invalid/nested rawData,
missing or malformed `rawData.zip`, collection, and current-cost errors are isolated
per individual. Queue exhaustion, oversized evidence, segment corruption, and
writer/storage failure are best-effort history loss and preserve a valid returned
cost. Strict CLI mode stops after an all-infinite generation and prints recent
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
