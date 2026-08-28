# C4 Containers

```mermaid
flowchart LR
    Operator --> CLI[benchmark.py CLI]
    CLI --> Facade[benchmark_core.py facade]
    Facade --> Runtime[benchmark_runtime services]
    Config[benchmark.toml] --> Runtime
    Inputs[baselines + strategies + histories] --> Runtime
    Runtime --> Spec[run_spec + matrix + owned execution/input snapshots]
    Runtime --> TimingHistory[bounded prior-run timing snapshot]
    Runtime --> Cells[isolated cell attempts]
    Cells --> Yadof[installed yadof]
    Yadof --> Logs[command logs + timestamped progress events + workspace evidence]
    Logs --> Progress[Rich live progress]
    Spec --> Inspect[read-only inspect]
    TimingHistory --> Inspect
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

`benchmark_core.py` is a compatibility facade. `benchmark_runtime` separates
contracts, storage, planning, state, execution, progress, results, and timing.
New runs copy that complete package and execute/resume from their own copy.

## Inputs and generated state

Tracked baseline/strategy/config content is mutable for future runs. Run-local
specs, matrices, timing-history snapshots, input snapshots, and attempt artifacts
are immutable. `run_state.json`
is the one atomically replaced execution index. Root `metrics.json`, `report.json`,
and `report.md` are latest derived views backed by append-only snapshots.

## Installed yadof boundary

Cells invoke a normal installed distribution and use public collection/viewer
surfaces. The runner does not import repository `src/`, scrape `.yadof` internals,
or patch a measured workspace.
