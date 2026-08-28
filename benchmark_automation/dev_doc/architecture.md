# Benchmark architecture

## System boundary

The benchmark compares complete yadof optimization strategies on self-describing
task baselines. Installed yadof owns optimization, evaluation, recording, and
single-workspace interpretation. The benchmark owns only cross-cell planning,
input isolation, execution sequencing, public result collection, and descriptive
alignment.

```text
external StudyRequest
  + discovered BaselineManifest objects
  + complete optimization.py sources
       ↓
deterministic RunSpec
       ↓
run-local driver and input snapshots
       ↓
materialized cell → yadof check → yadof run
       ↓
public yadof rows and metadata
       ↓
generic results, CSV, and report
```

## Responsibilities

- `benchmark.py` parses the five commands and renders JSON or progress events.
- `benchmark_core.py` explicitly exposes baseline discovery, study loading,
  planning, running, recovery, and inspection.
- `contracts.py` owns immutable public models and format identities.
- `baselines.py` recursively discovers manifests and copies clean workspaces.
- `planning.py` validates external TOML and expands a deterministic matrix.
- `storage.py` owns provenance digests, atomic JSON/text, driver/input snapshots,
  run state, and immutable attempts.
- `execution.py` checks resources, runs child commands, seals attempts, collects
  results, and resumes from run-owned inputs.
- `progress.py` calculates read-only elapsed and inactivity values; execution emits
  small lifecycle records through the caller-provided event sink.
- `results.py` uses public yadof APIs, preserves opaque optimization metadata,
  builds long rows, calculates optional reference deltas, and renders current
  artifacts.

Runtime modules import public sibling names only. The CLI delegates behavior to
the public core.

## Inputs

A baseline directory contains `baseline.json` and one workspace. The manifest is
the only baseline declaration. A clean snapshot includes every workspace input
except standard generated state, caches, and explicit task-neutral exclusions.

A study lives outside the benchmark directory. It selects baseline IDs, one or more
complete strategy sources, seeds, a uniform population and generation count, an
optional reference strategy, failure policy, Python interpreter, and output root.
Relative study paths resolve from the study file.

The planner never imports a strategy. It parses the source, verifies that
`build_optimization()` is defined, records a digest, and otherwise treats the
file as opaque.

## State and recovery

Cells move through:

```text
planned → checked → running → succeeded → collected
                       ↘ failed
```

Every attempt has its own workspace and command directory. An interrupted checked
or running attempt is marked interrupted and a later recovery creates a new
attempt. A succeeded cell retries collection without repeating measured execution.
A collected cell is never executed again.

`spec.json` is immutable. `state.json` is the only atomically replaced
operational index. Command metadata, logs, cell results, and attempts are
append-only. Latest aggregate result files are reproducible views and may be
atomically regenerated.

A run stores a complete `driver/` copy. Recovery dynamically imports
`driver/benchmark_runtime` and consumes only run-local `spec.json`,
`state.json`, baseline snapshots, strategy snapshots, attempts, and results.
Current checkout files locate and start the run but do not define its behavior.

## Result contract

Each public cost row is stored with baseline, strategy, seed, budget, job,
optimization generation, objective mapping, and public provenance metadata.
Per-cell summaries retain status counts, success rate, objective/rawData contract
checks, final cumulative hypervolume when available, issues, and opaque public
optimization metadata.

Comparison groups require identical baseline, seed, population, and generation
count. Any declared reference contributes a simple paired final-hypervolume
difference. No reference is required. The report does not rank strategies or
perform scientific inference.

## Safety invariants

- No child command uses a shell string.
- A resource declaration checks only baseline-owned external prerequisites.
- The exact final workspace is passed to `yadof check`.
- Snapshot paths are run-relative and remain usable after moving the run.
- Source digests are provenance and do not compare against current files on
  recovery.
- Inspection reads state and bounded command timestamps without writing or waiting.
- The benchmark never reads yadof private state or changes algorithm configuration.
