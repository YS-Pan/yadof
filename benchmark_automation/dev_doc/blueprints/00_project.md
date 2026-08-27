# Blueprint: Benchmark Automation

## Intent

Provide a reproducible, resumable, agent-readable comparison harness for several
real yadof tasks and complete optimization strategies without moving experiment
logic into the installed package. Preserve raw evidence and validity while keeping
default output small enough for repeated agent decisions.

## Functional contract

1. Expand configuration into a deterministic no-write plan.
2. Preserve optional versioned preregistrations that can freeze schemas, legal
   provenance, splits, metrics, comparisons, seeds, resources, threshold-sealing
   rules, and stop conditions without pretending to be suites or results.
3. Preflight exact external and installed-package prerequisites without simulation.
4. Snapshot mutable declared inputs and publish immutable run identity.
5. Execute isolated case/arm/seed cells sequentially with resumable attempts.
6. Preserve subprocess output, show coherent live cell/global progress, and expose
   read-only status/ETA after the launching turn ends.
7. Collect only through public yadof observations.
8. Produce structural validity or paired descriptive performance evidence without
   ranking algorithms.

## I/O

Inputs are TOML configuration, semantic baseline directories, strategy templates,
optional history snapshots, optional tracked preregistration contracts, selectors,
installed package identity, and resource facts. A preregistration is inert until a
runner/config change explicitly consumes a later sealed input. Durable output is
the documented run tree. Default CLI output is bounded JSON plus narrowly scoped
stderr rendering; full evidence stays on disk.

## Non-obvious techniques

- Mutable templates become immutable run-local snapshots.
- New runs shallow-scan a bounded set of earlier immediate run directories and
  freeze completed matched-cell durations into an immutable operational timing
  snapshot; later inspection never rescans the runs root.
- Resume validates frozen identity and replaces interrupted attempts.
- Rich owns cursor movement on the foreground runner thread; pipe-drain threads
  only log and enqueue events. The foreground loop appends timestamped lifecycle
  and parsed progress events while the same parser feeds live rendering and ETA
  phase interpretation. A verified interactive stream overrides an inherited
  Rich-only `TERM=dumb`/`unknown` classification without changing global or child
  environments.
- ETA excludes cross-arm same-case point estimates, prefers exact/compatible
  matched-cell medians, uses current same-arm evidence only as a later fallback,
  and can raise active time with a robust non-decreasing generation-duration trend.
  It reports basis/sample/dispersion confidence and never becomes a deadline or
  evidence field.
- Performance pairing validates equal budgets and initial populations before
  calculating descriptive differences.

## Mutability

Cases, arms, suites, estimates, and baselines are expected to evolve for new runs.
Run artifacts, identity, attempted evidence, and prior reports never mutate. Public
summary shapes and semantics change deliberately with tests/docs.
