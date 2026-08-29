# Workflow API

Every workspace `benchmark.py` defines one function:

```python
from yadof_benchmark import Benchmark, PostprocessContext


def create_plots(context: PostprocessContext) -> dict[str, str]:
    output = context.visualizations / "comparison.txt"
    output.write_text("created from results.json", encoding="utf-8")
    return {"output": output.name}


def build_benchmark(benchmark: Benchmark) -> None:
    benchmark.configure(
        name="antenna-comparison",
        evidence="structural",
        fail_fast=False,
    )
    benchmark.strategy(
        "nsga3",
        "resources/strategies/nsga3/optimization.py",
        name="NSGA-III",
    )
    benchmark.strategy(
        "gpsaf-conditional-inr",
        name="GPSAF + conditional INR",
        sources={
            "test-com/synthetic-antenna":
                "resources/strategies/gpsaf/antenna/optimization.py",
            "ngspice/saw-ladder":
                "resources/strategies/gpsaf/circuit/optimization.py",
        },
    )
    benchmark.compare(
        "main",
        baselines=["test-com/synthetic-antenna", "ngspice/saw-ladder"],
        strategies=["nsga3", "gpsaf-conditional-inr"],
        seeds=[101, 102, 103],
        population=12,
        generations=20,
        reference="nsga3",
    )
    benchmark.postprocess("plots", create_plots)
```

## `Benchmark.configure()`

`configure(name=None, evidence=None, fail_fast=None, runs_dir=None, python=None)`
sets run-level policy. `evidence` is mandatory before the workflow can freeze and
accepts only `"structural"` or `"performance"`. Structural means integration-only
smoke/canary evidence and forbids algorithm performance conclusions. Performance
means descriptive performance evidence; it still does not authorize execution or
permit the package to rank strategies or make acceptance decisions. Relative paths
resolve from the workspace. Other defaults are the workspace name,
continue-on-cell-failure, `runs/`, and the current Python interpreter.

## `Benchmark.strategy()`

`strategy(id, source=None, *, name=None, sources=None)` registers an opaque,
complete `optimization.py`. `source` applies to every baseline. `sources` maps
individual baseline IDs to different complete modules and overrides `source`.
Every selected module must define `build_optimization()`; the benchmark package
does not maintain an algorithm registry or interpret algorithm-specific settings.
Choose an ID and display name that state the actual algorithm composition, such as
`nsga3` or `gpsaf-conditional-inr`. Role-only names such as `reference`,
`candidate`, or `real-search` hide what was executed and are not valid authoring
practice. `reference=` below expresses the comparison role separately.

## `Benchmark.compare()`

`compare(id, *, baselines, strategies, seeds, population, generations,
reference=None)` declares one Cartesian comparison matrix. Call it more than once
to express different baselines, strategy subsets, seeds, or budgets. IDs are stable
evidence identifiers. A reference is optional and must be selected by that
comparison.

## `Benchmark.postprocess()`

`postprocess(id, callback)` registers a named top-level function from the same
`benchmark.py`. It runs after all cells are collected and the descriptive result
set has been published. The callback receives a
`PostprocessContext` with `run`, `inputs`, `results`, `visualizations`, `reports`,
`temp`, and the current `attempt` directory. It may return any JSON-compatible
summary. A failed callback is retried in a new attempt during `resume`; collected
cells are not rerun.

This workflow-level callback is separate from the required baseline-local
`postprocess.py`. The runtime invokes the baseline script after each optimization,
alongside the automatic cost-history plot, before that cell is accepted as
collected.

## Other public functions

- `init_workspace(path)` creates the timestamp-prefixed workspace skeleton and
  returns its resolved path.
- `discover_baselines(root=None)` returns validated baseline manifests.
- `load_workflow(workspace)` executes and freezes `benchmark.py`.
- `plan_workspace(workspace, baselines_root=None)` returns the complete immutable
  `RunSpec`; only the CLI presentation defaults to a bounded summary.
- `run_workspace(...)` and `resume_run(...)` accept
  `stream_child_output=False`. When it is explicitly true, raw child lines are
  delivered as `child-output` events to the caller's `event_sink`; per-command
  stdout/stderr logs are written in either mode.
- `inspect_run(...)` returns a bounded, read-only summary with status, validity,
  comparison readiness, anomalies, next commands, active-cell activity, and
  matched-history ETA evidence.
- `user_doc_root()` locates this installed documentation.

All public imports are available from `yadof_benchmark`; `yadof_benchmark.api`
provides the same explicit surface.

Python `run_workspace()` and `resume_run()` are synchronous and window-neutral.
They never launch a console or wait for input. A caller may pass `event_sink=` to
receive lifecycle and real intermediate cell-progress mappings on the caller's
foreground thread. The Rich terminal and visible-by-default Windows `--detach`
launcher belong to the CLI boundary, not the public Python API.
