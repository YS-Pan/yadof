# Module Blueprint: Runner Core

## Intent

Own deterministic benchmark orchestration and stable transformations while making
filesystem/state behavior directly testable without a simulator.

## Responsibilities

- `contracts` owns errors, paths, constants, and JSON-compatible contract types.
- `storage` owns confinement, JSON writes, manifests, and provenance digests.
- `planning` owns validation, plan/preflight, and run-spec construction.
- `state` owns run/attempt state and execution/baseline/strategy/history snapshots.
- `execution` and `progress` own subprocess/cell lifecycle and stream visibility.
- `results` owns collection/reports; `timing` owns bounded histories and ETA.
- Attempt materialization, subprocess logging, timeout/failure translation,
  progress rendering, postprocessing, visualization, sealing, and resume.
- Per-arm single templates or complete per-case template mappings. Materialization
  copies the sealed case selection into `submit/optimization.py`; component settings
  never travel through managed config overrides.
- Bounded prior-run timing snapshot creation plus read-only estimation over the
  immutable plan, matched/current completed wall time, and the active command's
  bounded progress-event tail.
- Public-yadof collection, structural checks, performance pairing, reports, and
  bounded summaries.
- `experiment_runtime.linear_subspace` independently plans, preflights, and—only
  with explicit authority—measures four offline recorded-data arms;
  `pca_svd_validation.py` is its thin CLI adapter. Neither materializes a simulator
  workspace nor feeds oracle rows into the formal optimizer runner.

## I/O

Functions consume mappings and explicit `Paths`; durable writes use new-file or
atomic-replace helpers according to ownership. Child commands are argument lists.
Public dictionaries remain JSON-safe: finite numbers, strings, booleans, null,
lists, and string-keyed objects.

Existing runs execute the complete runtime copy they own. Hashes identify
provenance only; unfinished runs without a snapshot require explicit migration or
restart, while completed legacy evidence remains readable.

## Non-obvious techniques

- One common parser recognizes plain piped yadof progress snapshots.
- Pipe-drain threads never render. They enqueue parsed/display events for the
  foreground subprocess wait loop, which regularly services the queue and owns
  every Rich refresh and append to `progress.jsonl`.
- Build Rich with a console-local environment that omits `TERM=dumb`/`unknown`
  only when the destination stream has already returned true from `isatty()`.
- Cumulative progress is generation index times local total plus local completion.
- ASCII bars use ceiling fill for positive ratios; small cumulative percentages
  retain a decimal.
- ETA cohort order is exact prior matched cell, current same case/arm, compatible
  prior matched cell, current same arm, declared lower bound, then plan-average
  lower bound. Cross-arm same-case and all-arm pooling are forbidden as point
  estimates. Three completed generation intervals enable a robust non-negative
  timing trend; linear cumulative progress is only the earlier fallback.
  Sequential execution makes remaining time additive. Confidence, basis, sample
  count, and relative MAD are output with the value.
- Read-only inspection tolerates a race between started and finished metadata and
  never requires run-root scanning; only new-run creation shallow-scans a bounded
  number of immediate prior directories.

## Failure behavior

Invalid inputs raise `BenchmarkError`. Command failures seal attempts. ETA parsing
failure lowers availability/confidence but cannot mutate or fail the run. Collection
keeps invalid/incomplete evidence visible.

Input before/after fingerprints are diagnostic fields and cannot turn a successful
attempt into failure.

## Mutability

Scientific matrices and report fields may grow. Immutable identity, append-only
attempt evidence, public-yadof-only collection, bounded summaries, and descriptive-
only interpretation remain stable.
