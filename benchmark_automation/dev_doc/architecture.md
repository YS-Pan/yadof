# Architecture landing page

The detailed current-view architecture now lives under
[`architecture/`](architecture/00_architecture_index.md). Read every view there for
a benchmark-development context pass. This page remains a legacy orientation for
older links; when wording differs, the split architecture views are authoritative.

This page is the current maintainer view of `benchmark_automation`. It describes
the runner as implemented; planned work belongs in an issue or an explicitly
named planning document rather than here.

## Purpose and boundary

The project compares snapshotted yadof tasks and optimization strategies through
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
benchmark.toml + editable baselines + strategy templates
                         |
                         v
                  plan / preflight
                         |
                         v
       run-local baseline snapshots + immutable run_spec.json and matrix.json
                         |
                         v
       isolated cell attempt workspaces and logs
                         |
                         +--> baseline postprocess.py
                         |    then yadof view cost
                         |      -> per-baseline result directory
                         |         + shared viewcost directory
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
| `benchmark.toml` | Declared cases, arms, suites, seeds, budgets, paths, measured-cell core-config overrides, per-case strategy-template selection, and resource requirements. |
| `strategy_templates/` | Complete arm/case-specific `submit/optimization.py` replacements carrying explicit component factory kwargs; the non-surrogate arm is explicitly identified as NSGA-III. |
| `baselines/` | Editable task templates plus provenance selected as `<provider>/<baseline-id>`; names are semantic rather than fingerprint-derived, and every selected workspace exposes root `postprocess.py`. |
| `history_snapshots/` | Optional immutable warm-start inputs; currently no snapshot is selected. |
| `tests/` | Unit coverage for validation, identity, state, I/O, and materialization contracts. |
| configured runs directory | Generated immutable specs/attempts/evidence plus atomically updated latest state; default checkout `temp/<run-id>/`, Git-ignored, with each run ID directly below the root. |
| `.staging/`, `.assembled/` | Local baseline construction evidence; Git-ignored and never runner inputs. |
| `verification/`, `tool_gaps/` | Human-readable historical verification and reusable-yadof issue records. |

## Core invariants

### Inputs and identity

- Every selected baseline, strategy, configuration, package installation, and
  runner module is fingerprinted before execution.
- Baseline directories and contents are mutable templates. Their IDs are semantic
  names without fingerprint suffixes. Preflight checks the current content and a
  new run copies every declared input to `inputs/baselines/<case>/workspace`, records
  that snapshot's fingerprint, and uses it for all cells and resume. Later source
  baseline edits therefore affect only later runs.
- A baseline manifest's yadof version and task fingerprint are creation provenance,
  not locks on current content or the exact execution patch. Preflight requires the
  version provenance, checks runtime cleanliness, runs current installed
  `yadof check`, and freezes the actual execution package and task identities.
- An automatically chosen run/output-directory name begins with a UTC
  `YYYYMMDD_HHMMSS` timestamp whose date and time components are digits only;
  optional sanitized label and run-spec fingerprint fields follow the prefix.
- Configured template/input paths remain contained below the benchmark root. Mutable run
  output may use an explicit external root; relative CLI overrides resolve from the
  invocation directory, and suggested follow-up commands preserve the resolved
  root.
- Baseline provider directories identify the simulator or adapter. Their child
  directory is a stable semantic baseline ID; manifest `provider_id`, `case_id`,
  and `baseline_id` agree with the path, while `task_id` names the optimization
  problem independently.
- Each case/arm/seed cell receives its own initialized workspace, state, logs, and
  checkpoint namespace; measured cells never share a smoke workspace.
- Performance arms for a paired case use equal planned attempted-real-evaluation
  budgets.
- The formal performance tier uses one paired seed and 100 individuals for 20
  generations in every measured cell. Its runner-owned measured-cell overrides
  provide recorder candidate headroom for at least one complete generation without
  editing baselines; the pilot remains a separate small cost-discovery tier.
- Surrogate/optimizer performance evaluation and result-driven algorithm tuning use
  the complete unfiltered performance matrix. Few-generation or dozens-of-individual
  structural/pilot runs are prohibited for that purpose and remain limited to
  wiring, prerequisite, failure-path, and runtime-cost evidence. The one-seed
  matrix is descriptive tuning evidence, not a statistical robustness claim.
- Measured cells deliberately use a 32-worker fast cap with fast resource
  autodetection disabled, allowing CPU oversubscription beyond the physical-core
  count. This is a benchmark experiment setting; preflight/pilot review still owns
  host memory, simulator, license, and external-runtime suitability.

