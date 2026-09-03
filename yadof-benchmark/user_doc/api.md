# Python and command-line API


For a sequential paired reference with strict cumulative top-10 stopping, use
`compare(..., reference=..., stop_on_top10_reference=True)` and the strategy
receipt contract in [perfect_surrogate.md](perfect_surrogate.md).
## `Benchmark.configure`

```python
benchmark.configure(
    name=None,
    evidence=None,
    fail_fast=None,
    cell_concurrency=None,
    representative_generation_seconds=None,
    python=None,
)
```

`evidence` is required and must be `"structural"` or `"performance"`.
`python` defaults to the interpreter running yadof-benchmark and should normally
remain unchanged.

## `Benchmark.strategy`

```python
benchmark.strategy(
    "surrogate-nsga3",
    "resources/strategies/surrogate/optimization.py",
    name="Surrogate NSGA-III",
    slow_surrogate=True,
)
```

A strategy source must declare a literal `YADOF_OPTIMIZATION_PROGRAM` using
`yadof.optimize.program/v1`. Every relative `.py` path in its literal `helpers` tuple/list
is part of the strategy. Helpers are resolved below the directory containing the
selected `optimization.py`; absolute paths, parent traversal, symlinks,
duplicates, and undeclared helper files are rejected. `sources={baseline_id:
path}` may select baseline-specific entry modules and their declared helpers.
`slow_surrogate=True` declares repeated expensive model training such as a
neural network. It affects only the default generation count of comparisons that
select the strategy; the strategy remains otherwise opaque to the runner.
The removed `build_optimization()` factory entry is rejected rather than translated.
Here `program/v1` is the exact executable protocol discriminator, not incidental
release prose: the planner accepts that value and rejects lookalike unsupported
values such as `program/v2`.

## `Benchmark.compare`

```python
benchmark.compare(
    "main",
    baselines=["ngspice/saw-ladder"],
    strategies=["nsga3", "surrogate-nsga3"],
    reference="nsga3",
)
```

Optional budget arguments are:

```python
seeds=[101]       # default
population=200    # default
generations=50    # default without a slow surrogate
generations=15    # default when any selected strategy is slow
```

Omitting an argument selects the applicable default. Passing an explicit positive
population or generation count, or an explicit unique integer seed list, always
wins. No evidence-class scale floor is imposed. A performance comparison with one
seed is labeled exploratory; pass multiple seeds for multi-seed descriptive
evidence.

All arms in one comparison use the same population, generations, and seeds so
paired evidence has equal planned and attempted budgets.

## Workflow postprocessors

Register a top-level named function:

```python
def summarize(context: PostprocessContext):
    # Read context.results.
    # Write durable output under context.reports, context.visualizations,
    # or the postprocessor-specific context.output.
    return {"status": "ok"}

benchmark.postprocess("summary", summarize)
```

`postprocess(..., run_on_failure=True)` opts a callback into execution after
failed or incomplete cells. Such a callback must handle missing cell results.
The default is `False`: these callbacks require all cells to be collected and
are marked `skipped` when that condition fails. The option is recorded in the
expanded plan. A successful failure-summary callback never changes a failed
benchmark to a successful one. An interrupted process or a fatal publication
error can prevent postprocessing altogether.

`PostprocessContext` provides:

- `workspace`
- `resources`
- `results`
- `visualizations`
- `reports`
- `temp`
- `output` (directly `postprocessing/<id>/`)

There is no attempt field.

## Public Python functions

- `discover_presets()`
- `init_workspace(path, preset="portable")`
- `load_workspace_preset(path)`
- `discover_baselines(root=None)`
- `load_workflow(workspace)`
- `plan_workspace(workspace, baselines_root=None, budget_profile="declared")`
- `run_workspace(workspace, baselines_root=None, budget_profile="declared", event_sink=None,
  stream_child_output=False)`
- `inspect_workspace(workspace)`
- `user_doc_root()`

`run_workspace` is synchronous and window-neutral. Use the CLI `--detach`
option when a visible independent Windows console is desired. That console remains
open after the command finishes until the user types `exit` or closes it; explicit
`--hidden` detach still exits automatically. The functions above are the complete
current public surface.

## CLI

```text
yadof-benchmark presets
yadof-benchmark init PATH [--preset {portable,complete} | --blank]
yadof-benchmark baselines [--root PATH]
yadof-benchmark check --workspace PATH [--baselines-root PATH]
                      [--budget-profile {declared,smoke}] [--json]
yadof-benchmark plan --workspace PATH [--baselines-root PATH]
                     [--budget-profile {declared,smoke}] [--json]
yadof-benchmark run --workspace PATH [--baselines-root PATH]
                    [--budget-profile {declared,smoke}]
                    [--detach] [--hidden] [--stream-child-output]
yadof-benchmark inspect --workspace PATH
yadof-benchmark docs list
yadof-benchmark docs show [PATH]
```

`--hidden` requires `--detach`. An AI-agent launch must also follow the host
account rule in [execution.md](execution.md).

There is no separate `canary` or `smoke-test` command. A benchmark smoke test uses
the normal commands on a fresh complete-preset workspace with
`--budget-profile smoke`; see
[Benchmark smoke test](execution.md#benchmark-smoke-test). This is distinct from
the core `yadof smoke-test` command, which evaluates one midpoint task individual
and does not validate a complete benchmark comparison.
