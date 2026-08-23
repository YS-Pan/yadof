# yadof benchmark automation

This directory owns a reproducible, resumable comparison of the frozen SAW,
PyChrono trebuchet, and synthetic `test_com` tasks. It has two deliberately
separate purposes:

- **Structural suites** verify task wiring, real-only search, GPSAF,
  conditional-INR training/use, checkpoint publication, and public inspection.
- **Performance suites** publish raw per-seed values and paired descriptive
  differences. They do not rank arms, apply significance tests, or decide which
  algorithm is better.

The runner never reads the mutable original task directories. Every cell starts
with `yadof init`, receives only declared inputs from one frozen baseline, and has
its own workspace, history, optimizer state, checkpoint namespace, logs, and lock.

## Current execution status

The frozen baselines and the runner were created on 2026-08-23 with installed
`yadof 0.4.0`.

| Evidence | Result |
|---|---|
| Phase-0 smoke for all three baselines | Passed; costs and rawData shapes match the frozen contracts |
| `adapter-smoke` run `20260823T052657Z-adapters-1b7c0d27af47` | Structural contract satisfied |
| yadof-tools repair `0665541155009787c938cbf15df177e8c9488fb8` | Built, force-reinstalled, 274 tests passed, and pushed to `origin/main` |
| post-fix `structural-canary` run `20260823T060003Z-post-viewer-fix-9e43d5c3327b` | Structural contract satisfied, including finite public summary and both audits |
| post-fix `structural-full` run `20260823T060119Z-post-viewer-fix-ba5ad9cc3103` | All three cases and both arms satisfied every structural check |
| `performance-pilot` run `20260823T060351Z-post-viewer-fix-5a583e492089` | 192/192 evaluations completed; three paired rows included and none excluded |
| final `performance` run `pfull-0823` | 18/18 cells completed; 1080 attempted, 1062 publicly recorded completions, 18 recorder-budget losses, zero timeouts/all-infinite generations, and 9/9 paired rows included |

The resolved viewer gap and its historical failure evidence are documented in
[`tool_gaps/20260823-surrogate-viewer-raw-variables.md`](tool_gaps/20260823-surrogate-viewer-raw-variables.md).
No benchmark-only checkpoint scraping or monkey patch was used. The final raw and
descriptive reports are
[`runs/pfull-0823/reports/report-0001/report.json`](runs/pfull-0823/reports/report-0001/report.json)
and
[`runs/pfull-0823/reports/report-0001/report.md`](runs/pfull-0823/reports/report-0001/report.md).

An earlier authorized full run,
`20260823T062344Z-approved-full-campaign-55651e90c9ef`, is retained as incomplete
evidence. Its three Chrono GPSAF cells reached a roughly 272-character PyChrono
child working directory and failed at Windows process launch with `WinError 267`.
The final run used the same frozen scientific inputs with the explicit short run
ID `pfull-0823`; all Chrono GPSAF cells then completed. Prefer short explicit run
IDs for Windows cases whose task adapters create nested subprocess scratch paths.

## Prerequisites

Run commands from the outer workspace directory with its fixed interpreter:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" --help
```

The runner preflights all selected resources without starting a simulator:

- SAW requires `YADOF_NGSPICE_EXE` to name a readable ngspice console executable.
- Chrono requires `YADOF_PYCHRONO_PYTHON` to name the external PyChrono Python.
- `test_com` requires Torch CUDA availability for the declared conditional-INR
  profile.
- At least the configured free-space floor (currently 2048 MiB) must remain.

The selected Python executable, Python version, installed yadof origin/version,
module hash, distribution `RECORD` hash, Torch/CUDA/device facts, baseline hashes,
history identity, strategy hashes, and fully expanded commands are frozen in each
`run_spec.json`.

## Commands

`plan` is the only no-write planning interface. It resolves the selected matrix,
explicit commands, real-evaluation counts, prerequisites, and rough lower-bound
evaluation/storage estimates:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" plan `
  --suite structural-canary
```

Preflight performs static validation and `yadof check`, but never launches the
task workflow:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" preflight `
  --suite structural-canary
