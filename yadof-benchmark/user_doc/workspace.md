# Benchmark workspace

## Create

```powershell
$workspace = (yadof-benchmark init D:\benchmarks\comparison |
  ConvertFrom-Json).workspace
```

`init` creates a timestamped directory and returns its actual absolute path.
That directory is both the authoring workspace and the root of its one execution.

## Layout

Before execution:

```text
WORKSPACE/
├── .benchmark/workspace.json
├── benchmark.py
├── resources/
├── cells/
├── postprocessing/
├── reports/
├── visualizations/
└── temp/
```

During execution, the same root gains `runtime.json`, `spec.json`,
`state.json`, `results.json`, `results.csv`, and `benchmark.log`.
Cells use short ordinal directories:

```text
cells/
├── c0001/
│   ├── baseline.json
│   ├── workspace/
│   ├── commands/
│   └── result.json
└── c0002/
```

Comparison, baseline, strategy, and seed semantics live in `spec.json` and
reports rather than directory or artifact names. This keeps Windows paths short.

There is intentionally no `runs/` or `attempts/0001` layer. To run another
benchmark, initialize a new workspace and place the desired `benchmark.py` and
resources there. The current package does not read an older multi-run workspace
format.

## Smoke workspace

A benchmark smoke test is also one complete execution, so it must use its own
fresh workspace. Start from the same authoring inputs as the measured benchmark
and change only the explicit positive evaluation budget. Keep the same
`benchmark.py` registrations and implementation, selected baselines, strategy
entry modules and declared helpers, task workspaces, configuration,
postprocessors, dependencies, and
failure/concurrency policy. The smoke workspace may have a different root and
generated outputs; those are execution locations, not benchmark behavior.

Do not create a smoke-only strategy, mock or synthetic baseline, reduced cell or
arm matrix, alternate task code, or smoke-only postprocessor. If the complete
postprocessing path needs more than the first trial budget to produce valid
output, increase the budget to the smallest positive value that exercises that
path; do not bypass or replace the postprocessor.

## Authoring boundary

`benchmark.py` is the only workflow-definition program. Put complete legacy
`optimization.py` strategies, or explicit program entry modules and every helper
they declare, under `resources/`. The program should only register
configuration, strategies, comparisons, and optional postprocessors.

`check` and `plan` import the file, so imports and
`build_benchmark(benchmark)` must be deterministic and cheap. They must not
start simulators, train models, mutate external systems, or create results.

The runner uses the installed package at execution time. It does not make a
versioned copy of `benchmark.py`, resources, strategies, or its own driver.
`runtime.json` records installed versions once before measured work. Per-cell
baseline materialization is an execution input copy required for isolated yadof
workspaces, not a resume/version snapshot.

## Evidence and concurrency

Every workflow must call:

```python
benchmark.configure(
    name="my-comparison",
    evidence="structural",  # or "performance"
    cell_concurrency=1,
)
```

Cell concurrency is a FIFO limit and defaults to one. Baseline simulation-worker
concurrency is a separate task-adapter setting. Increase either only after
reviewing simulator licenses, CPU, memory, and storage.

Structural workflows fail fast by default; performance workflows continue
independent cells by default so completed expensive evidence is retained.
Explicit `fail_fast` overrides this policy. Any invalid or incomplete cell still
makes final execution status non-successful.
