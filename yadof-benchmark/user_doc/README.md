# yadof-benchmark user guide

Use these version-matched documents for the installed package:

1. Read [workspace.md](workspace.md) to create and structure one workspace.
2. Read [api.md](api.md) while authoring `benchmark.py`.
3. Read [baselines.md](baselines.md) to select or provide task baselines.
4. Read [execution.md](execution.md) before launching or inspecting measured work.

The central contract is one workspace equals one execution. Another execution
uses another workspace. Results are direct children of the workspace; there is no
`runs/`, run ID, resume command, or attempt-number directory.

Comparisons use one seed by default. Standard optimization defaults to population
`200` and `50` generations. A comparison containing a strategy declared
`slow_surrogate=True` defaults to `15` generations, keeping repeated neural
network or similarly expensive surrogate training within the intended 10-20
generation range. Explicit budgets and seed lists override defaults.

Individual simulation errors are evidence, not an automatic whole-cell failure.
A cell can remain valid when all planned evaluations were attempted and some
simulations failed or produced non-finite results, provided finite output,
contracts, generation-0 pairing, and the descriptive metric remain available.

Before a measured execution, use a [benchmark smoke test](execution.md#benchmark-smoke-test)
in a separate workspace. It is the same benchmark with only a smaller explicit
evaluation budget: the cell/arm matrix, baseline and strategy code, task inputs,
postprocessors, and output contracts must remain the same. Smoke output validates
the execution path only and is never measured performance evidence.

For long Windows work launched by an AI agent, [execution.md](execution.md)
requires host execution under the signed-in human user's account. A sandbox-owned
detached process cannot show a console in the user's interactive session.
`--detach` controls console/process lifetime; it does not change the account.
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
