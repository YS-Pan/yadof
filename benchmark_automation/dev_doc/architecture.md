# Architecture

This page is the current maintainer view of `benchmark_automation`. It describes
the runner as implemented; planned work belongs in an issue or an explicitly
named planning document rather than here.

## Purpose and boundary

The project compares frozen yadof tasks and optimization strategies through
isolated, identity-stable cells. It owns experiment assembly, cross-case/arm/seed
alignment, validity handling, and descriptive reporting. It does not own yadof's
optimizer, task execution lifecycle, recorded-data API, or single-workspace viewer
logic. It is a source-checkout tool below the yadof repository root, not an
installed `src/yadof` module or runtime resource.

The benchmark has two evidence modes:

- structural suites check that the declared task, strategy, checkpoint, and public
  inspection paths work together;
- performance suites retain raw paired observations and descriptive differences
  without ranking algorithms or performing significance tests.

## Data flow

```text
benchmark.toml + frozen baselines + strategy templates
                         |
                         v
                  plan / preflight
                         |
                         v
       immutable run_spec.json and matrix.json
                         |
                         v
       isolated cell attempt workspaces and logs
                         |
                         v
          public yadof collection surfaces
                         |
                         v
          append-only evidence and reports
                         |
                         v
       bounded CLI/inspect summary (default view)
```

`benchmark.py` parses CLI arguments and maps failures to process exit codes.
`benchmark_core.py` owns configuration validation, fingerprints, planning,
preflight, run state, attempt materialization/execution, collection, and reporting.
Keeping the CLI thin makes core behavior directly testable.

## File and directory roles

| Path | Role |
|---|---|
| `benchmark.py` | Thin command-line entry point. |
| `benchmark_core.py` | Runner implementation and stable data transformations. |
| `AGENTS.md` | Token-bounded reading route and execution guidance for coding agents. |
| `benchmark.toml` | Declared cases, arms, suites, seeds, budgets, paths, and resource requirements. |
| `strategy_templates/` | Complete arm-specific `submit/optimization.py` replacements. |
| `baselines/` | Immutable task inputs plus provenance selected by exact identity. |
| `history_snapshots/` | Optional immutable warm-start inputs; currently no snapshot is selected. |
| `tests/` | Unit coverage for validation, identity, state, I/O, and materialization contracts. |
| configured runs directory | Generated immutable specs/attempts/evidence plus atomically updated latest state; default `runs/`, Git-ignored. |
| `.staging/`, `.assembled/` | Local baseline construction evidence; Git-ignored and never runner inputs. |
| `verification/`, `tool_gaps/` | Human-readable historical verification and reusable-yadof issue records. |

## Core invariants

### Inputs and identity

- Every selected baseline, strategy, configuration, package installation, and
  runner module is fingerprinted before execution.
- Immutable input paths remain contained below the benchmark root. Mutable run
  output may use an explicit external root; relative CLI overrides resolve from the
  invocation directory, and suggested follow-up commands preserve the resolved
  root.
- A baseline ID and its contents are immutable. Refreshing creates a new directory.
- Each case/arm/seed cell receives its own initialized workspace, state, logs, and
  checkpoint namespace; measured cells never share a smoke workspace.
- Performance arms for a paired case use equal planned attempted-real-evaluation
  budgets.

### Execution and recovery

- `plan` writes nothing. `preflight` may validate materialized inputs but never
  launches a simulator workflow.
- A run specification and expanded matrix are immutable after creation.
- Resume skips completed cells and refuses input drift. An interrupted in-generation
  workspace is sealed; retry uses a linked replacement attempt rather than
  mutating the failed attempt.
- Commands execute sequentially by default to avoid contention for external
  simulators, CUDA, disk, and shared host resources.
- Child stdout/stderr is always preserved in command logs. It is not forwarded to
  the terminal unless `--stream-output` is explicitly selected.
- The Python environment check verifies a matching installed distribution and its
  fingerprintable `RECORD`; it does not depend on a virtual-environment directory
  name.

### Evidence and interpretation

- Collection reads public yadof APIs and tools only; it does not scrape private
  `.yadof` internals.
- Attempt records, command logs, collection snapshots, and report snapshots are
  append-only. Only explicitly documented latest-state/root report files are
  atomically replaced.
- Incomplete or invalid pairs remain visible and are excluded explicitly rather
  than silently removed.
- Reports are descriptive. Operational failures and durations are validity or
  diagnostic facts, not algorithm-performance conclusions.
- Default CLI summaries omit expanded commands, fingerprints, raw rows, and full
  diagnostics. Full plan/preflight/report JSON remains explicitly available, and
  `inspect` points from bounded evidence to progressively deeper artifacts.

## Change map

- CLI changes: update `benchmark.py`, CLI-focused tests, and command examples in
  the root README.
- Schema, validation, planning, execution, or reporting changes: update
  `benchmark_core.py`, `benchmark.toml` when applicable, focused tests, and the
  affected invariant above.
- New case: add a new immutable baseline, provenance, TOML declaration, expected
  objective/rawData contracts, and the smallest structural validation evidence.
- New arm: add a complete strategy template, TOML declaration, equal-budget
  coverage, and structural validation.
- New public output field: define its stable JSON meaning, validity behavior, and
  derivation; decide which disclosure layer owns it, then update tests, agent
  routing, and operator documentation.
- Missing reusable single-workspace observation: record the gap in `tool_gaps/`
  and implement the reusable capability in yadof rather than adding private-state
  scraping here.
