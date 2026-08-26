# C4 Containers

```mermaid
flowchart LR
    Operator --> CLI[benchmark.py CLI]
    CLI --> Core[benchmark_core.py]
    Config[benchmark.toml] --> Core
    Inputs[baselines + strategies] --> Core
    Core --> Spec[run_spec + matrix + input snapshots]
    Core --> Cells[isolated cell attempts]
    Cells --> Yadof[installed yadof]
    Yadof --> Logs[command logs + workspace evidence]
    Logs --> Progress[Rich live progress]
    Spec --> Inspect[read-only inspect]
    Logs --> Inspect
    State[atomic run_state] --> Inspect
    Inspect --> ETA[bounded status and ETA JSON]
    Cells --> Collect[public API collection]
    Collect --> Report[descriptive report]
```

## CLI

`benchmark.py` parses commands, selects bounded or full output, maps errors to exit
codes, renders the final hypervolume table, and pauses a completed interactive
window. It contains no planning, state, ETA, or reporting algorithm.

## Core runner

`benchmark_core.py` validates TOML, creates plans/specs, preflights dependencies,
snapshots inputs, advances attempts, logs subprocesses, adapts yadof progress,
estimates completion, collects public observations, and builds reports.

## Inputs and generated state

Tracked baseline/strategy/config content is mutable for future runs. Run-local
specs, matrices, snapshots, and attempt artifacts are immutable. `run_state.json`
is the one atomically replaced execution index. Root `metrics.json`, `report.json`,
and `report.md` are latest derived views backed by append-only snapshots.

## Installed yadof boundary

Cells invoke a normal installed distribution and use public collection/viewer
surfaces. The runner does not import repository `src/`, scrape `.yadof` internals,
or patch a measured workspace.
