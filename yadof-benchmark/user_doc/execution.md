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
4. return the receipt containing PID, workspace, log, and inspect command.

```powershell
yadof-benchmark run --workspace WORKSPACE --detach
```

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
