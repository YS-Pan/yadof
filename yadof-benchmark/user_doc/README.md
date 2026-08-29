# yadof-benchmark user guide

Use this guide for the installed `yadof-benchmark` package. The shortest route is:

1. Read [workspace.md](workspace.md) before creating or editing a workspace.
2. Read [api.md](api.md) while writing `benchmark.py`.
3. Read [baselines.md](baselines.md) to choose packaged baseline IDs or provide a
   separate baseline collection.
4. Read [run_and_recovery.md](run_and_recovery.md) before execution, interruption,
   resume, or evidence review.

Measured `run` and `resume` commands use a visible process window by default,
whether a human or an AI agent starts them. An already visible terminal may run the
command in the foreground; on Windows an agent detaches with `--detach`, which
creates a normal visible console and immediately returns PID/run/log/inspect
details. `--hidden` requires that explicit detach mode and a user request. The
foreground terminal uses two Rich-owned progress rows backed by real child
generation updates; non-interactive API calls remain synchronous and never wait
for input.

The workflow contract is Python-only. `check` and `plan` import and execute the
workspace's `benchmark.py`, so planning code should be deterministic and should not
start simulators, mutate external state, or perform expensive work. Measured work
belongs to strategy execution; visualization and analysis belong to the required
baseline postprocessor and optional workflow-level postprocessors.

Every workflow explicitly declares `evidence="structural"` or
`evidence="performance"`. Structural fake/cheap runs, CLI smoke, and bounded
canaries validate integration only; their plan, inspect, CSV/JSON, and Markdown
outputs carry a structural-only notice and cannot support algorithm performance
conclusions. Performance reports remain descriptive and never announce a winner or
scientific acceptance. Package tests and recovery fault injection are separate
engineering evidence and do not substitute for either a real adapter smoke or an
authorized performance campaign.

Performance comparisons have a hard per-cell floor of 100 individuals per
generation and 20 generations (2000 planned real evaluations). That floor is a
validity guard, not a claim that the task is difficult enough. Before a surrogate
comparison, calibrate the baseline with a complete non-surrogate NSGA-III run so
convergence is nearer roughly 10000 evaluations; a task already solved easily at
2000 needs more difficulty. Single-seed performance work is reported as
exploratory for fast algorithm iteration. Use any explicit multi-seed list needed
for a stronger campaign; three historical seeds are an example, not a constant.

Reports verify same-baseline/same-seed pairing from the frozen task snapshot,
planned/attempted budgets, and complete generation-0 normalized population. They
publish planned/attempted/completed/finite counts plus final HV and an
attempted-evaluation-aligned HV trajectory/AUC. Invalid or incomplete evidence is
preserved and visibly excluded from cross-seed aggregates, never converted into a
performance score. Surrogate-training time is separate from optimizer wall time
and may be contextualized only against an explicitly configured representative
expensive generation.

Both planning commands return bounded summaries by default; request their complete
expanded JSON with `--json`. Child stdout/stderr is kept in separate command logs
during `run` and `resume`; raw streaming is an explicit
`--stream-child-output` diagnostic option. Use the bounded, read-only `inspect`
summary for status, validity, comparison readiness, anomalies, activity, and ETA
before opening larger evidence.

Human-visible workspace, run, and workspace-level output-index names begin with
local `YYYYMMDD_HHMMSS`. Every collected cell owns an automatic cost plot and one
baseline-local domain postprocess result below its run root; the workspace's
top-level report and visualization indexes lead back to that authoritative root.

List and read the version-matched installed documents with:

```powershell
yadof-benchmark docs list
yadof-benchmark docs show api.md
```
