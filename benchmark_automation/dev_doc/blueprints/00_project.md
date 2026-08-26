# Blueprint: Benchmark Automation

## Intent

Provide a reproducible, resumable, agent-readable comparison harness for several
real yadof tasks and complete optimization strategies without moving experiment
logic into the installed package. Preserve raw evidence and validity while keeping
default output small enough for repeated agent decisions.

## Functional contract

1. Expand configuration into a deterministic no-write plan.
2. Preflight exact external and installed-package prerequisites without simulation.
3. Snapshot mutable declared inputs and publish immutable run identity.
4. Execute isolated case/arm/seed cells sequentially with resumable attempts.
5. Preserve subprocess output, show coherent live cell/global progress, and expose
   read-only status/ETA after the launching turn ends.
6. Collect only through public yadof observations.
7. Produce structural validity or paired descriptive performance evidence without
   ranking algorithms.

## I/O

Inputs are TOML configuration, semantic baseline directories, strategy templates,
optional history snapshots, selectors, installed package identity, and resource
facts. Durable output is the documented run tree. Default CLI output is bounded
JSON plus narrowly scoped stderr rendering; full evidence stays on disk.

## Non-obvious techniques

- Mutable templates become immutable run-local snapshots.
- Resume validates frozen identity and replaces interrupted attempts.
- Rich owns cursor movement on the foreground runner thread; pipe-drain threads
  only log and enqueue events. One parser feeds both live rendering and ETA log-
  tail interpretation.
- ETA uses hierarchical wall-time cohorts plus live cumulative progress, reports
  confidence/basis, and never becomes a deadline or evidence field.
- Performance pairing validates equal budgets and initial populations before
  calculating descriptive differences.

## Mutability

Cases, arms, suites, estimates, and baselines are expected to evolve for new runs.
Run artifacts, identity, attempted evidence, and prior reports never mutate. Public
summary shapes and semantics change deliberately with tests/docs.