```

Create and execute a new run:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" run `
  --suite structural-canary `
  --label local-check
```

Select a precise subset without editing TOML. Repeat a selector to include more
than one value:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" run `
  --suite performance `
  --case saw `
  --arm real-search `
  --arm gpsaf-conditional-inr `
  --seed 104729
```

Collection is intentionally separate because surrogate audit performs model
inference. Reporting is a pure transformation of the latest collected snapshot:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" collect `
  --run-id <existing-id>

& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" report `
  --run-id <existing-id>
```

Resume the exact immutable spec after a completed-boundary interruption:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" run `
  --resume <existing-id>
```

The equivalent `resume --run-id <existing-id>` command is also available. Resume
refuses config, installed-package, baseline, history, strategy, or execution-runner
fingerprint drift. Completed cells are skipped. A workspace that stopped inside a
generation is sealed and retained; retry creates a new attempt workspace with an
explicit `replacement_for` link. It never reruns that generation in the failed
workspace.

## Suites and cost/risk

Suite order is deterministic and execution is sequential to avoid shared-resource
contention.

| Suite | Scope | Default behavior |
|---|---|---|
| `structural-canary` | `test_com` smoke, real generation 0, GPSAF generations 0–1, and declared generation 2 when no surrogate use has occurred | Fail fast; full declared training profile |
| `adapter-smoke` | one disposable SAW smoke and one disposable Chrono smoke | Fail fast; no measured arm |
| `structural-full` | full structural path for all three cases | Fail fast; manual/release tier |
| `performance-pilot` | one paired seed, three generations per arm and case | Continue independent cells; bounded cost discovery |
| `performance` | three paired seeds, three generations per arm and case | Continue independent cells; potentially expensive |

`plan` estimates task-evaluation time from prior observations and declared worker
caps. It excludes optimizer and surrogate training overhead. The pilot must be run
and reviewed before the full matrix. If the resulting full real-evaluation or
training cost is material, obtain explicit user approval before starting it.

The current performance matrix uses cold starts, equal planned attempted
real-evaluation budgets across arms for each case, and the seeds `104729`, `130363`,
and `155921`. Failed candidates consume attempted budget but do not contribute a
Pareto or hypervolume point.

## Output and immutability

Each run is identity-stable:

```text
runs/<run-id>/
  run_spec.json              immutable resolved inputs and runner identity
  matrix.json                immutable selected cell/command expansion
  run_state.json             atomically advanced execution state
  metrics.json               latest derived public-API collection
  report.json                latest derived report
  report.md                  latest concise report
  cells/<cell-id>/attempts/<NNNN>/
    input_manifest.json
    workspace/
    commands/<NNNN-label>/
      command.started.json
      command.finished.json
      stdout.log
      stderr.log
  evidence/collect-<NNNN>/   append-only collection and public tool outputs
  reports/report-<NNNN>/     append-only report snapshots
```

`run_spec.json`, `matrix.json`, command attempts, logs, and prior evidence/report
snapshots are never overwritten. `run_state.json` and the root-level latest
`metrics.json`/reports are written atomically. Collection and reporting do not
modify measured workspaces, histories, or checkpoints.

Smoke workspaces are separate disposable cells. Their records never enter a
measured real-search or GPSAF arm.

## Measurements and interpretation

Collection uses these public surfaces:

- `yadof.recorded_data` for records, generation metadata, normalized variables,
  rawData samples, and surrogate training metadata;
- `yadof.tools.cost_viewer` for recalculated cost rows, Pareto summary, and
  cumulative/current-generation hypervolume;
- `yadof view surrogate summary/audit --format json` for supported surrogate
  observations.

Generation-0 normalized populations are reconstructed in the public
`created_job_names` order and content-fingerprinted. A paired performance row is
excluded from primary descriptive aggregates if either cell is incomplete, its
observed attempted budget differs, or its generation-0 fingerprint differs. The
raw evidence remains listed.

Hypervolume is aligned at cumulative attempted real-evaluation generation ends.
Evaluation-normalized HV-AUC is `null` because yadof 0.4.0 exposes no public metric
contract for it. Checkpoint training-cutoff provenance is also unavailable, so
surrogate audit matrices are never relabeled or summarized as out-of-sample.

Command failures, timeouts, missing generations, all-infinite generations, and
warnings live in the validity section. They are not algorithm-performance metrics.
Optimizer wall time, peak resource use, and checkpoint size are not comparison
metrics. Command durations remain in command metadata only for operational
diagnosis.

## Worked examples

A no-write canary plan resolves to three isolated cells:

```text
smoke__test-com__seed-20260816
  smoke: 1 disposable midpoint evaluation
