# Workflow API

Every workspace `benchmark.py` defines one function:

```python
from yadof_benchmark import Benchmark, PostprocessContext


def create_plots(context: PostprocessContext) -> dict[str, str]:
    output = context.visualizations / "comparison.txt"
    output.write_text("created from results.json", encoding="utf-8")
    return {"output": output.name}


def build_benchmark(benchmark: Benchmark) -> None:
    benchmark.configure(name="antenna-comparison", fail_fast=False)
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

`configure(name=None, fail_fast=None, runs_dir=None, python=None)` sets run-level
policy. Relative paths resolve from the workspace. Defaults are the workspace name,
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
`benchmark.py`. It runs after every cell is collected. The callback receives a
`PostprocessContext` with `run`, `inputs`, `results`, `visualizations`, `reports`,
`temp`, and the current `attempt` directory. It may return any JSON-compatible
summary. A failed callback is retried in a new attempt during `resume`; collected
cells are not rerun.

## Other public functions

- `init_workspace(path)` creates the workspace skeleton.
- `discover_baselines(root=None)` returns validated baseline manifests.
- `load_workflow(workspace)` executes and freezes `benchmark.py`.
- `plan_workspace(workspace, baselines_root=None)` returns an immutable `RunSpec`.
- `run_workspace(...)`, `resume_run(...)`, and `inspect_run(...)` provide the CLI
  behavior to Python callers.
- `user_doc_root()` locates this installed documentation.

All public imports are available from `yadof_benchmark`; `yadof_benchmark.api`
provides the same explicit surface.
