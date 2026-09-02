# Benchmark workspace

## Create

```powershell
$workspace = (yadof-benchmark init .\benchmarks\comparison |
  ConvertFrom-Json).workspace
```

This selects the runnable `portable` preset. Other explicit choices are:

```powershell
yadof-benchmark presets
yadof-benchmark init .\benchmarks\complete --preset complete
yadof-benchmark init .\benchmarks\authoring --blank
```

`init` creates a timestamped directory, materializes wheel-contained workflow and
strategy resources, records their SHA-256 provenance, and returns its actual path.
That directory is both the authoring workspace and the root of its one execution.

## Layout

Before execution:

```text
WORKSPACE/
├── .benchmark/
│   ├── workspace.json
│   └── preset.json
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

Each cell keeps a short `cNNNN` directory, while its full baseline, strategy, and
seed `display_label` is carried by `spec.json`, `state.json`, terminal events,
inspect output, errors, results, and reports. This keeps Windows paths short
without hiding semantic identity.

There is intentionally no `runs/` or `attempts/0001` layer. To run another
benchmark, initialize a new workspace and place the desired `benchmark.py` and
resources there. The current package does not read an older multi-run workspace
format.

## Smoke workspace

A benchmark smoke test is also one complete execution, so it must use its own
fresh `complete` preset workspace. Select `--budget-profile smoke` for check,
plan, and run. This mechanical profile retains population 200 and changes only
generations from 25 to 1. Keep the same
`benchmark.py` registrations and implementation, selected baselines, strategy
entry modules and declared helpers, task workspaces, configuration,
postprocessors, dependencies, and
failure/concurrency policy. The smoke workspace may have a different root and
generated outputs; those are execution locations, not benchmark behavior.

Do not edit `benchmark.py` to create a smoke budget, create a smoke-only strategy,
mock or synthetic baseline, reduced cell or
arm matrix, alternate task code, or smoke-only postprocessor. If the complete
postprocessing path needs more than the first trial budget to produce valid
output, increase the budget to the smallest positive value that exercises that
path; do not bypass or replace the postprocessor.

## Authoring boundary

`benchmark.py` is the only workflow-definition program. Put explicit
`optimization.py` program entry modules and every helper they declare under
`resources/`. The program should only register
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
concurrency is a separate task-adapter multiplier of the runtime host's physical
core count. The plan retains the multiplier while cell state records its resolved
worker count. Increase either only after reviewing simulator licenses, CPU,
memory, and storage; yadof does not reduce an explicitly resolved worker cap.

Structural workflows fail fast by default; performance workflows continue
independent cells by default so completed expensive evidence is retained.
Explicit `fail_fast` overrides this policy. Any invalid or incomplete cell still
makes final execution status non-successful.
