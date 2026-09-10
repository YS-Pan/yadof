# Execution and evidence

## Before execution

Run `check` and `plan` first. They import `benchmark.py`, validate strategies
and baselines, and do not create execution outputs or start simulators.

```powershell
yadof-benchmark check --workspace WORKSPACE
yadof-benchmark plan --workspace WORKSPACE
```

Both commands print a bounded summary by default. Add `--json` only when the
complete expanded plan is needed. Planning code must therefore be deterministic,
cheap, and free of simulator or external-state side effects.

## Benchmark smoke test

Use **benchmark smoke test** as the current name for the pre-measured execution
check. Older discussion may call this a *canary*, but a canary-specific workflow
is not a separate benchmark contract. The smoke test must exercise the same
benchmark path as the measured run; the only intentional benchmark-definition
change is a smaller positive evaluation count.

Create a fresh workspace with `init --preset complete`, then select
`--budget-profile smoke` on check, plan, and run. The profile mechanically keeps
the complete preset's 18 cells, population 200, strategies, seeds, hashes,
policies, and 7200-second timeout while changing only generations from 25 to 1.
Keep all of the following unchanged:

- `benchmark.py` implementation and registrations, including the complete cell,
  comparison, and arm matrix;
- selected baseline IDs and their manifests, task workspaces, assets, `config.py`,
  `submit/`, `job_template/`, and task postprocessing code;
- every strategy entry module and declared helper, algorithm/model setting,
  seed, evidence classification,
  failure policy, concurrency policy, dependency, and registered workflow
  postprocessor;
- result, contract, metric, visualization, and postprocessing paths.

Do not edit `benchmark.py` for this reduction. A different workspace root and a foreground versus detached
launch are execution controls and do not count as benchmark-code changes. Do not
change the seed merely to make the smoke pass.

The smoke test must not add conditional smoke branches, a simplified strategy,
mock or synthetic task code, a different baseline, a reduced cell/arm matrix, or
an omitted/replacement postprocessor. Run the complete chain, including the
normal baseline postprocess and every registered workflow postprocessor. Choose
the smallest budget that makes that unchanged chain produce valid output; if a
postprocessor requires more data, increase the budget instead of weakening the
chain.

Run the same preflight and execution commands against the smoke workspace:

```powershell
yadof-benchmark check --workspace SMOKE_WORKSPACE --budget-profile smoke
yadof-benchmark plan --workspace SMOKE_WORKSPACE --budget-profile smoke --json
yadof-benchmark run --workspace SMOKE_WORKSPACE --budget-profile smoke
yadof-benchmark inspect --workspace SMOKE_WORKSPACE
```

Compare the smoke plan with the measured plan before the measured run. The
semantic cells, selected source digests, baselines, strategies, postprocessors,
seeds, and policies should match; only the evaluation budget may differ. A smoke
test passes only when every planned cell reaches the normal valid/collected state
and all postprocessors succeed. Individual simulation failures may still be
tolerated under the ordinary cell-validity rules, but missing attempts, broken
contracts, missing metrics, or a postprocessor failure block the measured run.

Smoke output is structural execution evidence only. Do not pool it with measured
results, use it to select an algorithm or parameter, or cite its metrics as
performance evidence. After it passes, start the full-budget measured execution
in another fresh workspace; never turn the smoke workspace into a resumed or
expanded run.

## AI agents on Windows: use the human account

When an AI agent launches a benchmark, it must execute the launch command through
host execution under the interactive human user's account. Do not launch it as
the Codex sandbox user.

Windows associates a visible console with the process account and interactive
session. A sandbox process is in a non-interactive session; adding `--detach`
does not change that identity and its new console will not be visible to the
human. The correct agent procedure is:

1. request or use approved host execution for the exact benchmark launch;
2. run it under the signed-in user's account;
3. add `--detach` for a visible independent console;
4. return the receipt containing PID, workspace, log, and inspect command;
5. record the receipt as launch evidence, not terminal benchmark evidence.

```powershell
yadof-benchmark run --workspace WORKSPACE --detach
```

