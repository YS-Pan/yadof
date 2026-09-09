# File blueprint: src/yadof/optimize/pymoo/backend.py

Retain P-sized survivors independently of B offspring and I initial samples.
GA/NSGA-III receive `n_offsprings=B`. The first uninitialized ask temporarily uses
I as pymoo sampling size and restores P in `finally` before any tell. History
replay remains one tell per real generation, preserving P survival. Reduce an
indexed initial batch larger than P immediately after its tell, before replaying
later groups, so discarded initial individuals cannot reappear during recovery.
Legacy unindexed warm-start history retains its established path. Diagnostics
record all resolved sizes; both B < P and B > P are legal.
Use pymoo `NoTermination` for private ask/tell algorithms: yadof's explicit
program owns the budget/stop decision. Backend default convergence or iteration
limits must not finalize long history replay or stop a small-B campaign early.

## Intent
- Isolate optional pymoo imports and adapters used by optimization algorithms.

## Functionalities
- Lazily construct pymoo algorithms, problems, populations, operators, and
  survival helpers.
- Translate between normalized yadof rows and pymoo representations.
- Expose the small adapter surface used by common search and GPSAF phases.
- Replay labeled true generations once each in population order, preserving
  survival normalization and n_gen instead of pooling the whole archive into one
  tell. Seed survival and infill independently by real-generation ordinal.
- Clone candidate Individuals before predicted tells; beta must not mutate source
  pools. Avoid a redundant survival pass after already-replayed generations.
- Perform configured ask attempts and bounded random refill with duplicate/archive
  counters; inability to fill an exact unique request raises the public typed
  insufficient-pool error rather than looping or returning partial success.

## I/O Format
- Accepts normalized bounds, populations, objective rows, core candidate-identity
  policy, and one immutable `PymooSearchSettings` snapshot.
- Returns pymoo-backed search contexts or normalized candidate rows through local
  adapter dataclasses.

## Non-Obvious Techniques
- Keeping this module in a separate private subpackage prevents importing the
  optional pymoo dependency when users import `yadof.optimize`.

## Mutability Profile
- Pymoo-version details stay here; public optimization factories and workspace
  contracts must not expose pymoo objects.
- Algorithms, operators, `Individual`, ask/tell, and survival stay private here;
  `primitives.py` owns only backend-neutral values and calls this adapter lazily.
- Operator, refill, and reference-direction values have no fallback lookup in
  `LoadedConfig`; the selected factory snapshot is authoritative.