### Execution and recovery

- `plan` writes nothing. `preflight` may validate materialized inputs but never
  launches a simulator workflow.
- A run specification and expanded matrix are immutable after creation.
- Resume skips completed cells and refuses input drift. An interrupted in-generation
  workspace is sealed; retry uses a linked replacement attempt rather than
  mutating the failed attempt.
- Cells execute sequentially by default to isolate comparison state and external
  resource ownership. Candidate simulation within a measured cell uses the declared
  32-way fast concurrency.
- Child stdout/stderr is always preserved in command logs. It is not forwarded to
  the terminal unless `--stream-output` is explicitly selected.
- The run/resume CLI owns one Rich live-progress region on stderr. Its active-cell
  individual-evaluation task is always above its global cell task; Rich clears and
  redraws the region below every unchanged lifecycle or streamed child line and
  removes it on exit. Automatic timer refresh is disabled: the runner updates both
  Rich tasks and performs one atomic event-driven refresh, preventing a stale cell
  frame from winning an adjacent global refresh. It converts yadof's piped
  per-generation snapshots into cumulative whole-cell evaluation progress and
  leads the compact detail with count, percentage, and current/total generation.
  Positive progress uses ceiling bar fill and sub-10% percentages retain one
  decimal. Count/unit text is compacted so normal terminal widths retain complete
  cell and global status without the former fixed detail cap. Original snapshots
  remain in command logs. Redirected streams receive
  complete snapshots throttled to bounded percentage advances. Interactive
  `--stream-output` routes both displayed child channels through the Rich stderr
  console while their append-only log files keep the original channel separation.
  A stream that proves interactive with `isatty()` ignores inherited
  `TERM=dumb`/`unknown` only inside its Rich console, preserving the process-wide
  and child-command environments while allowing explicit live refreshes.
- After every measured optimization and any declared extension, the runner invokes
  the baseline workspace's common `postprocess.py` interface exactly once with
  `--workspace`, `--output-dir`, and `--output-prefix`. Task-specific visualization
  logic remains baseline-owned.
- Every measured attempt writes postprocessor artifacts to its baseline workspace's
  shared `<run-root>/visualizations/<baseline-id>/` directory with the
  collision-safe `<cell-id>__attempt-####__` filename prefix. The current matrix
  therefore produces three task-result directories instead of eighteen. All cost
  views share
  `<run-root>/visualizations/viewcost/` and retain the collision-safe
  `<cell-id>__attempt-####__benchmark-cost.png` name. Either command failing fails
  the immutable attempt instead of silently omitting required human-review
  artifacts.
- Runner child processes set `PYTHONDONTWRITEBYTECODE=1`, so importing task or
  postprocessor modules cannot add `__pycache__` files to sealed declared inputs.
- Once run/resume reaches its final state, an interactive stdin waits for Enter so
  a separately launched console remains visible; non-interactive callers return
  immediately with the normal exit code.
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
- A running `inspect` adds read-only timing: active progress/inactivity, remaining
  seconds, completion UTC, confidence, basis, and sample/dispersion support. New
  runs freeze a bounded shallow snapshot of prior completed-cell wall times.
  Estimation prefers exact or compatible matched-cell history and current-run
  same-case/arm evidence, never a same-case duration from another arm. Timestamped
  command progress events permit a non-decreasing generation-duration trend to
  raise the active estimate; a bounded stderr tail remains an old-run fallback.
  Lower-bound fallbacks explicitly exclude optimizer/surrogate overhead. ETA never
  writes state or becomes benchmark evidence.
- Default report and completed inspect keep the bounded JSON surface on stdout and
  render a compact final cumulative-hypervolume Markdown table on stderr. Table
  columns use the configured concrete arm display names rather than generic
  experimental roles.

## Change map

- CLI changes: update `benchmark.py`, CLI-focused tests, and command examples in
  the root README.
- Schema, validation, planning, execution, or reporting changes: update
  `benchmark_core.py`, `benchmark.toml` when applicable, focused tests, and the
  affected invariant above.
- New case: add an editable semantic baseline directory, provenance, TOML
  declaration, expected objective/rawData contracts, and the smallest structural
  validation evidence.
- New arm: add a complete strategy template, TOML declaration, equal-budget
  coverage, and structural validation.
- New public output field: define its stable JSON meaning, validity behavior, and
  derivation; decide which disclosure layer owns it, then update tests, agent
  routing, and operator documentation.
- Missing reusable single-workspace observation: record the gap in `tool_gaps/`
  and implement the reusable capability in yadof rather than adding private-state
  scraping here.