A full-budget measured benchmark may run for hours. A successful receipt alone
does not satisfy a task whose definition of done requires terminal results. The
default agent handoff still avoids unrequested polling. If the user explicitly
requests monitoring or a heartbeat, bind that monitor to the same task, workspace,
receipt, and PID; use bounded `inspect` snapshots at the requested interval and
stop the monitor immediately after terminal evidence is collected.

When the user later asks for progress or results, run one bounded `inspect` and
report that snapshot. A launch error or an incomplete/ambiguous receipt may be
diagnosed immediately, but a successful receipt alone is not a reason for a
follow-up inspection.

Do not substitute other launch or visibility mechanisms for this command:

- Do not use a Codex execution PTY or Codex Terminal panel as the user-visible
  Windows console.
- Do not write a separate `Start-Process` command or auxiliary PowerShell launcher;
  `--detach` owns console creation, argument quoting, and window persistence.
- Do not poll `MainWindowHandle` or the window title to decide whether the detached
  launch succeeded. Use the returned launch receipt and `inspect`; Windows window
  registration may lag behind process creation.

The visible detached console remains open after the benchmark succeeds or fails,
preserving its final progress and error output for review. Type `exit` at the
PowerShell prompt or close the window when it is no longer needed. An explicit
`--hidden` launch remains noninteractive and exits automatically.

`--hidden` is only for an explicit user request. If host execution is not
available, run in the foreground and clearly state that no separate visible
window can be created; do not silently fall back to a sandbox-owned detached
process.

## Low-cost monitoring for agents

Long benchmarks can run for hours. When the user requests monitoring or terminal
results, the main agent must delegate monitoring to a low-cost subagent with no
inherited conversation context (`fork_turns="none"`, or the host equivalent).
In September 2026 select `gpt-5.6-luna` with low reasoning effort. At a later date,
choose the then-available inexpensive monitoring model occupying that same role;
do not silently substitute the main expensive model. If delegation is unavailable,
report that limitation and use the user's approved sparse fallback.

Give the monitor a self-contained assignment containing the exact workspace,
interpreter, launch receipt/PID, inspect command, output location and stop rule.
It checks one bounded read-only `inspect` snapshot every five minutes. It stays
active and waits between checks; one observation followed by a final response is
not a continuing monitor. Retain observation timestamps in task-owned monitoring
evidence so gaps remain visible. It never trains, changes inputs, restarts work,
reinstalls packages, or performs broad history/response audits.

The main agent uses long event waits and requests a compact summary at most once
per hour while nothing actionable changes. It must not independently poll the
benchmark. At the hourly boundary it may read the monitor’s latest saved bounded
summary without launching another inspect. A running state file alone does not
prove liveness; diagnose suspected process loss using an exact child PID from the
command log and a process query, rather than unrelated Python processes. Completion, failure, lost process/progress, or required user action
should wake it immediately. Do not send routine five-minute user updates. Where
the host limits a single wait duration, chain quiet event waits without adding
benchmark reads or model-generated status messages; shorter wait slices do not
change the five-minute inspection and hourly summary cadence.

A tool returning a live session/cell identifier has yielded an observation
window; this is not a process exit or an agent time limit. Continue waiting on
that same handle until a final exit code or explicit terminal evidence arrives.
Do not start duplicate waits or samplers to obtain another status message.
A helper process can retain the five-minute sampling cadence while an agent turn
is idle, but it cannot by itself provide agent notifications. If the monitor ends
its turn early, report that interruption and the resulting notification delay;
the main agent may re-contact the same low-cost monitor at its hourly cadence.
Never describe a live helper alone as an actively waiting agent.

Terminal evidence, not disappearance of a console or a launch receipt, ends the
monitor. Send terminal status, validity counts and report paths to the main agent,
then stop. A terminal failure stays failed; the main agent owns diagnosis and any
new authorized execution. A monitoring gap must be reported honestly.

## One workspace, one execution

`run` writes the execution directly into the workspace. To execute again,
initialize another workspace and copy or regenerate the desired authoring inputs.
There is no run ID, `runs/` directory, resume command, or attempt hierarchy.
The implementation assumes a fresh workspace; it does not contain a separate
policy layer whose purpose is to reject repeat or resume requests.