test-com__real-search__seed-20260816
  population 12 × 1 generation = 12 planned attempted evaluations
test-com__gpsaf-conditional-inr__seed-20260816
  population 12 × 2 base generations = 24 planned attempted evaluations
  one declared generation-2 extension when the base run has not used the surrogate
```

The executed adapter example produced this root-level report result:

```json
{
  "run_id": "20260823T052657Z-adapters-1b7c0d27af47",
  "suite": "adapter-smoke",
  "purpose": "structural",
  "structural": {
    "contract_satisfied": true
  }
}
```

The original corrected canary report had `contract_satisfied=false` for exactly
one public viewer error. After the reusable yadof-tools repair, the post-fix canary
and `structural-full` reports both have `contract_satisfied=true`. The final
performance report contains all nine predeclared case/seed pairs and zero excluded
pairs. It remains descriptive only: raw hypervolume values and paired differences
are not an algorithm ranking or acceptance verdict.

The three final `test-com` real-search cells each emitted six best-effort recorder
budget losses. Optimization still completed all planned attempted evaluations, but
the public evidence contains 66 rather than 72 completed rows in each affected
cell. The stable JSON report exposes the resulting totals (1080 attempted, 1062
completed, 18 failed/missing); consumers must retain that validity context when
interpreting the nine descriptive rows.

## Failure diagnosis

1. Read `run_state.json` and find cells not marked `completed`.
2. Open the latest attempt's `command.finished.json`, then its separate stdout and
   stderr logs. A `command.started.json` without a finished companion indicates an
   interrupted command.
3. Run `collect --run-id ...` even for an incomplete performance matrix; partial
   evidence is retained and incomplete pairs are excluded rather than hidden.
4. Fix only the external prerequisite or reusable yadof issue. Do not edit a
   measured workspace.
5. Use `run --resume ...`; the old attempt stays sealed and a replacement is linked.

Structural suites stop after the first failed cell by default. Performance suites
continue independent cells and exit nonzero when any cell is incomplete.
`--fail-fast` overrides the performance default for that invocation.

## Extending the benchmark without editing yadof

To add a case:

1. Create a new immutable `baselines/<case>/<date>-<fingerprint>/workspace` with
   current `yadof init`, deliberate task-input transfer, zero runtime evidence,
   `yadof check`, and one disposable smoke.
2. Add `baseline.json` provenance and explicit `include_paths`, objective count,
   rawData shapes, resource prerequisite, history policy, and budgets to
   `benchmark.toml`.
3. Run `plan`, `preflight`, and the smallest structural tier before performance.

To add an arm, add a complete strategy module under `strategy_templates/` with a
callable `build_optimization()`, declare its exact overrides in TOML, and give it
equal performance budgets. To add seeds, edit the suite's predeclared list before
creating a run. To add a cross-arm descriptive metric, consume a public
single-workspace yadof API/tool result and version the emitted schema. If the
single-workspace observation does not exist publicly, document a yadof-tools gap;
do not scrape `.yadof` internals in the benchmark.

Reusable single-workspace analyzers belong in yadof. This directory owns only
frozen experiment assembly, cross-case/arm/seed alignment, validity handling, and
descriptive aggregation.

## Development

Maintainers should start with [`dev_doc/README.md`](dev_doc/README.md). The
developer guide defines the repository boundary, fixed environment, verification
workflow, and links to the current architecture and invariants.
