# yadof-benchmark user guide

Use these version-matched documents for the installed package:

1. Read [workspace.md](workspace.md) to create and structure one workspace.
2. Read [api.md](api.md) while authoring `benchmark.py`.
3. Read [baselines.md](baselines.md) to select or provide task baselines.
4. Read [execution.md](execution.md) before launching or inspecting measured work.
5. For the real-simulation oracle experiment, read [perfect_surrogate.md](perfect_surrogate.md).

The no-argument initializer creates the packaged `portable` preset: two canonical
real-only and PCA/SVD+GPSAF strategies on the synthetic antenna baseline, seed
101, population 12, and two generations. Select the long-running 18-cell
`complete` preset explicitly with `init --preset complete`; it fixes population
200, generations 25, seeds 101/102/103, and a 7200-second cell timeout. Use
`init --blank` only when authoring a workflow from scratch. `presets` lists the
budgets, dependencies, and long-run warning before any workspace is created.

The central contract is one workspace equals one execution. Another execution
uses another workspace. Results are direct children of the workspace; there is no
`runs/`, run ID, resume command, or attempt-number directory.

Custom comparisons use one seed by default. Standard optimization defaults to population
`200` and `50` generations. A comparison containing a strategy declared
`slow_surrogate=True` defaults to `15` generations, keeping repeated neural
network or similarly expensive surrogate training within the intended 10-20
generation range. Explicit budgets and seed lists override defaults.

Individual simulation errors are evidence, not an automatic whole-cell failure.
A cell can remain valid when all planned evaluations were attempted and some
simulations failed or produced non-finite results, provided finite output,
contracts, generation-0 pairing, and the descriptive metric remain available.

Before a measured execution, use the mechanical `--budget-profile smoke` described
under [benchmark smoke test](execution.md#benchmark-smoke-test) in a separate
complete-preset workspace. It keeps population 200 and changes only generations
to one: the cell/arm matrix, baseline and strategy code, task inputs,
postprocessors, and output contracts must remain the same. Smoke output validates
the execution path only and is never measured performance evidence.

For long Windows work launched by an AI agent, [execution.md](execution.md)
requires host execution under the signed-in human user's account. A sandbox-owned
detached process cannot show a console in the user's interactive session.
`--detach` controls console/process lifetime; it does not change the account.
For a full-budget measured benchmark, a successful detached launch receipt proves
only that launch was requested; it does not prove benchmark completion. Unless a
task explicitly requests monitoring, the receipt is the normal handoff boundary.
When monitoring or a heartbeat is explicitly required, the same task retains
ownership and uses bounded `inspect` snapshots at the requested interval until a
terminal result is collected.
The visible detached console remains open after the benchmark finishes so the
terminal result can be reviewed; type `exit` or close the window when finished.

Every workflow explicitly declares `evidence="structural"` or
`evidence="performance"`. Structural output validates integration only.
Performance output is descriptive and single-seed performance is labeled
exploratory.

List or read the installed documents with:

```powershell
yadof-benchmark docs list
yadof-benchmark docs show execution.md
```

For explicitly requested long-run monitoring, use the low-cost, context-free
subagent policy in [execution.md](execution.md#low-cost-monitoring-for-agents): five-minute monitor inspections and hourly main-agent summaries.


`init --preset surrogate-complete` adds amplitude/shape GP and experimental
retrieval response to the complete comparison: three baselines × four strategies
× seeds 101/102/103 = 36 cells, each P200/B200/I200/G25 (5000 formal attempts).
It uses two concurrent cells and the normal 7200-second per-cell timeout. Install
`yadof[gp,retrieval]`. Run its unchanged matrix with `--budget-profile smoke` in a
separate workspace first. These are descriptive standard-budget results, not the
historical P50 median-to-perfect confirmation. `complete` remains 18 cells.