Immediately before cell work, the runner writes:

- `runtime.json`: installed yadof-benchmark/yadof versions, Python, host, and
  process account, recorded once;
- `spec.json`: the complete expanded plan;
- `state.json`: current execution state.

For each materialized fast/local cell, state includes the detected physical core
count, baseline `physical_core_multiplier`, floor rounding rule, and resolved
maximum simulator workers. The baseline's fixed input remains the multiplier in
`spec.json`; the host-specific integer is execution evidence.

The installed package performs the execution directly. The runner does not copy
its own driver, `benchmark.py`, resources, or strategy source as a versioned
code snapshot. A baseline is materialized into each cell only because yadof needs
an isolated execution workspace.

## Budget defaults

Packaged preset budgets are explicit and therefore do not use these authoring
defaults. `portable` is population 12 by two generations for two cells.
`complete` is population 200 by 25 generations for 18 cells; every baseline
declares a 7200-second per-cell command timeout. The derived `smoke` profile keeps
population 200 and sets generations to one.

- Default seeds: `[101]`.
- Standard optimization-only comparison: population `200`, generations `50`.
- Any comparison containing a strategy declared `slow_surrogate=True`:
  population `200`, generations `15`.
- Explicit `seeds`, `population`, or `generations` override these defaults.

The slow-surrogate default deliberately keeps generations in the 10-20 range.
Population is not reduced automatically. Paired strategies must have matching
initial designs and formal budgets; P/B may differ through explicit arm overrides.
Use explicit values after inspecting the
plan when a task needs a different tradeoff.

## Improving throughput

The default is `benchmark.configure(cell_concurrency=4)`, including the packaged
portable, complete and perfect workflows. Independent cells can cover time spent
waiting for simulators, selection, collection or publication. Top-10 comparisons
support this too: only each candidate's paired reference is a dependency.

There are two general capacity controls. `cell_concurrency` caps active cells;
the copied baseline's `execution.simulation_concurrency.physical_core_multiplier`
sets workers per cell to `max(1, floor(physical_cores * multiplier))`. For example,
four cells with multiplier `1.0` on eight physical cores request 32 concurrent
simulations. A multiplier of `2.0` requests 64 across four such cells. Waiting
and startup time can make these oversubscribed settings faster than matching the
logical-core count. A cell may retain additional idle formal/oracle worker pools;
this calculation describes active simulation capacity, not total process count.

Keep the baseline-specific defaults as a starting point. When changing capacity,
try a few small batches of the already planned cells with different multipliers
in fresh workspaces, keeping each same-seed reference and all candidate arms
together. Retain capped noncrossings in the statistics and report invalid runs
separately. Compare complete
wall time and memory as well as CPU use; different P/B combinations and stopping
lengths make unpaired cell timings descriptive. An exact speed comparison needs
the same seeds and budgets. A baseline that benefits from more workers need not
share the multiplier of another simulator.

Keep native BLAS/OpenMP pools at one thread for many independent CPU workers;
the benchmark child launcher sets this before starting each command, and spawned
simulator descendants inherit it. This also avoids large per-process native
thread buffers consuming Windows commit memory despite low resident RAM usage.
The effective environment limits are recorded in each command's `started.json`.
Increasing every
parallelism control at once can slow the run through contention and memory growth.

Benchmark execution reserves host memory as well as CPU capacity. On Windows it
checks system committed memory and its current limit, rather than treating free
physical RAM as sufficient. A shared Windows job limits private committed memory
for cell command trees to the smaller of 60% of the initial system commit limit
and the initially available commit minus a 20% system reserve (at least 2 GiB).
An independent watchdog stops admission and cancels commands if global commit
headroom falls below that reserve, or available physical memory falls below 10%
(at least 1 GiB). Memory exhaustion is fatal even with `fail_fast=False`;
ordinary simulator failures keep their existing treatment. The runner records
`resource_protection` in `state.json`. This changes no system page-file settings.

