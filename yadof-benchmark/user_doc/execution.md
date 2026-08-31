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

Create a fresh smoke workspace from the complete measured-workflow authoring
inputs. Keep all of the following unchanged:

- `benchmark.py` implementation and registrations, including the complete cell,
  comparison, and arm matrix;
- selected baseline IDs and their manifests, task workspaces, assets, `config.py`,
  `submit/`, `job_template/`, and task postprocessing code;
- every strategy entry module and declared helper, algorithm/model setting,
  seed, evidence classification,
  failure policy, concurrency policy, dependency, and registered workflow
  postprocessor;
- result, contract, metric, visualization, and postprocessing paths.

Change only the explicit evaluation budget, normally `population` and/or
`generations` in every comparison, while keeping one identical reduced budget
across paired arms. A different workspace root and a foreground versus detached
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
yadof-benchmark check --workspace SMOKE_WORKSPACE
yadof-benchmark plan --workspace SMOKE_WORKSPACE --json
yadof-benchmark run --workspace SMOKE_WORKSPACE
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
5. treat that successful receipt as the handoff boundary for a full-budget measured
   benchmark.

```powershell
yadof-benchmark run --workspace WORKSPACE --detach
```

A full-budget measured benchmark may run for hours. After the detached launch
returns a successful receipt, do not immediately or repeatedly run `inspect`, poll
the process or window, wait on the benchmark, or keep the current agent turn open
solely to observe completion. The agent may continue work that is independent of
the benchmark result. If no such work remains, or every remaining step depends on
the benchmark finishing, report the receipt and end the current turn. This is the
default behavior; do not create a recurring check or otherwise simulate waiting
unless the user explicitly asks for monitoring.

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

The installed package performs the execution directly. The runner does not copy
its own driver, `benchmark.py`, resources, or strategy source as a versioned
code snapshot. A baseline is materialized into each cell only because yadof needs
an isolated execution workspace.

## Budget defaults

- Default seeds: `[101]`.
- Standard optimization-only comparison: population `200`, generations `50`.
- Any comparison containing a strategy declared `slow_surrogate=True`:
  population `200`, generations `15`.
- Explicit `seeds`, `population`, or `generations` override these defaults.

The slow-surrogate default deliberately keeps generations in the 10-20 range.
Population is not reduced automatically because paired strategies must use the
same population and evaluation budget. Use explicit values after inspecting the
plan when a task needs a different tradeoff.

## Failure and validity

`yadof run` is invoked with `--fail-on-all-infinite`. Individual simulation
failures are allowed. A collected cell is valid when:

- attempted evaluations equal the planned evaluation count;
- at least one finite result exists;
- objective and rawData contracts match;
- the complete generation-0 normalized population is available;
- final descriptive hypervolume is available.

Completed and finite counts may be smaller than attempted count. The report
publishes failed and non-finite counts plus
`simulation_errors_tolerated=true`; diagnostic issues remain visible. Missing
attempts, no finite result, broken contracts, missing initial-population evidence,
or missing metric still invalidate the cell.

A command, storage, visualization, collection, or workflow postprocessor failure
is retained in `state.json` and makes the overall status non-successful. Create
a new workspace after correcting the problem.

## Progress, logs, and inspection

Foreground execution owns a Rich active-cell row and a global benchmark row.
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

Review in this order: inspect summary, `reports/summary.md`, the targeted CSV or
descriptive JSON report, then a specific cell command log.
