# yadof-benchmark

`yadof-benchmark` is an independent Python package for reproducible,
code-first comparisons of complete yadof optimization strategies. A benchmark
workspace owns one `benchmark.py`; that Python file declares the whole workflow,
including an explicit `structural` or `performance` evidence class, strategies,
comparison matrices, execution policy, and postprocessing. Structural runs are
smoke/canary integration evidence only and must never be presented as algorithm
performance evidence. Performance runs publish descriptive measurements without
ranking strategies or making acceptance decisions.

Every performance cell must plan at least 100 individuals per generation and at
least 20 generations, for a hard minimum of 2000 real evaluations. This minimum
prevents structural-scale runs from being mislabeled; it is not a task-difficulty
target. Calibrate each baseline so a complete non-surrogate NSGA-III reference is
closer to roughly 10000 evaluations (historically 200 × 50) before expecting a
meaningful surrogate comparison. A single-seed performance comparison is carried
through plans and reports as exploratory; stronger campaigns use an explicit,
configurable multi-seed list rather than a package-fixed seed count.

Same-baseline/same-seed arms are paired only when their frozen task snapshot,
planned/attempted real-evaluation budgets, and complete generation-0 normalized
population match. Reports retain raw invalid/incomplete evidence, exclude affected
seeds from aggregates, and publish planned/attempted/completed/finite counts plus
final HV and attempted-evaluation-aligned HV trajectory/AUC. They never turn
failures into a performance score or use optimizer wall time as the main metric.
Structural workflows fail fast by default. Performance workflows default to
continuing independent cells so expensive evidence is retained, but any invalid or
incomplete cell still makes the run non-successful and the CLI exit nonzero.
Aggregate publication is a barrier before the next cell; a storage failure stops
the campaign and is retained in run diagnostics.

```powershell
$workspace = (yadof-benchmark init D:\benchmarks\my-comparison |
  ConvertFrom-Json).workspace
yadof-benchmark baselines
yadof-benchmark check --workspace $workspace
yadof-benchmark run --workspace $workspace
```

Before a long performance campaign, run bounded `check`/`plan`, smoke every
selected real adapter through its yadof workspace, and complete a bounded
`evidence="structural"` canary that uses the same baseline IDs and complete
strategy/configuration paths. These measured steps remain subject to simulator
execution authority; package pytest and recovery fault-injection tests do not
replace them and do not constitute performance evidence.

`check` and `plan` print bounded summaries by default. Add `--json` only when the
complete expanded cell plan is needed. Measured child stdout/stderr always has
separate per-command logs and is not copied to the terminal unless
`--stream-child-output` is explicitly selected.

Each execution attempt has its own `attempt.json`. Interrupted or failed attempts
are sealed incomplete, retain their compact execution workspace and logs, and are
never reused; `resume` creates a new attempt/workspace. A run also verifies its
frozen workflow, resources, baseline, strategy, and driver snapshots before
execution, so editing the reusable sources affects only a later run.

Foreground runs show a Rich active-cell row followed by a global benchmark row.
For an agent-owned long Windows run, add `--detach`: it opens a normal visible
console and immediately returns PID/run/log/inspect details. Hidden execution is
available only as the explicit `--detach --hidden` exception. The receipt repeats
the frozen evidence class and its scope notice.

`inspect --run RUN_PATH` is read-only and bounded. It reports status, validity,
comparison readiness, anomalies, active-cell activity, elapsed time, and an ETA
with exact/compatible matched-history evidence. The suggested review order is the
inspect summary, `reports/summary.md`, selected fields from the bounded descriptive
JSON report, then one cell log or targeted `results.json` fields.

`init` prints the actual `YYYYMMDD_HHMMSS-...` workspace path, and automatic or
explicit run names use the same local timestamp prefix. Each run keeps its complete
reports and grouped cost/domain visualizations under one run root; timestamped
indexes in the workspace's top-level `reports/` and `visualizations/` lead to it.

`benchmark.py` is the only workflow-definition surface. Distribution metadata in
`pyproject.toml` is not a benchmark workflow input. Read the installed
documentation with:

```powershell
yadof-benchmark docs show README.md
yadof-benchmark docs show api.md
```

Maintainers should start at [dev_doc/README.md](dev_doc/README.md). Users should
start at [user_doc/README.md](user_doc/README.md).