Put known long baselines first in `compare(baselines=[...])` to reduce the final
tail when ready work is otherwise comparable. Keep the resident `fast` baseline
adapters: they reuse simulator sessions across batches. No custom process-pool
implementation is needed in a strategy. Low total CPU/GPU activity can also mean
a serial Python or numerical step occupies one core; GPU utilization is relevant
only for components that actually execute on the GPU.

For a large matrix, divide the seed list between a few fresh workspaces and keep
every same-seed reference and candidate arm together. Run one workspace at a time
with the chosen cell concurrency. Publication rewrites the cumulative per-point
reports after each cell, so smaller matrices reduce repeated report work and the
largest report held in memory. Preserve the original full seed list and budgets.
Combine individual seed results for final statistics; never average or take the
median of workspace medians. Each workspace still needs its normal collection
and postprocessing outputs.

## Failure and validity

`yadof run` is invoked with `--fail-on-all-infinite`. Individual simulation
failures are allowed. A collected cell is valid when:

- attempted evaluations equal the planned count, or exactly the first strict
  crossing under the explicitly declared top-10 stopping protocol;
- at least one finite result exists;
- objective and rawData contracts match;
- the complete generation-0 normalized population is available;
- final descriptive hypervolume is available.

Completed and finite counts may be smaller than attempted count. The report
publishes failed and non-finite counts plus
`simulation_errors_tolerated=true`; diagnostic issues remain visible. Missing
attempts, no finite result, broken contracts, missing initial-population evidence,
or missing metric still invalidate the cell.

An evaluator's explicit `physical_failure=False` marks a task or infrastructure
fault, such as a simulator process that could not start. Collection rejects the
cell even if other candidates produced finite results; it must not become an
ordinary failed-design penalty or weaken a paired reference.

A command, storage, visualization, collection, or workflow postprocessor failure
is retained in `state.json` and makes the overall status non-successful. Create
a new workspace after correcting the problem.

On Windows, a reader can briefly prevent atomic replacement of a JSON report.
Publication automatically retries access/sharing/lock conflicts for up to two
seconds while preserving the previous complete file. Persistent storage errors
still stop execution. The runner records the primary scheduler failure as
`execution_error` and attempts to save terminal failed state after cancelling
active commands. If the storage remains unwritable, use the process exit and
error log even when the last readable state still says `running`.

Workflow postprocessors normally require all cells to be collected. A callback
registered with `run_on_failure=True` may summarize failed or incomplete cells
after scheduling ends; default callbacks are then marked `skipped`. Such a
summary does not override cell failure or relax the evidence-validity rules.

A cell timeout stops the child process tree, records
`process_tree_cleanup=requested-and-parent-exited`, fails that cell, and—when
`fail_fast=False`—continues independent cells. Any timeout still makes the final
workspace status non-successful.

## Progress, logs, and inspection

Foreground execution owns a Rich active-cell row and a global benchmark row.
The active lifecycle includes the semantic display label, cell/global counts,
elapsed command time, generation/evaluation counts, phase, failures, and timeout
state. Progress percentages advance only from actual version-matched yadof
`evaluation` snapshots; command heartbeats never manufacture completion. TTY
output refreshes live. Non-TTY output is append-only, contains no ANSI control
sequences, and emits bounded progress/elapsed snapshots.
Every measured command has separate `stdout.log` and `stderr.log` files below
`cells/cNNNN/commands/`. Raw child output is echoed only with the explicit
`--stream-child-output` diagnostic option.

`inspect` is bounded and read-only:

```powershell
yadof-benchmark inspect --workspace WORKSPACE
```

It reports status, active logs, current-workspace timing evidence, validity,
simulation errors that were tolerated, anomalies, and artifact paths. Timing
estimates use only this workspace's observed generation trend and baseline lower
bounds; there is no cross-workspace timing history.

While a workspace is running, planned and active cells are expected to be
incomplete and are not reported as anomalies. Real state errors and validity
issues from completed cells remain visible. Once the workspace is terminal,
incomplete-cell validity issues are included so a failed campaign retains its
full diagnostic evidence.

Review in this order: inspect summary, `reports/summary.md`, the targeted CSV or
descriptive JSON report, then a specific cell command log.
