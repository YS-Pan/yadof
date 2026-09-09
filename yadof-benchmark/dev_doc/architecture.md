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
    ↓ dependency-ready cells in declaration order
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
- `perfect_oracle.py` owns transient simulator-backed predictions and fatal
  interface-error handling; it never creates recorded yadof evaluations.
- `perfect_program.py`, `perfect_protocol.py`, and `runtime_freeze.py` own the
  opt-in paired top-10 protocol, explicit programs, metric receipts, independent
  real-history verification, final summary and installed-code guard.
- `planning.py` expands comparisons into deterministic short ordinal cells.
- `baselines.py` discovers task adapters and materializes clean cell workspaces.
- `concurrency.py` validates portable physical-core multipliers and resolves them
  from the execution host's physical CPU count.
- `storage.py` owns direct JSON publication, one-time runtime provenance, state,
  and cell materialization.
- `execution.py` owns subprocess logs, dependency-aware cell scheduling, collection, and
  publication barriers.
- `results.py` owns public-yadof collection, validity, descriptive pairing,
  reports, and bounded inspection.
- `progress.py` reads active command evidence and estimates timing from the
  current workspace only.
- `postprocessing.py` invokes live workspace callbacks once into
  `postprocessing/<id>/`. Explicit `run_on_failure` callbacks may consume an
  incomplete terminal matrix; other callbacks are skipped in that case.
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

## Simulator concurrency

Fast/local baseline manifests contain only
`simulation_concurrency.physical_core_multiplier`. Planning freezes that
portable value without detecting the planning host. Cell materialization detects
physical cores with `psutil.cpu_count(logical=False)`, computes
`max(1, floor(physical_cores * multiplier))`, writes that integer to the isolated
yadof config, and records the complete resolution in state and reports. Fixed
worker counts and the former per-baseline resource-autodetection switch are
rejected as unknown manifest fields.

Workflow `cell_concurrency` defaults to four and remains independent. Packaged
workflows also declare four; previously saved specifications retain their recorded
value. The simulator envelope scales with physical cores through the baseline
multiplier, so four cells at multiplier one request four times that core count.
The resolved per-cell value is
an explicit yadof fast/local worker cap; yadof may observe CPU, memory, and disk
capacity for diagnostics but does not clamp the user's value.

The internal executor also accepts a task-owned `capacity_policy` callback for
resource calibration during one formal matrix. The callback sees a detached
snapshot after completion counts change and may choose only the active cell
limit (up to the declared workflow cap) and physical-core multipliers by baseline.
It cannot rewrite seeds, P/B/I, budgets, strategy settings, or simulator modes.
Ready baselines share admission slots while this policy is active. A lower limit
drains existing work; it never resizes or restarts a running cell. Each newly
admitted cell captures one immutable capacity revision and materializes its own
worker count from that revision. The frozen scientific spec is preserved.

State records `capacity_history` and `effective_cell_concurrency`; cell state and
results record `capacity_revision` and resolved simulation concurrency. Policy
source and settings belong in task-owned frozen resources. This internal hook is
for controlled execution research; ordinary workflows continue to use the two
existing configuration knobs. A malformed decision stops admission and uses the
normal cancellation and failed-state path.

## Budget resolution

`Benchmark.compare` stores omitted values until the workflow is frozen. Freeze
checks selected strategy declarations and resolves:

- seeds → `(101,)`;
- population → `200`;
- batch and initial design → the resolved arm population;
- generations → `15` if any selected strategy is slow, otherwise `50`.

An explicit value is never rewritten. If a comparison mixes slow and standard
strategies, every arm receives the same resolved 15-generation default so pairing
budgets remain equal.

Strategy declarations may explicitly override P, B, I and generations. Planning
resolves each arm's I + (G - 1) B budget; pairing remains by comparison/case/seed
and verifies equal planned attempts plus identical actual initial designs. The
smoke profile replaces both comparison and strategy generation counts with one.
Top-10 reference dependencies gate admission through the completed reference's
publication boundary while independent ready cells use the configured concurrency.

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
admission of independent dependency-ready cells when `fail_fast=False`.

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
∧ attempted == planned (or validated first strict top-10 crossing)
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

The task model identifies numerical divergence in Chrono-produced state with
`PyChronoSimulationError`, separate from configuration, API and schema faults.
Oracle and formal workers therefore share per-candidate failure semantics.
Oracle prediction events retain failed normalized candidates without entering
the formal recorder. The perfect summary explicitly accepts failed cells and
cannot change their validity or terminal status.

Perfect screening uses a distinct campaign-owned `FastWorkerPool` through the
same versioned task-session interface and immutable candidate protocol as formal
fast evaluation. Its completion consumer computes current cost from
`StructuredRawDataSample.cost_items()` without a recorder. Compatible interpreter
and native sessions survive prediction calls/generations; each simulation remains
a fresh physical call. Query rows, physical calls, zero cache hits and wall time
are audited separately from formal attempts. Interface faults abort prediction;
only typed physical failure or timeout can become an invalid prediction.

The perfect GPSAF strategy explicitly freezes greedy-HV infill, matching the
framework default while preserving alpha=3, beta=3, gamma=0.5, exploration=0.10
and the existing genetic operators. A paired reference supplies the strict final
cumulative top-ten threshold. Screening never changes that formal budget or metric.

## Persistence

All mutable lifecycle state is atomically written to `state.json`. Command logs
and cell results are append/new-file evidence. Aggregate publication after each
terminal cell is a fatal boundary: a persistence failure stops further admission
rather than losing which evidence was considered complete.

Atomic replacement retries Windows access/sharing/lock violations for at most
two seconds of elapsed retry time. The completed old file remains in place until
replacement succeeds; no delete-before-write fallback is permitted. Other I/O
errors fail immediately. A fatal scheduler exception cancels and joins active
commands, records `execution_error`, and persists terminal failed state when the
storage is writable. If that terminal write also fails, the original failure and
the persistence failure are both reported to the caller.

The runner does not preserve alternate versions of code. `runtime.json` records
the installed versions and execution account once before the scheduler starts.
A per-cell baseline copy is merely the isolated yadof execution workspace.

## Process identity

Every cell command receives a private environment copy with native BLAS/OpenMP,
BLIS, Accelerate and NumExpr thread limits set to one before interpreter import.
The caller's environment is not mutated. This timing matters on Windows: a later
threadpoolctl scope can limit computation after native buffers have already
consumed substantial system commit memory.

`memory_guard.py` reads Windows commit totals through `GetPerformanceInfo`, without
enumerating processes, and polls independently of completion/publication. The
real executor uses a shared `ResourceCancellation` and Windows memory job for
cell command roots and descendants. Initial job commit budget is bounded by 60%
of the host limit and initial available commit less a 20% (minimum 2 GiB) reserve.
Global reserve exhaustion or a memory-specific command failure cancels peers and
aborts the workspace regardless of ordinary fail-fast policy. A physical-memory
reserve also applies on other platforms. The controller is never assigned to
the job; job close cleans only command descendants. Failure to establish the
Windows protection fails before proceeding without a limit. Cancellation on
BaseException happens before executor shutdown waits for its workers.

This guard limits resource use; it does not change scientific budgets or silently
turn infrastructure failures into failed physical simulations. It does not modify
machine page-file settings or impose limits on unrelated applications.

`--detach` changes Windows console/process lifetime but cannot change the caller
account or session. Its visible console stays open after success or failure until
the user types `exit` or closes it. Documentation therefore makes the host-account
launch requirement an agent responsibility rather than embedding account-switching
machinery in the package.
