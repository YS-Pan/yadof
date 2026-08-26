# Module Blueprint: Runner Core

## Intent

Own deterministic benchmark orchestration and stable transformations while making
filesystem/state behavior directly testable without a simulator.

## Responsibilities

- Configuration/path/schema validation and canonical fingerprints.
- Plan, preflight, spec/matrix creation, baseline snapshots, and state publication.
- Attempt materialization, subprocess logging, timeout/failure translation,
  progress rendering, postprocessing, visualization, sealing, and resume.
- Read-only timing estimation over immutable plans, completed wall time, and the
  active command's bounded log tail.
- Public-yadof collection, structural checks, performance pairing, reports, and
  bounded summaries.

## I/O

Functions consume mappings and explicit `Paths`; durable writes use new-file or
atomic-replace helpers according to ownership. Child commands are argument lists.
Public dictionaries remain JSON-safe: finite numbers, strings, booleans, null,
lists, and string-keyed objects.

## Non-obvious techniques

- One common parser recognizes plain piped yadof progress snapshots.
- Pipe-drain threads never render. They enqueue parsed/display events for the
  foreground subprocess wait loop, which regularly services the queue and owns
  every Rich refresh.
- Build Rich with a console-local environment that omits `TERM=dumb`/`unknown`
  only when the destination stream has already returned true from `isatty()`.
- Cumulative progress is generation index times local total plus local completion.
- ASCII bars use ceiling fill for positive ratios; small cumulative percentages
  retain a decimal.
- ETA cohort order is same case/arm, same case, same arm, all completed, declared
  lower bound, then plan-average lower bound. Sequential execution makes remaining
  time additive. Confidence and basis are output with the value.
- Read-only inspection tolerates a race between started and finished metadata and
  never requires recursive run scanning.

## Failure behavior

Invalid inputs raise `BenchmarkError`. Command failures seal attempts. ETA parsing
failure lowers availability/confidence but cannot mutate or fail the run. Collection
keeps invalid/incomplete evidence visible.

## Mutability

Scientific matrices and report fields may grow. Immutable identity, append-only
attempt evidence, public-yadof-only collection, bounded summaries, and descriptive-
only interpretation remain stable.
