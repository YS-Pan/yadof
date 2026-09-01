# Architecture

## Boundary

`yadof-benchmark` is a separate distribution and console script. It calls public
installed yadof APIs and commands. The yadof package has no dependency on the
benchmark runner.

The core lifecycle is linear:

```text
packaged preset or explicit blank authoring
    ↓ materialize + hash
benchmark.py + resources + .benchmark/preset.json
    ↓ load + freeze
expanded RunSpec
    ↓ initialize once
runtime.json + spec.json + state.json
    ↓ FIFO cells
cells/cNNNN/{workspace,commands,result.json}
    ↓ publication after each terminal cell
results + reports + visualizations
    ↓ optional workflow postprocessors
final state
```

There is no execution container below the workspace and no recovery branch.

## Components

- `workspace.py` creates and identifies timestamped code-first workspaces.
- `presets.py` validates the packaged catalog, copies only canonical relative
  resources, and records portable SHA-256 provenance.
- `workflow.py` implements the small authoring builder and resolves defaults.
- `planning.py` expands comparisons into deterministic short ordinal cells.
- `baselines.py` discovers task adapters and materializes clean cell workspaces.
- `storage.py` owns direct JSON publication, one-time runtime provenance, state,
  and cell materialization.
- `execution.py` owns subprocess logs, FIFO cell scheduling, collection, and
  publication barriers.
- `results.py` owns public-yadof collection, validity, descriptive pairing,
  reports, and bounded inspection.
- `progress.py` reads active command evidence and estimates timing from the
  current workspace only.
- `postprocessing.py` invokes live workspace callbacks once into
  `postprocessing/<id>/`.
- `launch.py` creates an optional Windows console process for the same installed
  CLI. A visible detached launch is hosted by a persistent PowerShell process so
  the final terminal output remains available after the benchmark command exits;
  hidden launches remain direct noninteractive processes.
- `terminal.py` presents foreground progress and appends `benchmark.log`.

Planning assigns both a safe `cNNNN` storage ID and a display-only identity that
contains the complete baseline ID/name, strategy ID/name, and seed. Duplicate
baseline/strategy/seed identities are rejected across comparisons. Display text
is never used to form a filesystem path.

The retained `RunSpec` name denotes the expanded single-execution plan; it does
not imply a `runs/` storage abstraction.

## Budget resolution

`Benchmark.compare` stores omitted values until the workflow is frozen. Freeze
checks selected strategy declarations and resolves:

- seeds → `(101,)`;
- population → `200`;
- generations → `15` if any selected strategy is slow, otherwise `50`.

An explicit value is never rewritten. If a comparison mixes slow and standard
strategies, every arm receives the same resolved 15-generation default so pairing
budgets remain equal.

Preset budgets are explicit: portable is 2 cells at 12 x 2; complete is 18 cells
at 200 x 25 with a 7200-second baseline timeout. `apply_budget_profile(...,
"smoke")` returns a new frozen request with generations set to one and leaves
population, matrix, identities, digests, execution/failure/concurrency policies,
dependencies, and postprocessors unchanged.

## Progress and timeouts

The runner parses version-matched yadof `evaluation` snapshots and infers a new
generation only when the observed evaluation batch resets. These observations
produce structured `cell-progress` JSONL; periodic `command-progress` records
only elapsed and inactivity time. Windows timeout cleanup enumerates and kills
the full descendant tree with `psutil`, uses recursive `taskkill /T /F` as a
fallback, and waits for the parent; POSIX uses a new process session and signals
the process group. Timeout evidence is terminal for the cell but does not stop
FIFO admission when `fail_fast=False`.

Inspection treats `checked` and `running` cells as active and also keeps a
`succeeded` cell active while its collection commands are still in flight. This
prevents the execution-to-collection boundary from appearing idle.
Planned/active incompleteness is filtered from running-workspace anomalies;
terminal workspaces still expose the full incomplete-cell validity diagnostics.

## Validity

Collection distinguishes planned, attempted, completed, and finite evaluation
counts. Validity requires:

```text
collected
∧ attempted == planned
∧ finite > 0
∧ objective contract matches
∧ rawData contract matches
∧ generation-0 population complete
∧ final hypervolume available
```

It deliberately does not require `completed == attempted` or
`finite == completed`. The differences are published as failed and non-finite
evaluation counts, and valid affected cells carry
`simulation_errors_tolerated=true`. Diagnostics do not by themselves invalidate
a cell.

## Persistence

All mutable lifecycle state is atomically written to `state.json`. Command logs
and cell results are append/new-file evidence. Aggregate publication after each
terminal cell is a fatal boundary: a persistence failure stops further admission
rather than losing which evidence was considered complete.

The runner does not preserve alternate versions of code. `runtime.json` records
the installed versions and execution account once before the scheduler starts.
A per-cell baseline copy is merely the isolated yadof execution workspace.

## Process identity

`--detach` changes Windows console/process lifetime but cannot change the caller
account or session. Its visible console stays open after success or failure until
the user types `exit` or closes it. Documentation therefore makes the host-account
launch requirement an agent responsibility rather than embedding account-switching
machinery in the package.
